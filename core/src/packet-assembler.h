#pragma once
#include <array>
#include <cstdint>
#include <vector>
using namespace std;

struct CommandPayload {
  uint8_t commandMode;
  vector<int8_t> orderedBytes;
};

struct UsbFrameParams {
  uint8_t ack_flg;
  uint16_t type = 0xA403;
  uint16_t subtype = 0x0000;
  uint16_t frame_head = 0xFFA5;
  array<uint8_t, 7> unuse = {0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
  const int MSG_HEAD_LEN = 0x10;
};

struct UsbComputed {
  uint32_t content_len;
  uint16_t mmnn;
  array<uint8_t, 4> msg_size;
  uint8_t checkSum;
};

array<uint8_t, 2> toBytes16BE(uint16_t value);
array<uint8_t, 4> toBytes32BE(uint32_t value);
vector<uint8_t> buildDatas(const CommandPayload &cmd);
UsbComputed computeUsbFieldsAndChecksum(const UsbFrameParams &params,
                                        const vector<uint8_t> &datas);
vector<uint8_t> buildUsbFrame(const UsbFrameParams &params,
                              const vector<uint8_t> &datas);
vector<uint8_t> appendPointTagForRouting(const vector<uint8_t> &usbFrame,
                                         uint8_t point_tag);
vector<uint8_t> assembleUsbFrameFromCommand(const CommandPayload &cmd,
                                            uint8_t ack_flg);
vector<uint8_t> assembleRoutedBuffer(const CommandPayload &cmd, uint8_t ack_flg,
                                     uint8_t point_tag);
