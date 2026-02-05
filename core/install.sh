#!/bin/bash
set -euo pipefail

g++ -std=c++20 src/main.cpp src/control-catalogue.cpp src/packet-assembler.cpp src/usb-send.cpp -o sanbot-mcu-bridge -lusb-1.0
g++ -std=c++20 gui-app/main.cpp -o sanbot-mcu-gui $(pkg-config --cflags --libs Qt5Widgets)
