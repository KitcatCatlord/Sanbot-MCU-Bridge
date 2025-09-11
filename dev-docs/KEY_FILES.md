# Sanbot Key Files and Hardware Control Map

This document lists the key files involved in hardware control on the stock Sanbot system image, where commands are sent/received, and how the MCUs connect over USB.

## Android App + Services

- `Sanbot-Original-Software/mounted-fw/app/main-release.apk` – Main system app containing the core service and MCU control logic.
- `tools/decompiled/main-release/smali/com/sunbo/main/MainService.smali` – Android `Service` coordinating robot features, implements `com/qihan/mcumanager/MCUManager$MCUListener`.
- `tools/decompiled/main-release/unknown/com/sunbo/main/aidl/IMyService.aidl` – AIDL for client commands to the main service.
- `tools/decompiled/main-release/unknown/com/sunbo/main/aidl/IMyServiceCallback.aidl` – AIDL for callbacks from main service.
- `tools/decompiled/main-release/unknown/com/sunbo/main/aidl/ZigbeeRemoteService.aidl` – AIDL to control ZigBee module.
- `tools/decompiled/main-release/unknown/com/sunbo/main/aidl/ZigbeeCallback.aidl` – Callback AIDL for ZigBee notifications.

## MCU Routing and USB Transport

- `tools/decompiled/main-release/smali/com/qihan/mcumanager/MCUManager.smali`
  - Entry points: `MCUSend(I,[B)`, `MCUSendToHead([B)`, `MCUSendToBottom([B)`.
  - Initializes USB via `UsbMessageMrg.getInstance().initUsbMessageMrg(...)`.
  - Uses `UsbMessageMrg.sendMessageToPoint/Head/Bottom` to write packets over USB.

- `tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/UsbMessageMrg.smali`
  - Enumerates and opens the two MCU USB devices (Vendor/Product):
    - Bottom MCU: `VID 0x0483`, `PID 0x5740` (STM32 VCP) – see `enumerateBottomDevice`.
    - Head MCU:   `VID 0x0483`, `PID 0x5741` – see `enumerateHeadDevice`.
  - Claims interfaces and selects bulk endpoints:
    - Assigns `mEpBulkOut_*` and `mEpBulkIn_*` via `assignBottomEndpoint`/`assignHeadEndpoint`.
  - Performs IO via `UsbDeviceConnection.bulkTransfer(endpoint, buffer, length, timeout)`.
  - Sends by point: `sendMessageToBottom([B)`, `sendMessageToHead([B)`, `sendMessageToPoint([B)`; core handler is `sendMessageToMcu(Message)`.

- `tools/decompiled/main-release/smali/com/qihan/uvccamera/USBCommand.smali`
  - Defines the USB packet frame used for MCU messages. Layout (big picture):
    - `type` (2B) + `subtype` (2B) + `msg_size` (4B) + `ack_flg` (1B) + `unuse` (7B)
    - `frame_head` (2B) + `ack_flg` (1B) + `mmnn` (2B) + `datas` (N) + `checkSum` (1B)
    - After building the frame, an extra trailing `point_tag` byte is appended by each command wrapper.
  - Defaults: `type = 0xA403` (bytes `A4 03`), `frame_head = 0xFFA5` (per short constants), ack flag typically `0x01`.

## Command Builders (examples)

- `tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HeartBeatCommand.smali`
  - Command bytes: `[0x04, 0x08, switchMode, (optional LSB, MSB)]`, then wrapped by `USBCommand` and point tag appended.

- `tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WheelUSBCommand.smali`
  - Builds motion payloads for drive/turn/time/distance; sets `point_tag = 0x02` (Bottom MCU).

- `tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/LEDLightCommand.smali` – LED control (head/bottom via `whichLight` and `point_tag`).
- Additional hardware queries/commands live under `com/qihan/uvccamera/bean/*` (gyro, buttons, projector, battery, upgrade, etc.).

## ZigBee

- ZigBee AIDL: see `ZigbeeRemoteService.aidl` and `ZigbeeCallback.aidl` above.
- Native library present in app APKs: `Sanbot-Original-Software/mounted-fw/app/main-release.apk -> lib/armeabi-v7a/libshuncomzigbee.so`.

## System USB/TTY Evidence

- `Sanbot-Original-Software/mounted-fw/build.prop:62` → `rild.libargs=-d/dev/ttyUSB2` (cell modem)
- `Sanbot-Original-Software/mounted-fw/etc/bluetooth/bt_vendor.conf:2` → `/dev/ttyS1`
- `Sanbot-Original-Software/mounted-fw/etc/gps/gpsconfig.xml:5` → `/dev/ttyS2`
- Kernel exports include `usb_serial_*`, `uart_*`, `tty_*` (Android kernel side).

## What Sends/Receives Commands

- High-level managers in OpenSDK (apps call these):
- `tools/Sanbot-Helpers/function/unit/*Manager.smali` (WheelMotionManager, HeadMotionManager, HandMotionManager, HardWareManager, ZigbeeManager, etc.).
  - These build an `Order` with `FuncConstant` and send via `BindBaseInterface.sendCommandToMainService(...)` to `MainService`.

- Main routing and IO:
  - `MainService` → `MCUManager` → `UsbMessageMrg` → USB bulk endpoints on the two MCU devices.

## Buildable Helpers in This Repo

- `tools/Sanbot-C-Helpers` – C representations of the data “beans” (LED, SpeakOption, etc.).
  - Note: These C helpers are experimental and not used by the Python library; listed here for reference only.

## USB MCU IDs

- Bottom MCU: `VID 0x0483`, `PID 0x5740` (STM32 VCP)
- Head MCU:   `VID 0x0483`, `PID 0x5741`
- Point tag convention (app payloads): Head = `0x01`, Bottom = `0x02`.
