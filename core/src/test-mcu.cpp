#include "usb-send.cpp"
#include <algorithm>
#include <array>
#include <cstdint>
#include <thread>
#include <vector>
using namespace std;

array<uint8_t, 2> toBytes16BE(uint16_t value) {
  uint8_t b0 = (value >> 8) & 0xFF;
  uint8_t b1 = value & 0xFF;
  return {b0, b1};
}

array<uint8_t, 4> toBytes32BE(uint32_t value) {
  uint8_t b0 = (value >> 24) & 0xFF;
  uint8_t b1 = (value >> 16) & 0xFF;
  uint8_t b2 = (value >> 8) & 0xFF;
  uint8_t b3 = value & 0xFF;
  return {b0, b1, b2, b3};
}

vector<uint8_t> buildDatas(uint8_t commandMode,
                           const vector<int8_t> &orderedBytes) {
  vector<int8_t> list;
  list.reserve(1 + orderedBytes.size());
  list.push_back(static_cast<int8_t>(commandMode));
  for (int8_t b : orderedBytes)
    list.push_back(b);
  list.erase(remove(list.begin(), list.end(), static_cast<int8_t>(-1)),
             list.end());
  vector<uint8_t> out;
  out.reserve(list.size());
  for (int8_t b : list)
    out.push_back(static_cast<uint8_t>(b));
  return out;
}

vector<uint8_t> buildUsbFrame(const vector<uint8_t> &datas, uint8_t ack) {
  uint16_t type = 0xA403;
  uint16_t subtype = 0x0000;
  uint16_t frame_head = 0xFFA5;
  array<uint8_t, 7> unuse = {0, 0, 0, 0, 0, 0, 0};

  uint32_t content_len = static_cast<uint32_t>(datas.size() + 5 + 1);
  uint16_t mmnn = static_cast<uint16_t>(datas.size() + 1);
  array<uint8_t, 4> msg_size = toBytes32BE(content_len);

  auto fh = toBytes16BE(frame_head);
  uint32_t data_sum = 0;
  data_sum += fh[0];
  data_sum += fh[1];
  data_sum += ack;
  data_sum += mmnn;
  for (auto b : datas)
    data_sum += b;
  uint8_t checksum = static_cast<uint8_t>(data_sum & 0xFF);

  vector<uint8_t> frame;
  frame.reserve(0x10 + content_len);
  auto t = toBytes16BE(type);
  frame.insert(frame.end(), t.begin(), t.end());
  auto st = toBytes16BE(subtype);
  frame.insert(frame.end(), st.begin(), st.end());
  frame.insert(frame.end(), msg_size.begin(), msg_size.end());
  frame.push_back(ack);
  frame.insert(frame.end(), unuse.begin(), unuse.end());
  frame.insert(frame.end(), fh.begin(), fh.end());
  frame.push_back(ack);
  auto mmnn_bytes = toBytes16BE(mmnn);
  frame.insert(frame.end(), mmnn_bytes.begin(), mmnn_bytes.end());
  frame.insert(frame.end(), datas.begin(), datas.end());
  frame.push_back(checksum);
  return frame;
}

vector<uint8_t> appendPointTag(const vector<uint8_t> &frame,
                               uint8_t point_tag) {
  vector<uint8_t> routed = frame;
  routed.push_back(point_tag);
  return routed;
}

vector<uint8_t> buildHandNudge(uint8_t whichHand, uint8_t direction,
                               uint16_t angle, uint8_t speed) {
  uint8_t mode = 0x02;
  uint8_t lsb = angle & 0xFF;
  uint8_t msb = (angle >> 8) & 0xFF;
  vector<int8_t> ordered = {static_cast<int8_t>(mode),
                            static_cast<int8_t>(whichHand),
                            static_cast<int8_t>(speed),
                            static_cast<int8_t>(direction),
                            static_cast<int8_t>(lsb),
                            static_cast<int8_t>(msb)};
  vector<uint8_t> datas = buildDatas(0x03, ordered);
  vector<uint8_t> frame = buildUsbFrame(datas, 0x01);
  return appendPointTag(frame, 0x02);
}

int main() {
  SanbotUsbManager manager;

  uint8_t left = 0x01;
  uint8_t right = 0x02;
  uint8_t up = 0x01;
  uint8_t down = 0x02;
  uint8_t speed = 0x05;
  uint16_t angle = 5;

  manager.sendToPoint(buildHandNudge(left, up, angle, speed));
  this_thread::sleep_for(chrono::milliseconds(300));
  manager.sendToPoint(buildHandNudge(left, down, angle, speed));
  this_thread::sleep_for(chrono::milliseconds(300));
  manager.sendToPoint(buildHandNudge(right, up, angle, speed));
  this_thread::sleep_for(chrono::milliseconds(300));
  manager.sendToPoint(buildHandNudge(right, down, angle, speed));
  this_thread::sleep_for(chrono::milliseconds(300));

  return 0;
}
