#pragma once
#include <cstdint>
#include <vector>
using namespace std;

vector<uint8_t> buildWheelNoAngle(uint8_t action, uint8_t speed,
                                  uint16_t duration, uint8_t durationMode);
vector<uint8_t> buildWheelRelativeAngle(uint8_t action, uint8_t speed,
                                        uint16_t angle);
vector<uint8_t> buildWheelDistance(uint8_t action, uint8_t speed,
                                   uint16_t distance);
vector<uint8_t> buildWheelTimed(uint8_t action, uint16_t time,
                                uint8_t degree);

vector<uint8_t> buildArmNoAngle(uint8_t part, uint8_t speed, uint8_t action);
vector<uint8_t> buildArmRelativeAngle(uint8_t part, uint8_t speed,
                                      uint8_t action, uint16_t angle);
vector<uint8_t> buildArmAbsoluteAngle(uint8_t part, uint8_t speed,
                                      uint16_t angle);

vector<uint8_t> buildHeadNoAngle(uint8_t action, uint8_t speed);
vector<uint8_t> buildHeadRelativeAngle(uint8_t action, uint16_t angle);
vector<uint8_t> buildHeadAbsoluteAngle(uint8_t action, uint16_t angle);
vector<uint8_t> buildHeadLocateAbsolute(uint8_t action, uint16_t hAngle,
                                        uint16_t vAngle);
vector<uint8_t> buildHeadLocateRelative(uint8_t action, uint8_t hAngle,
                                        uint8_t vAngle, uint8_t hDirection,
                                        uint8_t vDirection);
vector<uint8_t> buildHeadCentreLock();
