PRAGMA foreign_keys=ON;

CREATE TABLE sources (
  source_id INTEGER PRIMARY KEY,
  source_path TEXT NOT NULL,
  decompiled_path TEXT,
  package_name TEXT,
  class_name TEXT,
  method_name TEXT,
  line_start INTEGER,
  line_end INTEGER,
  evidence_note TEXT NOT NULL
);

CREATE TABLE usb_targets (
  target_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  route_tag_hex TEXT,
  product_id_hex TEXT,
  transport TEXT NOT NULL,
  description TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE packet_fields (
  packet_field_id INTEGER PRIMARY KEY,
  packet_name TEXT NOT NULL,
  absolute_start INTEGER,
  absolute_end INTEGER,
  name TEXT NOT NULL,
  width_bytes INTEGER,
  endian TEXT NOT NULL,
  value_expr TEXT NOT NULL,
  description TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE commands (
  command_id INTEGER PRIMARY KEY,
  package_name TEXT NOT NULL,
  class_name TEXT NOT NULL,
  canonical_name TEXT NOT NULL,
  command_group TEXT NOT NULL,
  command_mode_hex TEXT,
  subcommand_hex TEXT,
  ack_default_hex TEXT,
  target_id INTEGER NOT NULL REFERENCES usb_targets(target_id),
  route_handling TEXT NOT NULL,
  payload_template TEXT NOT NULL,
  description TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id),
  UNIQUE(package_name, class_name),
  UNIQUE(canonical_name)
);

CREATE TABLE command_payload_fields (
  payload_field_id INTEGER PRIMARY KEY,
  command_id INTEGER NOT NULL REFERENCES commands(command_id) ON DELETE CASCADE,
  ordinal INTEGER NOT NULL,
  payload_offset INTEGER,
  absolute_packet_offset INTEGER,
  field_name TEXT NOT NULL,
  field_role TEXT NOT NULL,
  value_expr TEXT,
  value_hex TEXT,
  condition_expr TEXT,
  omit_if_minus_one INTEGER NOT NULL DEFAULT 0 CHECK (omit_if_minus_one IN (0,1)),
  description TEXT,
  source_id INTEGER NOT NULL REFERENCES sources(source_id),
  UNIQUE(command_id, ordinal)
);

CREATE TABLE command_flags (
  flag_id INTEGER PRIMARY KEY,
  command_id INTEGER NOT NULL REFERENCES commands(command_id) ON DELETE CASCADE,
  field_name TEXT NOT NULL,
  byte_hex TEXT NOT NULL,
  flag_name TEXT NOT NULL,
  effect TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE command_logic (
  logic_id INTEGER PRIMARY KEY,
  command_id INTEGER REFERENCES commands(command_id) ON DELETE CASCADE,
  logic_name TEXT NOT NULL,
  logic_text TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE high_level_methods (
  method_id INTEGER PRIMARY KEY,
  manager_class TEXT NOT NULL,
  method_name TEXT NOT NULL,
  command_id INTEGER REFERENCES commands(command_id),
  description TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE receive_primary_switch (
  primary_id INTEGER PRIMARY KEY,
  primary_byte_hex TEXT,
  primary_byte_signed INTEGER,
  label TEXT NOT NULL UNIQUE,
  group_name TEXT NOT NULL,
  description TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE mcu_receive_cases (
  receive_case_id INTEGER PRIMARY KEY,
  primary_id INTEGER NOT NULL REFERENCES receive_primary_switch(primary_id),
  decoded_class_name TEXT NOT NULL,
  command_type_int INTEGER,
  command_type_hex TEXT,
  payload_match_expr TEXT,
  cause TEXT NOT NULL,
  decoded_content TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE receive_payload_fields (
  receive_field_id INTEGER PRIMARY KEY,
  receive_case_id INTEGER NOT NULL REFERENCES mcu_receive_cases(receive_case_id) ON DELETE CASCADE,
  payload_offset INTEGER,
  absolute_packet_offset INTEGER,
  field_name TEXT NOT NULL,
  field_type TEXT,
  decode_expr TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE TABLE gpio_outputs (
  gpio_output_id INTEGER PRIMARY KEY,
  actor_type TEXT NOT NULL,
  process_or_module TEXT NOT NULL,
  path_or_symbol TEXT NOT NULL,
  write_method TEXT NOT NULL,
  value_expr TEXT NOT NULL,
  purpose TEXT NOT NULL,
  evidence_strength TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(source_id)
);

CREATE VIEW v_command_overview AS
SELECT
  c.command_id,
  c.canonical_name,
  c.package_name,
  c.class_name,
  c.command_group,
  c.command_mode_hex,
  c.subcommand_hex,
  c.ack_default_hex,
  t.name AS target_name,
  t.route_tag_hex,
  c.payload_template,
  c.description
FROM commands c
JOIN usb_targets t ON t.target_id = c.target_id;

CREATE VIEW v_command_payloads AS
SELECT
  c.canonical_name,
  cpf.ordinal,
  cpf.payload_offset,
  cpf.absolute_packet_offset,
  cpf.field_name,
  cpf.field_role,
  cpf.value_hex,
  cpf.value_expr,
  cpf.condition_expr,
  cpf.omit_if_minus_one,
  cpf.description
FROM command_payload_fields cpf
JOIN commands c ON c.command_id = cpf.command_id
ORDER BY c.canonical_name, cpf.ordinal;

CREATE VIEW v_receive_overview AS
SELECT
  r.receive_case_id,
  p.primary_byte_hex,
  p.label AS primary_label,
  r.decoded_class_name,
  r.command_type_int,
  r.command_type_hex,
  r.payload_match_expr,
  r.cause
FROM mcu_receive_cases r
JOIN receive_primary_switch p ON p.primary_id = r.primary_id;
