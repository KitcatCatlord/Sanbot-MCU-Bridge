#include "command-database.h"
#include "control-catalogue.h"
#include "packet-assembler.h"

#include <cstdio>
#include <exception>
#include <string>
#include <vector>

using sanbot::CommandArgs;
using sanbot::CommandDatabase;

static bool expectEqual(const char *name, const std::vector<uint8_t> &actual,
                        const std::vector<uint8_t> &expected) {
  if (actual == expected)
    return true;

  std::fprintf(stderr, "%s packet mismatch\n", name);
  std::fprintf(stderr, "actual:  ");
  for (uint8_t b : actual)
    std::fprintf(stderr, "%02X ", b);
  std::fprintf(stderr, "\nexpected:");
  for (uint8_t b : expected)
    std::fprintf(stderr, "%02X ", b);
  std::fprintf(stderr, "\n");
  return false;
}

int main(int argc, char **argv) {
  try {
    std::string dbPath =
        argc > 1 ? argv[1] : CommandDatabase::findDefaultDatabasePath();
    CommandDatabase db(dbPath);

    if (db.commands().size() < 80) {
      std::fprintf(stderr, "expected at least 80 commands, got %zu\n",
                   db.commands().size());
      return 1;
    }

    auto wheelDistance = db.buildCommand(
        "wheel", CommandArgs{{"mode", "distance"},
                             {"direction", "forward"},
                             {"speed", "50"},
                             {"distance", "1000"}});
    if (!expectEqual("wheel distance", wheelDistance.bytes,
                     buildWheelDistance(0x01, 50, 1000)))
      return 1;

    auto wheelTimed = db.buildCommand(
        "wheel", CommandArgs{{"mode", "timed"},
                             {"direction", "right"},
                             {"time", "500"},
                             {"degree", "45"}});
    if (!expectEqual("wheel timed", wheelTimed.bytes,
                     buildWheelTimed(0x04, 500, 45)))
      return 1;

    auto armNoAngle = db.buildCommand("arm",
                                      CommandArgs{{"mode", "no-angle"},
                                                  {"hand", "left"},
                                                  {"speed", "40"},
                                                  {"action", "up"}});
    if (!expectEqual("arm no-angle", armNoAngle.bytes,
                     buildArmNoAngle(0x01, 40, 0x01)))
      return 1;

    auto headLocate = db.buildCommand(
        "head", CommandArgs{{"mode", "locate-absolute"},
                            {"lock", "both-lock"},
                            {"horizontal-degree", "30"},
                            {"vertical-degree", "20"}});
    if (!expectEqual("head locate absolute", headLocate.bytes,
                     buildHeadLocateAbsolute(0x03, 30, 20)))
      return 1;

    auto ambientTemperature =
        db.buildCommand("ambient-temperature", CommandArgs{});
    CommandPayload ambientPayload;
    ambientPayload.commandMode = 0x81;
    ambientPayload.orderedBytes = {0x10, 0x00};
    if (!expectEqual("ambient temperature", ambientTemperature.bytes,
                     assembleRoutedBuffer(ambientPayload, 0x01, 0x01)))
      return 1;

    std::printf("command database smoke test passed (%zu commands)\n",
                db.commands().size());
    return 0;
  } catch (const std::exception &ex) {
    std::fprintf(stderr, "command database smoke test failed: %s\n",
                 ex.what());
    return 1;
  }
}
