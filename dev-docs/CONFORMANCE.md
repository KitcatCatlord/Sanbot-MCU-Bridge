# Sanbot MCU Library — Conformance Notes (T033)

This document cross‑checks the library/CLI coverage against the stock app’s
MCU beans and highlights any caveats or differences. It also notes bug fixes
applied during implementation.

## Coverage Summary

- Transport & Framing
  - USB frame matches `USBCommand` (type/subtype/msg_size/ack/unuse/frame_head/ack/mmnn/datas/checksum + trailing point_tag).
  - VID/PIDs and endpoint selection mirror `UsbMessageMrg`.

- Commands (Outbound)
  - Heartbeat: 0x04/0x08 — implemented.
  - Wheels: angle(0x02), time(0x10), distance(0x11) — implemented.
  - Head: absolute(0x21), relative(0x22), angle(0x02/0x03), time(0x10), no‑angle(0x01) — implemented.
  - Hands: angle(0x02/0x03), time(0x10), no‑angle(0x01) — implemented.
  - LEDs: LEDLightCommand 0x04/0x02 — implemented (which->point tag mapping included).
  - Projector: power/status/connection, quality/output/picture/other/type/expert — implemented.
  - System: motor_defend, motor_lock, white_light, black_shield, follow, wander, hide_mode, dance, speaker, body_recover — implemented.
  - Sensors/Queries: battery/temperature, button, obstacle/hide‑obstacle, PIR, gyro,
    bottom encoder, UART connection, 3D detect, expression version/status — implemented.
  - ZigBee: raw and JSON helpers — implemented (ack=0 path as in app).
  - MCU upgrade: YMODEM header/data/empty with pre‑upgrade command — implemented.

- Listener/Decoders (Inbound)
  - Added labeled decoders for obstacle/PIR/touch/gyro and improved button.
  - Decodes projector status, version queries, private peripheral frames (charge pile/telecontrol),
    auto‑report, work status, IR sensor/receive, etc.

## Deviations and Heuristics

- Touch part_name is inferred from usage in `MainService.doTouch` and related code.
- PIR sensor layout varies by device batch; decoder includes both raw list and
  best‑effort mapping when lengths match common patterns (3 or 6 values).
- Work status (0x81/0x22) fields are presented as raw bytes with tentative names.
- Some projector picture/other/type subcodes are device‑specific; library exposes raw setters.

## Bug Fixes vs Decompiled Logic

- Fixed nested conditional causing private peripheral decode (0xFF 0xA6) to be unreachable.
- Added explicit photoelectric switch decoder (0x81/0x11) and corrected hide‑obstacle naming.
- Removed stray dead code after `listen()` loop.

## Potential Missing Minor Items

- Additional private peripheral subtypes (vendor‑specific) beyond charge pile/telecontrol
  are forwarded as `private_peripheral` with raw bytes.
- Head/hand direction codes are device constants; the library passes through integers and documents usage.

If you spot any commands seen in smali under `tools/decompiled` not represented in
`toolbox/mcu_bridge/usb_bridge.py` or `toolbox/mcu_bridge/lib/bridge.py`, please open an issue
with the smali path and a short description; we’ll add it swiftly.

