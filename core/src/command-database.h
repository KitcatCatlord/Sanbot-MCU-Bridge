#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace sanbot {

using CommandArgs = std::map<std::string, std::string>;

struct CommandParameter {
  int ordinal = 0;
  int payloadOffset = 0;
  std::string fieldName;
  std::string fieldRole;
  std::string valueExpr;
  std::string valueHex;
  std::string conditionExpr;
  bool omitIfMinusOne = false;
  std::string description;
};

struct CommandInfo {
  int commandId = 0;
  std::string canonicalName;
  std::vector<std::string> aliases;
  std::string commandGroup;
  std::string commandModeHex;
  std::string ackDefaultHex;
  std::string targetName;
  std::string routeTagHex;
  std::string routeHandling;
  std::string payloadTemplate;
  std::string description;
  std::vector<CommandParameter> parameters;
};

struct BuiltCommand {
  std::string canonicalName;
  std::string targetName;
  uint8_t ackFlag = 0x01;
  std::optional<uint8_t> routeTag;
  std::vector<uint8_t> bytes;

  bool hasRouteTag() const { return routeTag.has_value(); }
};

class CommandDatabase {
public:
  explicit CommandDatabase(const std::string &dbPath);

  static std::string findDefaultDatabasePath(const std::string &startDir = {});

  const std::string &path() const { return dbPath_; }
  const std::vector<CommandInfo> &commands() const { return commands_; }
  const CommandInfo &resolveCommand(const std::string &name) const;
  BuiltCommand buildCommand(const std::string &name,
                            const CommandArgs &args) const;

private:
  std::string dbPath_;
  std::vector<CommandInfo> commands_;
  std::map<std::string, std::size_t> uniqueAliases_;
  std::map<std::string, std::vector<std::string>> ambiguousAliases_;

  void load();
  void indexAliases();
};

CommandArgs parseCommandArgs(const std::vector<std::string> &tokens);
std::string commandAliasName(const std::string &name);

} // namespace sanbot
