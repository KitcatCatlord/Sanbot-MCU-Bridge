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

- Relative turn (`RelativeAngleWheelMotion`, mode 0x02)
```
sanbot-usb wheels angle --direction left --speed 100 --deg 90
sanbot-usb wheels angle --direction right --speed 120 --deg 45
```

- Timed run (`NoAngleWheelMotion`, mode 0x01)
```
sanbot-usb wheels time --pattern forward --speed 100 --ms 1500 --no-circle
sanbot-usb wheels time --pattern turn-left --speed 90 --ms 600
```

- Distance run (`DistanceWheelMotion`, mode 0x11)
```
sanbot-usb wheels distance --pattern forward --speed 120 --mm 500
sanbot-usb wheels distance --pattern strafe-right --speed 80 --mm 300
```

Common wheel patterns:

| Pattern         | Hex | Notes                    |
|-----------------|-----|--------------------------|
| forward         | 0x01| run forward              |
| back            | 0x02| run backward             |
| left            | 0x03| run left (lateral)       |
| right           | 0x04| run right (lateral)      |
| forward-left    | 0x05| diagonal forward-left    |
| forward-right   | 0x06| diagonal forward-right   |
| back-left       | 0x07| diagonal back-left       |
| back-right      | 0x08| diagonal back-right      |
| strafe-left     | 0x0A| side-step left           |
| strafe-right    | 0x0B| side-step right          |
| turn-left       | 0x0C| spin left                |
| turn-right      | 0x0D| spin right               |

Stop is `0x00`. Start with short durations and low speeds when exercising real hardware.

## Head

- Absolute axis move (`AbsoluteAngleHeadMotion`, mode 0x03)
```
sanbot-usb head absolute --axis vertical --deg -10 --speed 40
sanbot-usb head absolute --axis horizontal --deg 30
```

- Locate relative (`LocateRelativeAngleHeadMotion`, mode 0x22)
```
sanbot-usb head relative --lock none --hdir left --hdeg 20 --vdir none --vdeg 0
sanbot-usb head relative --lock both --hdir right --hdeg 15 --vdir up --vdeg 8
```

- Relative angle (`RelativeAngleHeadMotion`, mode 0x02)
```
sanbot-usb head angle --direction left --speed 50 --deg 25
sanbot-usb head angle --direction up --speed 40 --deg 15
```

- Timed / continuous (`NoAngleHeadMotion`, mode 0x10 / 0x01)
```
sanbot-usb head time --direction center-reset --ms 500
sanbot-usb head noangle --direction left-up --speed 60
```

Head action cheat-sheet:

| Action             | Hex | Description                  |
|--------------------|-----|------------------------------|
| up                 | 0x01| pitch up                     |
| down               | 0x02| pitch down                   |
| left               | 0x03| yaw left                     |
| right              | 0x04| yaw right                    |
| left-up            | 0x05| diagonal                     |
| right-up           | 0x06| diagonal                     |
| left-down          | 0x07| diagonal                     |
| right-down         | 0x08| diagonal                     |
| vertical-reset     | 0x09| zero vertical axis           |
| horizontal-reset   | 0x0A| zero horizontal axis         |
| center-reset       | 0x0B| zero both axes               |

Locate locks: `none (0x00)`, `horizontal (0x01)`, `vertical (0x02)`, `both (0x03)`.

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

## Quick Self-Test

Need a fast sanity check on hardware?  Run the interactive helper (prompts for
confirmation after each action):

```
sanbot-usb self-test --skip-wheels
python -m transfer.test_bridge --skip-wheels  # or --include-wheels
```

Use `--include-wheels` only if the robot is safely lifted; otherwise stick to
head/arm/sensor tests.

## Extending

- To add a new command: port its bytes (per smali `getCommandBytes()`) into a small builder and route to the correct point_tag.
  See the source repository docs under `tools/decompiled/.../bean/` for references.
