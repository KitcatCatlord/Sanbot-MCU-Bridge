#include "command-database.h"

#include "packet-assembler.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <set>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

#include <sqlite3.h>

namespace sanbot {
namespace {

namespace fs = std::filesystem;

std::string trim(std::string s) {
  auto notSpace = [](unsigned char c) { return !std::isspace(c); };
  s.erase(s.begin(), std::find_if(s.begin(), s.end(), notSpace));
  s.erase(std::find_if(s.rbegin(), s.rend(), notSpace).base(), s.end());
  return s;
}

bool endsWith(const std::string &s, const std::string &suffix) {
  return s.size() >= suffix.size() &&
         s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
}

void stripSuffix(std::string &s, const std::string &suffix) {
  if (endsWith(s, suffix))
    s.erase(s.size() - suffix.size());
}

std::string normalizeKey(const std::string &s) {
  std::string out;
  out.reserve(s.size());
  for (unsigned char c : s) {
    if (std::isalnum(c))
      out.push_back(static_cast<char>(std::tolower(c)));
  }
  return out;
}

void addUnique(std::vector<std::string> &values, const std::string &value) {
  if (value.empty())
    return;
  if (std::find(values.begin(), values.end(), value) == values.end())
    values.push_back(value);
}

bool isSimpleIdentifier(const std::string &s) {
  if (s.empty())
    return false;
  for (unsigned char c : s) {
    if (!std::isalnum(c) && c != '_')
      return false;
  }
  return true;
}

uint64_t parseUnsigned(const std::string &text, uint64_t maxValue,
                       const std::string &what) {
  std::string s = trim(text);
  if (s.empty())
    throw std::runtime_error("empty " + what);

  std::size_t consumed = 0;
  unsigned long long value = 0;
  try {
    value = std::stoull(s, &consumed, 0);
  } catch (...) {
    throw std::runtime_error("invalid " + what + ": " + text);
  }
  if (consumed != s.size() || value > maxValue)
    throw std::runtime_error("out-of-range " + what + ": " + text);
  return static_cast<uint64_t>(value);
}

uint8_t parseByteLiteral(const std::string &text) {
  return static_cast<uint8_t>(parseUnsigned(text, 0xFF, "byte"));
}

uint16_t parseU16Literal(const std::string &text) {
  return static_cast<uint16_t>(parseUnsigned(text, 0xFFFF, "u16"));
}

std::vector<uint8_t> parseByteList(const std::string &text) {
  std::vector<uint8_t> bytes;
  std::stringstream ss(text);
  std::string token;
  while (std::getline(ss, token, ',')) {
    token = trim(token);
    if (!token.empty())
      bytes.push_back(parseByteLiteral(token));
  }
  if (bytes.empty())
    throw std::runtime_error("array argument must contain at least one byte");
  return bytes;
}

std::string sqliteText(sqlite3_stmt *stmt, int column) {
  const unsigned char *text = sqlite3_column_text(stmt, column);
  return text ? reinterpret_cast<const char *>(text) : "";
}

struct SQLiteHandle {
  sqlite3 *db = nullptr;

  explicit SQLiteHandle(const std::string &path) {
    if (sqlite3_open_v2(path.c_str(), &db, SQLITE_OPEN_READONLY, nullptr) !=
        SQLITE_OK) {
      std::string message = db ? sqlite3_errmsg(db) : "sqlite open failed";
      if (db)
        sqlite3_close(db);
      db = nullptr;
      throw std::runtime_error("failed to open command database '" + path +
                               "': " + message);
    }
  }

  ~SQLiteHandle() {
    if (db)
      sqlite3_close(db);
  }

  SQLiteHandle(const SQLiteHandle &) = delete;
  SQLiteHandle &operator=(const SQLiteHandle &) = delete;
};

struct Statement {
  sqlite3_stmt *stmt = nullptr;

