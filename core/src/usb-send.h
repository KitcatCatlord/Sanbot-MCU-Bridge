#pragma once
#include <atomic>
#include <condition_variable>
#include <cstdint>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>
using namespace std;

class SanbotUsbManager {
public:
  static constexpr uint16_t VID = 0x0483;
  static constexpr uint16_t PID_BOTTOM = 0x5740;
  static constexpr uint16_t PID_HEAD = 0x5741;

  static constexpr int WHAT_SEND_TO_HEAD = 0x01;
  static constexpr int WHAT_SEND_TO_BOTTOM = 0x02;
  static constexpr int WHAT_SEND_TO_POINT = 0x04;

  SanbotUsbManager();
  ~SanbotUsbManager();

  void sendToHead(const vector<uint8_t> &frame);
  void sendToBottom(const vector<uint8_t> &frame);
  void sendToPoint(const vector<uint8_t> &routedFrameWithTag);

private:
  struct EndpointSet {
    struct libusb_device_handle *handle = nullptr;
    uint8_t outEp = 0;
    uint8_t inEp = 0;
    int iface = -1;
    int failCount = 0;
  };

  struct Message {
    int what;
    vector<uint8_t> data;
  };

  struct libusb_context *ctx = nullptr;
  EndpointSet bottom;
  EndpointSet head;

  thread worker;
  mutex mtx;
  condition_variable cv;
  queue<Message> msgQueue;
  atomic<bool> running{false};

  void enqueueMessage(int what, const vector<uint8_t> &data);
  void sendLoop();
  void handlePointMessage(const vector<uint8_t> &buffers);
  void sendBufferTo(EndpointSet &dev, uint16_t pid,
                    const vector<uint8_t> &buf);
  void openDevice(EndpointSet &dev, uint16_t pid);
  void closeDevice(EndpointSet &dev);
};
