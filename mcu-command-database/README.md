# Sanbot MCU Command Database

This directory contains a normalized SQLite database and reproducible SQL export for the USB MCU protocol found in the unpacked Sanbot firmware.

## Files

- `sanbot_mcu_commands.sqlite` - SQLite database.
- `sanbot_mcu_commands.sql` - schema plus data used to build the database.
- `schema.sql` - schema only.
- `EXTRACTION_NOTES.md` - source evidence, extraction notes, and GPIO scope notes.

## Packet Layout

All command payload offsets are relative to the MCU payload. The absolute packet offset is `21 + payload_offset`.

The outgoing USB packet body produced by `USBCommand.getMessage()` is:

| Absolute bytes | Name | Value |
| --- | --- | --- |
| 0-1 | OuterType | `A4 03` |
| 2-3 | Subtype | `00 00` |
| 4-7 | MessageSize | `payload_length + 6`, serialized by `integerToByteArray` |
| 8 | OuterAckFlag | `ack_flg` |
| 9-15 | Unused | seven zero bytes |
| 16-17 | FrameHead | `FF A5` |
| 18 | InnerAckFlag | `ack_flg` |
| 19-20 | Mmnn | `payload_length + 1` |
| 21.. | Payload | rows in `command_payload_fields` |
| last | Checksum | low byte of the Java-byte sum described in `packet_fields` |

Some command classes append a trailing route tag after the checksum. `UsbMessageMrg` strips that byte before USB transfer: `0x01` head, `0x02` bottom, `0x03` both.

## Main Tables

- `sources.source_id` is the evidence key used by every protocol/GPIO table.
- `commands.command_id` is the primary key for outgoing command classes.
- `command_payload_fields.command_id` links each payload byte/field to `commands`.
- `command_flags.command_id` records mode bytes that alter payload structure.
- `command_logic.command_id` records branch logic that must be applied before building a packet.
- `commands.target_id` links to `usb_targets.target_id` for head, bottom, both, caller-selected, or upgrade-callback routing.
- `packet_fields` describes the shared USB/MCU wrapper.
- `mcu_receive_cases.primary_id` links to `receive_primary_switch`.
- `receive_payload_fields.receive_case_id` lists decoded incoming fields where DecodeCommand assigns packet bytes to bean fields.
- `gpio_outputs.source_id` links GPIO evidence to `sources`.

Typical joins:

- Outgoing command bytes: `commands -> command_payload_fields` on `command_id`.
- Outgoing route details: `commands -> usb_targets` on `target_id`.
- Command evidence: any table with `source_id -> sources.source_id`.
- Incoming MCU cases: `mcu_receive_cases -> receive_primary_switch` on `primary_id`.
- Incoming decoded fields: `mcu_receive_cases -> receive_payload_fields` on `receive_case_id`.

## Example Queries

List outgoing commands with targets:

```sql
SELECT canonical_name, command_group, payload_template, target_name, route_tag_hex
FROM v_command_overview
ORDER BY canonical_name;
```

Show a command payload byte-by-byte:

```sql
SELECT ordinal, payload_offset, field_name, value_hex, value_expr, condition_expr, omit_if_minus_one
FROM v_command_payloads
WHERE canonical_name = 'WheelUSBCommand'
ORDER BY ordinal;
```

Find flags that change payload shape:

```sql
SELECT c.canonical_name, f.field_name, f.byte_hex, f.flag_name, f.effect
FROM command_flags f
JOIN commands c ON c.command_id = f.command_id
ORDER BY c.canonical_name, f.field_name, f.byte_hex;
```

Inspect incoming MCU decode cases:

```sql
SELECT primary_byte_hex, decoded_class_name, command_type_int, payload_match_expr, cause
FROM v_receive_overview
ORDER BY command_type_int, receive_case_id;
```

Inspect GPIO writers:

```sql
SELECT actor_type, process_or_module, path_or_symbol, write_method, purpose, evidence_strength
FROM gpio_outputs
ORDER BY actor_type, process_or_module;
```