  Statement(sqlite3 *db, const std::string &sql) {
    if (sqlite3_prepare_v2(db, sql.c_str(), -1, &stmt, nullptr) != SQLITE_OK)
      throw std::runtime_error("sqlite prepare failed: " +
                               std::string(sqlite3_errmsg(db)));
  }

  ~Statement() {
    if (stmt)
      sqlite3_finalize(stmt);
  }

  Statement(const Statement &) = delete;
  Statement &operator=(const Statement &) = delete;

  void bindInt(int index, int value) {
    if (sqlite3_bind_int(stmt, index, value) != SQLITE_OK)
      throw std::runtime_error("sqlite bind failed");
  }

  bool step() {
    int rc = sqlite3_step(stmt);
    if (rc == SQLITE_ROW)
      return true;
    if (rc == SQLITE_DONE)
      return false;
    throw std::runtime_error("sqlite step failed");
  }
};

std::string friendlyAlias(const std::string &canonicalName) {
  std::string s = canonicalName;
  stripSuffix(s, "Command");
  stripSuffix(s, "USB");
  return commandAliasName(s);
}

std::vector<std::string> generatedAliasesFor(const CommandInfo &command) {
  std::vector<std::string> aliases;
  addUnique(aliases, commandAliasName(command.canonicalName));
  addUnique(aliases, friendlyAlias(command.canonicalName));

  if (command.canonicalName == "HandUSBCommand")
    addUnique(aliases, "arm");
  if (command.canonicalName == "HeadUSBCommand")
    addUnique(aliases, "head");
  if (command.canonicalName == "WheelUSBCommand")
    addUnique(aliases, "wheel");

  return aliases;
}

struct ArgumentBag {
  std::map<std::string, std::string> values;

  explicit ArgumentBag(const CommandArgs &args) {
    for (const auto &[key, value] : args)
      values[normalizeKey(key)] = value;
  }

