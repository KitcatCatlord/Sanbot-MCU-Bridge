#!/usr/bin/env python3
import sys
import struct
import time
import logging
import errno
import threading
import atexit
import click
from click.exceptions import Abort

from .lib.safety import SafetyValidator

try:
    import usb.core
    import usb.util
except ImportError as e:
    print("This tool requires pyusb. Install with: pip install -r requirements.txt", file=sys.stderr)
    raise


VID = 0x0483
PID_BOTTOM = 0x5740  # Bottom MCU
PID_HEAD = 0x5741    # Head MCU

POINT_HEAD = 0x01
POINT_BOTTOM = 0x02


class USBEndpoints:
    def __init__(self, dev, cfg, intf, ep_out, ep_in):
        self.dev = dev
        self.cfg = cfg
        self.intf = intf
        self.ep_out = ep_out
        self.ep_in = ep_in


def find_device(vid, pid) -> usb.core.Device | None:
    return usb.core.find(idVendor=vid, idProduct=pid)


def claim_bulk_endpoints(dev: usb.core.Device | None) -> USBEndpoints:
    if dev is None:
        raise click.ClickException("Device not found; ensure the Sanbot MCU is connected and powered")
    if isinstance(dev, Abort):
        raise dev
    try:
        dev.set_configuration()
    except usb.core.USBError as exc:
        raise click.ClickException(f"Failed to configure USB device: {exc}") from exc
    cfg = dev.get_active_configuration()
    # Iterate interfaces; pick first one with bulk in/out endpoints
    ep_out = ep_in = None
    intf = None
    for i in cfg:
        intf = i
        intf_num = intf.bInterfaceNumber
        try:
            if dev.is_kernel_driver_active(intf_num):
                try:
                    dev.detach_kernel_driver(intf_num)
                    LOG.debug("Detached kernel driver from interface %d", intf_num)
                except usb.core.USBError as exc:
                    raise click.ClickException(
                        f"Kernel driver in use on interface {intf_num}: {exc}"
                    ) from exc
        except NotImplementedError:
            pass
        for ep in i:
            # bmAttributes lower bits 0x02 = bulk; bEndpointAddress bit7 = direction
            is_bulk = (ep.bmAttributes & 0x03) == 0x02
            is_in = (ep.bEndpointAddress & 0x80) == 0x80
            if is_bulk and not is_in and ep_out is None:
                ep_out = ep
            if is_bulk and is_in and ep_in is None:
                ep_in = ep
        if ep_out is not None and ep_in is not None:
            break
    if ep_out is None or ep_in is None:
        raise RuntimeError("Failed to find bulk in/out endpoints")
    try:
        usb.util.claim_interface(dev, intf)
    except usb.core.USBError as exc:
        raise click.ClickException(f"Unable to claim USB interface: {exc}") from exc
    return USBEndpoints(dev, cfg, intf, ep_out, ep_in)


def short_to_bytes(val: int) -> bytes:
    return struct.pack('>H', val & 0xFFFF)  # big-endian unsigned short


def int_to_bytes(val: int) -> bytes:
    return struct.pack('>I', val)  # big-endian unsigned int


def build_usb_frame(datas: bytes, ack_flag: int = 0x01) -> bytes:
    # Mirrors com.qihan.uvccamera.USBCommand
    # Defaults from decompiled app
    type_short = 0xA403  # bytes A4 03
    subtype_short = 0x0000
    frame_head_short = 0xFFA5  # matches (-0x5b) << 8 | ? in app; empirically used

    # content_len = len(datas) + 5 (frame_head[2] + ack[1] + mmnn[2]) + 1 (checksum)
    content_len = len(datas) + 6
    mmnn = (len(datas) + 1) & 0xFFFF

    msg_size = int_to_bytes(content_len)

    # data_sum accumulates: frame_head bytes + ack + mmnn + all datas, truncated to 1 byte
    fh = short_to_bytes(frame_head_short)
    data_sum = 0
    data_sum += fh[0]
    data_sum += fh[1]
    data_sum += (ack_flag & 0xFF)
    data_sum += (mmnn & 0xFFFF)
    for b in datas:
        data_sum += b
    # checksum is 1-byte sum truncated to 8 bits; pack as unsigned
    checksum = struct.pack('B', data_sum & 0xFF)

    buf = bytearray()
    buf += short_to_bytes(type_short)
    buf += short_to_bytes(subtype_short)
    buf += msg_size
    buf += struct.pack('B', ack_flag)
    buf += b'\x00' * 7  # unuse[7]
    buf += fh
    buf += struct.pack('B', ack_flag)
    buf += short_to_bytes(mmnn)
    buf += datas
    buf += checksum
    return bytes(buf)


def heartbeat_payload(switch_mode: int = 1, lsb: int = 0, msb: int = 0) -> bytes:
    # Mirrors HeartBeatCommand.getMessageCommand() payload (before USB frame)
    # [0x04, 0x08, switchMode] (and optionally lsb, msb when switchMode != 1)
    if switch_mode == 1:
        return bytes([0x04, 0x08, switch_mode & 0xFF])
    return bytes([0x04, 0x08, switch_mode & 0xFF, lsb & 0xFF, msb & 0xFF])


CLI_RETRIES = 1
CLI_SAFETY = SafetyValidator()
LOG = logging.getLogger("mcu_bridge")
USB_SEND_LOCK = threading.Lock()

CLI_AUTO_READ = True
CLI_READ_TIMEOUT_MS = 300
CLI_AUTO_HEARTBEAT = True
CLI_HEARTBEAT_INTERVAL_MS = 1500
CLI_HEARTBEAT_HEAD = False


def send_bulk(ep_out, data: bytes, timeout_ms: int = 1000) -> int:
    last_err = None
    for attempt in range(1, CLI_RETRIES + 1):
        try:
            wrote = ep_out.write(data, timeout=timeout_ms)
            if attempt > 1:
                LOG.debug("write succeeded after retry %d", attempt)
            return wrote
        except Exception as e:
            last_err = e
            LOG.warning("USB write failed (attempt %d/%d): %s", attempt, CLI_RETRIES, e)
            time.sleep(0.05)
    assert last_err is not None
    raise last_err


def send_command(eps: USBEndpoints, data: bytes, *, label: str | None = None,
                 expect_response: bool | None = None,
                 read_timeout_ms: int | None = None) -> int:
    with USB_SEND_LOCK:
        if CLI_DUMP_TX:
            prefix = label or 'tx'
            print(f'-> {prefix}: len={len(data)} hex={data.hex()}')
        wrote = send_bulk(eps.ep_out, data)
        should_read = CLI_AUTO_READ if expect_response is None else bool(expect_response)
        if should_read and eps.ep_in is not None:
            timeout = read_timeout_ms if read_timeout_ms is not None else CLI_READ_TIMEOUT_MS
            _maybe_auto_read(eps, label=label, timeout_ms=timeout)
        return wrote


def release_endpoints(eps: USBEndpoints | None) -> None:
    if eps is None:
        return
    try:
        usb.util.release_interface(eps.dev, eps.intf)
    except Exception:
        pass
    try:
        usb.util.dispose_resources(eps.dev)
    except Exception:
        pass


# ----- Safety / validation helpers -----

def _assert_range(name, val, min_v, max_v):
    if val < min_v or val > max_v:
        raise click.ClickException("{} out of range [{}..{}]: {}".format(name, min_v, max_v, val))


def _assert_in(name, val, allowed):
    if val not in allowed:
        raise click.ClickException("{} must be one of {}: {}".format(name, allowed, val))


