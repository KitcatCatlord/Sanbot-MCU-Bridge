# sanbot-mcu-bridge

A C++ library and CLI to control the Sanbot Elf S1-B2 humanoid robot over USB, bypassing the original Android controller.

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