  std::optional<std::string> find(const std::vector<std::string> &keys) const {
    for (const auto &key : keys) {
      auto it = values.find(normalizeKey(key));
      if (it != values.end())
        return it->second;
    }
    return std::nullopt;
  }
};

std::string stripMotionPrefix(std::string s) {
  for (const std::string &prefix : {"moveWheel", "moveHand", "moveHead"}) {
    if (s.rfind(prefix, 0) == 0) {
      s.erase(0, prefix.size());
      return s;
    }
  }
  return s;
}

std::string removeFirst(std::string s, const std::string &needle) {
  std::size_t pos = s.find(needle);
  if (pos != std::string::npos)
    s.erase(pos, needle.size());
  return s;
}

std::string replaceFirst(std::string s, const std::string &from,
                         const std::string &to) {
  std::size_t pos = s.find(from);
  if (pos != std::string::npos)
    s.replace(pos, from.size(), to);
  return s;
}

std::vector<std::string> baseKeysForHalfField(const std::string &fieldName) {
  std::vector<std::string> keys;
  if (fieldName.find("LSB") == std::string::npos &&
      fieldName.find("MSB") == std::string::npos)
    return keys;

  std::string base = removeFirst(removeFirst(fieldName, "LSB"), "MSB");
  std::string simple = stripMotionPrefix(base);
  addUnique(keys, base);
  addUnique(keys, simple);
  addUnique(keys, commandAliasName(base));
  addUnique(keys, commandAliasName(simple));

  if (base.find("Degree") != std::string::npos) {
    addUnique(keys, replaceFirst(base, "Degree", "Angle"));
    addUnique(keys, replaceFirst(simple, "Degree", "Angle"));
    addUnique(keys, "degree");
    addUnique(keys, "angle");
  }
  if (base.find("Time") != std::string::npos) {
    addUnique(keys, "time");
    addUnique(keys, "duration");
  }
  if (base.find("Distance") != std::string::npos)
    addUnique(keys, "distance");

  return keys;
}

std::vector<std::string> argumentKeysForField(const CommandParameter &field) {
  std::vector<std::string> keys;
  addUnique(keys, field.fieldName);
  addUnique(keys, commandAliasName(field.fieldName));

  if (isSimpleIdentifier(field.valueExpr) && field.valueExpr != "constant") {
    addUnique(keys, field.valueExpr);
    addUnique(keys, commandAliasName(field.valueExpr));
  }

  std::string simple = stripMotionPrefix(field.fieldName);
  addUnique(keys, simple);
  addUnique(keys, commandAliasName(simple));

  std::string lower = normalizeKey(field.fieldName);
  if (field.fieldRole == "mode_flag" || lower == "switchmode")
    addUnique(keys, "mode");
  if (lower == "whichhand") {
    addUnique(keys, "hand");
    addUnique(keys, "arm");
    addUnique(keys, "part");
  }
  if (lower.find("speed") != std::string::npos)
    addUnique(keys, "speed");
  if (lower.find("direction") != std::string::npos) {
    addUnique(keys, "direction");
    addUnique(keys, "action");
  }
  if (lower == "moveheaddirection")
    addUnique(keys, "lock");
  if (lower.find("degree") != std::string::npos) {
    addUnique(keys, "degree");
    addUnique(keys, "angle");
  }
  if (lower.find("distance") != std::string::npos)
    addUnique(keys, "distance");
  if (lower.find("time") != std::string::npos) {
    addUnique(keys, "time");
    addUnique(keys, "duration");
  }
  if (lower == "switchmode") {
    addUnique(keys, "switch");
    addUnique(keys, "enabled");
  }

  return keys;
}

std::optional<uint8_t> valueAlias(const std::string &fieldName,
                                  const std::string &rawValue) {
  std::string field = normalizeKey(fieldName);
  std::string value = normalizeKey(rawValue);
  std::map<std::string, uint8_t> aliases;

  auto add = [&](const std::string &name, uint8_t byte) {
    aliases[normalizeKey(name)] = byte;
  };

  if (field.find("switch") != std::string::npos ||
      field.find("status") != std::string::npos) {
    add("off", 0x00);
    add("disable", 0x00);
    add("disabled", 0x00);
    add("false", 0x00);
    add("on", 0x01);
    add("enable", 0x01);
    add("enabled", 0x01);
    add("true", 0x01);
  }

  if (field == "movewheeldirection") {
    add("stop", 0x00);
    add("forward", 0x01);
    add("back", 0x02);
    add("backward", 0x02);
    add("left", 0x03);
    add("right", 0x04);
    add("left-forward", 0x05);
    add("right-forward", 0x06);
    add("left-back", 0x07);
    add("right-back", 0x08);
    add("left-translation", 0x0A);
    add("right-translation", 0x0B);
    add("turn-left", 0x0C);
    add("turn-right", 0x0D);
    add("stop-turn", 0xF0);
  }

  if (field == "whichhand") {
    add("left", 0x01);
    add("right", 0x02);
    add("both", 0x03);
  }

  if (field == "movehanddirection") {
    add("up", 0x01);
    add("down", 0x02);
    add("stop", 0x03);
    add("reset", 0x04);
  }

  if (field == "moveheaddirection") {
    add("stop", 0x00);
    add("up", 0x01);
    add("vertical", 0x01);
    add("horizontal-lock", 0x01);
    add("down", 0x02);
    add("horizontal", 0x02);
    add("vertical-lock", 0x02);
    add("left", 0x03);
    add("both-lock", 0x03);
    add("right", 0x04);
    add("left-up", 0x05);
    add("right-up", 0x06);
    add("left-down", 0x07);
    add("right-down", 0x08);
    add("vertical-reset", 0x09);
    add("horizontal-reset", 0x0A);
    add("centre-reset", 0x0B);
    add("center-reset", 0x0B);
    add("no-lock", 0x00);
  }

  if (field.find("relative_direction") != std::string::npos ||
      field.find("relativedirection") != std::string::npos) {
    add("left", 0x01);
    add("up", 0x01);
    add("right", 0x02);
    add("down", 0x02);
  }

  if (field.find("mode") != std::string::npos) {
    add("no-angle", 0x01);
    add("direct", 0x01);
    add("relative", 0x02);
    add("absolute", 0x03);
    add("timed", 0x10);
    add("time", 0x10);
    add("distance", 0x11);
    add("centre", 0x20);
    add("center", 0x20);
    add("locate-absolute", 0x21);
    add("locate-relative", 0x22);
  }

  auto it = aliases.find(value);
  if (it == aliases.end())
    return std::nullopt;
  return it->second;
}

struct BuildContext {
  std::unordered_map<std::string, uint64_t> values;