def _decode_known_datas(datas: bytes) -> dict | None:
    """Best-effort decoder for common inbound payloads (datas segment).

    Returns a dict with 'name' and 'fields' when recognized.
    """
    if not datas:
        return None
    b0 = datas[0]
    b1 = datas[1] if len(datas) > 1 else None
    # 0x81 group: queries/status
    if b0 == 0x81:
        # Battery query / change
        if b1 == 0x01:
            level = datas[2] if len(datas) > 2 else None
            return {'name': 'battery', 'fields': {'level': level, 'raw': datas.hex()}}
        if b1 == 0x03:
            status = datas[2] if len(datas) > 2 else None
            return {'name': 'battery_change', 'fields': {'status': status}}
        if b1 == 0x04:
            temp = datas[2] if len(datas) > 2 else None
            return {'name': 'battery_temp', 'fields': {'temp': temp}}
        if b1 == 0x05:
            # Touch: turnal (part) + information when available
            fields = {'raw': datas.hex()}
            if len(datas) >= 4:
                turnal = datas[2]
                info = datas[3]
                part_map = {
                    0x01: 'head_front', 0x02: 'head_back',
                    0x05: 'left_arm', 0x06: 'right_arm',
                    0x0B: 'chest_left', 0x0C: 'chest_mid', 0x0D: 'chest_right',
                }
                fields.update({'part': turnal, 'part_name': part_map.get(turnal, 'unknown'), 'info': info})
            else:
                fields['values'] = list(datas[2:])
            return {'name': 'touch', 'fields': fields}
        if b1 == 0x06:
            # PIR: label common sensor positions if lengths match expectations
            vals = list(datas[2:])
            pfields = {'values': vals}
            if len(vals) == 3:
                pfields['sensors'] = {'left': vals[0], 'mid': vals[1], 'right': vals[2]}
            elif len(vals) >= 6:
                pfields['sensors'] = {
                    'front_low': vals[0], 'front_high': vals[1], 'front_arm': vals[2],
                    'left': vals[3], 'mid': vals[4], 'right': vals[5],
                }
            return {'name': 'pir', 'fields': pfields}
        if b1 == 0x02:
            # Obstacle: direction/distance + per-location values when available
            fields = {'raw': datas.hex()}
            if len(datas) >= 4:
                fields['direction'] = datas[2]
                fields['distance'] = datas[3]
            vals = list(datas[4:]) if len(datas) > 4 else []
            if len(vals) >= 6:
                fields['sensors'] = {
                    'front_low': vals[0], 'front_high': vals[1], 'front_arm': vals[2],
                    'left': vals[3], 'mid': vals[4], 'right': vals[5],
                }
            elif vals:
                fields['values'] = vals
            return {'name': 'obstacle', 'fields': fields}
        if b1 == 0x13:
            status = datas[2] if len(datas) > 2 else None
            return {'name': 'uart_connection', 'fields': {'status': status}}
        if b1 == 0x15:
            status = datas[2] if len(datas) > 2 else None
            return {'name': 'bottom_encoder', 'fields': {'status': status}}
        if b1 == 0x16:
            status = datas[2] if len(datas) > 2 else None
            return {'name': 'ir_sender', 'fields': {'status': status}}
        if b1 == 0x17:
            status = datas[2] if len(datas) > 2 else None
            f = {'status': status}
            if status is not None:
                f['pressed'] = (status != 0)
            return {'name': 'button', 'fields': f}
        if b1 == 0x18:
            status = datas[2] if len(datas) > 2 else None
            fields = {'status': status}
            if status in (0x00, 0x01):
                fields['powered'] = True if status == 0x01 else False
            return {'name': 'projector_status', 'fields': fields}
        if b1 == 0x12:
            # Could be projector connection (no args) or optocoupler (with whichPart)
            fields = {'raw': datas.hex()}
            if len(datas) >= 3:
                fields['which_part'] = datas[2]
            return {'name': 'conn_or_optocoupler', 'fields': fields}
        if b1 == 0x19:
            which = datas[2] if len(datas) > 2 else None
            return {'name': 'photoelectric_abnormal', 'fields': {'which_part': which}}
        if b1 == 0x09:
            which = datas[2] if len(datas) > 2 else None
            st = datas[3] if len(datas) > 3 else None
            return {'name': 'head_motor_abnormal', 'fields': {'which_part': which, 'status': st}}
        if b1 == 0x22:
            # Work status (mode/follow/obstacle)
            # Heuristic: [0x81,0x22, mode?, follow?, obstacle?]
            fields = {}
            if len(datas) > 2:
                fields['mode'] = datas[2]
            if len(datas) > 3:
                fields['follow'] = datas[3]
            if len(datas) > 4:
                fields['obstacle'] = datas[4]
            return {'name': 'work_status', 'fields': fields}
        if b1 == 0x0D:
            ver = bytes(datas[2:])
            return {'name': 'mcu_version', 'fields': {'version_bytes': ver.hex()}}
        if b1 == 0x1A:
            # Hide obstacle status summary (which + status)
            fields = {'raw': datas.hex()}
            if len(datas) >= 4:
                fields['which'] = datas[2]
                fields['status'] = datas[3]
            return {'name': 'hide_obstacle_status', 'fields': fields}
        if b1 == 0x0A:
            # Hide obstacle status
            return {'name': 'hide_obstacle_status', 'fields': {'raw': datas.hex()}}
        if b1 == 0x0B:
            # IR receive status
            return {'name': 'ir_receive_status', 'fields': {'raw': datas.hex()}}
        if b1 == 0x08:
            # Gyro readings: three 16-bit numbers (drift/elevation/roll)
            vals = list(datas[2:])
            fields = {'values': vals}
            def _u16(lsb: int, msb: int) -> int:
                v = (lsb & 0xFF) | ((msb & 0xFF) << 8)
                return v - 0x10000 if v & 0x8000 else v
            if len(vals) >= 6:
                fields['drift_angle'] = _u16(vals[0], vals[1])
                fields['elevation']   = _u16(vals[2], vals[3])
                fields['roll_angle']  = _u16(vals[4], vals[5])
            return {'name': 'gyro', 'fields': fields}
        if b1 == 0x14:
            return {'name': 'spi_flash_status', 'fields': {'raw': datas.hex()}}
        if b1 == 0x1B:
            ver = bytes(datas[2:])
            return {'name': 'expression_version', 'fields': {'version_bytes': ver.hex()}}
        if b1 == 0x11:
            # Photoelectric switch (broadcast)
            return {'name': 'photoelectric_switch', 'fields': {'raw': datas.hex()}}
        if b1 == 0x0C:
            # Upgrade status: [0x81,0x0C,0x00,type]
            up_type = datas[3] if len(datas) > 3 else None
            return {'name': 'upgrade_status', 'fields': {'type': up_type, 'raw': datas.hex()}}
    # 0x82 group: sensor/data
    if b0 == 0x82:
        if b1 == 0x03:
            return {'name': 'detect_3d', 'fields': {'raw': datas.hex()}}
        if b1 == 0x02:
            return {'name': 'voice_location', 'fields': {'hdeg': datas[2] | (datas[3] << 8) if len(datas) >= 4 else None,
                                                        'vdeg': datas[4] | (datas[5] << 8) if len(datas) >= 6 else None}}
    # 0x80 group: auto-report
    if b0 == 0x80:
        return {'name': 'auto_report', 'fields': {'mode': datas[1] if len(datas) > 1 else None, 'raw': datas.hex()}}
    # 0x83 group: vendor sensor
    if b0 == 0x83 and b1 == 0x81:
        return {'name': 'ir_sensor_cmd', 'fields': {'raw': datas.hex()}}
    # Private peripherals frame (charge pile / telecontrol): 0xFF 0xA6 ...
    if b0 == 0xFF and b1 == 0xA6 and len(datas) >= 7:
        # datas[2] is 0x01 constant; datas[3:5] mmnn; datas[5] primary type; datas[6] subtype
        ptype = datas[5]
        subtype = datas[6]
        if ptype == 0x00:
            # Query private type results (maps 1..8)
            return {'name': 'private_query_type', 'fields': {'type': subtype, 'raw': datas.hex()}}
        if ptype == 0x01:
            # Operate charge pile
            sub_dev = datas[7] if len(datas) > 7 else None
            return {'name': 'charge_pile_status', 'fields': {'sub_device_type': sub_dev, 'raw': datas.hex()}}
        if ptype == 0x02:
            # Operate telecontrol (IR remote?)
            sub_dev = datas[7] if len(datas) > 7 else None
            back_msg = datas[8] if len(datas) > 8 else None
            back_status = datas[9] if len(datas) > 9 else None
            return {'name': 'telecontrol_status', 'fields': {'sub_device_type': sub_dev, 'back_message': back_msg, 'back_status': back_status, 'raw': datas.hex()}}
        return {'name': 'private_peripheral', 'fields': {'ptype': ptype, 'subtype': subtype, 'raw': datas.hex()}}
    return None


@click.group()
@click.option('--log-level', default='WARNING', type=click.Choice(['DEBUG','INFO','WARNING','ERROR','CRITICAL']))
@click.option('--retries', default=1, type=int, help='USB write retries on failure')
@click.option('--unsafe/--safe', 'unsafe', default=False, help='Disable safety checks (not recommended)')
@click.option('--auto-read/--no-auto-read', default=True, help='Read one response frame after each command when possible')
@click.option('--read-timeout', default=300, type=int, help='Response read timeout (ms) when auto-read is enabled')
@click.option('--auto-heartbeat/--no-auto-heartbeat', default=True, help='Send periodic heartbeats while the CLI is running')
@click.option('--heartbeat-interval', default=1500, type=int, help='Heartbeat interval in milliseconds')
@click.option('--heartbeat-head/--no-heartbeat-head', default=False, help='Include head MCU in auto heartbeat loop')
def cli(log_level: str, retries: int, unsafe: bool, auto_read: bool, read_timeout: int,
        auto_heartbeat: bool, heartbeat_interval: int, heartbeat_head: bool):
    """Sanbot USB MCU bridge (experimental)."""
    global CLI_RETRIES
    global CLI_AUTO_READ
    global CLI_READ_TIMEOUT_MS
    global CLI_AUTO_HEARTBEAT
    global CLI_HEARTBEAT_INTERVAL_MS
    global CLI_HEARTBEAT_HEAD
    CLI_RETRIES = max(1, retries)
    logging.basicConfig(level=getattr(logging, log_level))
    LOG.setLevel(getattr(logging, log_level))
    try:
        CLI_SAFETY.set_unsafe(bool(unsafe))
    except Exception:
        # Safety validator not critical for CLI init
        pass
    CLI_AUTO_READ = bool(auto_read)
    CLI_READ_TIMEOUT_MS = max(1, read_timeout)
    CLI_AUTO_HEARTBEAT = bool(auto_heartbeat)
    CLI_HEARTBEAT_INTERVAL_MS = max(100, heartbeat_interval)
    CLI_HEARTBEAT_HEAD = bool(heartbeat_head)
    HEARTBEAT_MANAGER.configure(
        enabled=CLI_AUTO_HEARTBEAT,
        interval_ms=CLI_HEARTBEAT_INTERVAL_MS,
        head_enabled=CLI_HEARTBEAT_HEAD,
    )


