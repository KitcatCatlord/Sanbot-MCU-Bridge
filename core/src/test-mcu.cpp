#include "control-catalogue.h"
#include "usb-send.h"
#include <chrono>
#include <thread>
#include <vector>
using namespace std;

int main() {
  SanbotUsbManager manager;

  uint8_t left = 0x01;
  uint8_t right = 0x02;
  uint8_t up = 0x01;
  uint8_t down = 0x02;
  uint8_t speed = 0x05;
  uint16_t angle = 5;
  {
    vector<uint8_t> v = buildArmRelativeAngle(left, speed, up, angle);
    vector<unsigned char> buf(v.begin(), v.end());
    manager.sendToPoint(buf);
  }
  this_thread::sleep_for(chrono::milliseconds(300));
  {
    vector<uint8_t> v = buildArmRelativeAngle(left, speed, down, angle);
    vector<unsigned char> buf(v.begin(), v.end());
    manager.sendToPoint(buf);
  }
  this_thread::sleep_for(chrono::milliseconds(300));
  {
    vector<uint8_t> v = buildArmRelativeAngle(right, speed, up, angle);
    vector<unsigned char> buf(v.begin(), v.end());
    manager.sendToPoint(buf);
  }
  this_thread::sleep_for(chrono::milliseconds(300));
  {
    vector<uint8_t> v = buildArmRelativeAngle(right, speed, down, angle);
    vector<unsigned char> buf(v.begin(), v.end());
    manager.sendToPoint(buf);
  }
  this_thread::sleep_for(chrono::milliseconds(300));

  return 0;
}
