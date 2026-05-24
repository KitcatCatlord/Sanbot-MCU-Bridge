#include "control-catalogue.h"
#include "command-database.h"
#include "usb-send.h"
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <exception>
#include <filesystem>
#include <memory>
#include <string>
#include <vector>
using namespace std;

static string lowerString(string s) {
  transform(s.begin(), s.end(), s.begin(),
            [](unsigned char c) { return static_cast<char>(tolower(c)); });
  return s;
}

static bool parseByteValue(const string &s, uint8_t &out) {
  try {
    int val = stoi(s, nullptr, 0);
    if (val < 0 || val > 255)
      return false;
    out = static_cast<uint8_t>(val);
    return true;
  } catch (...) {
    return false;
  }
}

static bool parseU16Value(const string &s, uint16_t &out) {
  try {
    int val = stoi(s, nullptr, 0);
    if (val < 0 || val > 65535)
      return false;
    out = static_cast<uint16_t>(val);
    return true;
  } catch (...) {
    return false;
  }
}

static void log_packet(const vector<unsigned char> &packet) {
  printf("[VERBOSE] ");
  for (size_t i = 0; i < packet.size(); ++i) {
    printf("%02X", packet[i]);
    if (i + 1 != packet.size())
      printf(" ");
  }
  printf("\n");
  fflush(stdout);
}

static bool parseWheelAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "forward")
    out = 0x01;
  else if (k == "back")
    out = 0x02;
  else if (k == "left")
    out = 0x03;
  else if (k == "right")
    out = 0x04;
  else if (k == "left-forward")
    out = 0x05;
  else if (k == "right-forward")
    out = 0x06;
  else if (k == "left-back")
    out = 0x07;
  else if (k == "right-back")
    out = 0x08;
  else if (k == "left-translation")
    out = 0x0A;
  else if (k == "right-translation")
    out = 0x0B;
  else if (k == "turn-left")
    out = 0x0C;
  else if (k == "turn-right")
    out = 0x0D;
  else if (k == "stop-turn")
    out = 0xF0;
  else if (k == "stop")
    out = 0x00;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseArmPart(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "left")
    out = 0x01;
  else if (k == "right")
    out = 0x02;
  else if (k == "both")
    out = 0x03;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseArmAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "up")
    out = 0x01;
  else if (k == "down")
    out = 0x02;
  else if (k == "stop")
    out = 0x03;
  else if (k == "reset")
    out = 0x04;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "stop")
    out = 0x00;
  else if (k == "up")
    out = 0x01;
  else if (k == "down")
    out = 0x02;
  else if (k == "left")
    out = 0x03;
  else if (k == "right")
    out = 0x04;
  else if (k == "left-up")
    out = 0x05;
  else if (k == "right-up")
    out = 0x06;
  else if (k == "left-down")
    out = 0x07;
  else if (k == "right-down")
    out = 0x08;
  else if (k == "vertical-reset")
    out = 0x09;
  else if (k == "horizontal-reset")
    out = 0x0A;
  else if (k == "centre-reset")
    out = 0x0B;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadAbsoluteAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "vertical")
    out = 0x01;
  else if (k == "horizontal")
    out = 0x02;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadLockAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "no-lock")
    out = 0x00;
  else if (k == "horizontal-lock")
    out = 0x01;
  else if (k == "vertical-lock")
    out = 0x02;
  else if (k == "both-lock")
    out = 0x03;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadDirection(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "left")
    out = 0x01;
  else if (k == "right")
    out = 0x02;
  else if (k == "up")
    out = 0x01;
  else if (k == "down")
    out = 0x02;
  else
    return parseByteValue(s, out);
  return true;
}

static void printUsage(const char *argv0) {
  fprintf(stderr,
          "Usage:\n"
          "  %s [--db PATH] [--debug] [--test] commands\n"
          "  %s [--db PATH] describe-command NAME\n"
          "  %s [--db PATH] [--target head|bottom|both] [--debug] [--test] "
          "send-command NAME key=value...\n"
          "  %s [--debug] [--test] <legacy-command> ...\n",
          argv0, argv0, argv0, argv0);
}