# ----- YMODEM helpers for MCU upgrade -----

def crc16_xmodem(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


def _compl(v: int) -> int:
    v = v % 0xFF if v > 0xFF else v
    return (0xFF - v) & 0xFF


def ymodem_file_header(fname: str, fsize: int) -> bytes:
    name_bytes = fname.encode('utf-8')
    size_bytes = str(fsize).encode('utf-8')
    block = bytearray(0x85)
    block[0] = 0x01  # SOH
    block[1] = 0x00
    block[2] = _compl(0)
    # payload area (128 bytes) starts at 3
    payload = bytearray(0x80)
    payload[:len(name_bytes)] = name_bytes
    idx = len(name_bytes)
    payload[idx] = 0x00
    idx += 1
    payload[idx: idx + len(size_bytes)] = size_bytes
    # copy payload into block
    block[3:3+0x80] = payload
    crc = crc16_xmodem(bytes(payload))
    block[0x83] = (crc >> 8) & 0xFF
    block[0x84] = crc & 0xFF
    return bytes(block)


def ymodem_data_block(index: int, data: bytes, block_size: int) -> bytes:
    if block_size not in (128, 1024):
        raise ValueError('block_size must be 128 or 1024')
    header = 0x02  # the stock app uses 0x02 for data blocks
    total_len = 3 + block_size + 2
    buf = bytearray(total_len)
    buf[0] = header
    buf[1] = index & 0xFF
    buf[2] = _compl(index)
    plen = min(len(data), block_size)
    buf[3:3+plen] = data[:plen]
    # pad with 0x1A
    for i in range(plen, block_size):
        buf[3+i] = 0x1A
    crc = crc16_xmodem(bytes(buf[3:3+block_size]))
    buf[-2] = (crc >> 8) & 0xFF
    buf[-1] = crc & 0xFF
    return bytes(buf)


def ymodem_empty_packet() -> bytes:
    # 0x85 length with SOH, 0 index, complement and rest zero
    buf = bytearray(0x85)
    buf[0] = 0x01
    buf[1] = 0x00
    buf[2] = _compl(0)
    return bytes(buf)


@cli.command('list')
def list_devices():
    """List available MCU USB devices."""
    for pid, label in [(PID_BOTTOM, 'bottom'), (PID_HEAD, 'head')]:
        dev = find_device(VID, pid)
        status = 'FOUND' if dev is not None else 'missing'
        print(f"{label}: VID=0x{VID:04X} PID=0x{pid:04X} -> {status}")


@cli.command()
@click.option('--target', type=click.Choice(['bottom', 'head']), default='bottom')
@click.option('--switch', 'switch_mode', type=int, default=1, help='Heartbeat switchMode (1=on)')
def heartbeat(target: str, switch_mode: int):
    """Send a heartbeat to the selected MCU."""
    pid = PID_BOTTOM if target == 'bottom' else PID_HEAD
    point_tag = POINT_BOTTOM if target == 'bottom' else POINT_HEAD
    dev = find_device(VID, pid)
    if dev is None:
        raise click.ClickException(f"Device not found: VID=0x{VID:04X} PID=0x{pid:04X}")
    eps = claim_bulk_endpoints(dev)
    datas = heartbeat_payload(switch_mode)
    frame = build_usb_frame(datas, ack_flag=1)
    # Append point tag as in app wrappers
    frame += struct.pack('B', point_tag)
    wrote = send_command(eps, frame)
    print(f"Sent heartbeat to {target} ({wrote} bytes)")


# ----- Wheel commands -----

def wheel_payload(mode: int, direction: int, *, speed: int = None,
                  deg: int = None, ms: int = None, mm: int = None,
                  is_circle: int = 0) -> bytes:
    # Mirrors WheelUSBCommand.getCommandBytes()
    # Payload: [0x01, mode, direction, ...variant...]
    datas = bytearray([0x01, mode & 0xFF, direction & 0xFF])
    if mode == 0x10:  # time-based
        if ms is None:
            raise click.ClickException('time mode (0x10) requires --ms')
        lsb_time = ms & 0xFF
        msb_time = (ms >> 8) & 0xFF
        datas += bytes([lsb_time, msb_time, is_circle & 0xFF])
    elif mode in (0x02, 0x03):  # angle-based (relative)
        if speed is None or deg is None:
            raise click.ClickException('angle mode (0x02/0x03) requires --speed and --deg')
        lsb_deg = deg & 0xFF
        msb_deg = (deg >> 8) & 0xFF
        datas += bytes([speed & 0xFF, lsb_deg, msb_deg])
    elif mode == 0x11:  # distance-based
        if speed is None or mm is None:
            raise click.ClickException('distance mode (0x11) requires --speed and --mm')
        lsb = mm & 0xFF
        msb = (mm >> 8) & 0xFF
        datas += bytes([speed & 0xFF, lsb, msb])
    else:
        raise click.ClickException(f'unsupported wheel mode: 0x{mode:02X}')
    return bytes(datas)


@cli.group()
def wheels():
    """Wheel motion helpers (angle, time, distance)."""


@wheels.command('angle')
@click.option('--dir', 'direction', type=click.Choice(['left', 'right']), required=True)
@click.option('--speed', type=int, required=True)
@click.option('--deg', type=int, required=True)
def wheels_angle(direction: str, speed: int, deg: int):
    mode = 0x02  # relative angle
    dir_code = 0x02 if direction == 'left' else 0x03
    CLI_SAFETY.wheels_angle(speed, deg)
    datas = wheel_payload(mode, dir_code, speed=speed, deg=deg)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    wrote = send_command(eps, frame)
    print(f"Wheels angle {direction} sent ({wrote} bytes)")


@wheels.command('time')
@click.option('--dir', 'direction', type=click.Choice(['forward', 'back']), required=True)
@click.option('--speed', type=int, default=100)
@click.option('--ms', type=int, required=True)
@click.option('--circle/--no-circle', default=False)
def wheels_time(direction: str, speed: int, ms: int, circle: bool):
    mode = 0x10  # time
    dir_code = 0x01 if direction == 'forward' else 0x00
    CLI_SAFETY.wheels_time(ms)
    datas = wheel_payload(mode, dir_code, ms=ms, is_circle=1 if circle else 0)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    wrote = send_command(eps, frame)
    print(f"Wheels time {direction} {ms}ms sent ({wrote} bytes)")


@wheels.command('distance')
@click.option('--dir', 'direction', type=click.Choice(['forward', 'back']), required=True)
@click.option('--speed', type=int, required=True)
@click.option('--mm', type=int, required=True)
def wheels_distance(direction: str, speed: int, mm: int):
    mode = 0x11  # distance
    dir_code = 0x01 if direction == 'forward' else 0x00
    CLI_SAFETY.wheels_distance(speed, mm)
    datas = wheel_payload(mode, dir_code, speed=speed, mm=mm)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    wrote = send_command(eps, frame)
    print(f"Wheels distance {direction} {mm}mm sent ({wrote} bytes)")


# ----- LED commands -----

def led_payload(which_light: int, switch_mode: int, rate: int = 0, random_count: int = 0) -> bytes:
    # Mirrors LEDLightCommand: [0x04, 0x02, whichLight|special, switchMode, rate, random]
    wl = which_light & 0xFF
    datas = bytearray([0x04, 0x02])
    if wl == 0x0A:
        datas.append(0x00)
    else:
        datas.append(wl)
    datas += bytes([(switch_mode & 0xFF), (rate & 0xFF), (random_count & 0xFF)])
    return bytes(datas)


def led_point_tag(which_light: int) -> int:
    # whichLight 0 -> tag 3; 4/5/0x0A -> head(1); else bottom(2)
    wl = which_light & 0xFF
    if wl == 0:
        return 0x03
    if wl in (0x04, 0x05, 0x0A):
        return POINT_HEAD
    return POINT_BOTTOM


@cli.command('led')
@click.option('--which', 'which_light', type=int, required=True, help='whichLight byte (e.g. 0=all, 4/5=head parts)')
@click.option('--mode', 'switch_mode', type=int, required=True, help='switch mode byte')
@click.option('--rate', type=int, default=0)
@click.option('--random', 'random_count', type=int, default=0)
def led_cmd(which_light: int, switch_mode: int, rate: int, random_count: int):
    datas = led_payload(which_light, switch_mode, rate, random_count)
    tag = led_point_tag(which_light)
    # Default to head device for tag==1 or 3 else bottom
    pid = PID_HEAD if tag in (POINT_HEAD, 0x03) else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"LED command sent (which=0x{which_light:02X}) ({wrote} bytes)")


