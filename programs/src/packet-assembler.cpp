#include <iostream>
#include <cstdint>
#include <vector>
#include <array>
using namespace std;

int main() {
  cout << "Placeholder";
}

struct CommandPayload {
  uint8_t commandMode;
  vector<uint8_t> orderedBytes;
};

array<uint8_t, 2> toBytes16BE(uint16_t value) {
  uint8_t hi = (value >> 8) & 0xFF;
  uint8_t lo = (value) & 0xFF;
  return {hi, lo};
}
