<!-- Generated/updated by GitHub Copilot on 2025-11-12 at user request. -->
# sanbot_mcu.sqlite guide

This database documents Sanbot MCU commands and the payload byte layout used by the CLI.

## What’s inside

- `commands` — One row per MCU command.
  - Columns: `cmd_id` (PK), `address_hex`, `command_mode_hex`, `class_name`, `file_path`, `category`, `mcu_target`, `description`, `api_group`, `api_action`, `api_name`.
- `command_bytes` — Byte-by-byte payload schema for each command.
  - Columns: `id`, `cmd_id` (FK → commands), `byte_order` (0..N), `label`, `description`, `source_field`, `source_type`.
- `logic_links` — Cross-references to firmware/reverse-eng symbols related to a command.
  - Columns: `id`, `cmd_id` (FK), `file_path`, `symbol`, `description`.
- `files_checklist` — Tracking for analyzed/decompiled files.
  - Columns: `id`, `file_path` (UNIQUE), `category`, `reviewed`, `notes`.

Note: The internal SQLite table `sqlite_sequence` may appear when AUTOINCREMENT is used; it’s empty/ignored.

## Typical workflow: build a CLI packet

1. Pick a command

- By id:

  ```sql
  SELECT *
  FROM commands
  WHERE cmd_id = ?;
  ```

- By category or class name:

  ```sql
  SELECT cmd_id, category, class_name, description
  FROM commands
  WHERE category = 'motion'
     OR class_name LIKE '%Wheel%'
  ORDER BY cmd_id;
  ```

1. Header bytes

- `address_hex` and `command_mode_hex` are hex strings for the command header. Convert these to bytes in the CLI before the payload.
  - Example: address_hex = "0x02", command_mode_hex = "0xA1" → bytes `02 A1`.

1. Payload schema (ordered)

- Get the payload layout for the chosen `cmd_id`:

  ```sql
  SELECT byte_order, label, description, source_field, source_type
  FROM command_bytes
  WHERE cmd_id = ?
  ORDER BY byte_order ASC;
  ```

- Build the payload by iterating in `byte_order`. For each row, look at `label/description` to know what value to insert. `source_type` hints how to pack (e.g., u8/i16/float/le/be); if omitted, treat as raw byte(s) per your protocol.

1. Optional: logic references

- Inspect reverse-eng notes / symbols tied to this command:

  ```sql
  SELECT file_path, symbol, description
  FROM logic_links
  WHERE cmd_id = ?
  ORDER BY id;
  ```

## Handy queries

- List all commands (quick view):

  ```sql
  SELECT cmd_id, address_hex, command_mode_hex, category, class_name
  FROM commands
  ORDER BY cmd_id;
  ```

- Show a command with its bytes in one view:

  ```sql
  SELECT c.cmd_id,
         c.address_hex,
         c.command_mode_hex,
         b.byte_order,
         b.label,
         b.source_type,
         b.description
  FROM commands c
  JOIN command_bytes b ON b.cmd_id = c.cmd_id
  WHERE c.cmd_id = ?
  ORDER BY b.byte_order;
  ```

- Find commands missing byte schema:

  ```sql
  SELECT c.cmd_id, c.class_name
  FROM commands c
  LEFT JOIN command_bytes b ON b.cmd_id = c.cmd_id
  WHERE b.cmd_id IS NULL
  ORDER BY c.cmd_id;
  ```

## Using the sqlite3 CLI

From the repo root:

```bash
sqlite3 dev/analysis/mcu_sql/sanbot_mcu.sqlite ".tables"
sqlite3 dev/analysis/mcu_sql/sanbot_mcu.sqlite ".schema commands"
sqlite3 dev/analysis/mcu_sql/sanbot_mcu.sqlite "SELECT * FROM commands LIMIT 10;"
```

Tip: For a friendlier UI, open the DB in DB Browser for SQLite or a VS Code SQLite extension, then browse `commands` → select a `cmd_id` → view its `command_bytes` rows ordered by `byte_order`.

## Notes

- The schema mirrors the reverse-engineering JSON sources: `commands` corresponds to per-command metadata; `command_bytes` expands payload fields/ordering.
- If a command’s payload packing rules are ambiguous, consult `logic_links` and `files_checklist` for original firmware references.
- Changes to labels/ordering should be versioned; consumers (CLI) assume `byte_order` is stable.

## Attribution

The initial pass of reviewing the original firmware `.smali` files and generating the structured dataset that seeded this database was performed with assistance from ChatGPT Codex.