# ----- Projector (image setting) -----

def projector_image_payload(control_content: int) -> bytes:
    # [0x04, 0x0A, 0x01, controlContent]
    return bytes([0x04, 0x0A, 0x01, control_content & 0xFF])


@cli.command('projector-image')
@click.option('--code', 'control_content', type=int, required=True, help='Projector image control code byte')
def projector_image(control_content: int):
    datas = projector_image_payload(control_content)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector image command sent ({wrote} bytes)")


def projector_power_payload(on: bool) -> bytes:
    # ProjectorCommand: [0x04, 0x03, switchMode]
    return bytes([0x04, 0x03, 0x01 if on else 0x00])


@cli.command('projector-power')
@click.option('--on/--off', 'switch_on', default=True)
def projector_power(switch_on: bool):
    datas = projector_power_payload(switch_on)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector power {'on' if switch_on else 'off'} sent ({wrote} bytes)")


def projector_status_payload() -> bytes:
    # QueryProjectorSwitch: [0x81, 0x18]
    return bytes([0x81 & 0xFF, 0x18])


@cli.command('projector-status')
def projector_status():
    datas = projector_status_payload()
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector status query sent ({wrote} bytes)")


@cli.command('projector-conn')
def projector_connection():
    """Query projector connection status (QueryProjectorConnection)."""
    datas = bytes([0x81 & 0xFF, 0x12])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector connection query sent ({wrote} bytes)")


@cli.group()
def upgrade():
    """MCU firmware upgrade via YMODEM (head/bottom)."""


def _upgrade_send_stream(dev_pid: int, tag: int, file_path: str, block_size: int = 1024):
    import os
    if not os.path.isfile(file_path):
        raise click.ClickException('File not found')
    fname = os.path.basename(file_path)
    fsize = os.path.getsize(file_path)
    dev = find_device(VID, dev_pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    # Step 0: broadcast upgrade command to prepare
    prep = build_usb_frame(bytes([0x04, 0x0B, 0x01])) + struct.pack('B', 0x03)
    send_command(eps, prep)
    time.sleep(0.05)
    # Step 1: send filename header
    hdr = ymodem_file_header(fname, fsize)
    frame = build_usb_frame(hdr) + struct.pack('B', tag)
    send_command(eps, frame)
    # Step 2: send data blocks
    index = 1
    sent = 0
    with open(file_path, 'rb') as f:
        while sent < fsize:
            chunk = f.read(block_size)
            if not chunk:
                break
            blk = ymodem_data_block(index, chunk, block_size)
            frame = build_usb_frame(blk) + struct.pack('B', tag)
            send_command(eps, frame)
            sent += len(chunk)
            index += 1
    # Step 3: send empty packet to finish
    fin = ymodem_empty_packet()
    frame = build_usb_frame(fin) + struct.pack('B', tag)
    send_command(eps, frame)


@upgrade.command('start')
@click.option('--target', type=click.Choice(['head', 'bottom']), required=True)
@click.option('--file', 'file_path', type=click.Path(exists=True, dir_okay=False, readable=True), required=True)
@click.option('--block', 'block_size', type=click.Choice(['128', '1024']), default='1024')
def upgrade_start(target: str, file_path: str, block_size: str):
    """Start MCU upgrade for head or bottom using YMODEM packets."""
    bsz = 128 if block_size == '128' else 1024
    if target == 'head':
        _upgrade_send_stream(PID_HEAD, POINT_HEAD, file_path, bsz)
    else:
        _upgrade_send_stream(PID_BOTTOM, POINT_BOTTOM, file_path, bsz)
    print(f"Upgrade stream sent to {target} MCU")


@upgrade.command('status')
@click.option('--type', 'up_type', type=click.Choice(['head', 'bottom']), required=True)
def upgrade_status(up_type: str):
    """Query upgrade status (head/bottom)."""
    tbyte = 0x01 if up_type == 'head' else 0x02
    datas = bytes([0x81 & 0xFF, 0x0C, 0x00, tbyte & 0xFF])
    # Route to broadcast tag 0x03 per bean
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"Upgrade status query sent ({wrote} bytes)")


@cli.command('movement-status')
@click.option('--which', 'which_part', type=int, required=True, help='which part byte')
@click.option('--status', type=int, required=True, help='status byte')
def movement_status(which_part: int, status: int):
    """Query movement status (shares 0x81/0x09 with HeadMotorAbnormal)."""
    datas = bytes([0x81 & 0xFF, 0x09, which_part & 0xFF, status & 0xFF])
    tag = POINT_HEAD if (which_part & 0xFF) in (0x04, 0x05) else POINT_BOTTOM
    pid = PID_HEAD if tag == POINT_HEAD else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Movement status query sent ({wrote} bytes)")