static string defaultDatabasePath(const char *argv0) {
  namespace fs = std::filesystem;
  fs::path exe = fs::absolute(argv0);
  return sanbot::CommandDatabase::findDefaultDatabasePath(
      exe.has_parent_path() ? exe.parent_path().string() : string{});
}

static void printCommandList(const sanbot::CommandDatabase &db) {
  for (const auto &command : db.commands()) {
    printf("%-30s %-22s", command.canonicalName.c_str(),
           command.commandGroup.c_str());
    if (!command.aliases.empty()) {
      printf(" aliases:");
      for (const auto &alias : command.aliases)
        printf(" %s", alias.c_str());
    }
    printf("\n");
  }
}

static void printCommandDescription(const sanbot::CommandInfo &command) {
  printf("%s\n", command.canonicalName.c_str());
  printf("  group: %s\n", command.commandGroup.c_str());
  printf("  target: %s\n", command.targetName.c_str());
  printf("  ack: %s\n", command.ackDefaultHex.c_str());
  if (!command.routeTagHex.empty())
    printf("  route tag: %s\n", command.routeTagHex.c_str());
  printf("  aliases:");
  for (const auto &alias : command.aliases)
    printf(" %s", alias.c_str());
  printf("\n");
  printf("  template: %s\n", command.payloadTemplate.c_str());
  printf("  parameters:\n");
  for (const auto &parameter : command.parameters) {
    if (parameter.fieldName == "commandMode" ||
        parameter.fieldRole == "command_mode")
      continue;
    printf("    %-28s role=%s", parameter.fieldName.c_str(),
           parameter.fieldRole.c_str());
    if (!parameter.valueHex.empty())
      printf(" const=%s", parameter.valueHex.c_str());
    else if (!parameter.valueExpr.empty())
      printf(" value=%s", parameter.valueExpr.c_str());
    if (!parameter.conditionExpr.empty())
      printf(" when %s", parameter.conditionExpr.c_str());
    printf("\n");
  }
}

