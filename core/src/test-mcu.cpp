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

  manager.sendToPoint(buildArmRelativeAngle(left, speed, up, angle));
  this_thread::sleep_for(chrono::milliseconds(300));
  manager.sendToPoint(buildArmRelativeAngle(left, speed, down, angle));
  this_thread::sleep_for(chrono::milliseconds(300));
  manager.sendToPoint(buildArmRelativeAngle(right, speed, up, angle));
  this_thread::sleep_for(chrono::milliseconds(300));
  manager.sendToPoint(buildArmRelativeAngle(right, speed, down, angle));
  this_thread::sleep_for(chrono::milliseconds(300));

  return 0;
}
