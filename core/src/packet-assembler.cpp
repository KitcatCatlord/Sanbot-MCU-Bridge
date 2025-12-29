#include <algorithm>
#include <array>
#include <cstdint>
#include <iostream>
#include <vector>
using namespace std;

int main() { cout << "Placeholder"; }

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

array<uint8_t, 2> toBytes16BE(uint16_t value) {
  uint8_t b0 = (value >> 8) & 0xFF;
  uint8_t b1 = (value) & 0xFF;
  return {b0, b1};
}

array<uint8_t, 4> toBytes32BE(uint32_t value) {
  uint8_t b0 = (value >> 24) & 0xFF;
  uint8_t b1 = (value >> 16) & 0xFF;
  uint8_t b2 = (value >> 8) & 0xFF;
  uint8_t b3 = value & 0xFF;
  return {b0, b1, b2, b3};
}

vector<uint8_t> buildDatas(const CommandPayload &cmd) {
  vector<int8_t> list;
  list.reserve(1 + cmd.orderedBytes.size());
  list.push_back(static_cast<int8_t>(cmd.commandMode));

  for (int8_t sb : cmd.orderedBytes)
    list.push_back(sb);

  list.erase(remove(list.begin(), list.end(), static_cast<int8_t>(-1)),
             list.end());

  vector<uint8_t> datas;
  datas.reserve(list.size());

  for (int8_t sb : list)
    datas.push_back(static_cast<uint8_t>(sb));

  return datas;
}

struct UsbComputed {
  uint32_t content_len;
  uint16_t mmnn;
  array<uint8_t, 4> msg_size;
  uint8_t checkSum;
};

UsbComputed computeUsbFieldsAndChecksum(const UsbFrameParams &params,
                                        const vector<uint8_t> &datas) {
  UsbComputed out;
  out.content_len = static_cast<uint32_t>(datas.size() + 5 + 1);
  out.mmnn = static_cast<uint16_t>(datas.size() + 1);
  out.msg_size = toBytes32BE(out.content_len);

  auto fh = toBytes16BE(params.frame_head);
  uint32_t data_sum = 0;
  data_sum += fh[0];
  data_sum += fh[1];
  data_sum += params.ack_flg;
  data_sum += out.mmnn;
  for (auto b : datas)
    data_sum += b;

  out.checkSum = static_cast<uint8_t>(data_sum & 0xFF);
  return out;
}

vector<uint8_t> buildUsbFrame(const UsbFrameParams &params,
                              const vector<uint8_t> &datas) {
  UsbComputed computed = computeUsbFieldsAndChecksum(params, datas);

  vector<uint8_t> frame;
  frame.reserve(params.MSG_HEAD_LEN + computed.content_len);
  auto t = toBytes16BE(params.type);
  frame.insert(frame.end(), t.begin(), t.end());
  auto st = toBytes16BE(params.subtype);
  frame.insert(frame.end(), st.begin(), st.end());
  frame.insert(frame.end(), computed.msg_size.begin(), computed.msg_size.end());
  frame.push_back(params.ack_flg);
  frame.insert(frame.end(), params.unuse.begin(), params.unuse.end());

  auto fh = toBytes16BE(params.frame_head);
  frame.insert(frame.end(), fh.begin(), fh.end());
  frame.push_back(params.ack_flg);
  auto mmnn = toBytes16BE(computed.mmnn);
  frame.insert(frame.end(), mmnn.begin(), mmnn.end());

  frame.insert(frame.end(), datas.begin(), datas.end());
  frame.push_back(computed.checkSum);

  return frame;
}

vector<uint8_t> appendPointTagForRouting(const vector<uint8_t>& usbFrame,
                                         uint8_t point_tag) {
  vector<uint8_t> routed = usbFrame;
  routed.push_back(point_tag);
  return routed;
}

vector<uint8_t> assembleUsbFrameFromCommand(const CommandPayload& cmd,
                                            uint8_t ack_flg) {
  UsbFrameParams params;
  params.ack_flg = ack_flg;

  vector<uint8_t> datas = buildDatas(cmd);
  return buildUsbFrame(params, datas);
}

vector<uint8_t> assembleRoutedBuffer(const CommandPayload& cmd, uint8_t ack_flg,
                                     uint8_t point_tag) {
  vector<uint8_t> usbFrame = assembleUsbFrameFromCommand(cmd, ack_flg);
  return appendPointTagForRouting(usbFrame, point_tag);
}
