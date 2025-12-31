cmake_minimum_required(VERSION 3.10)
project(sanbot-mcu-bridge)
set(CMAKE_CXX_STANDARD 20)

add_executable(sanbot-mcu-bridge
  src/main.cpp
  src/control-catalogue.cpp
  src/packet-assembler.cpp
  src/usb-send.cpp
)

target_link_libraries(sanbot-mcu-bridge usb-1.0)
