# sanbot-mcu-bridge

A C++ library and CLI to control the Sanbot Elf S1-B2 humanoid robot over USB, bypassing the original Android controller.

## Quick start

Build the CLI, list the database-backed commands, inspect a command, and dry-run
a packet before sending it to hardware:

```sh
cd core
./install-cli.sh
./sanbot-mcu-bridge commands
./sanbot-mcu-bridge describe-command wheel
./sanbot-mcu-bridge --test --debug send-command wheel mode=distance direction=forward speed=50 distance=1000
```

Commands come from `mcu-command-database/sanbot_mcu_commands.sqlite`. Use
`commands` to list them and `describe-command NAME` to see the accepted fields.
You can point at another copy with `--db /path/to/sanbot_mcu_commands.sqlite`
or `SANBOT_MCU_COMMAND_DB=/path/to/sanbot_mcu_commands.sqlite`.

Start USB control and the packet listener like this:

```sh
./sanbot-mcu-bridge take-control
./sanbot-mcu-bridge listen
./sanbot-mcu-bridge listen 30
```

`listen` runs until Ctrl-C, unless you pass a timeout in seconds. The current
`main` build is CLI-only and does not include a Qt GUI target; use the CLI
commands below or check out the old GUI branch if you specifically need the
removed GUI prototype.

### Command examples

Locomotion:

```sh
./sanbot-mcu-bridge send-command wheel mode=distance direction=forward speed=50 distance=1000
./sanbot-mcu-bridge send-command wheel mode=relative direction=left speed=40 angle=90
./sanbot-mcu-bridge send-command wheel mode=timed direction=turn-left time=1000 degree=90
./sanbot-mcu-bridge send-command wheel mode=no-angle direction=right-translation speed=40 time=1000 isCircle=0
./sanbot-mcu-bridge send-command wheel mode=no-angle direction=stop speed=0 time=0 isCircle=0
```

Lights:

```sh
./sanbot-mcu-bridge send-command LEDLightCommand whichLight=1 switchMode=on led_rate=5 led_random_number=0
./sanbot-mcu-bridge send-command WhiteLightCommand switchMode=on
./sanbot-mcu-bridge send-command SetWhiteBrightness setWhiteBrightness=1 brightness=80
./sanbot-mcu-bridge send-command QueryWhiteBrightness queryWhiteBrightness=1
```

Battery:

```sh
./sanbot-mcu-bridge send-command QueryBatteryCommand battery=0 currentBattery=0
./sanbot-mcu-bridge send-command BatteryTemperatureCommand temperature=0
./sanbot-mcu-bridge send-command AutoBatteryCommand switchMode=on threshold=20
./sanbot-mcu-bridge send-command AutoBatteryCommand switchMode=off
```

The same examples are available from the binary:

```sh
./sanbot-mcu-bridge help
./sanbot-mcu-bridge examples
```

## The project

**This project is currently in development - it's not ready yet!**

This project aims to create a comprehensive and easy-to-use CLI and library to control the Sanbot Elf S1-B2 from (almost) any device, fully bypassing the original Android board. This will be used in a project of mine called Sunny-Sanbot, which you can find on my GitHub profile.

## Roadmap

- [x] Working packet send/receive to MCUs
- [x] Database-backed command catalogue exposed to the CLI/library
- [ ] Hardware-test every database-backed command
- [ ] Audio & Camera bridge
- [ ] C++ library

## Database-backed commands

The C++ core can now load `mcu-command-database/sanbot_mcu_commands.sqlite`
and build packets from the normalized command tables instead of requiring a
new C++ function for every command.

```sh
sanbot-mcu-bridge commands
sanbot-mcu-bridge describe-command wheel
sanbot-mcu-bridge --test --debug send-command wheel mode=distance direction=forward speed=50 distance=1000
```

Use `--db /path/to/sanbot_mcu_commands.sqlite` or
`SANBOT_MCU_COMMAND_DB=/path/to/sanbot_mcu_commands.sqlite` if the default
database discovery cannot find the repo-local database.

## CLI install

`core/install.sh` and `core/install-cli.sh` build only the CLI and smoke-test
binary. They auto-install the required package-manager dependencies where
possible: `pkg-config`, SQLite3 development headers, and `libusb-1.0`
development headers.

```sh
cd core
./install-cli.sh
./sanbot-mcu-bridge take-control
./sanbot-mcu-bridge listen
```

## Notes from the dev

The sources for algorithms, addresses and commands are private, since I can't publish them as they're not open source (I pulled it from the firmware such that it's legal for me to reference where necessary but not use or share).

This library had a Python predecessor. For more info, see docs/History.md.

## License

This repository is currently unlicensed.
You may view the code, but you do not have permission to use, modify, or redistribute it outside GitHub.
