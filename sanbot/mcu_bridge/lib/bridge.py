from __future__ import annotations

import dataclasses
import logging
from typing import Optional
import threading
import time

try:
    import usb.core  # type: ignore
    import usb.util  # type: ignore
except Exception:  # pragma: no cover - imported by CLI normally
    usb = None  # type: ignore

from .. import usb_bridge as _cli
from .safety import SafetyValidator, SafetyLimits, SafetyError


@dataclasses.dataclass
class ParsedFrame:
    type: int
    subtype: int
    content_len: int
    ack0: int
    frame_head: int
    ack1: int
    mmnn: int
    datas: bytes
    checksum: int
    total_len: int
    decoded: Optional[dict] = None


class USBBridge:
    """Lightweight helper to talk to Sanbot MCUs over USB.

    Example:
        bridge = USBBridge(vid=0x0483, pid=0x5740)
        bridge.open()
        frame_len = bridge.send_payload(b"\x04\x08\x01", tag=0x02)
        frame = bridge.read_frame(timeout_ms=1000)
        bridge.close()
    """

    def __init__(self, vid: int, pid: int, logger: Optional[logging.Logger] = None):
        self.vid = vid
        self.pid = pid
        self.dev = None
        self._eps = None
        self.log = logger or logging.getLogger(__name__)

    def open(self):
        """Open the USB device and claim bulk endpoints.

        Raises:
            RuntimeError: if the device cannot be found.
        """
        self.dev = _cli.find_device(self.vid, self.pid)
        if self.dev is None:
            raise RuntimeError(f"Device not found VID=0x{self.vid:04X} PID=0x{self.pid:04X}")
        self._eps = _cli.claim_bulk_endpoints(self.dev)
        self.log.debug("Claimed endpoints: out=%s in=%s", self._eps.ep_out, self._eps.ep_in)

    def close(self):
        """Release the claimed USB interface and clear handles."""
        if self._eps is not None:
            try:
                usb.util.release_interface(self._eps.dev, self._eps.intf)  # type: ignore[attr-defined]
            except Exception:
                pass
        self._eps = None
        self.dev = None

    @property
    def is_open(self) -> bool:
        return self._eps is not None

    def _reconnect(self):
        self.log.warning("USB reconnect: VID=0x%04X PID=0x%04X", self.vid, self.pid)
        self.dev = _cli.find_device(self.vid, self.pid)
        if self.dev is None:
            raise RuntimeError(f"Device not found VID=0x{self.vid:04X} PID=0x{self.pid:04X}")
        self._eps = _cli.claim_bulk_endpoints(self.dev)

    def send_payload(self, datas: bytes, tag: int, ack_flag: int = 1, timeout_ms: int = 1000, retries: int = 1) -> int:
        """Build and send a framed USB packet with a trailing point-tag.

        Args:
            datas: The payload before framing (the bean bytes).
            tag: The point_tag appended after the USB frame (1=head,2=bottom,3=broadcast).
            ack_flag: The ack flag written into the frame header.
            timeout_ms: USB write timeout.
            retries: Number of send retries on failure.

        Returns:
            The number of bytes written.

        Raises:
            RuntimeError: if the bridge is not opened.
            Exception: from the underlying USB write if all retries fail.
        """
        if not self._eps:
            raise RuntimeError("Bridge not opened")
        frame = _cli.build_usb_frame(datas, ack_flag=ack_flag) + bytes([tag & 0xFF])
        last_err: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                wrote = _cli.send_bulk(self._eps.ep_out, frame, timeout_ms)
                self.log.debug("sent %d bytes (attempt %d)", wrote, attempt)
                return wrote
            except Exception as e:
                last_err = e
                self.log.warning("send failed (attempt %d/%d): %s", attempt, retries, e)
                # Try a reconnect once per failed attempt
                try:
                    self._reconnect()
                except Exception as re:
                    self.log.warning("reconnect failed: %s", re)
        assert last_err is not None
        raise last_err

    def read_frame(self, timeout_ms: int = 1000, decode: bool = True) -> Optional[ParsedFrame]:
        """Read a single USB frame from the IN endpoint.

        Args:
            timeout_ms: Read timeout.
            decode: If True, attempts to decode known datas payloads.

        Returns:
            ParsedFrame or None when there is no data.

        Raises:
            RuntimeError: if the bridge is not opened.
        """
        if not self._eps:
            raise RuntimeError("Bridge not opened")
        try:
            chunk = self._eps.ep_in.read(self._eps.ep_in.wMaxPacketSize, timeout_ms)
            if not chunk:
                return None
            buf = bytearray(chunk)
            parsed = _cli.parse_usb_frame(buf)
            if not parsed:
                return None
            decoded = _cli._decode_known_datas(parsed['datas']) if decode else None
            return ParsedFrame(
                type=parsed['type'],
                subtype=parsed['subtype'],
                content_len=parsed['content_len'],
                ack0=parsed['ack0'],
                frame_head=parsed['frame_head'],
                ack1=parsed['ack1'],
                mmnn=parsed['mmnn'],
                datas=parsed['datas'],
                checksum=parsed['checksum'],
                total_len=parsed['total_len'],
                decoded=decoded,
            )
        except usb.core.USBTimeoutError:  # type: ignore[attr-defined]
            return None
        except Exception as e:
            # Attempt reconnect and return None; caller loop can continue
            self.log.warning("read failed: %s; attempting reconnect", e)
            try:
                self._reconnect()
            except Exception as re:
                self.log.warning("reconnect failed: %s", re)
            return None