@cli.command('projector-quality')
@click.option('--contrast', type=int, required=True)
@click.option('--brightness', type=int, required=True)
@click.option('--chroma-u', type=int, required=True)
@click.option('--chroma-v', type=int, required=True)
@click.option('--saturation-u', type=int, required=True)
@click.option('--saturation-v', type=int, required=True)
@click.option('--acutance', type=int, required=True)
def projector_quality(contrast: int, brightness: int, chroma_u: int, chroma_v: int, saturation_u: int, saturation_v: int, acutance: int):
    # ProjectorImageQualitySetting: [0x04, 0x0A, 0x08, contrast, brightness, chroma_u, chroma_v, saturation_u, saturation_v, acutance]
    datas = bytes([0x04, 0x0A, 0x08,
                   contrast & 0xFF, brightness & 0xFF,
                   chroma_u & 0xFF, chroma_v & 0xFF,
                   saturation_u & 0xFF, saturation_v & 0xFF,
                   acutance & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector quality set ({wrote} bytes)")


@cli.command('projector-output')
@click.option('--setting', 'proj_setting', type=int, required=True, help='projectorImageSetting code')
@click.option('--h-tilt', type=int, required=True, help='horizontal trapezoid')
@click.option('--v-tilt', type=int, required=True, help='vertical trapezoid')
def projector_output(proj_setting: int, h_tilt: int, v_tilt: int):
    # ProjectorOutputSetting: [0x04, 0x0A, 0x07, projectorImageSetting, horizontalTiXing, verticalTiXing]
    datas = bytes([0x04, 0x0A, 0x07, proj_setting & 0xFF, h_tilt & 0xFF, v_tilt & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector output set ({wrote} bytes)")


@cli.command('projector-picture')
@click.option('--control', type=int, required=True, help='controlContent byte')
@click.option('--sub', 'sub_type', type=int, required=True, help='sub_type byte')
@click.option('--degree', type=int, required=True, help='degree byte')
def projector_picture(control: int, sub_type: int, degree: int):
    # ProjectorPictureSetting: [0x04, 0x0A, 0x03, controlContent, sub_type, degree]
    datas = bytes([0x04, 0x0A, 0x03, control & 0xFF, sub_type & 0xFF, degree & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector picture set ({wrote} bytes)")


@cli.command('projector-other')
@click.option('--mode', 'switch_mode', type=int, required=True)
def projector_other(switch_mode: int):
    # ProjectorOtherSetting: [0x04, 0x0A, 0x05, switchMode]
    datas = bytes([0x04, 0x0A, 0x05, switch_mode & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector other set ({wrote} bytes)")


@cli.command('projector-type')
@click.option('--type', 'proj_type', type=int, required=True)
def projector_type(proj_type: int):
    # ProjectorTypeSetting: [0x04, 0x0A, 0x06, projector_type]
    datas = bytes([0x04, 0x0A, 0x06, proj_type & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector type set ({wrote} bytes)")


# ----- Motor defend (protection) -----

def motor_defend_payload(which_part: int, enable: bool) -> bytes:
    # [0x05, 0x02, whichPart, switchMode]
    switch_mode = 0x01 if enable else 0x00
    return bytes([0x05, 0x02, which_part & 0xFF, switch_mode])


def motor_defend_point_tag(which_part: int) -> int:
    # whichPart in (1,2,3) -> head; else bottom
    return POINT_HEAD if (which_part & 0xFF) in (1, 2, 3) else POINT_BOTTOM


@cli.command('motor-defend')
@click.option('--part', 'which_part', type=int, required=True, help='whichPart byte')
@click.option('--enable/--disable', default=True)
def motor_defend(which_part: int, enable: bool):
    datas = motor_defend_payload(which_part, enable)
    tag = motor_defend_point_tag(which_part)
    pid = PID_HEAD if tag == POINT_HEAD else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Motor defend {'enable' if enable else 'disable'} sent ({wrote} bytes)")


# ----- MCU reset -----

def mcu_reset_payload(time_byte: int) -> bytes:
    # [0x04, 0x0C, 0x01, time]
    return bytes([0x04, 0x0C, 0x01, time_byte & 0xFF])


@cli.command('mcu-reset')
@click.option('--target', type=click.Choice(['bottom', 'head']), required=True)
@click.option('--time', 'time_byte', type=int, default=1, help='reset delay/time byte')
def mcu_reset(target: str, time_byte: int):
    datas = mcu_reset_payload(time_byte)
    tag = POINT_HEAD if target == 'head' else POINT_BOTTOM
    pid = PID_HEAD if target == 'head' else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"MCU reset ({target}) sent ({wrote} bytes)")


# ----- Battery query -----

def battery_query_payload(current_batt: int = -1) -> bytes:
    # [0x81, battery(1), currentBattery]
    curr = current_batt & 0xFF
    return bytes([(0x81 & 0xFF), 0x01, curr])


@cli.command('battery')
def battery_query():
    datas = battery_query_payload()
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Battery query sent ({wrote} bytes)")


@cli.command('battery-temp')
@click.option('--temp', 'temp_byte', type=int, default=0)
def battery_temperature(temp_byte: int):
    datas = bytes([0x81 & 0xFF, 0x04, temp_byte & 0xFF])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Battery temperature query sent ({wrote} bytes)")


def gyro_query_payload(accel_status: int = -1, compass_status: int = -1) -> bytes:
    # [0x81, 0x08, accelerometer_status, compass_status]
    parts = [0x81 & 0xFF, 0x08]
    if accel_status != -1:
        parts.append(accel_status & 0xFF)
    if compass_status != -1:
        parts.append(compass_status & 0xFF)
    return bytes(parts)


@cli.command('gyro')
@click.option('--accel', 'accel_status', type=int, default=-1)
@click.option('--compass', 'compass_status', type=int, default=-1)
def gyro_query(accel_status: int, compass_status: int):
    datas = gyro_query_payload(accel_status, compass_status)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Gyroscope query sent ({wrote} bytes)")


def touch_query_payload(touch_turnal: int = -1, touch_info: int = -1) -> bytes:
    # [0x81, 0x05, touchTurnal?, touchInformation?]
    parts = [0x81 & 0xFF, 0x05]
    if touch_turnal != -1:
        parts.append(touch_turnal & 0xFF)
    if touch_info != -1:
        parts.append(touch_info & 0xFF)
    return bytes(parts)


@cli.command('touch')
@click.option('--turnal', 'touch_turnal', type=int, default=-1)
@click.option('--info', 'touch_info', type=int, default=-1)
def touch_query(touch_turnal: int, touch_info: int):
    datas = touch_query_payload(touch_turnal, touch_info)
    # point tag depends on turnal; default to bottom
    tag = POINT_BOTTOM
    if touch_turnal in (1, 2, 5, 6, 11, 12, 13):
        tag = POINT_HEAD
    elif touch_turnal == 0x93:  # -0x6d as unsigned
        tag = 0x03
    pid = PID_HEAD if tag in (POINT_HEAD, 0x03) else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Touch query sent ({wrote} bytes)")


@cli.command('pir')
@click.option('--type', 'pir_type', type=int, default=-1)
@click.option('--status', 'pir_status', type=int, default=-1)
def pir_query(pir_type: int, pir_status: int):
    parts = [0x81 & 0xFF, 0x06]
    if pir_type != -1:
        parts.append(pir_type & 0xFF)
    if pir_status != -1:
        parts.append(pir_status & 0xFF)
    datas = bytes(parts)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"PIR query sent ({wrote} bytes)")


@cli.command('obstacle')
@click.option('--dir', 'direction', type=int, default=-1)
@click.option('--dist', 'distance', type=int, default=-1)
def obstacle_query(direction: int, distance: int):
    parts = [0x81 & 0xFF, 0x02]
    if direction != -1:
        parts.append(direction & 0xFF)
    if distance != -1:
        parts.append(distance & 0xFF)
    datas = bytes(parts)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Obstacle query sent ({wrote} bytes)")


@cli.command('button')
def button_status():
    datas = bytes([0x81 & 0xFF, 0x17])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Button status query sent ({wrote} bytes)")


@cli.command('work-status')
def work_status():
    # QueryWorkStatus: [0x81, 0x22], tag 0x03
    datas = bytes([0x81 & 0xFF, 0x22])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"Work status query sent ({wrote} bytes)")


@cli.command('encoder-status')
def encoder_status():
    # BottomEncoderConnection: [0x81, 0x15], tag bottom
    datas = bytes([0x81 & 0xFF, 0x15])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Bottom encoder status query sent ({wrote} bytes)")


@cli.command('mcu-version')
def mcu_version():
    # QueryMCUVersion: [0x81, 0x0D]
    datas = bytes([0x81 & 0xFF, 0x0D])
    # version likely per MCU; query both
    for target, pid, tag in [('head', PID_HEAD, POINT_HEAD), ('bottom', PID_BOTTOM, POINT_BOTTOM)]:
        dev = find_device(VID, pid) or click.Abort()
        eps = claim_bulk_endpoints(dev)
        frame = build_usb_frame(datas) + struct.pack('B', tag)
        wrote = send_command(eps, frame)
        print(f"MCU version query sent to {target} ({wrote} bytes)")


@cli.command('head-motor-abnormal')
@click.option('--which', 'which_part', type=int, required=True, help='which_part byte (e.g., 4/5=head)')
@click.option('--status', type=int, required=True, help='status byte')
def head_motor_abnormal(which_part: int, status: int):
    # HeadMotorAbnormal: [0x81, 0x09, which_part, status]; tag head if which_part in {4,5} else bottom
    datas = bytes([0x81 & 0xFF, 0x09, which_part & 0xFF, status & 0xFF])
    tag = POINT_HEAD if (which_part & 0xFF) in (0x04, 0x05) else POINT_BOTTOM
    pid = PID_HEAD if tag == POINT_HEAD else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Head motor abnormal query sent ({wrote} bytes)")


@cli.command('photocoupler-abnormal')
@click.option('--which', 'which_part', type=int, required=True, help='whichPart byte (1/2=head else bottom)')
def photocoupler_abnormal(which_part: int):
    # PhotoelectricAbnormal: [0x81, 0x19, whichPart]
    datas = bytes([0x81 & 0xFF, 0x19, which_part & 0xFF])
    tag = POINT_HEAD if (which_part & 0xFF) in (0x01, 0x02) else POINT_BOTTOM
    pid = PID_HEAD if tag == POINT_HEAD else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Photoelectric abnormal query sent ({wrote} bytes)")


@cli.command('detect-3d')
@click.option('--distance', type=int, default=0, help='distance parameter (byte)')
def detect_3d(distance: int):
    # Detect3DData: [0x82, 0x03, 0x01, distance], tag bottom
    datas = bytes([0x82 & 0xFF, 0x03, 0x01, distance & 0xFF])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"3D detect query sent ({wrote} bytes)")


@cli.command('expression-status')
def expression_status():
    # QueryExpressionStatus: [0x81, 0x1C], tag head
    datas = bytes([0x81 & 0xFF, 0x1C])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Expression status query sent ({wrote} bytes)")


@cli.command('dance')
@click.option('--enable/--disable', 'enable', default=True)
def dance(enable: bool):
    # DanceCommand: [0x04, 0x06, switchMode], tag 0x03
    datas = bytes([0x04, 0x06, 0x01 if enable else 0x00])
    # routes to 0x03 per bean
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"Dance {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('projector-expert')
@click.option('--adjust', 'adjust_mode', type=int, required=True)
@click.option('--ctrl-mode', 'control_mode', type=int, required=True)
@click.option('--ctrl-content', 'control_content', type=int, required=True)
def projector_expert(adjust_mode: int, control_mode: int, control_content: int):
    # ProjectorExpertMode: [0x04, 0x0A, 0x04, adjustMode, controlMode, controlContent]
    datas = bytes([0x04, 0x0A, 0x04, adjust_mode & 0xFF, control_mode & 0xFF, control_content & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Projector expert set ({wrote} bytes)")


@cli.command('recover-position')
@click.option('--mode', 'switch_mode', type=int, default=1, help='switch_mode (default 1)')
def body_recover(switch_mode: int):
    """Reset body/head/arms to neutral (BodyRecover)."""
    # BodyRecover: [0x04, 0x18, switch_mode], point tag = 0x01 (head) per bean
    datas = bytes([0x04, 0x18, switch_mode & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Body recover command sent ({wrote} bytes)")


@cli.command('expression-normal')
@click.option('--type', 'expression_type', type=int, required=True)
def expression_normal(expression_type: int):
    # LiliNormalExpression: [0x06, 0x01, expression_type], tag head
    datas = bytes([0x06, 0x01, expression_type & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Expression normal set ({wrote} bytes)")


@cli.command('expression-version')
@click.option('--hex', 'hexbytes', type=str, required=True, help='hex string of version bytes, e.g., 010203')
def expression_version(hexbytes: str):
    # SetExpressionVersion: [0x04, 0x11] + version bytes, tag head
    try:
        ver = bytes.fromhex(hexbytes)
    except ValueError:
        raise click.ClickException('Invalid hex string')
    prefix = bytes([0x04, 0x11])
    datas = prefix + ver
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Expression version set ({wrote} bytes)")


@cli.command('expression-version-query')
def expression_version_query():
    """Query expression version (QueryExpressionVersion)."""
    datas = bytes([0x81 & 0xFF, 0x1B])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Expression version query sent ({wrote} bytes)")


@cli.command('zigbee-send')
@click.option('--hex', 'hexbytes', type=str, required=True, help='raw ZigBee payload (hex, without 0xA0)')
def zigbee_send(hexbytes: str):
    """Send raw ZigBee data via ZigbeeCommand wrapper (routes to head)."""
    try:
        payload = bytes.fromhex(hexbytes)
    except ValueError:
        raise click.ClickException('Invalid hex string')
    datas = bytes([0xA0]) + payload
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas, ack_flag=0) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"ZigBee data sent ({wrote} bytes)")


@cli.group()
def zigbee():
    """ZigBee helpers (via ZigbeeCommand)."""


def _zigbee_send_json(s: str):
    datas = bytes([0xA0]) + s.encode('utf-8')
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas, ack_flag=0) + struct.pack('B', POINT_HEAD)
    return send_command(eps, frame)


@zigbee.command('send-json')
@click.option('--json', 'json_str', type=str, required=True, help='JSON payload to send to ZigBee module')
def zigbee_send_json(json_str: str):
    wrote = _zigbee_send_json(json_str)
    print(f"ZigBee JSON sent ({wrote} bytes)")


@zigbee.command('allow-join')
@click.option('--time', 'seconds', type=int, required=True, help='Allow-join duration in seconds')
def zigbee_allow_join(seconds: int):
    wrote = _zigbee_send_json('{"time":%d}' % seconds)
    print(f"ZigBee allow-join for {seconds}s ({wrote} bytes)")


@zigbee.command('switch-whitelist')
@click.option('--on/--off', 'on', default=True)
def zigbee_switch_whitelist(on: bool):
    wrote = _zigbee_send_json('{"switch":%d}' % (1 if on else 0))
    print(f"ZigBee whitelist switch set to {'on' if on else 'off'} ({wrote} bytes)")


@zigbee.command('add-whitelist')
@click.option('--id', 'device_id', type=str, required=True)
def zigbee_add_whitelist(device_id: str):
    wrote = _zigbee_send_json('{"id":"%s"}' % device_id)
    print(f"ZigBee add whitelist id={device_id} ({wrote} bytes)")


@zigbee.command('delete-whitelist')
@click.option('--id', 'device_id', type=str, required=True)
def zigbee_delete_whitelist(device_id: str):
    wrote = _zigbee_send_json('{"id":"%s"}' % device_id)
    print(f"ZigBee delete whitelist id={device_id} ({wrote} bytes)")


@zigbee.command('clear-whitelist')
def zigbee_clear_whitelist():
    wrote = _zigbee_send_json('{}')
    print(f"ZigBee clear whitelist ({wrote} bytes)")


@zigbee.command('remove-device')
@click.option('--id', 'device_id', type=str, required=True)
def zigbee_remove_device(device_id: str):
    wrote = _zigbee_send_json('{"id":"%s"}' % device_id)
    print(f"ZigBee remove device id={device_id} ({wrote} bytes)")


@zigbee.command('get-whitelist')
def zigbee_get_whitelist():
    wrote = _zigbee_send_json('{}')
    print(f"ZigBee get whitelist ({wrote} bytes)")


@zigbee.command('get-list')
def zigbee_get_list():
    wrote = _zigbee_send_json('{}')
    print(f"ZigBee get device list ({wrote} bytes)")


@cli.command('ir-sender')
def ir_sender():
    # QueryIRSender: [0x81, 0x16], tag 0x03
    datas = bytes([0x81 & 0xFF, 0x16])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"IR sender query sent ({wrote} bytes)")


@cli.command('ir-receive-status')
def ir_receive_status():
    """Query IR receive status (QueryIRReceiveStatus)."""
    datas = bytes([0x81 & 0xFF, 0x0B])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"IR receive status query sent ({wrote} bytes)")


@cli.command('ir-sensor')
@click.option('--content', 'sensor_content', type=int, default=-1)
@click.option('--info', 'sensor_info', type=int, default=-1)
def ir_sensor(sensor_content: int, sensor_info: int):
    """IR sensor command (IRSensor): advanced; sends content/info bytes if provided."""
    parts = [0x83 & 0xFF, 0x81 & 0xFF, 0x02]
    if sensor_content != -1:
        parts.append(sensor_content & 0xFF)
    if sensor_info != -1:
        parts.append(sensor_info & 0xFF)
    datas = bytes(parts)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    # default to broadcast 0x03 per many sensor queries
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"IR sensor command sent ({wrote} bytes)")


@cli.command('uart-status')
def uart_status():
    # QueryUARTConnection: [0x81, 0x13], tag 0x03
    datas = bytes([0x81 & 0xFF, 0x13])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"UART connection status query sent ({wrote} bytes)")


@cli.command('spi-flash-status')
def spi_flash_status():
    """Query SPI flash status (QuerySPIFLASHStatus)."""
    datas = bytes([0x81 & 0xFF, 0x14])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"SPI flash status query sent ({wrote} bytes)")


@cli.command('hide-cat-status')
@click.option('--retain', type=int, default=-1)
@click.option('--status', type=int, default=-1)
def hide_cat_status(retain: int, status: int):
    """Query hide-cat (hide-and-seek) status (QueryHideCatStatus)."""
    parts = [0x81 & 0xFF, 0x1A]
    if retain != -1:
        parts.append(retain & 0xFF)
    if status != -1:
        parts.append(status & 0xFF)
    datas = bytes(parts)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Hide-cat status query sent ({wrote} bytes)")


@cli.command('hide-obstacle-status')
@click.option('--which', type=int, default=-1)
@click.option('--status', type=int, default=-1)
def hide_obstacle_status(which: int, status: int):
    """Query hide-obstacle status (QueryHideObstacleStatus)."""
    parts = [0x81 & 0xFF, 0x0A]
    if which != -1:
        parts.append(which & 0xFF)
    if status != -1:
        parts.append(status & 0xFF)
    datas = bytes(parts)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Hide-obstacle status query sent ({wrote} bytes)")


@cli.command('photoelectric-switch')
@click.option('--retain', 'retain_data', type=int, default=1, help='retain byte (default 1)')
def photoelectric_switch(retain_data: int):
    """Query photoelectric switch status (QueryPhotoelectricSwitch)."""
    # [0x81, 0x11, retain]
    datas = bytes([0x81 & 0xFF, 0x11, retain_data & 0xFF])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"Photoelectric switch query sent ({wrote} bytes)")


@cli.command('optocoupler-status')
@click.option('--which', 'which_part', type=int, required=True, help='whichPart (3/4=head else bottom)')
def optocoupler_status(which_part: int):
    """Query optocoupler status (QueryOptocouplerStatus)."""
    datas = bytes([0x81 & 0xFF, 0x12, which_part & 0xFF])
    tag = POINT_HEAD if (which_part & 0xFF) in (0x03, 0x04) else POINT_BOTTOM
    pid = PID_HEAD if tag == POINT_HEAD else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Optocoupler status query sent ({wrote} bytes)")


@cli.command('white-light')
@click.option('--level', type=int, required=True, help='0-100 or device-specific scale')
def white_light(level: int):
    # SetWhiteBrightness uses setWhiteBrightness=0x02 and brightness param
    datas = bytes([0x04, 0x01, 0x02, level & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"White light level set ({wrote} bytes)")


@cli.command('speaker')
@click.option('--enable/--disable', 'enable', default=True)
def speaker(enable: bool):
    """Toggle speaker (beep) switch."""
    datas = bytes([0x04, 0x04, 0x01 if enable else 0x00])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Speaker {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('black-shield')
@click.option('--enable/--disable', 'enable', default=True)
def black_shield(enable: bool):
    # [0x04, 0x0D, switch_mode]
    datas = bytes([0x04, 0x0D, 0x01 if enable else 0x00])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Black shield {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('follow')
@click.option('--enable/--disable', 'enable', default=True)
def follow_switch(enable: bool):
    # [0x04, 0x0E, switch]
    datas = bytes([0x04, 0x0E, 0x01 if enable else 0x00])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Follow {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('wander')
@click.option('--enable/--disable', 'enable', default=True)
@click.option('--type', 'wander_type', type=int, default=1)
def wander_switch(enable: bool, wander_type: int):
    # [0x04, 0x09, switchMode, type]
    datas = bytes([0x04, 0x09, 0x01 if enable else 0x00, wander_type & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Wander {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('auto-charge')
@click.option('--enable/--disable', 'enable', default=True)
@click.option('--threshold', type=int, default=None, help='optional threshold byte')
def auto_charge(enable: bool, threshold: int | None):
    """Toggle auto-charge mode (AutoBatteryCommand)."""
    parts = [0x04, 0x05, 0x01 if enable else 0x00]
    if threshold is not None:
        parts.append(threshold & 0xFF)
    datas = bytes(parts)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Auto-charge {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('motor-lock')
@click.option('--which', 'which_part', type=int, required=True, help='whichPart (1=head_h,2=head_v,3=head_all, else bottom)')
@click.option('--enable/--disable', 'enable', default=True)
def motor_lock(which_part: int, enable: bool):
    """Lock/unlock motors (MotorLockSetting)."""
    # [0x05, 0x01, whichPart, switchMode]
    datas = bytes([0x05, 0x01, which_part & 0xFF, (0x01 if enable else 0x00)])
    tag = POINT_HEAD if (which_part & 0xFF) in (0x01, 0x02, 0x03) else POINT_BOTTOM
    pid = PID_HEAD if tag == POINT_HEAD else PID_BOTTOM
    dev = find_device(VID, pid) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', tag)
    wrote = send_command(eps, frame)
    print(f"Motor lock {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('charge-pile')
@click.option('--hex', 'hexbytes', type=str, required=True, help='raw payload bytes (without 0xA1), hex string')
def charge_pile(hexbytes: str):
    """Operate charge pile (raw ChangePileCommand payload). Advanced use."""
    try:
        payload = bytes.fromhex(hexbytes)
    except ValueError:
        raise click.ClickException('Invalid hex string')
    # ChangePileCommand prepends 0xA1 (-0x5f)
    datas = bytes([0xA1]) + payload
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Charge pile op sent ({wrote} bytes)")


@cli.command('hide-mode')
@click.option('--enable/--disable', 'enable', default=True)
def hide_mode(enable: bool):
    # [0x04, 0x0F, switchMode]
    datas = bytes([0x04, 0x0F, 0x01 if enable else 0x00])
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Hide mode {'enabled' if enable else 'disabled'} ({wrote} bytes)")


@cli.command('voice-location')
@click.option('--hdeg', type=int, required=True)
@click.option('--vdeg', type=int, required=True)
def voice_location(hdeg: int, vdeg: int):
    # VoiceLocation: [0x82, 0x02, hLSB, hMSB, vLSB, vMSB]
    datas = bytes([0x82 & 0xFF, 0x02,
                   hdeg & 0xFF, (hdeg >> 8) & 0xFF,
                   vdeg & 0xFF, (vdeg >> 8) & 0xFF])
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Voice location command sent ({wrote} bytes)")


@cli.command('auto-report')
@click.option('--mode', 'switch_mode', type=int, required=True, help='0/1')
def auto_report(switch_mode: int):
    """Toggle MCU auto-reporting (AutoReportCommand)."""
    datas = bytes([0x80 & 0xFF, switch_mode & 0xFF])
    # Route to 0x03 (broadcast group)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', 0x03)
    wrote = send_command(eps, frame)
    print(f"Auto-report set to {switch_mode} ({wrote} bytes)")


# ----- Head motion -----

def head_payload(mode: int, direction: int, **kwargs) -> bytes:
    # Mirrors HeadUSBCommand: [0x02, moveHeadMode, moveHeadDirection, ...variant...]
    datas = bytearray([0x02, mode & 0xFF, direction & 0xFF])
    if mode == 0x10:  # time
        lsb = (kwargs.get('ms', 0)) & 0xFF
        msb = ((kwargs.get('ms', 0)) >> 8) & 0xFF
        deg_or_flag = kwargs.get('deg_or_flag', 0) & 0xFF
        datas += bytes([lsb, msb, deg_or_flag])
    elif mode in (0x02, 0x03):  # angle on one axis
        speed = kwargs.get('speed')
        deg = kwargs.get('deg')
        if speed is None or deg is None:
            raise click.ClickException('head mode 0x02/0x03 requires --speed and --deg')
        datas += bytes([speed & 0xFF, (deg & 0xFF), ((deg >> 8) & 0xFF)])
    elif mode == 0x21:  # absolute H/V
        h = kwargs.get('hdeg', 0)
        v = kwargs.get('vdeg', 0)
        datas += bytes([(h & 0xFF), ((h >> 8) & 0xFF), (v & 0xFF), ((v >> 8) & 0xFF)])
    elif mode == 0x22:  # relative H/V
        hdir = kwargs.get('hdir', 0) & 0xFF
        hdeg = kwargs.get('hdeg', 0) & 0xFF
        vdir = kwargs.get('vdir', 0) & 0xFF
        vdeg = kwargs.get('vdeg', 0) & 0xFF
        datas += bytes([hdir, hdeg, vdir, vdeg])
    elif mode == 0x01:  # no-angle
        speed = kwargs.get('speed', 0) & 0xFF
        datas += bytes([speed])
    else:
        raise click.ClickException(f'unsupported head mode: 0x{mode:02X}')
    return bytes(datas)


@cli.group()
def head():
    """Head motion helpers (absolute/relative/time/noangle)."""


@head.command('absolute')
@click.option('--hdeg', type=int, required=True, help='horizontal degrees (0-360 or device range)')
@click.option('--vdeg', type=int, required=True, help='vertical degrees')
def head_absolute(hdeg: int, vdeg: int):
    _assert_range('hdeg', hdeg, -180, 180)
    _assert_range('vdeg', vdeg, -90, 90)
    CLI_SAFETY.head_absolute(hdeg, vdeg)
    datas = head_payload(0x21, 0x00, hdeg=hdeg, vdeg=vdeg)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Head absolute sent ({wrote} bytes)")


@head.command('relative')
@click.option('--hdir', type=int, required=True, help='horizontal direction code')
@click.option('--hdeg', type=int, required=True, help='horizontal degrees')
@click.option('--vdir', type=int, required=True, help='vertical direction code')
@click.option('--vdeg', type=int, required=True, help='vertical degrees')
def head_relative(hdir: int, hdeg: int, vdir: int, vdeg: int):
    datas = head_payload(0x22, 0x00, hdir=hdir, hdeg=hdeg, vdir=vdir, vdeg=vdeg)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Head relative sent ({wrote} bytes)")


@head.command('angle')
@click.option('--axis', type=click.Choice(['h', 'v']), required=True, help='axis: h=0x02, v=0x03')
@click.option('--dir', 'direction', type=int, required=True, help='direction code')
@click.option('--speed', type=int, required=True)
@click.option('--deg', type=int, required=True)
def head_angle(axis: str, direction: int, speed: int, deg: int):
    _assert_range('speed', speed, 0, 255)
    _assert_range('deg', deg, 0, 90)
    CLI_SAFETY.head_axis(speed, deg)
    mode = 0x02 if axis == 'h' else 0x03
    datas = head_payload(mode, direction, speed=speed, deg=deg)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Head angle sent ({wrote} bytes)")


@head.command('time')
@click.option('--dir', 'direction', type=int, required=True, help='direction code')
@click.option('--ms', type=int, required=True)
@click.option('--flag', 'deg_or_flag', type=int, default=0)
def head_time(direction: int, ms: int, deg_or_flag: int):
    _assert_range('ms', ms, 1, 600000)
    CLI_SAFETY.head_time(ms)
    datas = head_payload(0x10, direction, ms=ms, deg_or_flag=deg_or_flag)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Head time sent ({wrote} bytes)")


@head.command('noangle')
@click.option('--dir', 'direction', type=int, required=True)
@click.option('--speed', type=int, required=True)
def head_noangle(direction: int, speed: int):
    _assert_range('speed', speed, 0, 255)
    CLI_SAFETY.head_noangle(speed)
    datas = head_payload(0x01, direction, speed=speed)
    dev = find_device(VID, PID_HEAD) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_HEAD)
    wrote = send_command(eps, frame)
    print(f"Head no-angle sent ({wrote} bytes)")


# ----- Hand/arm motion -----

def hand_payload(mode: int, which: int, **kwargs) -> bytes:
    # Mirrors HandUSBCommand: [0x03, moveHandMode, whichHand, ...variant...]
    datas = bytearray([0x03, mode & 0xFF, which & 0xFF])
    if mode == 0x10:  # time
        lsb = (kwargs.get('ms', 0)) & 0xFF
        msb = ((kwargs.get('ms', 0)) >> 8) & 0xFF
        deg_lsb = (kwargs.get('deg', 0)) & 0xFF
        deg_msb = ((kwargs.get('deg', 0)) >> 8) & 0xFF
        datas += bytes([lsb, msb, deg_lsb, deg_msb])
    elif mode in (0x02, 0x03):  # angle
        speed = kwargs.get('speed')
        direction = kwargs.get('direction')
        deg = kwargs.get('deg')
        if speed is None or direction is None or deg is None:
            raise click.ClickException('hand mode 0x02/0x03 requires --speed --direction --deg')
        datas += bytes([speed & 0xFF, direction & 0xFF, (deg & 0xFF), ((deg >> 8) & 0xFF)])
    elif mode == 0x01:  # no-angle
        speed = kwargs.get('speed')
        direction = kwargs.get('direction')
        if speed is None or direction is None:
            raise click.ClickException('hand mode 0x01 requires --speed --direction')
        datas += bytes([speed & 0xFF, direction & 0xFF])
    else:
        raise click.ClickException(f'unsupported hand mode: 0x{mode:02X}')
    return bytes(datas)


@cli.group()
def hand():
    """Hand/arm motion helpers."""


@hand.command('angle')
@click.option('--which', type=int, required=True, help='which hand: 0=both,1=left,2=right (typical)')
@click.option('--mode', type=int, default=0x02, show_default=True, help='angle mode (0x02 or 0x03 depending on axis)')
@click.option('--direction', '--dir', 'direction', type=int, required=True, help='direction code')
@click.option('--speed', type=int, required=True)
@click.option('--deg', type=int, required=True)
def hand_angle(which: int, mode: int, direction: int, speed: int, deg: int):
    _assert_in('which', which, (0, 1, 2))
    _assert_range('speed', speed, 0, 255)
    _assert_range('deg', deg, 0, 90)
    CLI_SAFETY.hand_angle(speed, deg)
    datas = hand_payload(mode, which, direction=direction, speed=speed, deg=deg)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Hand angle sent ({wrote} bytes)")


@hand.command('time')
@click.option('--which', type=int, required=True)
@click.option('--ms', type=int, required=True)
@click.option('--deg', type=int, default=0)
def hand_time(which: int, ms: int, deg: int):
    _assert_in('which', which, (0, 1, 2))
    _assert_range('ms', ms, 1, 600000)
    _assert_range('deg', deg, 0, 90)
    CLI_SAFETY.hand_time(ms, deg)
    datas = hand_payload(0x10, which, ms=ms, deg=deg)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Hand time sent ({wrote} bytes)")


@hand.command('noangle')
@click.option('--which', type=int, required=True)
@click.option('--direction', type=int, required=True)
@click.option('--speed', type=int, required=True)
def hand_noangle(which: int, direction: int, speed: int):
    _assert_in('which', which, (0, 1, 2))
    _assert_range('speed', speed, 0, 255)
    CLI_SAFETY.hand_noangle(speed)
    datas = hand_payload(0x01, which, direction=direction, speed=speed)
    dev = find_device(VID, PID_BOTTOM) or click.Abort()
    eps = claim_bulk_endpoints(dev)
    frame = build_usb_frame(datas) + struct.pack('B', POINT_BOTTOM)
    wrote = send_command(eps, frame)
    print(f"Hand no-angle sent ({wrote} bytes)")


# ----- Listener for inbound frames -----

def parse_usb_frame(buf: bytes):
    # Minimal parser for frames built by USBCommand on device side
    if len(buf) < 16:
        return None
    type_short = struct.unpack('>h', buf[0:2])[0]
    subtype = struct.unpack('>h', buf[2:4])[0]
    content_len = struct.unpack('>I', buf[4:8])[0]
    ack0 = buf[8]
    # buf[9:16] unuse
    total_len = 16 + content_len
    if len(buf) < total_len:
        return None
    frame_head = struct.unpack('>h', buf[16:18])[0]
    ack1 = buf[18]
    mmnn = struct.unpack('>h', buf[19:21])[0]
    datas = buf[21: total_len - 1]
    checksum = buf[total_len - 1]
    return {
        'type': type_short & 0xFFFF,
        'subtype': subtype & 0xFFFF,
        'content_len': content_len,
        'ack0': ack0,
        'frame_head': frame_head & 0xFFFF,
        'ack1': ack1,
        'mmnn': mmnn & 0xFFFF,
        'datas': datas,
        'checksum': checksum,
        'total_len': total_len,
    }


def _maybe_auto_read(eps: USBEndpoints, *, label: str | None = None, timeout_ms: int = CLI_READ_TIMEOUT_MS) -> None:
    if eps.ep_in is None:
        return
    timeout = max(1, timeout_ms)
    try:
        data = eps.ep_in.read(eps.ep_in.wMaxPacketSize, timeout)
    except usb.core.USBError as exc:  # type: ignore[attr-defined]
        err_no = getattr(exc, 'errno', None)
        if err_no in (errno.ETIMEDOUT, errno.EAGAIN, 110, 60):
            return
        LOG.debug("USB auto-read error: %s", exc)
        return
    except Exception as exc:  # pragma: no cover - defensive
        LOG.debug("USB auto-read unexpected error: %s", exc)
        return
    payload = bytes(data)
    if not payload:
        return
    prefix = label or "response"
    print(f"<- {prefix}: len={len(payload)} hex={payload.hex()}")
    parsed = parse_usb_frame(payload)
    if parsed and parsed.get('datas'):
        decoded = _decode_known_datas(parsed['datas'])
        if decoded:
            print(f"   decoded: {decoded}")


class HeartbeatManager:
    def __init__(self):
        self.enabled = False
        self.head_enabled = False
        self.interval_ms = 1500
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def configure(self, *, enabled: bool, interval_ms: int, head_enabled: bool) -> None:
        self.enabled = enabled
        self.head_enabled = head_enabled
        self.interval_ms = max(100, interval_ms)
        if enabled:
            self.start()
        else:
            self.stop()

    def start(self) -> None:
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="sanbot-heartbeat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_ms / 1000.0):
            self._heartbeat_cycle('bottom', PID_BOTTOM, POINT_BOTTOM)
            if self.head_enabled:
                self._heartbeat_cycle('head', PID_HEAD, POINT_HEAD)

    def _heartbeat_cycle(self, label: str, pid: int, point_tag: int) -> None:
        dev = find_device(VID, pid)
        if dev is None:
            return
        eps = None
        try:
            eps = claim_bulk_endpoints(dev)
            datas = heartbeat_payload()
            frame = build_usb_frame(datas, ack_flag=1) + struct.pack('B', point_tag)
            send_command(eps, frame, label=f'heartbeat-{label}', expect_response=False)
        except click.ClickException as exc:
            LOG.debug("Heartbeat %s skipped: %s", label, exc)
        except Exception as exc:  # pragma: no cover - defensive
            LOG.debug("Heartbeat %s unexpected error: %s", label, exc)
        finally:
            release_endpoints(eps)


HEARTBEAT_MANAGER = HeartbeatManager()
atexit.register(HEARTBEAT_MANAGER.stop)


@cli.command('listen')
@click.option('--target', type=click.Choice(['bottom', 'head']), default='bottom')
@click.option('--timeout', type=int, default=1000, help='read timeout ms')
@click.option('--verbose', is_flag=True, help='verbose/decoded output')
def listen(target: str, timeout: int, verbose: bool):
    pid = PID_BOTTOM if target == 'bottom' else PID_HEAD
    buf = bytearray()
    print(f"Listening on {target} MCU (Ctrl-C to stop)...")
    while True:
        dev = find_device(VID, pid)
        if dev is None:
            time.sleep(0.5)
            continue
        eps = None
        try:
            eps = claim_bulk_endpoints(dev)
            chunk = eps.ep_in.read(eps.ep_in.wMaxPacketSize, timeout)
            if chunk:
                buf.extend(bytearray(chunk))
                # Try to parse frames greedily
                while True:
                    if len(buf) < 16:
                        break
                    parsed = parse_usb_frame(buf)
                    if not parsed:
                        # discard one byte to resync if header mismatches
                        buf.pop(0)
                        continue
                    frame_bytes = bytes(buf[:parsed['total_len']])
                    del buf[:parsed['total_len']]
                    if verbose:
                        dec = _decode_known_datas(parsed['datas'])
                        if dec:
                            print(f"<- type=0x{parsed['type']:04X} sub=0x{parsed['subtype']:04X} mmnn={parsed['mmnn']} ack={parsed['ack1']} len={len(parsed['datas'])}")
                            print(f"   {dec['name']}: {dec['fields']}")
                        else:
                            print(f"<- type=0x{parsed['type']:04X} sub=0x{parsed['subtype']:04X} mmnn={parsed['mmnn']} ack={parsed['ack1']} len={len(parsed['datas'])}")
                            print(f"   data: {parsed['datas'].hex()}")
                    else:
                        print(f"<- type=0x{parsed['type']:04X} sub=0x{parsed['subtype']:04X} len={len(parsed['datas'])} data={parsed['datas'].hex()}")
            else:
                time.sleep(0.01)
        except KeyboardInterrupt:
            break
        except usb.core.USBTimeoutError:
            continue
        except Exception as e:
            LOG.warning("listen read error on %s: %s", target, e)
            time.sleep(0.2)
        finally:
            release_endpoints(eps)

if __name__ == '__main__':
    cli()
