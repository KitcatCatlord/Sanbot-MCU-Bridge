#!/usr/bin/env python3
"""Interactive USB bridge tester with GUI, media capture, and logging."""

from __future__ import annotations

import json
import logging
import queue
import struct
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import click
import numpy as np
import usb.core
import usb.util

try:
    import cv2
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit("opencv-python is required: pip install opencv-python") from exc

try:
    import sounddevice as sd
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit("sounddevice is required: pip install sounddevice") from exc

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit("PySide6 is required: pip install PySide6") from exc

try:
    import pyqtgraph as pg
except ImportError as exc:  # pragma: no cover - handled at runtime
    raise SystemExit("pyqtgraph is required: pip install pyqtgraph") from exc

from sanbot.mcu_bridge import usb_bridge
from sanbot.mcu_bridge.lib.safety import SafetyError

LOG = logging.getLogger("usb_bridge_tester")

VID = usb_bridge.VID
PID_BOTTOM = usb_bridge.PID_BOTTOM
PID_HEAD = usb_bridge.PID_HEAD


@dataclass
class ClickCommandNode:
    name: str
    command: click.Command
    parent: Optional["ClickCommandNode"]
    children: List["ClickCommandNode"]

    def full_path(self) -> Tuple[str, ...]:
        parts: List[str] = []
        node: Optional[ClickCommandNode] = self
        while node is not None and node.name:
            parts.append(node.name)
            node = node.parent
        return tuple(reversed(parts))

    @property
    def is_group(self) -> bool:
        return isinstance(self.command, click.Group)

    def help_text(self) -> str:
        if self.command.help:
            return self.command.help
        doc = (self.command.callback.__doc__ or "") if self.command.callback else ""
        return doc.strip()


def build_command_tree(root: click.Group) -> ClickCommandNode:
    def _build(cmd: click.Command, name: str, parent: Optional[ClickCommandNode]) -> ClickCommandNode:
        node = ClickCommandNode(name=name, command=cmd, parent=parent, children=[])
        if isinstance(cmd, click.Group):
            for child_name, child_cmd in sorted(cmd.commands.items()):
                node.children.append(_build(child_cmd, child_name, node))
        return node

    return _build(root, name="", parent=None)


class RecordingManager:
    def __init__(self, base_dir: Path | str = Path("recordings")):
        self.base_dir = Path(base_dir)
        self.session_dir: Optional[Path] = None
        self.command_log_file: Optional[Path] = None
        self._command_fp: Optional[open] = None

    def start_session(self) -> None:
        if self.session_dir is not None:
            return
        self.base_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = self.base_dir / f"session_{ts}"
        for sub in ("camera", "audio", "usb", "commands"):
            (self.session_dir / sub).mkdir(parents=True, exist_ok=True)
        self.command_log_file = self.session_dir / "commands" / "commands.jsonl"
        self._command_fp = open(self.command_log_file, "a", encoding="utf-8")
        LOG.info("Recording session started at %s", self.session_dir)

    def stop_session(self) -> None:
        if self._command_fp is not None:
            self._command_fp.close()
        self._command_fp = None
        self.command_log_file = None
        self.session_dir = None
        LOG.info("Recording session stopped")

    def ensure_session(self) -> None:
        if self.session_dir is None:
            self.start_session()

    def path_for(self, category: str, suffix: str, tag: Optional[str] = None) -> Path:
        self.ensure_session()
        assert self.session_dir is not None
        dir_path = self.session_dir / category
        dir_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%H%M%S")
        parts = [category]
        if tag:
            parts.append(tag)
        parts.append(ts)
        filename = "_".join(parts) + suffix
        return dir_path / filename

    def log_command(self, entry: Dict[str, object]) -> None:
        if self._command_fp is None:
            return
        json.dump(entry, self._command_fp)
        self._command_fp.write("\n")
        self._command_fp.flush()


