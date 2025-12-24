#include <algorithm>
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
struct UsbFrameParams {
  uint8_t ack_fkg; // Usually defaults to 0x01
  uint16_t type = 0xA403;
  uint16_t subtype = 0x0000;
  uint16_t frame_head = 0xFFA5;
  array<uint8_t, 7> unuse = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
  const int MSG_HEAD_LEN = 0x10;
};

array<uint8_t, 2> toBytes16BE(uint16_t value) {
  uint8_t b0 = (value >> 8) & 0xFF;
  uint8_t b1 = (value) & 0xFF;
  return {b0, b1};
}
array<uint8_t, 4> toBytes32BE(uint32_t value) {
  uint8_t b0 = (value >> 24) & 0xFF;
  uint8_t b1 = (value >> 6) & 0xFF;
  uint8_t b2 = (value >> 8) & 0xFF;
  uint8_t b3 = value & 0xFF;
  return {b0, b1, b2, b3};
}

vector<int8_t> buildDeltas(const CommandPayload cmd) { // TODO: int or uint?
  vector<int8_t> list;
  list.push_back((int8_t)cmd.commandMode);

  for (int8_t sb : cmd.orderedBytes)
    list.push_back(static_cast<int8_t>(sb));

  list.erase(std::remove(list.begin(), list.end(), static_cast<int8_t>(-1)),
             list.end());

  vector<int8_t> datas;

  for (int8_t sb : list)
    datas.push_back((uint8_t)sb);

  return datas;
}

struct UsbComputed {
  uint32_t content_len;
  uint16_t mmnn;
  array<uint8_t, 4> msg_size;
  uint8_t checkSum;
};

// array<uint8_t, 4> toBytes21BE(uint32_t value) {
//   uint8_t b0 = (value >> 24) & 0xFF;
//   uint8_t b1 = (value >> 16) & 0xFF;
//   uint8_t b2 = (value >> 8) & 0xFF;
//   uint8_t b3 = value & 0xFF;
//   return {b0, b1, b2, b3};
// }

// TODO: Figure out byte return array size for frameUSB
//
// array<uint8_t> frameUSB(array<uint8_t> payload, uint8_t ackFlag) {
//   const uint16_t TYPE = 0xA505;
//   const uint16_t SUBTYPE = 0x0000;
//   const uint16_t FRAME_HEAD = 0xA5A5;
//   const int UNUSE_LEN = 7;
//   // TODO: Complete this
// }