class Sanbot:
    """High-level Sanbot API covering MCU operations.

    Wraps two USB endpoints (head and bottom MCUs) and exposes typed methods
    that mirror the original Android MCU beans. All methods send immediately;
    reading responses is event-driven (see `start_listening` and `on`).

    General conventions:
    - Units: degrees (int), milliseconds (int), millimeters (int) unless noted.
    - Tags: head=1, bottom=2; some commands use broadcast=3 as per firmware.
    - Safety: This layer does not enforce motion bounds; add checks in your app.
    - Events: Use `on('decoded:<name>', ...)` to act on incoming data.
    """

    VID = _cli.VID
    PID_BOTTOM = _cli.PID_BOTTOM
    PID_HEAD = _cli.PID_HEAD
    POINT_HEAD = _cli.POINT_HEAD
    POINT_BOTTOM = _cli.POINT_BOTTOM

    def __init__(self, logger: Optional[logging.Logger] = None, *, safety_limits: SafetyLimits | None = None, unsafe: bool = False):
        self.log = logger or logging.getLogger(__name__)
        self.bottom = USBBridge(self.VID, self.PID_BOTTOM, logger=self.log)
        self.head = USBBridge(self.VID, self.PID_HEAD, logger=self.log)
        self._callbacks: dict[str, list] = {}
        self._listener_threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self.safety = SafetyValidator(limits=safety_limits, unsafe=unsafe)

    # Lifecycle
    def open(self):
        """Open both head and bottom bridges.

        Claims the bulk interfaces. Raises if devices are not present.
        """
        self.bottom.open()
        self.head.open()

    def close(self):
        """Close both head and bottom bridges and release interfaces."""
        self.bottom.close()
        self.head.close()

    # Event callbacks
    def on(self, event: str, callback):
        """Register a callback for an event.

        Events:
          - 'frame': receives ParsedFrame for every frame
          - 'decoded:<name>': receives (name, fields, ParsedFrame)
          - For convenience, also '<name>': receives (fields, ParsedFrame)
        """
        self._callbacks.setdefault(event, []).append(callback)

    def off(self, event: str, callback=None):
        """Unregister callback(s) for an event."""
        if event not in self._callbacks:
            return
        if callback is None:
            del self._callbacks[event]
        else:
            self._callbacks[event] = [cb for cb in self._callbacks[event] if cb != callback]
            if not self._callbacks[event]:
                del self._callbacks[event]

    def _emit(self, event: str, *args):
        for key in (event,):
            for cb in self._callbacks.get(key, []):
                try:
                    cb(*args)
                except Exception as e:
                    self.log.warning("callback '%s' error: %s", key, e)

    def _listener_loop(self, bridge: USBBridge, name: str, decode: bool, interval_ms: int):
        while not self._stop_event.is_set():
            frame = bridge.read_frame(timeout_ms=interval_ms, decode=decode)
            if frame is None:
                continue
            self._emit('frame', frame)
            if frame.decoded:
                dname = frame.decoded.get('name')
                fields = frame.decoded.get('fields')
                if dname:
                    self._emit(f'decoded:{dname}', dname, fields, frame)
                    self._emit(dname, fields, frame)

    def start_listening(self, targets: tuple[str, ...] = ('bottom',), decode: bool = True, interval_ms: int = 1000):
        """Start background listener threads and emit events to callbacks."""
        self._stop_event.clear()
        self._listener_threads = []
        for t in targets:
            bridge = self.head if t == 'head' else self.bottom
            th = threading.Thread(target=self._listener_loop, args=(bridge, t, decode, interval_ms), daemon=True)
            th.start()
            self._listener_threads.append(th)

    def stop_listening(self, join_timeout: float = 0.5):
        """Stop listener threads."""
        self._stop_event.set()
        for th in self._listener_threads:
            th.join(timeout=join_timeout)
        self._listener_threads = []

    # Utilities
    def _send_head(self, datas: bytes, ack: int = 1) -> int:
        return self.head.send_payload(datas, self.POINT_HEAD, ack_flag=ack)

    def _send_bottom(self, datas: bytes, ack: int = 1, tag: int = POINT_BOTTOM) -> int:
        return self.bottom.send_payload(datas, tag, ack_flag=ack)

    # Heartbeat
    def heartbeat(self, target: str = 'bottom', switch_mode: int = 1) -> int:
        """Send heartbeat to a MCU.

        Args:
            target: 'head' or 'bottom'.
            switch_mode: 1 to keepalive; other modes per firmware (rare).
        Returns: bytes written.
        """
        datas = _cli.heartbeat_payload(switch_mode)
        if target == 'head':
            return self._send_head(datas)
        return self._send_bottom(datas)

    # Wheels (bottom)
    def wheels_angle(self, direction: str, speed: int, deg: int) -> int:
        """Rotate in place by relative angle.

        Args:
            direction: 'left' or 'right'.
            speed: 0-255 (device scale).
            deg: degrees (0-65535) LSB/MSB on wire.
        """
        mode = 0x02
        dir_code = 0x02 if direction == 'left' else 0x03
        self.safety.wheels_angle(speed, deg)
        datas = _cli.wheel_payload(mode, dir_code, speed=speed, deg=deg)
        return self._send_bottom(datas)

    def wheels_time(self, direction: str, ms: int, circle: bool = False) -> int:
        """Drive forward/back for a duration.

        Args:
            direction: 'forward' or 'back'.
            ms: milliseconds duration.
            circle: circle mode flag.
        """
        mode = 0x10
        dir_code = 0x01 if direction == 'forward' else 0x00
        self.safety.wheels_time(ms)
        datas = _cli.wheel_payload(mode, dir_code, ms=ms, is_circle=1 if circle else 0)
        return self._send_bottom(datas)

    def wheels_distance(self, direction: str, speed: int, mm: int) -> int:
        """Drive forward/back for a distance in millimeters.

        Args:
            direction: 'forward' or 'back'.
            speed: 0-255.
            mm: millimeters (0-65535).
        """
        mode = 0x11
        dir_code = 0x01 if direction == 'forward' else 0x00
        self.safety.wheels_distance(speed, mm)
        datas = _cli.wheel_payload(mode, dir_code, speed=speed, mm=mm)
        return self._send_bottom(datas)

    # LED
    def led(self, which_light: int, switch_mode: int, rate: int = 0, random_count: int = 0) -> int:
        """Control LEDs.

        Args:
            which_light: LED group byte (0=all, 4/5/0x0A=head sets, others bottom).
            switch_mode: effect code per device (blink/flicker modes).
            rate: effect speed parameter.
            random_count: randomization parameter if supported.
        """
        datas = _cli.led_payload(which_light, switch_mode, rate, random_count)
        tag = _cli.led_point_tag(which_light)
        pid = self.PID_HEAD if tag in (self.POINT_HEAD, 0x03) else self.PID_BOTTOM
        # send via appropriate bridge
        if pid == self.PID_HEAD:
            return self.head.send_payload(datas, tag)
        return self.bottom.send_payload(datas, tag)

    # Projector
    def projector_power(self, on: bool) -> int:
        """Power projector on/off."""
        datas = bytes([0x04, 0x03, 0x01 if on else 0x00])
        return self._send_head(datas)

    def projector_status(self) -> int:
        """Query projector on/off status.

        Event: 'projector_status' with fields {'status': byte, 'powered': bool?}
        """
        return self._send_head(bytes([0x81 & 0xFF, 0x18]))

    def projector_connection(self) -> int:
        """Query projector connection state (presence)."""
        return self._send_head(bytes([0x81 & 0xFF, 0x12]))

    def projector_quality(self, contrast: int, brightness: int, chroma_u: int, chroma_v: int, saturation_u: int, saturation_v: int, acutance: int) -> int:
        """Set projector quality parameters.

        Args: 0-255 values; device maps to actual picture settings.
        """
        datas = bytes([0x04, 0x0A, 0x08, contrast & 0xFF, brightness & 0xFF, chroma_u & 0xFF, chroma_v & 0xFF, saturation_u & 0xFF, saturation_v & 0xFF, acutance & 0xFF])
        return self._send_head(datas)

    def projector_output(self, proj_setting: int, h_tilt: int, v_tilt: int) -> int:
        """Set output geometry (e.g., trapezoid/tilt)."""
        datas = bytes([0x04, 0x0A, 0x07, proj_setting & 0xFF, h_tilt & 0xFF, v_tilt & 0xFF])
        return self._send_head(datas)

    def projector_picture(self, control: int, sub_type: int, degree: int) -> int:
        """Low-level picture control (raw codes).

        Args:
            control: primary control code.
            sub_type: sub-control code.
            degree: parameter byte.
        """
        datas = bytes([0x04, 0x0A, 0x03, control & 0xFF, sub_type & 0xFF, degree & 0xFF])
        return self._send_head(datas)

    def projector_other(self, switch_mode: int) -> int:
        """Other projector setting (raw switch_mode)."""
        datas = bytes([0x04, 0x0A, 0x05, switch_mode & 0xFF])
        return self._send_head(datas)

    def projector_type(self, proj_type: int) -> int:
        """Set projector type (raw device code)."""
        datas = bytes([0x04, 0x0A, 0x06, proj_type & 0xFF])
        return self._send_head(datas)

    def projector_expert(self, adjust_mode: int, control_mode: int, control_content: int) -> int:
        """Expert adjust (axis/phase), raw modes and content codes."""
        datas = bytes([0x04, 0x0A, 0x04, adjust_mode & 0xFF, control_mode & 0xFF, control_content & 0xFF])
        return self._send_head(datas)

    # Head motion
    def head_absolute(self, hdeg: int, vdeg: int) -> int:
        """Move head to absolute angles (horizontal/vertical)."""
        self.safety.head_absolute(hdeg, vdeg)
        return self._send_head(_cli.head_payload(0x21, 0x00, hdeg=hdeg, vdeg=vdeg))

    def head_relative(self, hdir: int, hdeg: int, vdir: int, vdeg: int) -> int:
        """Move head by relative deltas on H and V axes."""
        return self._send_head(_cli.head_payload(0x22, 0x00, hdir=hdir, hdeg=hdeg, vdir=vdir, vdeg=vdeg))

    def head_angle(self, axis: str, direction: int, speed: int, deg: int) -> int:
        """Move head on a single axis by angle with speed.

        axis: 'h' uses mode 0x02, 'v' uses 0x03 (firmware definitions).
        """
        self.safety.head_axis(speed, deg)
        mode = 0x02 if axis == 'h' else 0x03
        return self._send_head(_cli.head_payload(mode, direction, speed=speed, deg=deg))

    def head_time(self, direction: int, ms: int, flag: int = 0) -> int:
        """Timed head move with an extra deg-or-flag byte (device-specific)."""
        self.safety.head_time(ms)
        return self._send_head(_cli.head_payload(0x10, direction, ms=ms, deg_or_flag=flag))

    def head_noangle(self, direction: int, speed: int) -> int:
        """Head move without angle (speed+direction only)."""
        self.safety.head_noangle(speed)
        return self._send_head(_cli.head_payload(0x01, direction, speed=speed))

    def voice_location(self, hdeg: int, vdeg: int) -> int:
        """Send target head angles derived from voice localization."""
        datas = bytes([0x82 & 0xFF, 0x02, hdeg & 0xFF, (hdeg >> 8) & 0xFF, vdeg & 0xFF, (vdeg >> 8) & 0xFF])
        return self._send_head(datas)

    # Hand/Arm (bottom)
    def hand_angle(self, which: int, mode: int, direction: int, speed: int, deg: int) -> int:
        """Move hand/arm by angle.

        which: 0=both, 1=left, 2=right (typical mapping).
        mode: 0x02/0x03 (firmware-defined variants).
        """
        self.safety.hand_angle(speed, deg)
        return self._send_bottom(_cli.hand_payload(mode, which, direction=direction, speed=speed, deg=deg))

    def hand_time(self, which: int, ms: int, deg: int = 0) -> int:
        """Timed hand/arm move, optional degrees param."""
        self.safety.hand_time(ms, deg)
        return self._send_bottom(_cli.hand_payload(0x10, which, ms=ms, deg=deg))

    def hand_noangle(self, which: int, direction: int, speed: int) -> int:
        """Hand/arm move without angle (speed+direction)."""
        self.safety.hand_noangle(speed)
        return self._send_bottom(_cli.hand_payload(0x01, which, direction=direction, speed=speed))

    # Protection / Locks
    def motor_defend(self, which_part: int, enable: bool) -> int:
        """Enable/disable motor protection for a part.

        which_part: 1/2/3=head routes to head MCU; otherwise bottom.
        """
        datas = bytes([0x05, 0x02, which_part & 0xFF, 0x01 if enable else 0x00])
        tag = self.POINT_HEAD if (which_part & 0xFF) in (1, 2, 3) else self.POINT_BOTTOM
        return (self._send_head(datas) if tag == self.POINT_HEAD else self._send_bottom(datas))

    def motor_lock(self, which_part: int, enable: bool) -> int:
        """Lock/unlock motors for a part (head or bottom based on code)."""
        datas = bytes([0x05, 0x01, which_part & 0xFF, 0x01 if enable else 0x00])
        tag = self.POINT_HEAD if (which_part & 0xFF) in (1, 2, 3) else self.POINT_BOTTOM
        return (self._send_head(datas) if tag == self.POINT_HEAD else self._send_bottom(datas))

    # System
    def mcu_reset(self, target: str, time_byte: int = 1) -> int:
        """Reset target MCU.

        Args:
            target: 'head' or 'bottom'.
            time_byte: device-defined delay parameter.
        """
        datas = bytes([0x04, 0x0C, 0x01, time_byte & 0xFF])
        return self._send_head(datas) if target == 'head' else self._send_bottom(datas)

    def white_light(self, level: int) -> int:
        """Set white light/brightness level (0-255)."""
        return self._send_head(bytes([0x04, 0x01, 0x02, level & 0xFF]))

    def black_shield(self, enable: bool) -> int:
        """Enable/disable black shield mode (screen dimming/safety)."""
        return self._send_bottom(bytes([0x04, 0x0D, 0x01 if enable else 0x00]))

    def follow(self, enable: bool) -> int:
        """Enable/disable follow mode (firmware motion mode)."""
        return self._send_bottom(bytes([0x04, 0x0E, 0x01 if enable else 0x00]))

    def wander(self, enable: bool, wander_type: int = 1) -> int:
        """Enable/disable wander mode with a type parameter."""
        return self._send_head(bytes([0x04, 0x09, 0x01 if enable else 0x00, wander_type & 0xFF]))

    def hide_mode(self, enable: bool) -> int:
        """Enable/disable hide mode (firmware behavior)."""
        return self._send_bottom(bytes([0x04, 0x0F, 0x01 if enable else 0x00]))

    def dance(self, enable: bool) -> int:
        """Enable/disable dance mode (broadcast tag)."""
        return self._send_bottom(bytes([0x04, 0x06, 0x01 if enable else 0x00]), tag=0x03)

    def speaker(self, enable: bool) -> int:
        """Toggle speaker/beeper on head MCU."""
        return self._send_head(bytes([0x04, 0x04, 0x01 if enable else 0x00]))

    # Battery/Power
    def battery(self, current: int = -1) -> int:
        """Query battery level; optional currentBattery override.

        Event: 'battery' with fields {'level': byte, 'raw': hex}
        """
        parts = [0x81 & 0xFF, 0x01]
        if current != -1:
            parts.append(current & 0xFF)
        return self._send_bottom(bytes(parts))

    def battery_temp(self, temp: int = 0) -> int:
        """Query battery temperature (raw byte argument preserved)."""
        return self._send_bottom(bytes([0x81 & 0xFF, 0x04, temp & 0xFF]))

    def auto_charge(self, enable: bool, threshold: int | None = None) -> int:
        """Toggle auto-charge (with optional threshold byte)."""
        parts = [0x04, 0x05, 0x01 if enable else 0x00]
        if threshold is not None:
            parts.append(threshold & 0xFF)
        return self._send_bottom(bytes(parts))

    def change_pile(self, raw_payload: bytes) -> int:
        """Operate charge pile (raw payload for PrivateCommandUtil path)."""
        # ChangePileCommand: data = 0xA1 + payload, tag bottom
        datas = bytes([0xA1]) + raw_payload
        return self._send_bottom(datas)

    def auto_report(self, mode: int) -> int:
        """Enable/disable MCU auto-report (broadcast group)."""
        # Broadcast group tag per bean usage
        return self.bottom.send_payload(bytes([0x80 & 0xFF, mode & 0xFF]), tag=0x03)

    # Sensors/Queries
    def gyro(self, accel_status: int = -1, compass_status: int = -1) -> int:
        """Query gyroscope/accelerometer/compass status filters.

        Event: 'gyro' with values list (raw flags).
        """
        parts = [0x81 & 0xFF, 0x08]
        if accel_status != -1:
            parts.append(accel_status & 0xFF)
        if compass_status != -1:
            parts.append(compass_status & 0xFF)
        return self._send_bottom(bytes(parts))

    def touch(self, turnal: int = -1, info: int = -1) -> int:
        """Query touch switch with optional parameters.

        Routes to head/bottom/broadcast per firmware mapping.
        """
        parts = [0x81 & 0xFF, 0x05]
        if turnal != -1:
            parts.append(turnal & 0xFF)
        if info != -1:
            parts.append(info & 0xFF)
        # route based on turnal per CLI logic
        tag = self.POINT_BOTTOM
        if turnal in (1, 2, 5, 6, 11, 12, 13):
            tag = self.POINT_HEAD
        elif turnal == 0x93:
            tag = 0x03
        return self.bottom.send_payload(bytes(parts), tag) if tag != self.POINT_HEAD else self.head.send_payload(bytes(parts), tag)

    def pir(self, pir_type: int = -1, status: int = -1) -> int:
        """Query PIR state with optional filters (raw values)."""
        parts = [0x81 & 0xFF, 0x06]
        if pir_type != -1:
            parts.append(pir_type & 0xFF)
        if status != -1:
            parts.append(status & 0xFF)
        return self._send_bottom(bytes(parts))

    def obstacle(self, direction: int = -1, distance: int = -1) -> int:
        """Query obstacle state (direction/distance filters).

        Event: 'obstacle' with raw values list.
        """
        parts = [0x81 & 0xFF, 0x02]
        if direction != -1:
            parts.append(direction & 0xFF)
        if distance != -1:
            parts.append(distance & 0xFF)
        return self._send_bottom(bytes(parts))

    def button(self) -> int:
        """Query button state (event: 'button' with status byte)."""
        return self._send_head(bytes([0x81 & 0xFF, 0x17]))

    def work_status(self) -> int:
        """Query current work/motion status.

        Event fields: {'mode', 'follow', 'obstacle'} (small ints).
        """
        return self._send_bottom(bytes([0x81 & 0xFF, 0x22]), tag=0x03)

    def encoder_status(self) -> int:
        """Query bottom encoder connection state (status byte)."""
        return self._send_bottom(bytes([0x81 & 0xFF, 0x15]))

    def mcu_version(self, target: str) -> int:
        """Query MCU version (head or bottom).

        Event: 'mcu_version' with 'version_bytes' hex string.
        """
        datas = bytes([0x81 & 0xFF, 0x0D])
        return self._send_head(datas) if target == 'head' else self._send_bottom(datas)

    def head_motor_abnormal(self, which_part: int, status: int) -> int:
        """Query/report head motor abnormal for a part.

        Event fields: {'which_part', 'status'}
        """
        datas = bytes([0x81 & 0xFF, 0x09, which_part & 0xFF, status & 0xFF])
        tag = self.POINT_HEAD if (which_part & 0xFF) in (0x04, 0x05) else self.POINT_BOTTOM
        return self._send_head(datas) if tag == self.POINT_HEAD else self._send_bottom(datas)

    def photocoupler_abnormal(self, which_part: int) -> int:
        """Query photoelectric abnormal for a part.

        Event fields: {'which_part'}
        """
        datas = bytes([0x81 & 0xFF, 0x19, which_part & 0xFF])
        tag = self.POINT_HEAD if (which_part & 0xFF) in (0x01, 0x02) else self.POINT_BOTTOM
        return self._send_head(datas) if tag == self.POINT_HEAD else self._send_bottom(datas)

    def detect_3d(self, distance: int = 0) -> int:
        """Query 3D detect reading.

        Note: not a point cloud; device computes and returns a reading.
        The 'distance' argument is a device parameter byte.
        """
        return self._send_bottom(bytes([0x82 & 0xFF, 0x03, 0x01, distance & 0xFF]))

    def expression_status(self) -> int:
        """Query expression status (asset presence/ok)."""
        return self._send_head(bytes([0x81 & 0xFF, 0x1C]))

    def expression_normal(self, expression_type: int) -> int:
        """Set a normal expression by type code (device-specific)."""
        return self._send_head(bytes([0x06, 0x01, expression_type & 0xFF]))

    def expression_version_set(self, version: bytes) -> int:
        """Set expression asset version (opaque bytes, vendor internal)."""
        return self._send_head(bytes([0x04, 0x11]) + version)

    def expression_version_query(self) -> int:
        """Query expression version (event: 'expression_version')."""
        return self._send_head(bytes([0x81 & 0xFF, 0x1B]))

    def ir_sender(self) -> int:
        """Query IR sender status (broadcast)."""
        return self._send_bottom(bytes([0x81 & 0xFF, 0x16]), tag=0x03)

    def uart_status(self) -> int:
        """Query UART connection status (broadcast)."""
        return self._send_bottom(bytes([0x81 & 0xFF, 0x13]), tag=0x03)

    def ir_receive_status(self) -> int:
        """Query IR receive status; raw summary of IR heads/count."""
        return self._send_bottom(bytes([0x81 & 0xFF, 0x0B]))

    def ir_sensor(self, content: int = -1, info: int = -1) -> int:
        """Low-level IR sensor command.

        Args are forwarded to device; upstream logic typically interprets.
        Event: 'ir_sensor_cmd' with 'raw'.
        """
        parts = [0x83 & 0xFF, 0x81 & 0xFF, 0x02]
        if content != -1:
            parts.append(content & 0xFF)
        if info != -1:
            parts.append(info & 0xFF)
        return self._send_bottom(bytes(parts), tag=0x03)

    def photoelectric_switch(self, retain_data: int = 1) -> int:
        """Query photoelectric switch status (broadcast).

        Event: 'photoelectric_switch' with 'raw' bytes.
        """
        return self.bottom.send_payload(bytes([0x81 & 0xFF, 0x11, retain_data & 0xFF]), tag=0x03)

    def optocoupler_status(self, which_part: int) -> int:
        """Query optocoupler status for a part.

        Event: 'conn_or_optocoupler' with 'which_part' and 'raw'.
        """
        datas = bytes([0x81 & 0xFF, 0x12, which_part & 0xFF])
        tag = self.POINT_HEAD if (which_part & 0xFF) in (0x03, 0x04) else self.POINT_BOTTOM
        return self._send_head(datas) if tag == self.POINT_HEAD else self._send_bottom(datas)

    def movement_status(self, which_part: int, status: int) -> int:
        """Query movement status (shares 0x81/0x09 channel).

        Event: 'head_motor_abnormal' equivalent fields.
        """
        datas = bytes([0x81 & 0xFF, 0x09, which_part & 0xFF, status & 0xFF])
        tag = self.POINT_HEAD if (which_part & 0xFF) in (0x04, 0x05) else self.POINT_BOTTOM
        return self._send_head(datas) if tag == self.POINT_HEAD else self._send_bottom(datas)

    def zigbee_send(self, payload: bytes) -> int:
        """Send raw ZigBee payload to the module.

        ZigBee is JSON-oriented; prefer `zigbee_send_json` for convenience.
        """
        # ZigbeeCommand: 0xA0 + payload, to head, ack=0
        return self.head.send_payload(bytes([0xA0]) + payload, self.POINT_HEAD, ack_flag=0)

    # ZigBee JSON helpers (passthrough to module)
    def zigbee_send_json(self, json_str: str) -> int:
        return self.zigbee_send(json_str.encode('utf-8'))

    def zigbee_allow_join(self, seconds: int) -> int:
        return self.zigbee_send_json('{"time":%d}' % seconds)

    def zigbee_switch_whitelist(self, on: bool) -> int:
        return self.zigbee_send_json('{"switch":%d}' % (1 if on else 0))

    def zigbee_add_whitelist(self, device_id: str) -> int:
        return self.zigbee_send_json('{"id":"%s"}' % device_id)

    def zigbee_delete_whitelist(self, device_id: str) -> int:
        return self.zigbee_send_json('{"id":"%s"}' % device_id)

    def zigbee_clear_whitelist(self) -> int:
        return self.zigbee_send_json('{}')

    def zigbee_remove_device(self, device_id: str) -> int:
        return self.zigbee_send_json('{"id":"%s"}' % device_id)

    def zigbee_get_whitelist(self) -> int:
        return self.zigbee_send_json('{}')

    def zigbee_get_list(self) -> int:
        return self.zigbee_send_json('{}')

    # MCU Upgrade (YMODEM)
    def mcu_upgrade(self, target: str, file_path: str, block_size: int = 1024):
        """Send a firmware image to head/bottom MCU via YMODEM packets.

        Args:
            target: 'head' or 'bottom'
            file_path: path to firmware binary
            block_size: 128 or 1024
        The listener will emit 'upgrade_status' events as the device reports.
        """
        import os
        if block_size not in (128, 1024):
            raise ValueError('block_size must be 128 or 1024')
        if not os.path.isfile(file_path):
            raise FileNotFoundError(file_path)
        # Choose bridge and tag
        bridge = self.head if target == 'head' else self.bottom
        tag = self.POINT_HEAD if target == 'head' else self.POINT_BOTTOM
        # Prepare
        bridge.send_payload(bytes([0x04, 0x0B, 0x01]), tag=0x03)
        # Header
        fname = os.path.basename(file_path)
        fsize = os.path.getsize(file_path)
        hdr = _cli.ymodem_file_header(fname, fsize)
        bridge.send_payload(hdr, tag)
        # Data
        index = 1
        sent = 0
        with open(file_path, 'rb') as f:
            while sent < fsize:
                chunk = f.read(block_size)
                if not chunk:
                    break
                blk = _cli.ymodem_data_block(index, chunk, block_size)
                bridge.send_payload(blk, tag)
                sent += len(chunk)
                index += 1
        # End
        fin = _cli.ymodem_empty_packet()
        bridge.send_payload(fin, tag)

    def mcu_upgrade_status(self, up_type: str) -> int:
        """Query upgrade status for 'head' or 'bottom' type (0x81/0x0C)."""
        tbyte = 0x01 if up_type == 'head' else 0x02
        return self.bottom.send_payload(bytes([0x81 & 0xFF, 0x0C, 0x00, tbyte & 0xFF]), tag=0x03)
