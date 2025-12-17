# Extraction Notes

## Scope

The database was built from `mounted-fw/app/main-release.apk`, decompiled with apktool into `/tmp/sanbot-main-apk/smali`. It covers the Java/smali command builders that produce packets for `com.qihan.uvccamera.USBCommand` and `com.qihan.mcuupgrade.bean.USBCommand`.

## Accuracy Model

Each substantive row links to `sources.source_id`. Source rows include the APK path, decompiled smali path, class/method, and line range where available.

No command names were invented from behavior alone. `commands.canonical_name` uses the firmware class name, with an `Upgrade` prefix only where the same class name appears in the separate `com.qihan.mcuupgrade.bean` package.

## Command Logic

The command builders commonly assemble an `ArrayList<Byte>`, remove every byte equal to `-1`, and then copy the result to the final payload. That behavior is represented by `command_payload_fields.omit_if_minus_one = 1` and by `command_logic.OmitMinusOneBytes`.

The movement commands have explicit branch logic by mode byte. Those branches are represented in both `command_payload_fields.condition_expr` and `command_flags`.

## Incoming MCU Bytes

`DecodeCommand.decodeCommandByData` reads the first MCU payload byte at absolute packet offset `0x15` (decimal 21). The sparse switch maps `0x01`, `0x02`, `0x03`, `0x04`, `0x05`, `0x06`, `0x81`, `0x82`, `0x83`, `0xA0`, and `0xA1` to decoder groups. Unknown values become command type `10021`.

Where DecodeCommand assigns packet bytes to bean fields, those assignments are in `receive_payload_fields`. Complex derived fields such as bit masks and byte-pair integer combines are stored as expressions in `decode_expr`.

## GPIO Outputs

User-space GPIO output evidence is exact for `mounted-fw/bin/glgps` plus `mounted-fw/etc/gps/gpsconfig.xml`: the GPS config names `/sys/devices/platform/gps/power_enable` as `gpioNStdbyPath`, and the binary strings include Broadcom GPS GPIO write paths and messages.

Kernel module GPIO rows are intentionally marked `KernelSymbols`. They show modules with GPIO output symbols and their likely hardware purpose, but not fixed user-space values or sysfs paths.
