cmake_minimum_required(VERSION 3.10)
project(sanbot-mcu-bridge)
set(CMAKE_CXX_STANDARD 20)

find_package(SQLite3)
find_package(PkgConfig)
if(APPLE)
  # The CLI depends on libusb; default off on macOS but keep explicit opt-in working.
  option(SANBOT_BUILD_CLI "Build the sanbot-mcu-bridge CLI" OFF)
else()
  option(SANBOT_BUILD_CLI "Build the sanbot-mcu-bridge CLI" ON)
endif()
option(SANBOT_BUILD_COMMAND_DB_SMOKE "Build the database command smoke test" ON)

if(SQLite3_FOUND)
  add_library(sanbot-mcu-core STATIC
    src/control-catalogue.cpp
    src/command-database.cpp
    src/packet-assembler.cpp
  )

  target_include_directories(sanbot-mcu-core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/src
  )
  target_link_libraries(sanbot-mcu-core PUBLIC SQLite::SQLite3)
else()
  message(WARNING "SQLite3 not found; skipping sanbot-mcu-core and database-backed commands.")
endif()

if(SANBOT_BUILD_CLI)
  if(PkgConfig_FOUND)
    pkg_check_modules(LIBUSB QUIET IMPORTED_TARGET libusb-1.0)
  endif()

  if(TARGET PkgConfig::LIBUSB AND TARGET sanbot-mcu-core)
    add_executable(sanbot-mcu-bridge
      src/main.cpp
      src/usb-send.cpp
    )

    target_link_libraries(sanbot-mcu-bridge sanbot-mcu-core PkgConfig::LIBUSB)
  else()
    message(WARNING "libusb-1.0 or sanbot-mcu-core not found; skipping sanbot-mcu-bridge (CLI). Install libusb-1.0 and SQLite3 to enable it.")
  endif()
endif()

if(SANBOT_BUILD_COMMAND_DB_SMOKE AND TARGET sanbot-mcu-core)
  enable_testing()
  add_executable(sanbot-command-db-smoke
    src/command-database-smoke.cpp
  )
  target_link_libraries(sanbot-command-db-smoke sanbot-mcu-core)
  add_test(
    NAME command-database-smoke
    COMMAND sanbot-command-db-smoke
      ${CMAKE_CURRENT_SOURCE_DIR}/../mcu-command-database/sanbot_mcu_commands.sqlite
  )
endif()
