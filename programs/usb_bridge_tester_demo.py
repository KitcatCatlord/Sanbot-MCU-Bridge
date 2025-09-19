#!/usr/bin/env python3
"""Demo harness for the USB bridge tester without Sanbot hardware.

Launches the GUI with simulated camera, microphone, USB data, and
command execution so the layout and interactions can be exercised on any
machine.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

import usb_bridge_tester as tester


class DemoRecordingManager(tester.RecordingManager):
    """Recording manager that stores demo sessions under a temp path."""

    def __init__(self):
        super().__init__(Path.home() / ".sanbot_demo_recordings")


class DemoCommandExecutor(QtCore.QObject):
    """Simulated command executor that never touches hardware."""

    started = QtCore.Signal(str)
    finished = QtCore.Signal(str)
    failed = QtCore.Signal(str)

    def __init__(self, recorder: tester.RecordingManager, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.recorder = recorder

    def execute(self, node: tester.ClickCommandNode, values: Dict[str, object]) -> None:
        path = " ".join(node.full_path())
        self.started.emit(f"{path} (demo)")
        entry = {
            "timestamp": QtCore.QDateTime.currentDateTimeUtc().toString(QtCore.Qt.ISODate),
            "command": path,
            "params": values,
            "status": "simulated",
        }
        self.recorder.log_command(entry)

        def _complete() -> None:
            self.finished.emit(f"{path} (simulated)")

        QtCore.QTimer.singleShot(400, _complete)

    def stop_all(self) -> None:  # pragma: no cover - no threads to join
        pass


class DemoCamera(tester.CameraController):
    """Camera controller that renders a synthetic pattern."""

    def start(self, device_index: int) -> None:
        if self.timer.isActive():
            self.status.emit("Demo camera already running")
            return
        self.device_index = device_index
        self.frame_size = (640, 360)
        self._phase = 0
        self.timer.start(66)  # ~15 FPS
        self.status.emit("Demo camera running (synthetic frames)")

    def stop(self) -> None:
        if self.timer.isActive():
            self.timer.stop()
        self.status.emit("Demo camera stopped")

    def set_recording(self, active: bool, output_path: Optional[Path] = None) -> None:
        self.recording_active = active
        if active:
            self.status.emit("Demo camera recording enabled (no file written)")
        else:
            self.status.emit("Demo camera recording disabled")

    def _grab_frame(self) -> None:
        if not self.timer.isActive() or self.frame_size is None:
            return
        w, h = self.frame_size
        image = QtGui.QImage(w, h, QtGui.QImage.Format_RGB32)
        image.fill(QtGui.QColor("#20262E"))
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setPen(QtGui.QPen(QtGui.QColor("#4FC3F7"), 3))
        painter.setBrush(QtGui.QColor("#1B5E20"))
        radius = 60 + 40 * math.sin(self._phase)
        center = QtCore.QPointF(w / 2, h / 2)
        painter.drawEllipse(center, radius, radius / 1.5)
        painter.setPen(QtGui.QPen(QtGui.QColor("#FDD835"), 2))
        painter.drawText(image.rect(), QtCore.Qt.AlignCenter, "Sanbot Demo")
        painter.end()
        self._phase += 0.15
        self.frame_ready.emit(image)


class DemoAudio(tester.AudioController):
    """Audio controller that emits a synthetic waveform."""

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self._demo_timer = QtCore.QTimer()
        self._demo_timer.timeout.connect(self._emit_wave)
        self._t = 0.0

    def list_input_devices(self):  # pragma: no cover - simple override
        return [(0, "Demo microphone")]

    def start(self, device_index: int, sample_rate: int) -> None:
        if self._demo_timer.isActive():
            self.status.emit("Demo microphone already running")
            return
        self.sample_rate = sample_rate
        self._demo_timer.start(50)
        self.status.emit("Demo microphone running (synthetic waveform)")

    def stop(self) -> None:
        self._demo_timer.stop()
        self.status.emit("Demo microphone stopped")

    def set_recording(self, active: bool, output_path: Optional[Path] = None) -> None:
        self.recording_active = active
        if active:
            self.status.emit("Demo audio recording enabled (no file written)")
        else:
            self.status.emit("Demo audio recording disabled")

    def _emit_wave(self) -> None:
        t = np.linspace(0, 1, 800, dtype=np.float32)
        waveform = 0.6 * np.sin(2 * np.pi * (2.5 + 0.5 * math.sin(self._t)) * t)
        self._t += 0.1
        self.waveform.emit(waveform)


class DemoUSBMonitor(QtCore.QObject):
    """USB monitor that periodically emits random payloads."""

    data_ready = QtCore.Signal(bytes)
    status = QtCore.Signal(str)

    def __init__(self, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.target = "bottom"
        self.chunk_size = 48
        self.timeout_ms = 500
        self._timer = QtCore.QTimer()
        self._timer.timeout.connect(self._emit_payload)
        self._recording = False

    def configure(self, target: str, chunk_size: int, timeout_ms: int) -> None:
        self.target = target
        self.chunk_size = chunk_size
        self.timeout_ms = timeout_ms
        if self._timer.isActive():
            self._timer.start(self.timeout_ms)

    def set_recording(self, active: bool, output_path: Optional[Path] = None) -> None:
        self._recording = active
        if active:
            self.status.emit("Demo USB recording enabled (no file written)")
        else:
            self.status.emit("Demo USB recording disabled")

    def start(self) -> None:
        if self._timer.isActive():
            self.status.emit("Demo USB monitor already running")
            return
        self._timer.start(self.timeout_ms)
        self.status.emit(f"Demo USB monitor running ({self.target})")

    def stop(self) -> None:
        self._timer.stop()
        self.status.emit("Demo USB monitor stopped")

    def _emit_payload(self) -> None:
        payload = os.urandom(self.chunk_size)
        self.data_ready.emit(payload)


def install_demo_overrides() -> None:
    tester.RecordingManager = DemoRecordingManager  # type: ignore[assignment]
    tester.CommandExecutor = DemoCommandExecutor  # type: ignore[assignment]
    tester.CameraController = DemoCamera  # type: ignore[assignment]
    tester.AudioController = DemoAudio  # type: ignore[assignment]
    tester.USBMonitor = DemoUSBMonitor  # type: ignore[assignment]


def main() -> int:
    install_demo_overrides()
    app = QtWidgets.QApplication(sys.argv)
    window = tester.MainWindow()
    window.setWindowTitle("Sanbot USB Bridge Tester (Demo Mode)")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