class CameraController(QtCore.QObject):
    frame_ready = QtCore.Signal(QtGui.QImage)
    status = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.device_index = 0
        self.capture: Optional[cv2.VideoCapture] = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._grab_frame)
        self.record_writer: Optional[cv2.VideoWriter] = None
        self.recording_active = False
        self.frame_size: Optional[Tuple[int, int]] = None

    def start(self, device_index: int) -> None:
        if self.capture is not None:
            self.status.emit("Camera already running")
            return
        self.device_index = device_index
        cap = cv2.VideoCapture(device_index)
        if not cap.isOpened():
            self.status.emit(f"Failed to open camera index {device_index}")
            return
        self.capture = cap
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        self.frame_size = (w, h)
        self.timer.start(33)
        self.status.emit(f"Camera started (index {device_index})")

    def stop(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if self.record_writer is not None:
            self.record_writer.release()
            self.record_writer = None
        self.status.emit("Camera stopped")

    def set_recording(self, active: bool, output_path: Optional[Path] = None) -> None:
        if active:
            if self.capture is None or self.frame_size is None or output_path is None:
                self.status.emit("Camera must be running before recording")
                self.recording_active = False
                return
            if self.record_writer is None:
                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                self.record_writer = cv2.VideoWriter(str(output_path), fourcc, 30.0, self.frame_size)
                if not self.record_writer.isOpened():
                    self.status.emit("Failed to open camera recorder")
                    self.record_writer = None
                    self.recording_active = False
                    return
                self.status.emit(f"Recording camera to {output_path}")
            self.recording_active = True
        elif not active and self.record_writer is not None:
            self.record_writer.release()
            self.record_writer = None
            self.recording_active = False
            self.status.emit("Camera recording stopped")
        else:
            self.recording_active = active

    def _grab_frame(self) -> None:
        if self.capture is None:
            return
        ret, frame = self.capture.read()
        if not ret:
            self.status.emit("Camera frame read failed")
            return
        if self.record_writer is not None and self.recording_active:
            self.record_writer.write(frame)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        bytes_per_line = ch * w
        image = QtGui.QImage(rgb.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        self.frame_ready.emit(image.copy())


class AudioController(QtCore.QObject):
    waveform = QtCore.Signal(np.ndarray)
    status = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.stream: Optional[sd.InputStream] = None
        self.device_index: Optional[int] = None
        self.sample_rate = 16000
        self.channels = 1
        self.audio_queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self.writer = None
        self.recording_active = False
        self.record_path: Optional[Path] = None
        self._file_lock = threading.Lock()
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._flush_queue)

    def list_input_devices(self) -> List[Tuple[int, str]]:
        result: List[Tuple[int, str]] = []
        try:
            devices = sd.query_devices()
        except Exception:  # pragma: no cover - environment dependent
            return result
        for idx, info in enumerate(devices):
            if info.get("max_input_channels", 0) > 0:
                name = info.get("name", f"Device {idx}")
                result.append((idx, name))
        return result

    def start(self, device_index: int, sample_rate: int) -> None:
        if self.stream is not None:
            self.status.emit("Microphone already running")
            return
        self.device_index = device_index
        self.sample_rate = sample_rate
        try:
            self.stream = sd.InputStream(device=device_index, channels=self.channels, samplerate=self.sample_rate, callback=self._audio_callback)
            self.stream.start()
        except Exception as exc:  # pragma: no cover - hardware dependent
            self.status.emit(f"Failed to start microphone: {exc}")
            self.stream = None
            return
        self._timer.start(100)
        self.status.emit(f"Microphone started (device {device_index})")

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        if self.writer is not None:
            with self._file_lock:
                self.writer.close()
            self.writer = None
        self.recording_active = False
        self._timer.stop()
        self.status.emit("Microphone stopped")

    def set_recording(self, active: bool, output_path: Optional[Path] = None) -> None:
        if active and self.writer is None and output_path is not None:
            if self.stream is None:
                self.status.emit("Microphone must be running before recording")
                self.recording_active = False
                return
            import wave

            self.record_path = output_path
            with self._file_lock:
                self.writer = wave.open(str(output_path), "wb")
                self.writer.setnchannels(self.channels)
                self.writer.setsampwidth(2)
                self.writer.setframerate(self.sample_rate)
            self.recording_active = True
            self.status.emit(f"Recording audio to {output_path}")
        elif not active and self.writer is not None:
            with self._file_lock:
                self.writer.close()
            self.writer = None
            self.record_path = None
            self.recording_active = False
            self.status.emit("Audio recording stopped")
        else:
            self.recording_active = active

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # pragma: no cover - realtime callback
        data = indata.copy()
        self.audio_queue.put(data)
        if self.writer is not None and self.recording_active:
            with self._file_lock:
                try:
                    self.writer.writeframes(data.tobytes())
                except Exception:
                    pass

    def _flush_queue(self) -> None:
        collected: List[np.ndarray] = []
        while True:
            try:
                collected.append(self.audio_queue.get_nowait())
            except queue.Empty:
                break
        if not collected:
            return
        merged = np.concatenate(collected, axis=0)
        mono = merged.reshape(-1)
        self.waveform.emit(mono)


class USBMonitor(QtCore.QObject):
    data_ready = QtCore.Signal(bytes)
    status = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.target = "bottom"
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.chunk_size = 64
        self.timeout_ms = 200
        self.record_path: Optional[Path] = None
        self._file_lock = threading.Lock()
        self._fp: Optional[open] = None

    def configure(self, target: str, chunk_size: int, timeout_ms: int) -> None:
        self.target = target
        self.chunk_size = max(1, chunk_size)
        self.timeout_ms = max(1, timeout_ms)

    def set_recording(self, active: bool, output_path: Optional[Path] = None) -> None:
        if active and self._fp is None and output_path is not None:
            self._fp = open(output_path, "ab")
            self.record_path = output_path
            self.status.emit(f"Recording USB data to {output_path}")
        elif not active and self._fp is not None:
            with self._file_lock:
                self._fp.close()
            self._fp = None
            self.record_path = None
            self.status.emit("USB recording stopped")

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.status.emit("USB monitor already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self.status.emit(f"USB monitor running ({self.target})")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        if self._fp is not None:
            with self._file_lock:
                self._fp.close()
            self._fp = None
        self.status.emit("USB monitor stopped")

    def _resolve_device(self) -> Tuple[usb.core.Device, usb.util.Endpoint]:
        pid = PID_BOTTOM if self.target == "bottom" else PID_HEAD
        dev = usb_bridge.find_device(VID, pid)
        if dev is None:
            raise RuntimeError(f"Device not found for {self.target} (VID=0x{VID:04X} PID=0x{pid:04X})")
        eps = usb_bridge.claim_bulk_endpoints(dev)
        return dev, eps.ep_in

    def _run(self) -> None:  # pragma: no cover - hardware dependent
        try:
            dev, ep_in = self._resolve_device()
        except Exception as exc:
            self.status.emit(str(exc))
            return
        while not self._stop_event.is_set():
            try:
                data = ep_in.read(self.chunk_size, timeout=self.timeout_ms)
                payload = bytes(data)
                if payload:
                    self.data_ready.emit(payload)
                    if self._fp is not None:
                        with self._file_lock:
                            self._fp.write(payload)
                            self._fp.flush()
            except usb.core.USBError as exc:
                if exc.errno == 110:  # timeout
                    continue
                self.status.emit(f"USB read error: {exc}")
                time.sleep(0.2)
            except Exception as exc:
                self.status.emit(f"USB monitor error: {exc}")
                time.sleep(0.5)
        try:
            usb.util.dispose_resources(dev)
        except Exception:
            pass


class CommandExecutor(QtCore.QObject):
    started = QtCore.Signal(str)
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, recorder: RecordingManager, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.recorder = recorder
        self._active_threads: List[threading.Thread] = []
        self._lock = threading.Lock()

    def execute(self, node: ClickCommandNode, values: Dict[str, object]) -> None:
        if node.is_group or node.command.callback is None:
            self.failed.emit("Selected item is a group")
            return
        path = " ".join(node.full_path())
        self.started.emit(path)

        def _runner() -> None:
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "command": path,
                "params": values,
            }
            try:
                node.command.callback(**values)
                entry["status"] = "ok"
                self.recorder.log_command(entry)
                self.finished.emit(path)
            except SafetyError as exc:
                entry["status"] = "safety_error"
                entry["error"] = str(exc)
                self.recorder.log_command(entry)
                self.failed.emit(f"SafetyError: {exc}")
            except click.ClickException as exc:
                entry["status"] = "click_error"
                entry["error"] = str(exc)
                self.recorder.log_command(entry)
                self.failed.emit(f"ClickError: {exc}")
            except Exception as exc:
                entry["status"] = "error"
                entry["error"] = str(exc)
                self.recorder.log_command(entry)
                self.failed.emit(f"Error: {exc}")
            finally:
                with self._lock:
                    try:
                        self._active_threads.remove(threading.current_thread())
                    except ValueError:
                        pass

        thread = threading.Thread(target=_runner, daemon=True)
        with self._lock:
            self._active_threads.append(thread)
        thread.start()

    def stop_all(self) -> None:
        with self._lock:
            threads = list(self._active_threads)
        for t in threads:
            if t.is_alive():
                t.join(timeout=0.1)
        with self._lock:
            self._active_threads = []


class ParameterWidget(QtWidgets.QWidget):
    def __init__(self, param: click.Parameter, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.param = param
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QtWidgets.QLabel(self._label_text())
        layout.addWidget(self.label)
        self.widget = self._create_widget()
        layout.addWidget(self.widget, stretch=1)

    def _label_text(self) -> str:
        required = "*" if self.param.required else ""
        return f"{self.param.name}{required}"

    def _create_widget(self) -> QtWidgets.QWidget:
        opt = self.param
        if isinstance(opt, click.Option):
            if opt.is_flag:
                chk = QtWidgets.QCheckBox()
                chk.setChecked(bool(opt.default))
                return chk
            if isinstance(opt.type, click.Choice):
                box = QtWidgets.QComboBox()
                for choice in opt.type.choices:
                    box.addItem(choice)
                if opt.default is not None and opt.default in opt.type.choices:
                    box.setCurrentText(opt.default)
                return box
            if isinstance(opt.type, click.types.IntParamType):
                spin = QtWidgets.QSpinBox()
                spin.setRange(-1_000_000, 1_000_000)
                if opt.default is not None:
                    spin.setValue(int(opt.default))
                return spin
            if isinstance(opt.type, click.types.FloatParamType):
                spin = QtWidgets.QDoubleSpinBox()
                spin.setRange(-1_000_000.0, 1_000_000.0)
                spin.setDecimals(3)
                if opt.default is not None:
                    spin.setValue(float(opt.default))
                return spin
        edit = QtWidgets.QLineEdit()
        if self.param.default is not None:
            edit.setText(str(self.param.default))
        if self.param.help:
            edit.setPlaceholderText(self.param.help)
        return edit

    def value(self, ctx: click.Context) -> Tuple[str, object]:
        param = self.param
        raw: object
        if isinstance(param, click.Option) and param.is_flag:
            raw = bool(self.widget.isChecked())  # type: ignore[attr-defined]
        elif isinstance(param, click.Option) and isinstance(self.widget, QtWidgets.QComboBox):
            raw = self.widget.currentText()
        elif isinstance(param, click.Option) and isinstance(self.widget, QtWidgets.QSpinBox):
            raw = int(self.widget.value())
        elif isinstance(param, click.Option) and isinstance(self.widget, QtWidgets.QDoubleSpinBox):
            raw = float(self.widget.value())
        else:
            text = self.widget.text().strip() if hasattr(self.widget, "text") else ""
            if text == "" and not param.required:
                return param.name, param.default
            raw = text
        if isinstance(param, click.Option) and not param.is_flag:
            try:
                converted = param.type.convert(raw, param, ctx)
            except click.ClickException:
                raise
            return param.name, converted
        if isinstance(param, click.Argument):
            converted = param.type.convert(raw, param, ctx)
            return param.name, converted
        return param.name, raw

    def reset(self) -> None:
        if isinstance(self.widget, QtWidgets.QLineEdit):
            if self.param.default is not None:
                self.widget.setText(str(self.param.default))
            else:
                self.widget.clear()
        elif isinstance(self.widget, QtWidgets.QSpinBox):
            if self.param.default is not None:
                self.widget.setValue(int(self.param.default))
            else:
                self.widget.setValue(self.widget.minimum())
        elif isinstance(self.widget, QtWidgets.QDoubleSpinBox):
            if self.param.default is not None:
                self.widget.setValue(float(self.param.default))
            else:
                self.widget.setValue(self.widget.minimum())
        elif isinstance(self.widget, QtWidgets.QCheckBox):
            self.widget.setChecked(bool(self.param.default))
        elif isinstance(self.widget, QtWidgets.QComboBox):
            if self.param.default is not None:
                idx = self.widget.findText(str(self.param.default))
                if idx >= 0:
                    self.widget.setCurrentIndex(idx)


class CommandPanel(QtWidgets.QWidget):
    execute_requested = QtCore.Signal(ClickCommandNode, dict)

    def __init__(self, root_node: ClickCommandNode, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.root_node = root_node
        self.selected_node: Optional[ClickCommandNode] = None
        self.param_widgets: List[ParameterWidget] = []

        layout = QtWidgets.QVBoxLayout(self)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["Command", "Help"])
        self.tree.itemSelectionChanged.connect(self._refresh_form)
        layout.addWidget(self.tree)

        self.form_container = QtWidgets.QWidget()
        self.form_layout = QtWidgets.QFormLayout(self.form_container)
        layout.addWidget(self.form_container)

        btn_row = QtWidgets.QHBoxLayout()
        self.execute_button = QtWidgets.QPushButton("Execute (Ctrl+Enter)")
        self.execute_button.clicked.connect(self._execute)
        btn_row.addWidget(self.execute_button)
        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_inputs)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self._populate_tree()

    def _populate_tree(self) -> None:
        def _add_items(node: ClickCommandNode, parent_item: Optional[QtWidgets.QTreeWidgetItem]):
            for child in node.children:
                item = QtWidgets.QTreeWidgetItem([child.name, child.help_text()])
                item.setData(0, QtCore.Qt.UserRole, child)
                if parent_item is None:
                    self.tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                if child.children:
                    _add_items(child, item)

        self.tree.clear()
        _add_items(self.root_node, None)
        self.tree.expandToDepth(0)

    def _clear_inputs(self) -> None:
        for widget in self.param_widgets:
            widget.reset()

    def _refresh_form(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        node: ClickCommandNode = item.data(0, QtCore.Qt.UserRole)
        self.selected_node = node
        for i in reversed(range(self.form_layout.count())):
            item_widget = self.form_layout.itemAt(i)
            if item_widget:
                widget = item_widget.widget()
                if widget:
                    widget.deleteLater()
                self.form_layout.removeItem(item_widget)
        self.param_widgets.clear()
        if node.is_group:
            info = QtWidgets.QLabel("Select a sub-command to configure parameters.")
            info.setWordWrap(True)
            self.form_layout.addRow(info)
            return
        ctx = click.Context(node.command)
        params = node.command.params
        for param in params:
            pw = ParameterWidget(param)
            self.param_widgets.append(pw)
            self.form_layout.addRow(pw)
        if not params:
            info = QtWidgets.QLabel("This command has no parameters.")
            self.form_layout.addRow(info)

    def _execute(self) -> None:
        if self.selected_node is None:
            return
        node = self.selected_node
        ctx = click.Context(node.command)
        values: Dict[str, object] = {}
        try:
            for pw in self.param_widgets:
                key, value = pw.value(ctx)
                if value is None and not pw.param.required:
                    continue
                values[key] = value
        except click.ClickException as exc:
            QtWidgets.QMessageBox.warning(self, "Parameter error", str(exc))
            return
        self.execute_requested.emit(node, values)


def parse_usb_frame(payload: bytes) -> Optional[Dict[str, object]]:
    if len(payload) < 16:
        return None
    try:
        type_short = struct.unpack_from(">H", payload, 0)[0]
        subtype_short = struct.unpack_from(">H", payload, 2)[0]
        content_len = struct.unpack_from(">I", payload, 4)[0]
        ack_flag = payload[8]
        frame_head = struct.unpack_from(">H", payload, 15)[0]
        datas_len = max(0, content_len - 6)
        datas_start = 20
        datas_end = min(len(payload), datas_start + datas_len)
        datas = payload[datas_start:datas_end]
        checksum = payload[datas_end] if datas_end < len(payload) else None
        return {
            "type": type_short,
            "subtype": subtype_short,
            "ack": ack_flag,
            "frame_head": frame_head,
            "datas": datas,
            "checksum": checksum,
        }
    except Exception:
        return None


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sanbot USB Bridge Tester")
        self.resize(1400, 900)

        self.recorder = RecordingManager()
        self.command_executor = CommandExecutor(self.recorder)
        self.camera = CameraController()
        self.audio = AudioController()
        self.usb_monitor = USBMonitor()
        self.recording = False

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QGridLayout(central)

        self.root_node = build_command_tree(usb_bridge.cli)
        self.command_panel = CommandPanel(self.root_node)
        self.command_panel.execute_requested.connect(self._execute_command)
        layout.addWidget(self.command_panel, 0, 0, 2, 1)

        media_split = QtWidgets.QVBoxLayout()
        layout.addLayout(media_split, 0, 1)

        self._build_camera_group(media_split)
        self._build_audio_group(media_split)
        self._build_usb_group(media_split)

        self.log_widget = QtWidgets.QPlainTextEdit()
        self.log_widget.setReadOnly(True)
        layout.addWidget(self.log_widget, 1, 1)

        self._build_status_panel(layout)
        self._connect_signals()
        self._setup_hotkeys()

        self.cli_log_level = "INFO"
        self.cli_retries = 1
        self.cli_unsafe = False
        self._apply_cli_settings()

    def _build_camera_group(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Camera")
        layout = QtWidgets.QVBoxLayout(group)
        self.camera_label = QtWidgets.QLabel()
        self.camera_label.setMinimumSize(480, 270)
        self.camera_label.setAlignment(QtCore.Qt.AlignCenter)
        self.camera_label.setStyleSheet("background-color: #202020; color: #DDDDDD;")
        layout.addWidget(self.camera_label)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Device index:"))
        self.camera_device_spin = QtWidgets.QSpinBox()
        self.camera_device_spin.setRange(0, 10)
        controls.addWidget(self.camera_device_spin)
        start_btn = QtWidgets.QPushButton("Start (Ctrl+K)")
        start_btn.clicked.connect(self._start_camera)
        controls.addWidget(start_btn)
        stop_btn = QtWidgets.QPushButton("Stop")
        stop_btn.clicked.connect(self.camera.stop)
        controls.addWidget(stop_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        parent_layout.addWidget(group)

    def _build_audio_group(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("Microphone")
        layout = QtWidgets.QVBoxLayout(group)
        self.wave_plot = pg.PlotWidget()
        self.wave_plot.setYRange(-1.0, 1.0)
        self.wave_plot.showGrid(x=True, y=True)
        self.wave_curve = self.wave_plot.plot()
        layout.addWidget(self.wave_plot)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Device:"))
        self.mic_combo = QtWidgets.QComboBox()
        devices = self.audio.list_input_devices()
        if devices:
            for idx, name in devices:
                self.mic_combo.addItem(f"{idx}: {name}", userData=idx)
        else:
            self.mic_combo.addItem("No input devices detected", userData=None)
            self.mic_combo.setEnabled(False)
        controls.addWidget(self.mic_combo)
        controls.addWidget(QtWidgets.QLabel("Rate:"))
        self.mic_rate_spin = QtWidgets.QSpinBox()
        self.mic_rate_spin.setRange(8000, 48000)
        self.mic_rate_spin.setValue(16000)
        controls.addWidget(self.mic_rate_spin)
        start_btn = QtWidgets.QPushButton("Start (Ctrl+M)")
        start_btn.clicked.connect(self._start_mic)
        controls.addWidget(start_btn)
        stop_btn = QtWidgets.QPushButton("Stop")
        stop_btn.clicked.connect(self.audio.stop)
        controls.addWidget(stop_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        parent_layout.addWidget(group)

    def _build_usb_group(self, parent_layout: QtWidgets.QVBoxLayout) -> None:
        group = QtWidgets.QGroupBox("USB Monitor")
        layout = QtWidgets.QVBoxLayout(group)

        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("Target:"))
        self.usb_target_combo = QtWidgets.QComboBox()
        self.usb_target_combo.addItems(["bottom", "head"])
        controls.addWidget(self.usb_target_combo)
        controls.addWidget(QtWidgets.QLabel("Chunk:"))
        self.usb_chunk_spin = QtWidgets.QSpinBox()
        self.usb_chunk_spin.setRange(8, 512)
        self.usb_chunk_spin.setValue(64)
        controls.addWidget(self.usb_chunk_spin)
        controls.addWidget(QtWidgets.QLabel("Timeout ms:"))
        self.usb_timeout_spin = QtWidgets.QSpinBox()
        self.usb_timeout_spin.setRange(10, 5000)
        self.usb_timeout_spin.setValue(200)
        controls.addWidget(self.usb_timeout_spin)
        start_btn = QtWidgets.QPushButton("Start (Ctrl+U)")
        start_btn.clicked.connect(self._start_usb)
        controls.addWidget(start_btn)
        stop_btn = QtWidgets.QPushButton("Stop")
        stop_btn.clicked.connect(self.usb_monitor.stop)
        controls.addWidget(stop_btn)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.usb_hex_view = QtWidgets.QPlainTextEdit()
        self.usb_hex_view.setReadOnly(True)
        layout.addWidget(self.usb_hex_view)

        parent_layout.addWidget(group)

    def _build_status_panel(self, layout: QtWidgets.QGridLayout) -> None:
        panel = QtWidgets.QFrame()
        panel.setFrameShape(QtWidgets.QFrame.StyledPanel)
        h = QtWidgets.QHBoxLayout(panel)

        self.log_level_combo = QtWidgets.QComboBox()
        self.log_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.log_level_combo.setCurrentText("INFO")
        h.addWidget(QtWidgets.QLabel("Log level:"))
        h.addWidget(self.log_level_combo)

        self.retries_spin = QtWidgets.QSpinBox()
        self.retries_spin.setRange(1, 10)
        self.retries_spin.setValue(1)
        h.addWidget(QtWidgets.QLabel("Retries:"))
        h.addWidget(self.retries_spin)

        self.unsafe_checkbox = QtWidgets.QCheckBox("Unsafe overrides")
        h.addWidget(self.unsafe_checkbox)

        apply_btn = QtWidgets.QPushButton("Apply CLI Settings (Ctrl+L)")
        apply_btn.clicked.connect(self._apply_cli_settings)
        h.addWidget(apply_btn)

        self.record_button = QtWidgets.QPushButton("Start Recording (Ctrl+R)")
        self.record_button.clicked.connect(self._toggle_recording)
        h.addWidget(self.record_button)

        self.emergency_button = QtWidgets.QPushButton("EMERGENCY STOP (Ctrl+Shift+E)")
        self.emergency_button.setStyleSheet("background-color: #C62828; color: white; font-weight: bold;")
        self.emergency_button.clicked.connect(self._emergency_stop)
        h.addWidget(self.emergency_button)

        h.addStretch(1)
        layout.addWidget(panel, 2, 0, 1, 2)

    def _connect_signals(self) -> None:
        self.camera.frame_ready.connect(self._update_camera_frame)
        self.camera.status.connect(self._append_log)
        self.audio.waveform.connect(self._update_waveform)
        self.audio.status.connect(self._append_log)
        self.usb_monitor.data_ready.connect(self._handle_usb_data)
        self.usb_monitor.status.connect(self._append_log)
        self.command_executor.started.connect(lambda txt: self._append_log(f"Running: {txt}"))
        self.command_executor.finished.connect(lambda txt: self._append_log(f"Completed: {txt}"))
        self.command_executor.failed.connect(self._append_log)

    def _setup_hotkeys(self) -> None:
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self, activated=self.command_panel._execute)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Enter"), self, activated=self.command_panel._execute)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+K"), self, activated=self._start_camera)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+M"), self, activated=self._start_mic)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+U"), self, activated=self._start_usb)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+R"), self, activated=self._start_recording)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+R"), self, activated=self._stop_recording)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+L"), self, activated=self._apply_cli_settings)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Shift+E"), self, activated=self._emergency_stop)

    def _apply_cli_settings(self) -> None:
        self.cli_log_level = self.log_level_combo.currentText()
        self.cli_retries = self.retries_spin.value()
        self.cli_unsafe = self.unsafe_checkbox.isChecked()
        try:
            usb_bridge.cli.callback(log_level=self.cli_log_level, retries=self.cli_retries, unsafe=self.cli_unsafe)
        except Exception as exc:
            self._append_log(f"Failed to apply CLI settings: {exc}")
            return
        self._append_log(f"CLI settings applied (level={self.cli_log_level}, retries={self.cli_retries}, unsafe={self.cli_unsafe})")

    def _execute_command(self, node: ClickCommandNode, values: Dict[str, object]) -> None:
        self.command_executor.execute(node, values)

    def _start_camera(self) -> None:
        idx = self.camera_device_spin.value()
        self.camera.start(idx)
        if getattr(self, "recording", False):
            path = self.recorder.path_for("camera", ".avi")
            self.camera.set_recording(True, path)

    def _start_mic(self) -> None:
        idx = self.mic_combo.currentData()
        if idx is None and self.mic_combo.count() > 0:
            idx = self.mic_combo.itemData(0)
        if idx is None:
            self._append_log("No microphone devices available")
            return
        rate = self.mic_rate_spin.value()
        self.audio.start(idx, rate)
        if getattr(self, "recording", False):
            path = self.recorder.path_for("audio", ".wav")
            self.audio.set_recording(True, path)

    def _start_usb(self) -> None:
        target = self.usb_target_combo.currentText()
        chunk = self.usb_chunk_spin.value()
        timeout = self.usb_timeout_spin.value()
        self.usb_monitor.configure(target, chunk, timeout)
        if getattr(self, "recording", False):
            path = self.recorder.path_for("usb", ".bin", tag=target)
            self.usb_monitor.set_recording(True, path)
        self.usb_monitor.start()

    def _update_camera_frame(self, image: QtGui.QImage) -> None:
        pix = QtGui.QPixmap.fromImage(image)
        self.camera_label.setPixmap(pix.scaled(self.camera_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def _update_waveform(self, samples: np.ndarray) -> None:
        if len(samples) == 0:
            return
        window = samples[-4000:]
        peak = np.max(np.abs(window)) + 1e-6
        normalized = window / peak
        self.wave_curve.setData(normalized)

    def _handle_usb_data(self, payload: bytes) -> None:
        parsed = parse_usb_frame(payload)
        hex_str = payload.hex()
        if parsed and parsed.get("datas"):
            decoded = usb_bridge._decode_known_datas(parsed["datas"])
        else:
            decoded = None
        line = f"[{datetime.now().strftime('%H:%M:%S')}] len={len(payload)} hex={hex_str}"
        if decoded:
            line += f"\n  decoded={decoded}"
        self.usb_hex_view.appendPlainText(line)
        if self.usb_hex_view.blockCount() > 500:
            self.usb_hex_view.clear()

    def _append_log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_widget.appendPlainText(f"[{ts}] {message}")

    def _toggle_recording(self) -> None:
        if getattr(self, "recording", False):
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if self.recording:
            return
        self.recorder.start_session()
        self.recording = True
        self.record_button.setText("Stop Recording (Ctrl+Shift+R)")
        if self.camera.capture is not None:
            self.camera.set_recording(True, self.recorder.path_for("camera", ".avi"))
        if self.audio.stream is not None:
            self.audio.set_recording(True, self.recorder.path_for("audio", ".wav"))
        if self.usb_monitor._thread and self.usb_monitor._thread.is_alive():
            target = self.usb_target_combo.currentText()
            self.usb_monitor.set_recording(True, self.recorder.path_for("usb", ".bin", tag=target))
        self._append_log("Recording enabled")

    def _stop_recording(self) -> None:
        was_recording = self.recording
        self.recording = False
        self.record_button.setText("Start Recording (Ctrl+R)")
        self.camera.set_recording(False)
        self.audio.set_recording(False)
        self.usb_monitor.set_recording(False)
        if was_recording:
            self.recorder.stop_session()
            self._append_log("Recording disabled")

    def _emergency_stop(self) -> None:
        self._append_log("Emergency stop invoked")
        self.camera.stop()
        self.audio.stop()
        self.usb_monitor.stop()
        self.command_executor.stop_all()
        self._stop_recording()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._emergency_stop()
        super().closeEvent(event)


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QtWidgets.QApplication(list(argv or sys.argv))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
