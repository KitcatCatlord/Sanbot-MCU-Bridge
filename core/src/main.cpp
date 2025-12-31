#include "control-catalogue.h"
#include "usb-send.h"
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>
using namespace std;

static string lowerString(string s) {
  transform(s.begin(), s.end(), s.begin(),
            [](unsigned char c) { return static_cast<char>(tolower(c)); });
  return s;
}

static bool parseByteValue(const string &s, uint8_t &out) {
  try {
    int val = stoi(s, nullptr, 0);
    if (val < 0 || val > 255)
      return false;
    out = static_cast<uint8_t>(val);
    return true;
  } catch (...) {
    return false;
  }
}

static bool parseU16Value(const string &s, uint16_t &out) {
  try {
    int val = stoi(s, nullptr, 0);
    if (val < 0 || val > 65535)
      return false;
    out = static_cast<uint16_t>(val);
    return true;
  } catch (...) {
    return false;
  }
}

static void log_packet(const vector<unsigned char> &packet) {
  for (size_t i = 0; i < packet.size(); ++i) {
    printf("%02X", packet[i]);
    if (i + 1 != packet.size())
      printf(" ");
  }
  printf("\n");
}

static bool parseWheelAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "forward")
    out = 0x01;
  else if (k == "back")
    out = 0x02;
  else if (k == "left")
    out = 0x03;
  else if (k == "right")
    out = 0x04;
  else if (k == "left-forward")
    out = 0x05;
  else if (k == "right-forward")
    out = 0x06;
  else if (k == "left-back")
    out = 0x07;
  else if (k == "right-back")
    out = 0x08;
  else if (k == "left-translation")
    out = 0x0A;
  else if (k == "right-translation")
    out = 0x0B;
  else if (k == "turn-left")
    out = 0x0C;
  else if (k == "turn-right")
    out = 0x0D;
  else if (k == "stop-turn")
    out = 0xF0;
  else if (k == "stop")
    out = 0x00;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseArmPart(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "left")
    out = 0x01;
  else if (k == "right")
    out = 0x02;
  else if (k == "both")
    out = 0x03;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseArmAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "up")
    out = 0x01;
  else if (k == "down")
    out = 0x02;
  else if (k == "stop")
    out = 0x03;
  else if (k == "reset")
    out = 0x04;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "stop")
    out = 0x00;
  else if (k == "up")
    out = 0x01;
  else if (k == "down")
    out = 0x02;
  else if (k == "left")
    out = 0x03;
  else if (k == "right")
    out = 0x04;
  else if (k == "left-up")
    out = 0x05;
  else if (k == "right-up")
    out = 0x06;
  else if (k == "left-down")
    out = 0x07;
  else if (k == "right-down")
    out = 0x08;
  else if (k == "vertical-reset")
    out = 0x09;
  else if (k == "horizontal-reset")
    out = 0x0A;
  else if (k == "centre-reset")
    out = 0x0B;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadAbsoluteAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "vertical")
    out = 0x01;
  else if (k == "horizontal")
    out = 0x02;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadLockAction(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "no-lock")
    out = 0x00;
  else if (k == "horizontal-lock")
    out = 0x01;
  else if (k == "vertical-lock")
    out = 0x02;
  else if (k == "both-lock")
    out = 0x03;
  else
    return parseByteValue(s, out);
  return true;
}

static bool parseHeadDirection(const string &s, uint8_t &out) {
  string k = lowerString(s);
  if (k == "left")
    out = 0x01;
  else if (k == "right")
    out = 0x02;
  else if (k == "up")
    out = 0x01;
  else if (k == "down")
    out = 0x02;
  else
    return parseByteValue(s, out);
  return true;
}

