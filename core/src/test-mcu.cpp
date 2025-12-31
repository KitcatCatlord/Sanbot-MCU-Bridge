#include "control-catalogue.h"
#include "usb-send.h"
#include <chrono>
#include <cstdio>
#include <thread>
#include <vector>
using namespace std;

static void log_packet(const vector<unsigned char> &packet) {
  for (size_t i = 0; i < packet.size(); ++i) {
    printf("%02X", packet[i]);
    if (i + 1 != packet.size())
      printf(" ");
  }
  printf("\n");
}

int main(int argc, char **argv) {
  bool debug = false;
  if (argc > 1 && string(argv[1]) == "--debug")
    debug = true;

  SanbotUsbManager manager;

  auto send_packet = [&](const vector<uint8_t> &packet) {
    vector<unsigned char> buf(packet.begin(), packet.end());
    if (debug)
      log_packet(buf);
    manager.sendToPoint(buf);
    manager.waitForPendingSends();
  };

  uint8_t left = 0x01;
  uint8_t right = 0x02;
  uint8_t up = 0x01;
  uint8_t down = 0x02;
  uint8_t speed = 0x05;
  uint16_t angle = 5;

  send_packet(buildArmRelativeAngle(left, speed, up, angle));
  this_thread::sleep_for(chrono::milliseconds(300));
  send_packet(buildArmRelativeAngle(left, speed, down, angle));
  this_thread::sleep_for(chrono::milliseconds(300));
  send_packet(buildArmRelativeAngle(right, speed, up, angle));
  this_thread::sleep_for(chrono::milliseconds(300));
  send_packet(buildArmRelativeAngle(right, speed, down, angle));
  this_thread::sleep_for(chrono::milliseconds(300));

  return 0;
}
