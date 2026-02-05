cmake_minimum_required(VERSION 3.10)
project(sanbot-mcu-bridge)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt5 COMPONENTS Widgets)

find_package(PkgConfig)
option(SANBOT_BUILD_CLI "Build the sanbot-mcu-bridge CLI" ON)
if(APPLE)
  # Most macOS users only need the GUI; the CLI depends on libusb being installed.
  set(SANBOT_BUILD_CLI OFF CACHE BOOL "Build the sanbot-mcu-bridge CLI" FORCE)
endif()

if(SANBOT_BUILD_CLI)
  if(PkgConfig_FOUND)
    pkg_check_modules(LIBUSB QUIET IMPORTED_TARGET libusb-1.0)
  endif()

  if(TARGET PkgConfig::LIBUSB)
    add_executable(sanbot-mcu-bridge
      src/main.cpp
      src/control-catalogue.cpp
      src/packet-assembler.cpp
      src/usb-send.cpp
    )

    target_link_libraries(sanbot-mcu-bridge PkgConfig::LIBUSB)
  else()
    message(WARNING "libusb-1.0 not found; skipping sanbot-mcu-bridge (CLI). Install libusb-1.0 to enable it.")
  endif()
endif()

if(Qt5Widgets_FOUND)
  add_executable(sanbot-mcu-gui
    gui-app/main.cpp
  )

  target_link_libraries(sanbot-mcu-gui Qt5::Widgets)
endif()
