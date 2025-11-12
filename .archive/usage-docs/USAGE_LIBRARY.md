# MCU Manager Library – Installed Package Guide

This guide teaches you how to control the robot from Python with zero prior
knowledge of the firmware. It explains what each function does, which hardware
it touches, how to receive data back from the robot, and how to use the head
camera.

Note: This usage document is bundled with the wheel for convenience. Full
protocol docs live in the source repository.

## Quick Start
1) Install
```
pip install sanbot-mcu-bridge
```
2) Import and open
```
from sanbot.mcu_bridge.lib import Sanbot
bot = Sanbot()
bot.open()              # claims both the head and bottom USB endpoints
```
3) Drive forward for 1 second
```
bot.wheels_time('forward', ms=1000)
```
4) Close when done
```
bot.close()
```

## Safety Checklist (Read This First)
- Start slow. Use small speeds (e.g., 60–100) and short durations.
- Keep room clear when testing wheels/head motions.
- Add your own soft E‑stop logic (e.g., on obstacle, stop/back off).
- Power: don’t attempt firmware upgrades unless you have stable power.
- Built‑in safeguards: by default, the library enforces conservative motion limits
  (speed, time, distance, degrees). You can tune or disable them:
  - `Sanbot(unsafe=True)` bypasses checks (not recommended).
  - Customize via `SafetyLimits` in `sanbot.mcu_bridge.lib.safety`.

## Events and Listening
Register callbacks and start listeners. Decoders add labels where known.
```
def on_battery(fields, frame):
    print('Battery level:', fields.get('level'))

bot.on('battery', on_battery)
bot.start_listening(targets=('bottom','head'), decode=True, interval_ms=500)
```

## Motion — Wheels (Bottom MCU)
```
bot.wheels_time(direction='forward'|'back', ms:int, circle:bool=False)
bot.wheels_distance(direction='forward'|'back', speed:int, mm:int)
bot.wheels_angle(direction='left'|'right', speed:int, deg:int)
```
Direction strings map to the firmware enums:
- `forward/back` → 0x01 / 0x02 for run/distance
- `left/right` (turn) → 0x01 / 0x02
- `circle=True` sets the `isCircle` byte (0x01).
For advanced gait patterns (strafe/diagonals/spins) use `transfer.usb_bridge.WHEEL_RUN_ACTIONS` to obtain the hex code and call `bot.bottom.send_payload` manually.

## Motion — Head (Head MCU)
```
bot.head_absolute(hdeg:int, vdeg:int)
bot.head_relative(hdir:int, hdeg:int, vdir:int, vdeg:int)
bot.head_angle(axis='h'|'v', direction:int, speed:int, deg:int)
bot.head_time(direction:int, ms:int, flag:int=0)
bot.head_noangle(direction:int, speed:int)
```
Head direction codes follow the Android beans:
- Absolute/relative: see `transfer.usb_bridge.HEAD_ABSOLUTE_AXES`, `HEAD_RELATIVE_ACTIONS`, and `HEAD_NOANGLE_ACTIONS` for the raw hex values (e.g. up=0x01, down=0x02, center-reset=0x0B).
- When targeting only one axis you may pass zero for the other.

## Motion — Hands/Arms (Bottom MCU)
```
bot.hand_angle(which:int, mode:int, direction:int, speed:int, deg:int)
bot.hand_time(which:int, ms:int, deg:int=0)
bot.hand_noangle(which:int, direction:int, speed:int)
```

## Lights and Projector
```
bot.led(which_light:int, switch_mode:int, rate:int=0, random_count:int=0)
bot.projector_power(True|False)
bot.projector_status(); bot.projector_connection()
```

## System Modes and Utilities
```
bot.mcu_reset(target='head'|'bottom', time_byte:int=1)
bot.motor_defend(which_part:int, enable:bool)
bot.motor_lock(which_part:int, enable:bool)
bot.white_light(level:int)
bot.black_shield(enable:bool)
bot.follow(enable:bool)
bot.wander(enable:bool, wander_type:int=1)
bot.hide_mode(enable:bool)
bot.dance(enable:bool)
bot.speaker(enable:bool)
```

## Sensors and Status
```
bot.battery(); bot.battery_temp()
bot.button(); bot.encoder_status(); bot.uart_status()
bot.gyro(accel_status=-1, compass_status=-1)        # adds drift/elevation/roll when present
bot.obstacle(); bot.work_status()
bot.pir(); bot.touch(); bot.ir_receive_status(); bot.ir_sensor(content, info)
```

## ZigBee
```
bot.zigbee_send_json('{"time":120}')
```

## MCU Upgrade (Firmware)
```
bot.mcu_upgrade(target='head'|'bottom', file_path='/path/fw.bin', block_size=1024)
bot.mcu_upgrade_status('head'|'bottom')
```

## Head Camera (UVC)
```
from sanbot.camera_bridge.camera import Camera
cam = Camera(index=0, width=1280, height=720)
cam.open()
...
cam.close()
```