int main(int argc, char **argv) {
  if (argc < 2)
    return 1;

  bool debug = false;
  int argi = 1;
  if (string(argv[1]) == "--debug") {
    debug = true;
    argi = 2;
  }

  if (argi >= argc)
    return 1;

  string cmd = lowerString(argv[argi]);
  SanbotUsbManager manager;

  auto send_packet = [&](const vector<uint8_t> &packet) {
    vector<unsigned char> buf(packet.begin(), packet.end());
    if (debug) log_packet(buf);
    manager.sendToPoint(buf);
    manager.waitForPendingSends();
  };

  if (cmd == "wheel-distance") {
    if (argc - argi != 4)
      return 1;
    uint8_t action, speed;
    uint16_t distance;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], distance))
      return 1;
    send_packet(buildWheelDistance(action, speed, distance));
    return 0;
  }

  if (cmd == "wheel-relative") {
    if (argc - argi != 4)
      return 1;
    uint8_t action, speed;
    uint16_t angle;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], angle))
      return 1;
    send_packet(buildWheelRelativeAngle(action, speed, angle));
    return 0;
  }

  if (cmd == "wheel-no-angle") {
    if (argc - argi != 5)
      return 1;
    uint8_t action, speed, durationMode;
    uint16_t duration;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], duration))
      return 1;
    if (!parseByteValue(argv[argi + 4], durationMode))
      return 1;
    send_packet(buildWheelNoAngle(action, speed, duration, durationMode));
    return 0;
  }

  if (cmd == "wheel-timed") {
    if (argc - argi != 4)
      return 1;
    uint8_t action, degree;
    uint16_t time;
    if (!parseWheelAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], time))
      return 1;
    if (!parseByteValue(argv[argi + 3], degree))
      return 1;
    send_packet(buildWheelTimed(action, time, degree));
    return 0;
  }

  if (cmd == "arm-no-angle") {
    if (argc - argi != 4)
      return 1;
    uint8_t part, speed, action;
    if (!parseArmPart(argv[argi + 1], part))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseArmAction(argv[argi + 3], action))
      return 1;
    send_packet(buildArmNoAngle(part, speed, action));
    return 0;
  }

  if (cmd == "arm-relative") {
    if (argc - argi != 5)
      return 1;
    uint8_t part, speed, action;
    uint16_t angle;
    if (!parseArmPart(argv[argi + 1], part))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseArmAction(argv[argi + 3], action))
      return 1;
    if (!parseU16Value(argv[argi + 4], angle))
      return 1;
    send_packet(buildArmRelativeAngle(part, speed, action, angle));
    return 0;
  }

  if (cmd == "arm-absolute") {
    if (argc - argi != 4)
      return 1;
    uint8_t part, speed;
    uint16_t angle;
    if (!parseArmPart(argv[argi + 1], part))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    if (!parseU16Value(argv[argi + 3], angle))
      return 1;
    send_packet(buildArmAbsoluteAngle(part, speed, angle));
    return 0;
  }

  if (cmd == "head-no-angle") {
    if (argc - argi != 3)
      return 1;
    uint8_t action, speed;
    if (!parseHeadAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], speed))
      return 1;
    send_packet(buildHeadNoAngle(action, speed));
    return 0;
  }

  if (cmd == "head-relative") {
    if (argc - argi != 3)
      return 1;
    uint8_t action;
    uint16_t angle;
    if (!parseHeadAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], angle))
      return 1;
    send_packet(buildHeadRelativeAngle(action, angle));
    return 0;
  }

  if (cmd == "head-absolute") {
    if (argc - argi != 3)
      return 1;
    uint8_t action;
    uint16_t angle;
    if (!parseHeadAbsoluteAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], angle))
      return 1;
    send_packet(buildHeadAbsoluteAngle(action, angle));
    return 0;
  }

  if (cmd == "head-locate-absolute") {
    if (argc - argi != 4)
      return 1;
    uint8_t action;
    uint16_t hAngle, vAngle;
    if (!parseHeadLockAction(argv[argi + 1], action))
      return 1;
    if (!parseU16Value(argv[argi + 2], hAngle))
      return 1;
    if (!parseU16Value(argv[argi + 3], vAngle))
      return 1;
    send_packet(buildHeadLocateAbsolute(action, hAngle, vAngle));
    return 0;
  }

  if (cmd == "head-locate-relative") {
    if (argc - argi != 6)
      return 1;
    uint8_t action, hAngle, vAngle, hDirection, vDirection;
    if (!parseHeadLockAction(argv[argi + 1], action))
      return 1;
    if (!parseByteValue(argv[argi + 2], hAngle))
      return 1;
    if (!parseByteValue(argv[argi + 3], vAngle))
      return 1;
    if (!parseHeadDirection(argv[argi + 4], hDirection))
      return 1;
    if (!parseHeadDirection(argv[argi + 5], vDirection))
      return 1;
    send_packet(buildHeadLocateRelative(action, hAngle, vAngle,
                                        hDirection, vDirection));
    return 0;
  }

  if (cmd == "head-centre") {
    send_packet(buildHeadCentreLock());
    return 0;
  }

  return 1;
}
