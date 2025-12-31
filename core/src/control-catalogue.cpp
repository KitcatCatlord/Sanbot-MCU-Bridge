#include "control-catalogue.h"
#include "packet-assembler.h"
#include <vector>
using namespace std;

static vector<uint8_t> assembleCommand(uint8_t commandMode,
                                       const vector<int8_t> &ordered,
                                       uint8_t point_tag) {
  CommandPayload cmd;
  cmd.commandMode = commandMode;
  cmd.orderedBytes = ordered;
  return assembleRoutedBuffer(cmd, 0x01, point_tag);
}

vector<uint8_t> buildWheelNoAngle(uint8_t action, uint8_t speed,
                                  uint16_t duration, uint8_t durationMode) {
  uint8_t mode = 0x01;
  uint8_t lsb = duration & 0xFF;
  uint8_t msb = (duration >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb),
                            static_cast<int8_t>(durationMode)};
  return assembleCommand(0x01, ordered, 0x02);
}

vector<uint8_t> buildWheelRelativeAngle(uint8_t action, uint8_t speed,
                                        uint16_t angle) {
  uint8_t mode = 0x02;
  uint8_t lsb = angle & 0xFF;
  uint8_t msb = (angle >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  return assembleCommand(0x01, ordered, 0x02);
}

vector<uint8_t> buildWheelDistance(uint8_t action, uint8_t speed,
                                   uint16_t distance) {
  uint8_t mode = 0x11;
  uint8_t lsb = distance & 0xFF;
  uint8_t msb = (distance >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  return assembleCommand(0x01, ordered, 0x02);
}

vector<uint8_t> buildWheelTimed(uint8_t action, uint16_t time,
                                uint8_t degree) {
  uint8_t mode = 0x10;
  uint8_t lsb = time & 0xFF;
  uint8_t msb = (time >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb),
                            static_cast<int8_t>(degree)};
  return assembleCommand(0x01, ordered, 0x02);
}

vector<uint8_t> buildArmNoAngle(uint8_t part, uint8_t speed, uint8_t action) {
  uint8_t mode = 0x01;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(part),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(action)};
  return assembleCommand(0x03, ordered, 0x02);
}

vector<uint8_t> buildArmRelativeAngle(uint8_t part, uint8_t speed,
                                      uint8_t action, uint16_t angle) {
  uint8_t mode = 0x02;
  uint8_t lsb = angle & 0xFF;
  uint8_t msb = (angle >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(part),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  return assembleCommand(0x03, ordered, 0x02);
}

vector<uint8_t> buildArmAbsoluteAngle(uint8_t part, uint8_t speed,
                                      uint16_t angle) {
  uint8_t mode = 0x03;
  uint8_t lsb = angle & 0xFF;
  uint8_t msb = (angle >> 8) & 0xFF;
  uint8_t direction = 0x02;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(part),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(direction),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  return assembleCommand(0x03, ordered, 0x02);
}

vector<uint8_t> buildHeadNoAngle(uint8_t action, uint8_t speed) {
  uint8_t mode = 0x01;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(speed)};
  return assembleCommand(0x02, ordered, 0x01);
}

vector<uint8_t> buildHeadRelativeAngle(uint8_t action, uint16_t angle) {
  uint8_t mode = 0x02;
  uint8_t lsb = angle & 0xFF;
  uint8_t msb = (angle >> 8) & 0xFF;
  uint8_t speed = 0x00;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  return assembleCommand(0x02, ordered, 0x01);
}

vector<uint8_t> buildHeadAbsoluteAngle(uint8_t action, uint16_t angle) {
  uint8_t mode = 0x03;
  uint8_t lsb = angle & 0xFF;
  uint8_t msb = (angle >> 8) & 0xFF;
  uint8_t speed = 0x00;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  return assembleCommand(0x02, ordered, 0x01);
}

vector<uint8_t> buildHeadLocateAbsolute(uint8_t action, uint16_t hAngle,
                                        uint16_t vAngle) {
  uint8_t mode = 0x21;
  uint8_t hLsb = hAngle & 0xFF;
  uint8_t hMsb = (hAngle >> 8) & 0xFF;
  uint8_t vLsb = vAngle & 0xFF;
  uint8_t vMsb = (vAngle >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(hLsb),
                            static_cast<int8_t>(hMsb),
                            static_cast<int8_t>(vLsb),
                            static_cast<int8_t>(vMsb)};
  return assembleCommand(0x02, ordered, 0x01);
}

vector<uint8_t> buildHeadLocateRelative(uint8_t action, uint8_t hAngle,
                                        uint8_t vAngle, uint8_t hDirection,
                                        uint8_t vDirection) {
  uint8_t mode = 0x22;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action),
                            static_cast<int8_t>(hDirection),
                            static_cast<int8_t>(hAngle),
                            static_cast<int8_t>(vDirection),
                            static_cast<int8_t>(vAngle)};
  return assembleCommand(0x02, ordered, 0x01);
}

vector<uint8_t> buildHeadCentreLock() {
  uint8_t mode = 0x20;
  uint8_t action = 0x01;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(action)};
  return assembleCommand(0x02, ordered, 0x01);
}
