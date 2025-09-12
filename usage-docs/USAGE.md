# MCU Manager CLI Usage (Installed Package)

This guide shows how to control Sanbot MCUs directly over USB from the CLI. It
mirrors the stock Android service behaviour and command framing extracted from
the firmware.

Devices:
- Bottom MCU (drive, many sensors): VID 0x0483, PID 0x5740, point_tag 0x02
- Head MCU (head, projector, some LEDs): VID 0x0483, PID 0x5741, point_tag 0x01

General framing:
- USB packet is built per `USBCommand` (see repo docs), then one trailing
  point_tag byte is appended.

Note: This usage document is bundled with the wheel for convenience. Full
protocol docs live in the source repository.

## Setup

```
pip install sanbot-mcu-bridge
sanbot-usb --help
```

List devices:
```
sanbot-usb list
```

Global options (apply to all commands):
```
--log-level DEBUG|INFO|WARNING|ERROR|CRITICAL   # default WARNING
--retries N                                      # USB write retries (default 1)
--unsafe                                         # bypass safety checks (not recommended)
```

Send heartbeat:
```
sanbot-usb heartbeat --target bottom --switch 1
```

## Wheels

- Angle (relative rotation) — mode 0x02
```
sanbot-usb wheels angle --dir left --speed 100 --deg 90
sanbot-usb wheels angle --dir right --speed 100 --deg 180
```

- Time (drive for duration) — mode 0x10
```
sanbot-usb wheels time --dir forward --speed 100 --ms 1500 --no-circle
sanbot-usb wheels time --dir back --speed 80 --ms 800
```

- Distance (drive for mm) — mode 0x11
```
sanbot-usb wheels distance --dir forward --speed 120 --mm 500
```

Notes:
- Wheel rotations use direction codes 0x02 (left) and 0x03 (right);
  forward/back map to 0x01/0x00. Degrees, milliseconds, and millimeters are
  encoded LSB/MSB within payloads.

## LEDs

Command layout (LEDLightCommand): `[0x04, 0x02, whichLight|special, switchMode, rate, random]`.

Examples:
```
sanbot-usb led --which 0 --mode 0x02 --rate 5  # broadcast
sanbot-usb led --which 4 --mode 0x13           # head LEDs
```

## Projector (Image Settings)

```
sanbot-usb projector-image --code 0x05
sanbot-usb projector-power --on
sanbot-usb projector-status
sanbot-usb projector-conn
```

## ZigBee Helpers

The ZigBee module accepts JSON payloads; helpers wrap JSON into frames routed to head.
```
sanbot-usb zigbee send-json --json '{"time":100}'
sanbot-usb zigbee allow-join --time 120
```

## MCU Upgrade

Start upgrade (YMODEM) for head or bottom MCU:
```
sanbot-usb upgrade start --target head --file /path/firmware.bin --block 1024
sanbot-usb upgrade start --target bottom --file /path/firmware.bin --block 128
```

Query status:
```
sanbot-usb upgrade status --type head
sanbot-usb upgrade status --type bottom
```

## Extending

- To add a new command: port its bytes (per smali `getCommandBytes()`) into a small builder and route to the correct point_tag.
  See the source repository docs under `tools/decompiled/.../bean/` for references.

