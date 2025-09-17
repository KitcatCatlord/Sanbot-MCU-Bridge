# sanbot-mcu-bridge

A Python library and CLI to control Sanbot Elf S1-B2 MCUs directly over USB (no Android).
It mirrors the original USB framing and covers wheels, motion,
LEDs, projector, sensors, ZigBee, and firmware upgrade.

## Install
```
pip install sanbot-mcu-bridge
```

## Quick start (library)
```
from sanbot.mcu_bridge.lib import Sanbot
bot = Sanbot()
bot.open()
bot.wheels_time('forward', ms=800)
bot.close()
```

## Quick start (CLI)
```
sanbot-usb list
sanbot-usb listen --target bottom --verbose
```

- Camera CLI: `sanbot-camera` (list/preview/snapshot/stream)
- Safety: conservative motion limits; bypass with `Sanbot(unsafe=True)` or `--unsafe` in CLI.

## Docs
- Basic usage docs are bundled in the wheel:
  - `sanbot/mcu_bridge/USAGE.md`
  - `sanbot/mcu_bridge/USAGE_LIBRARY.md`
- Deep protocol docs (smali references, hardware maps) live in the development repo.
- GUI tester: see `usage-docs/USB_BRIDGE_TESTER.md` for the interactive bridge
  test bench with camera/microphone/USB monitoring.

## Changelog
See `CHANGELOG.md` for release notes.

## Notes from the dev
I'd just like to note that ChatGPT Codex *was* used in this project, but it was used almost exclusively for: documentation, TODO compression, searching original firmware for files, packaging project as a library. The core functionality was pretty much exclusively written by me, @KitcatCatlord.
This was initially written in a separate private project, so I could easily reference files I am not able to make public. If it seems unrealistic that I did all of this in one commit - it is, it was done over many sessions.

## License
This repository is currently unlicensed.
You may view the code, but you do not have permission to use, modify, or redistribute it outside GitHub.