  void set(const std::string &name, uint64_t value) {
    if (!name.empty())
      values[normalizeKey(name)] = value;
  }

  std::optional<uint64_t> get(const std::string &name) const {
    auto it = values.find(normalizeKey(name));
    if (it == values.end())
      return std::nullopt;
    return it->second;
  }
};

std::optional<const CommandParameter *>
findFieldByName(const CommandInfo &command, const std::string &name) {
  std::string normalized = normalizeKey(name);
  for (const auto &field : command.parameters) {
    if (normalizeKey(field.fieldName) == normalized ||
        normalizeKey(field.valueExpr) == normalized)
      return &field;
  }
  return std::nullopt;
}

std::optional<uint8_t> lookupNamedByte(const CommandInfo &command,
                                       const ArgumentBag &bag,
                                       const BuildContext &context,
                                       const std::string &name) {
  if (auto value = context.get(name))
    return static_cast<uint8_t>(*value & 0xFF);

  std::vector<std::string> keys{name};
  if (auto field = findFieldByName(command, name)) {
    for (const auto &key : argumentKeysForField(**field))
      addUnique(keys, key);
  }

  auto raw = bag.find(keys);
  if (!raw)
    return std::nullopt;

  if (auto field = findFieldByName(command, name)) {
    if (auto alias = valueAlias((**field).fieldName, *raw))
      return *alias;
  }

  return parseByteLiteral(*raw);
}

bool evalCondition(const std::string &condition, const CommandInfo &command,
                   const ArgumentBag &bag, const BuildContext &context) {
  std::string expr = trim(condition);
  if (expr.empty())
    return true;

  std::size_t inPos = expr.find(" in ");
  if (inPos != std::string::npos) {
    std::string name = trim(expr.substr(0, inPos));
    std::size_t open = expr.find('(', inPos);
    std::size_t close = expr.find(')', open);
    if (open == std::string::npos || close == std::string::npos)
      throw std::runtime_error("unsupported condition: " + condition);

    auto value = lookupNamedByte(command, bag, context, name);
    if (!value)
      throw std::runtime_error("missing argument needed by condition: " + name);

    std::stringstream items(expr.substr(open + 1, close - open - 1));
    std::string item;
    while (std::getline(items, item, ',')) {
      if (*value == parseByteLiteral(item))
        return true;
    }
    return false;
  }

  for (const std::string op : {"!=", "=="}) {
    std::size_t opPos = expr.find(op);
    if (opPos == std::string::npos)
      continue;

    std::string name = trim(expr.substr(0, opPos));
    std::string rhs = trim(expr.substr(opPos + op.size()));
    auto value = lookupNamedByte(command, bag, context, name);
    if (!value)
      throw std::runtime_error("missing argument needed by condition: " + name);
    bool equal = (*value == parseByteLiteral(rhs));
    return op == "==" ? equal : !equal;
  }

  throw std::runtime_error("unsupported condition: " + condition);
}

uint8_t evalTermByte(const std::string &term, const CommandInfo &command,
                     const ArgumentBag &bag, const BuildContext &context,
                     const CommandParameter &field) {
  std::string value = trim(term);
  if (value.rfind("0x", 0) == 0 || (!value.empty() && std::isdigit(value[0])))
    return parseByteLiteral(value);

  auto named = lookupNamedByte(command, bag, context, value);
  if (named)
    return *named;

  if (auto raw = bag.find(argumentKeysForField(field))) {
    if (auto alias = valueAlias(field.fieldName, *raw))
      return *alias;
    return parseByteLiteral(*raw);
  }

  throw std::runtime_error("missing argument: " + value);
}

std::optional<std::vector<uint8_t>>
resolveFieldBytes(const CommandInfo &command, const CommandParameter &field,
                  const ArgumentBag &bag, const BuildContext &context,
                  bool required) {
  if (!field.valueHex.empty())
    return std::vector<uint8_t>{parseByteLiteral(field.valueHex)};

  std::string expr = trim(field.valueExpr);
  if (expr.empty() || expr == "constant")
    return std::nullopt;

  if (endsWith(expr, "[]")) {
    std::string base = expr.substr(0, expr.size() - 2);
    std::vector<std::string> keys = argumentKeysForField(field);
    addUnique(keys, base);
    addUnique(keys, expr);
    auto raw = bag.find(keys);
    if (!raw) {
      if (required)
        throw std::runtime_error("missing array argument: " + base);
      return std::nullopt;
    }
    return parseByteList(*raw);
  }

  std::size_t question = expr.find('?');
  std::size_t colon = expr.find(':', question == std::string::npos ? 0 : question);
  if (question != std::string::npos && colon != std::string::npos) {
    std::string condition = trim(expr.substr(0, question));
    std::string thenTerm = trim(expr.substr(question + 1, colon - question - 1));
    std::string elseTerm = trim(expr.substr(colon + 1));
    bool conditionValue = evalCondition(condition, command, bag, context);
    return std::vector<uint8_t>{
        evalTermByte(conditionValue ? thenTerm : elseTerm, command, bag,
                     context, field)};
  }

  bool wantsLsb = field.fieldName.find("LSB") != std::string::npos;
  bool wantsMsb = field.fieldName.find("MSB") != std::string::npos;
  if (wantsLsb || wantsMsb) {
    if (auto wideRaw = bag.find(baseKeysForHalfField(field.fieldName))) {
      uint16_t value = parseU16Literal(*wideRaw);
      return std::vector<uint8_t>{static_cast<uint8_t>(
          wantsLsb ? (value & 0xFF) : ((value >> 8) & 0xFF))};
    }
  }

  auto raw = bag.find(argumentKeysForField(field));
  if (!raw) {
    if (required)
      throw std::runtime_error("missing argument: " + field.fieldName);
    return std::nullopt;
  }

  if (auto alias = valueAlias(field.fieldName, *raw))
    return std::vector<uint8_t>{*alias};

  return std::vector<uint8_t>{parseByteLiteral(*raw)};
}

void rememberSingleByte(BuildContext &context, const CommandParameter &field,
                        const std::vector<uint8_t> &bytes) {
  if (bytes.size() != 1)
    return;
  context.set(field.fieldName, bytes.front());
  if (isSimpleIdentifier(field.valueExpr))
    context.set(field.valueExpr, bytes.front());
}

bool isCommandModeField(const CommandParameter &field) {
  return field.payloadOffset == 0 &&
         (normalizeKey(field.fieldName) == "commandmode" ||
          field.fieldRole == "command_mode");
}

} // namespace

std::string commandAliasName(const std::string &name) {
  std::string out;
  out.reserve(name.size() + 8);

  for (std::size_t i = 0; i < name.size(); ++i) {
    unsigned char c = static_cast<unsigned char>(name[i]);
    if (std::isalnum(c)) {
      bool upper = std::isupper(c);
      bool prevLowerOrDigit =
          i > 0 && (std::islower(static_cast<unsigned char>(name[i - 1])) ||
                    std::isdigit(static_cast<unsigned char>(name[i - 1])));
      bool acronymBoundary =
          i > 0 && upper &&
          std::isupper(static_cast<unsigned char>(name[i - 1])) &&
          i + 1 < name.size() &&
          std::islower(static_cast<unsigned char>(name[i + 1]));
      if ((upper && prevLowerOrDigit) || acronymBoundary) {
        if (!out.empty() && out.back() != '-')
          out.push_back('-');
      }
      out.push_back(static_cast<char>(std::tolower(c)));
    } else if (!out.empty() && out.back() != '-') {
      out.push_back('-');
    }
  }

  while (!out.empty() && out.back() == '-')
    out.pop_back();
  return out;
}

CommandArgs parseCommandArgs(const std::vector<std::string> &tokens) {
  CommandArgs args;
  for (const auto &token : tokens) {
    std::size_t pos = token.find('=');
    if (pos == std::string::npos || pos == 0)
      throw std::runtime_error("expected key=value argument, got: " + token);
    args[token.substr(0, pos)] = token.substr(pos + 1);
  }
  return args;
}

CommandDatabase::CommandDatabase(const std::string &dbPath) : dbPath_(dbPath) {
  load();
  indexAliases();
}

std::string CommandDatabase::findDefaultDatabasePath(
    const std::string &startDir) {
  if (const char *env = std::getenv("SANBOT_MCU_COMMAND_DB")) {
    if (*env)
      return env;
  }

  std::vector<fs::path> roots;
  if (!startDir.empty())
    roots.push_back(fs::absolute(startDir));
  roots.push_back(fs::current_path());

  std::set<fs::path> tried;
  for (fs::path root : roots) {
    for (int depth = 0; depth < 8 && !root.empty(); ++depth) {
      fs::path candidate =
          root / "mcu-command-database" / "sanbot_mcu_commands.sqlite";
      if (tried.insert(candidate).second && fs::exists(candidate))
        return candidate.string();
      fs::path parent = root.parent_path();
      if (parent == root)
        break;
      root = parent;
    }
  }

  throw std::runtime_error(
      "could not find mcu-command-database/sanbot_mcu_commands.sqlite; set "
      "SANBOT_MCU_COMMAND_DB or pass --db");
}

void CommandDatabase::load() {
  SQLiteHandle db(dbPath_);

  Statement commands(
      db.db,
      "SELECT c.command_id, c.canonical_name, c.command_group, "
      "c.command_mode_hex, c.ack_default_hex, c.payload_template, "
      "c.description, t.name, COALESCE(t.route_tag_hex, ''), "
      "c.route_handling "
      "FROM commands c "
      "JOIN usb_targets t ON t.target_id = c.target_id "
      "ORDER BY c.canonical_name");

  while (commands.step()) {
    CommandInfo info;
    info.commandId = sqlite3_column_int(commands.stmt, 0);
    info.canonicalName = sqliteText(commands.stmt, 1);
    info.commandGroup = sqliteText(commands.stmt, 2);
    info.commandModeHex = sqliteText(commands.stmt, 3);
    info.ackDefaultHex = sqliteText(commands.stmt, 4);
    info.payloadTemplate = sqliteText(commands.stmt, 5);
    info.description = sqliteText(commands.stmt, 6);
    info.targetName = sqliteText(commands.stmt, 7);
    info.routeTagHex = sqliteText(commands.stmt, 8);
    info.routeHandling = sqliteText(commands.stmt, 9);
    commands_.push_back(std::move(info));
  }

  for (auto &command : commands_) {
    Statement fields(
        db.db,
        "SELECT ordinal, payload_offset, field_name, field_role, "
        "COALESCE(value_expr, ''), COALESCE(value_hex, ''), "
        "COALESCE(condition_expr, ''), omit_if_minus_one, "
        "COALESCE(description, '') "
        "FROM command_payload_fields "
        "WHERE command_id = ? "
        "ORDER BY payload_offset, ordinal");
    fields.bindInt(1, command.commandId);

    while (fields.step()) {
      CommandParameter parameter;
      parameter.ordinal = sqlite3_column_int(fields.stmt, 0);
      parameter.payloadOffset = sqlite3_column_int(fields.stmt, 1);
      parameter.fieldName = sqliteText(fields.stmt, 2);
      parameter.fieldRole = sqliteText(fields.stmt, 3);
      parameter.valueExpr = sqliteText(fields.stmt, 4);
      parameter.valueHex = sqliteText(fields.stmt, 5);
      parameter.conditionExpr = sqliteText(fields.stmt, 6);
      parameter.omitIfMinusOne = sqlite3_column_int(fields.stmt, 7) != 0;
      parameter.description = sqliteText(fields.stmt, 8);
      command.parameters.push_back(std::move(parameter));
    }
  }
}

void CommandDatabase::indexAliases() {
  std::map<std::string, std::vector<std::size_t>> owners;
  for (std::size_t i = 0; i < commands_.size(); ++i) {
    commands_[i].aliases = generatedAliasesFor(commands_[i]);
    addUnique(commands_[i].aliases, commands_[i].canonicalName);
    std::set<std::string> normalizedForCommand;
    for (const auto &alias : commands_[i].aliases) {
      std::string normalized = normalizeKey(alias);
      if (normalizedForCommand.insert(normalized).second)
        owners[normalized].push_back(i);
    }
  }

  for (const auto &[alias, indexes] : owners) {
    if (indexes.size() == 1) {
      uniqueAliases_[alias] = indexes.front();
      continue;
    }

    std::vector<std::string> names;
    for (std::size_t index : indexes)
      addUnique(names, commands_[index].canonicalName);
    ambiguousAliases_[alias] = std::move(names);
  }
}

const CommandInfo &CommandDatabase::resolveCommand(
    const std::string &name) const {
  std::string key = normalizeKey(name);
  auto found = uniqueAliases_.find(key);
  if (found != uniqueAliases_.end())
    return commands_[found->second];

  auto ambiguous = ambiguousAliases_.find(key);
  if (ambiguous != ambiguousAliases_.end()) {
    std::ostringstream message;
    message << "ambiguous command alias '" << name << "' matches";
    for (const auto &candidate : ambiguous->second)
      message << " " << candidate;
    throw std::runtime_error(message.str());
  }

  throw std::runtime_error("unknown command: " + name);
}

BuiltCommand CommandDatabase::buildCommand(const std::string &name,
                                           const CommandArgs &args) const {
  const CommandInfo &command = resolveCommand(name);
  ArgumentBag bag(args);
  BuildContext context;

  CommandPayload payload;
  payload.commandMode = parseByteLiteral(command.commandModeHex);
  context.set("commandMode", payload.commandMode);

  for (const auto &field : command.parameters) {
    if (isCommandModeField(field))
      continue;
    if (!field.conditionExpr.empty())
      continue;
    auto bytes = resolveFieldBytes(command, field, bag, context, false);
    if (bytes)
      rememberSingleByte(context, field, *bytes);
  }

  for (const auto &field : command.parameters) {
    if (isCommandModeField(field))
      continue;

    if (!field.conditionExpr.empty() &&
        !evalCondition(field.conditionExpr, command, bag, context))
      continue;

    auto bytes = resolveFieldBytes(command, field, bag, context, true);
    if (!bytes)
      continue;

    for (uint8_t byte : *bytes)
      payload.orderedBytes.push_back(static_cast<int8_t>(byte));
    rememberSingleByte(context, field, *bytes);
  }

  BuiltCommand built;
  built.canonicalName = command.canonicalName;
  built.targetName = command.targetName;
  built.ackFlag = command.ackDefaultHex.empty()
                      ? 0x01
                      : parseByteLiteral(command.ackDefaultHex);

  if (command.routeTagHex.empty()) {
    built.bytes = assembleUsbFrameFromCommand(payload, built.ackFlag);
  } else {
    built.routeTag = parseByteLiteral(command.routeTagHex);
    built.bytes = assembleRoutedBuffer(payload, built.ackFlag, *built.routeTag);
  }

  return built;
}

} // namespace sanbot
