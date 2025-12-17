#include <array>
#include <cstdint>
#include <iostream>
#include <vector>
using namespace std;

int main() { cout << "Placeholder"; }

struct CommandPayload {
  uint8_t commandMode;
  vector<uint8_t> orderedBytes;
};

array<uint8_t, 2> toBytes16BE(uint16_t value) {
  uint8_t hi = (value >> 8) & 0xFF;
  uint8_t lo = (value) & 0xFF;
  return {hi, lo};
}
array<uint8_t, 2> toBytes16LE(uint16_t value) {
  uint8_t lo = value & 0xFF;
  uint8_t hi = (value >> 8) & 0xFF;
  return {lo, hi};
}
array<uint8_t, 4> toBytes21BE(uint32_t value) {
  uint8_t b0 = (value >> 24) & 0xFF;
  uint8_t b1 = (value >> 16) & 0xFF;
  uint8_t b2 = (value >> 8) & 0xFF;
  uint8_t b3 = value & 0xFF;
  return {b0, b1, b2, b3};
}

 // TODO: Figure out byte return array size for frameUSB
array<uint8_t> frameUSB(array<uint8_t> payload, uint8_t ackFlag) {
  const uint16_t TYPE = 0xA505;
  const uint16_t SUBTYPE = 0x0000;
  const uint16_t FRAME_HEAD = 0xA5A5;
  const int UNUSE_LEN = 7;
}