int main(int argc, char **argv) {
  if (argc < 2) {
    printUsage(argv[0]);
    return 1;
  }

  bool debug = false;
  bool test = false;
  string dbPath;
  string directTarget;
  int argi = 1;
  while (argi < argc) {
    string flag = argv[argi];
    if (flag == "--debug" || flag == "--verbose") {
      debug = true;
      argi++;
      continue;
    }
    if (flag == "--test" || flag == "--dry-run") {
      test = true;
      argi++;
      continue;
    }
    if (flag == "--db") {
      if (argi + 1 >= argc) {
        printUsage(argv[0]);
        return 1;
      }
      dbPath = argv[argi + 1];
      argi += 2;
      continue;
    }
    if (flag == "--target") {
      if (argi + 1 >= argc) {
        printUsage(argv[0]);
        return 1;
      }
      directTarget = lowerString(argv[argi + 1]);
      argi += 2;
      continue;
    }
    if (flag == "--help" || flag == "-h") {
      printUsage(argv[0]);
      return 0;
    }
    break;
  }

  if (argi >= argc) {
    printUsage(argv[0]);
    return 1;
  }

  string cmd = lowerString(argv[argi]);
  unique_ptr<SanbotUsbManager> manager;

  auto open_database = [&]() {
    return sanbot::CommandDatabase(
        dbPath.empty() ? defaultDatabasePath(argv[0]) : dbPath);
  };

  auto ensure_manager = [&]() -> SanbotUsbManager * {
    if (!test && !manager)
      manager = make_unique<SanbotUsbManager>();
    return manager.get();
  };

  auto send_packet = [&](const vector<uint8_t> &packet) {
    vector<unsigned char> buf(packet.begin(), packet.end());
    if (!test) {
      SanbotUsbManager *usb = ensure_manager();
      usb->sendToPoint(buf);
      usb->waitForPendingSends();
    }
    if (debug) log_packet(buf);
    if (test) {
      printf("[TEST] Skipped USB send\n");
      fflush(stdout);
    }
  };

  auto send_built_command = [&](const sanbot::BuiltCommand &built) -> bool {
    vector<unsigned char> buf(built.bytes.begin(), built.bytes.end());
    if (!test) {
      SanbotUsbManager *usb = ensure_manager();
      if (built.hasRouteTag()) {
        usb->sendToPoint(buf);
      } else if (directTarget == "head") {
        usb->sendToHead(buf);
      } else if (directTarget == "bottom") {
        usb->sendToBottom(buf);
      } else if (directTarget == "both") {
        usb->sendToHead(buf);
        usb->sendToBottom(buf);
      } else {
        fprintf(stderr,
                "%s has no database route tag. Pass --target head, bottom, "
                "or both.\n",
                built.canonicalName.c_str());
        return false;
      }
      usb->waitForPendingSends();
    }
    if (debug) log_packet(buf);
    if (test) {
      printf("[TEST] Skipped USB send\n");
      fflush(stdout);
    }
    return true;
  };

  try {
    if (cmd == "commands" || cmd == "list-commands" || cmd == "db-list") {
      auto db = open_database();
      printCommandList(db);
      return 0;
    }

    if (cmd == "describe-command" || cmd == "describe" ||
        cmd == "db-describe") {
      if (argc - argi != 2) {
        printUsage(argv[0]);
        return 1;
      }
      auto db = open_database();
      printCommandDescription(db.resolveCommand(argv[argi + 1]));
      return 0;
    }

    if (cmd == "send-command" || cmd == "db-send" || cmd == "command") {
      if (argc - argi < 2) {
        printUsage(argv[0]);
        return 1;
      }
      vector<string> tokens;
      for (int i = argi + 2; i < argc; ++i)
        tokens.push_back(argv[i]);
      auto db = open_database();
      auto built =
          db.buildCommand(argv[argi + 1], sanbot::parseCommandArgs(tokens));
      return send_built_command(built) ? 0 : 1;
    }
  } catch (const exception &ex) {
    fprintf(stderr, "sanbot-mcu-bridge: %s\n", ex.what());
    return 1;
  }

  if (cmd == "hex-send") {
    if (argc - argi < 2)
      return 1;
    vector<uint8_t> bytes;
    for (int i = argi + 1; i < argc; ++i) {
      uint8_t byte;
      try {
        int val = stoi(argv[i], nullptr, 16);
        if (val < 0 || val > 255)
          return 1;
        byte = static_cast<uint8_t>(val);
      } catch (...) {
        return 1;
      }
      bytes.push_back(byte);
    }
    send_packet(bytes);
    return 0;
  }

  if (cmd == "wheel-distance") {
    if (argc - argi != 4)
      return 1;
    uint8_t action, speed;
    uint16_t distance;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], distance))
      return 1;
    send_packet(buildWheelDistance(action, speed, distance));
    return 0;
  }

  if (cmd == "wheel-relative") {
    if (argc - argi != 4)
      return 1;
    uint8_t action, speed;
    uint16_t angle;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], angle))
      return 1;
    send_packet(buildWheelRelativeAngle(action, speed, angle));
    return 0;
  }

  if (cmd == "wheel-no-angle") {
    if (argc - argi != 5)
      return 1;
    uint8_t action, speed, durationMode;
    uint16_t duration;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], duration))
      return 1;
    if (!parseByteValue(argv[argi + 4], durationMode))
      return 1;
    send_packet(buildWheelNoAngle(action, speed, duration, durationMode));
    return 0;
  }

  if (cmd == "wheel-timed") {
    if (argc - argi != 4)
      return 1;
    uint8_t action, degree;
    uint16_t time;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], time))
      return 1;
    if (!parseByteValue(argv[argi + 3], degree))
      return 1;
    send_packet(buildWheelTimed(action, time, degree));
    return 0;
  }

  if (cmd == "arm-no-angle") {
    if (argc - argi != 4)
      return 1;
    uint8_t part, speed, action;
    if (!parseArmPart(argv[argi + 1], part))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseArmAction(argv[argi + 3], action))
      return 1;
    send_packet(buildArmNoAngle(part, speed, action));
    return 0;
  }

  if (cmd == "arm-relative") {
    if (argc - argi != 5)
      return 1;
    uint8_t part, speed, action;
    uint16_t angle;
    if (!parseArmPart(argv[argi + 1], part))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseArmAction(argv[argi + 3], action))
      return 1;
    if (!parseU16Value(argv[argi + 4], angle))
      return 1;
    send_packet(buildArmRelativeAngle(part, speed, action, angle));
    return 0;
  }

  if (cmd == "arm-absolute") {
    if (argc - argi != 4)
      return 1;
    uint8_t part, speed;
    uint16_t angle;
    if (!parseArmPart(argv[argi + 1], part))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], angle))
      return 1;
    send_packet(buildArmAbsoluteAngle(part, speed, angle));
    return 0;
  }

  if (cmd == "head-no-angle") {
    if (argc - argi != 3)
      return 1;
    uint8_t action, speed;
    if (!parseHeadAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    send_packet(buildHeadNoAngle(action, speed));
    return 0;
  }

  if (cmd == "head-relative") {
    if (argc - argi != 3 && argc - argi != 2)
      return 1;
    uint8_t action;
    if (!parseHeadAction(argv[argi + 1], action))
      return 1;
    if (argc - argi == 2) {
      if (action != 0x09 && action != 0x0A && action != 0x0B)
        return 1;
      send_packet(buildHeadNoAngle(action, 0x00));
      return 0;
    }
    uint16_t angle;
    if (!parseU16Value(argv[argi + 2], angle))
      return 1;
    send_packet(buildHeadRelativeAngle(action, angle));
    return 0;
  }

  if (cmd == "head-absolute") {
    if (argc - argi != 3)
      return 1;
    uint8_t action;
    uint16_t angle;
    if (!parseHeadAbsoluteAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], angle))
      return 1;
    send_packet(buildHeadAbsoluteAngle(action, angle));
    return 0;
  }

  if (cmd == "head-locate-absolute") {
    if (argc - argi != 4)
      return 1;
    uint8_t action;
    uint16_t hAngle, vAngle;
    if (!parseHeadLockAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], hAngle))
      return 1;
    if (!parseU16Value(argv[argi + 3], vAngle))
      return 1;
    send_packet(buildHeadLocateAbsolute(action, hAngle, vAngle));
    return 0;
  }

  if (cmd == "head-locate-relative") {
    if (argc - argi != 6)
      return 1;
    uint8_t action, hAngle, vAngle, hDirection, vDirection;
    if (!parseHeadLockAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], hAngle))
      return 1;
    if (!parseByteValue(argv[argi + 3], vAngle))
      return 1;
    if (!parseHeadDirection(argv[argi + 4], hDirection))
      return 1;
    if (!parseHeadDirection(argv[argi + 5], vDirection))
      return 1;
    send_packet(buildHeadLocateRelative(action, hAngle, vAngle,
                                        hDirection, vDirection));
    return 0;
  }

  if (cmd == "head-centre") {
    send_packet(buildHeadCentreLock());
    return 0;
  }

  try {
    vector<string> tokens;
    for (int i = argi + 1; i < argc; ++i)
      tokens.push_back(argv[i]);
    auto db = open_database();
    auto built = db.buildCommand(argv[argi], sanbot::parseCommandArgs(tokens));
    return send_built_command(built) ? 0 : 1;
  } catch (const exception &ex) {
    fprintf(stderr, "sanbot-mcu-bridge: %s\n", ex.what());
  }

  return 1;
}
