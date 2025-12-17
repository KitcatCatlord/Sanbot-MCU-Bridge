# Compiled by ChatGPT Codex from original firmware files

# ======================================================
# Complete MCU Command Catalog (original .smali)
# ======================================================
#
# Purpose:
#   Every MCU command slot (0x01–0x68) from the stock Sanbot firmware,
#   showing the exact payload layout, commandMode byte, and MCU target
#   routing as implemented in the original smali classes.
#
# Key sources (smali):
#   - tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/*.smali
#   - tools/decompiled/main-release/smali/com/qihan/uvccamera/USBCommand.smali
#   - tools/decompiled/main-release/smali/com/qihan/uvccamera/DecodeCommand.smali
#   - MCU command switch table: MCUCmdGetByte in UsbMessageMrg.smali
#
# Companion guides:
#   - Guides/USB_Send.md   — queueing + bulkTransfer paths
#   - Guides/USB_Receive.md— frame splitting + checksum
#
# Notes on accuracy:
#   - Payload orders are taken directly from each bean’s getCommandBytes()
#     (or equivalent) in the smali. Fields left as -1 in constructors are
#     removed before sending (see iterator/remove logic in each bean).
#   - ack_flag defaults to 0x01 in all beans unless the smali sets it
#     otherwise (none do in this set).
#   - point_tag is appended inside getMessageCommand() exactly as in smali.
#     Most beans force a tag (1=head, 2=bottom, 3=broadcast). Some leave
#     point_tag=-1 (passthrough/direct send).
#   - command_mode_hex below is the first byte added to the payload by
#     getCommandBytes() (e.g., 0x04 for most actuator commands, 0x81/0x82
#     for queries/telemetry, 0x05/0x06/0xA0/0xA1 for specials).
#
# How to send (matches firmware):
#   1) Instantiate the bean, set its public fields.
#   2) Call getMessageCommand() → returns USBCommand frame + trailing point_tag.
#      - If you use UsbMessageMrg.sendMessageToPoint(), the firmware will
#        strip the trailing point_tag and route correctly.
#      - If you bulkTransfer directly to an OUT endpoint, drop the trailing
#        point_tag yourself (frame is everything except the last byte).
#   3) bulkTransfer(out_endpoint, frame, len(frame), timeout_ms).
#
# Receive decoding:
#   - ConvertUtils.returnListByte() / isComplete() split and checksum frames.
#   - DecodeCommand.smali maps inbound frames back to bean objects; a few
#     commonly needed offsets are summarized near the end of this file.

# -----------------------------
# 1) Command map (0x01–0x68)
# -----------------------------
#
# MCU target column reflects the tag/route chosen in the bean:
#   head   = point_tag 0x01, head MCU
#   bottom = point_tag 0x02, bottom MCU
#   broadcast = point_tag 0x03 (head then bottom)
#   dynamic/passthrough = tag set by bean logic or left -1; see payload notes.

| ID | Hex | Class | mode | target |
|---:|----|-------|------|--------|
| 1 | 0x01 | WheelUSBCommand | 0x01 | bottom |
| 2 | 0x02 | HeadUSBCommand | 0x02 | head |
| 3 | 0x03 | HandUSBCommand | 0x03 | bottom |
| 4 | 0x04 | WhiteLightCommand | 0x04 | head |
| 5 | 0x05 | LEDLightCommand | 0x04 | dynamic |
| 6 | 0x06 | ProjectorCommand | 0x04 | head |
| 7 | 0x07 | SpeakerCommand | 0x04 | head |
| 8 | 0x08 | AutoBatteryCommand | 0x04 | bottom |
| 9 | 0x09 | DanceCommand | 0x04 | broadcast |
| 10 | 0x0A | SelfCheckedCommand | 0x04 | dynamic |
| 11 | 0x0B | HeartBeatCommand | 0x04 | passthrough |
| 12 | 0x0C | AutoReportCommand | 0x80 | passthrough |
| 13 | 0x0D | QueryBatteryCommand | 0x81 | bottom |
| 14 | 0x0E | QueryObstacleCommand | 0x81 | bottom |
| 15 | 0x0F | BatteryChangeCommand | 0x81 | bottom |
| 16 | 0x10 | QueryBatteryCommand | 0x81 | bottom |
| 17 | 0x11 | QueryObstacleCommand | 0x81 | bottom |
| 18 | 0x12 | BatteryChangeCommand | 0x81 | bottom |
| 19 | 0x13 | BatteryTemperatureCommand | 0x81 | bottom |
| 20 | 0x14 | GyroscopeCommand | 0x82 | bottom |
| 21 | 0x15 | VoiceLocation | 0x82 | head |
| 22 | 0x16 | TouchSwitch | 0x83 | passthrough |
| 23 | 0x17 | MotorSelfCheck | 0x83 | passthrough |
| 24 | 0x18 | IRSensor | 0x83 | passthrough |
| 25 | 0x19 | TouchSensor | 0x83 | passthrough |
| 26 | 0x1A | AccelerateSensor | 0x83 | bottom |
| 27 | 0x1B | WanderCommand | 0x04 | head |
| 28 | 0x1C | ProjectorImageSetting | 0x04 | head |
| 29 | 0x1D | ProjectorTiXingSetting | 0x04 | head |
| 30 | 0x1E | ProjectorPictureSetting | 0x04 | head |
| 31 | 0x1F | ProjectorExpertMode | 0x04 | head |
| 32 | 0x20 | ProjectorOtherSetting | 0x04 | head |
| 33 | 0x21 | QueryPIRCommand | 0x81 | bottom |
| 34 | 0x22 | QueryMotorStatus | 0x81 | dynamic |
| 35 | 0x23 | QueryGyroscopeStatus | 0x81 | bottom |
| 36 | 0x24 | QueryTouchSwitch | 0x81 | dynamic |
| 37 | 0x25 | ProjectorTypeSetting | 0x04 | head |
| 38 | 0x26 | Detect3DData | 0x82 | bottom |
| 39 | 0x27 | QueryMovementStatus | 0x81 | dynamic |
| 40 | 0x28 | QueryHideObstacleStatus | 0x81 | bottom |
| 41 | 0x29 | MotorLockSetting | 0x05 | dynamic |
| 42 | 0x2A | — | — | — |
| 43 | 0x2B | — | — | — |
| 44 | 0x2C | — | — | — |
| 45 | 0x2D | — | — | — |
| 46 | 0x2E | — | — | — |
| 47 | 0x2F | — | — | — |
| 48 | 0x30 | — | — | — |
| 49 | 0x31 | — | — | — |
| 50 | 0x32 | — | — | — |
| 51 | 0x33 | QueryIRReceiveStatus | 0x81 | bottom |
| 52 | 0x34 | ZigbeeCommand | 0xA0 | head |
| 53 | 0x35 | MCUUpgradeCommand | 0x04 | broadcast |
| 54 | 0x36 | MCUResetCommand | 0x04 | passthrough |
| 55 | 0x37 | QueryUpgradeStatus | 0x81 | broadcast |
| 56 | 0x38 | QueryMCUVersion | 0x81 | passthrough |
| 57 | 0x39 | ChangePileCommand | 0xA1 | bottom |
| 58 | 0x3A | AutoChangeStatus | 0x81 | bottom |
| 59 | 0x3B | IllegalUseCommand | 0x81 | broadcast |
| 60 | 0x3C | ProjectorOutputSetting | 0x04 | head |
| 61 | 0x3D | ProjectorImageQualitySetting | 0x04 | head |
| 62 | 0x3E | BlackShieldSwitch | 0x04 | bottom |
| 63 | 0x3F | LiliNormalExpression | 0x06 | head |
| 64 | 0x40 | AmbientTemperature | 0x81 | head |
| 65 | 0x41 | QueryOptocouplerStatus | 0x81 | dynamic |
| 66 | 0x42 | — | — | — |
| 67 | 0x43 | QueryIRSender | 0x81 | broadcast |
| 68 | 0x44 | BottomEncoderConnection | 0x81 | bottom |
| 69 | 0x45 | QuerySPIFLASHStatus | 0x81 | broadcast |
| 70 | 0x46 | QueryUARTConnection | 0x81 | broadcast |
| 71 | 0x47 | QueryProjectorConnection | 0x81 | head |
| 72 | 0x48 | QueryPhotoelectricSwitch | 0x81 | broadcast |
| 73 | 0x49 | FollowSwitch | 0x04 | bottom |
| 74 | 0x4A | QueryButtonStatus | 0x81 | head |
| 75 | 0x4B | QueryProjectorSwitch | 0x81 | head |
| 76 | 0x4C | PhotoelectricAbnormal | 0x81 | dynamic |
| 77 | 0x4D | HideModeSwitch | 0x04 | passthrough |
| 78 | 0x4E | MotorDefendCommand | 0x05 | dynamic |
| 79 | 0x4F | QueryHideCatStatus | 0x81 | passthrough |
| 80 | 0x50 | SetWhiteBrightness | 0x04 | passthrough |
| 81 | 0x51 | QueryWhiteBrightness | 0x04 | passthrough |
| 82 | 0x52 | RingArrayReset | 0x82 | passthrough |
| 83 | 0x53 | RingArrayAdjust | 0x82 | passthrough |
| 84 | 0x54 | RingArrayDegree | 0x82 | passthrough |
| 85 | 0x55 | QueryExpressionVersion | 0x81 | passthrough |
| 86 | 0x56 | SetExpressionVersion | 0x04 | passthrough |
| 87 | 0x57 | QueryExpressionStatus | 0x81 | passthrough |
| 88 | 0x58 | — | — | — |
| 89 | 0x59 | — | — | — |
| 90 | 0x5A | — | — | — |
| 91 | 0x5B | — | — | — |
| 92 | 0x5C | — | — | — |
| 93 | 0x5D | — | — | — |
| 94 | 0x5E | — | — | — |
| 95 | 0x5F | — | — | — |
| 96 | 0x60 | — | — | — |
| 97 | 0x61 | — | — | — |
| 98 | 0x62 | — | — | — |
| 99 | 0x63 | — | — | — |
| 100 | 0x64 | — | — | — |
| 101 | 0x65 | — | — | — |
| 102 | 0x66 | — | — | — |
| 103 | 0x67 | — | — | — |
| 104 | 0x68 | BodyRecover | 0x04 | passthrough |

# -----------------------------------------
# 2) Payload skeletons (exact smali order)
# -----------------------------------------
#
# - Order is exactly as added in getCommandBytes() before -1 stripping.
# - Any byte set to -1 is removed at runtime (see iterator().remove()).
# - Paths point to the authoritative smali file.

- 0x01 — WheelUSBCommand (commandMode 0x01, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WheelUSBCommand.smali
  payload order (drop any -1 values at runtime): 0x1, moveWheelMode, moveWheelDirection, moveWheelLSBTime, moveWheelMSBTime, moveWheelDegree, moveWheelSpeed, moveWheelLSBDegree, moveWheelMSBDegree, moveWheelSpeed, moveWheelLSBTime, moveWheelMSBTime, isCircle, moveWheelSpeed, moveWheelLSBDistance, moveWheelMSBDistance
- 0x02 — HeadUSBCommand (commandMode 0x02, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HeadUSBCommand.smali
  payload order (drop any -1 values at runtime): 0x2, moveHeadMode, moveHeadDirection, moveHeadLSBTime, moveHeadMSBTime, moveHeadDegree, moveHeadSpeed, moveHeadLSBDegree, moveHeadMSBDegree, moveHeadSpeed, horizontalLSBDegree, horizontalMSBDegree, verticalLSBDegree, verticalMSBDegree, horizontal_relative_direction, horizontalDegree, vertical_relative_direction, verticalDegree
- 0x03 — HandUSBCommand (commandMode 0x03, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HandUSBCommand.smali
  payload order (drop any -1 values at runtime): 0x3, moveHandMode, whichHand, moveHandLSBTime, moveHandMSBTime, moveHandLSBDegree, moveHandMSBDegree, moveHandSpeed, moveHandDirection, moveHandLSBDegree, moveHandMSBDegree, moveHandSpeed, moveHandDirection
- 0x04 — WhiteLightCommand (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WhiteLightCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x1, switchMode
- 0x05 — LEDLightCommand (commandMode 0x04, target dynamic, point_tag [1, 2, 3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/LEDLightCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x2, 0x0, switchMode, led_rate, led_random_number, whichLight
- 0x06 — ProjectorCommand (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x3, switchMode
- 0x07 — SpeakerCommand (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SpeakerCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x4, switchMode
- 0x08 — AutoBatteryCommand (commandMode 0x04, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AutoBatteryCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x5, switchMode, 0x4, 0x5, switchMode, threshold
- 0x09 — DanceCommand (commandMode 0x04, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/DanceCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x6, switchMode
- 0x0A — SelfCheckedCommand (commandMode 0x04, target dynamic, point_tag [1, 2, 3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SelfCheckedCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x7, type, switchMode
- 0x0B — HeartBeatCommand (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HeartBeatCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x8, switchMode, 0x4, 0x8, switchMode, lsb, msb
- 0x0C — AutoReportCommand (commandMode 0x80, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AutoReportCommand.smali
  payload order (drop any -1 values at runtime): -0x80, switchMode
- 0x0D — QueryBatteryCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryBatteryCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, battery, currentBattery
- 0x0E — QueryObstacleCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryObstacleCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x2, obstacleDirection, distance, data1, data2, data3, data4, data5, data6, data7, data8, data9, data10, data11, data12, data13, data14, data15, data16, data17
- 0x0F — BatteryChangeCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BatteryChangeCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, BatteryChange, batteryStatus
- 0x10 — QueryBatteryCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryBatteryCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, battery, currentBattery
- 0x11 — QueryObstacleCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryObstacleCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x2, obstacleDirection, distance, data1, data2, data3, data4, data5, data6, data7, data8, data9, data10, data11, data12, data13, data14, data15, data16, data17
- 0x12 — BatteryChangeCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BatteryChangeCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, BatteryChange, batteryStatus
- 0x13 — BatteryTemperatureCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BatteryTemperatureCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x4, temperature
- 0x14 — GyroscopeCommand (commandMode 0x82, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/GyroscopeCommand.smali
  payload order (drop any -1 values at runtime): -0x7e, 0x1, LSBDriftAngle, MSBDriftAngle, LSBElevation, MSBElevation, LSBRollAngle, MSBRollAngle
- 0x15 — VoiceLocation (commandMode 0x82, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/VoiceLocation.smali
  payload order (drop any -1 values at runtime): -0x7e, 0x2, horizontalLSBAngle, horizontalMSBAngle, verticalLSBAngle, verticalMSBAngle
- 0x16 — TouchSwitch (commandMode 0x83, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/TouchSwitch.smali
  payload order (drop any -1 values at runtime): -0x7d, 0x1, touchTurnal, touchInformation
- 0x17 — MotorSelfCheck (commandMode 0x83, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MotorSelfCheck.smali
  payload order (drop any -1 values at runtime): -0x7d, -0x7f, 0x1, selfCheckContent, selfCheckInformation
- 0x18 — IRSensor (commandMode 0x83, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/IRSensor.smali
  payload order (drop any -1 values at runtime): -0x7d, -0x7f, 0x2, sensorContent, sensorInformation
- 0x19 — TouchSensor (commandMode 0x83, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/TouchSensor.smali
  payload order (drop any -1 values at runtime): -0x7d, -0x7f, 0x3, sensorContent, sensorInformation
- 0x1A — AccelerateSensor (commandMode 0x83, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AccelerateSensor.smali
  payload order (drop any -1 values at runtime): -0x7d, -0x7f, 0x1, sensorContent, sensorInformation
- 0x1B — WanderCommand (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WanderCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0x9, switchMode, type
- 0x1C — ProjectorImageSetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorImageSetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x1, controlContent
- 0x1D — ProjectorTiXingSetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorTiXingSetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x2, switchMode, controlContent, horizontalDegree, verticalDegree
- 0x1E — ProjectorPictureSetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorPictureSetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x3, controlContent, sub_type, degree
- 0x1F — ProjectorExpertMode (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorExpertMode.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x4, adjustMode, controlMode, controlContent
- 0x20 — ProjectorOtherSetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorOtherSetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x5, switchMode
- 0x21 — QueryPIRCommand (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryPIRCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x6, pir_type, pir_status
- 0x22 — QueryMotorStatus (commandMode 0x81, target dynamic, point_tag [1, 2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryMotorStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x7, which_part, motor_status
- 0x23 — QueryGyroscopeStatus (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryGyroscopeStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x8, accelerometer_status, compass_status
- 0x24 — QueryTouchSwitch (commandMode 0x81, target dynamic, point_tag [1, 2, 3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryTouchSwitch.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x5, touchTurnal, touchInformation
- 0x25 — ProjectorTypeSetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorTypeSetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x6, projector_type
- 0x26 — Detect3DData (commandMode 0x82, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/Detect3DData.smali
  payload order (drop any -1 values at runtime): -0x7e, 0x3, 0x1, distance
- 0x27 — QueryMovementStatus (commandMode 0x81, target dynamic, point_tag [1, 2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryMovementStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x9, which_part, status
- 0x28 — QueryHideObstacleStatus (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryHideObstacleStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0xa, which, status
- 0x29 — MotorLockSetting (commandMode 0x05, target dynamic, point_tag [1, 2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MotorLockSetting.smali
  payload order (drop any -1 values at runtime): 0x5, 0x1, whichPart, switchMode
- 0x2A — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x2B — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x2C — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x2D — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x2E — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x2F — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x30 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x31 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x32 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x33 — QueryIRReceiveStatus (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryIRReceiveStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0xb, receive_number, receive_head1, receive_head2, receive_head3, receive_head4, receive_head5, receive_head6
- 0x34 — ZigbeeCommand (commandMode 0xA0, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ZigbeeCommand.smali
  payload: (none, command mode only)
- 0x35 — MCUUpgradeCommand (commandMode 0x04, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MCUUpgradeCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0xb, 0x1
- 0x36 — MCUResetCommand (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MCUResetCommand.smali
  payload order (drop any -1 values at runtime): 0x4, 0xc, 0x1, time
- 0x37 — QueryUpgradeStatus (commandMode 0x81, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryUpgradeStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0xc, 0x0, type
- 0x38 — QueryMCUVersion (commandMode 0x81, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryMCUVersion.smali
  payload: (none, command mode only)
- 0x39 — ChangePileCommand (commandMode 0xA1, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ChangePileCommand.smali
  payload: (none, command mode only)
- 0x3A — AutoChangeStatus (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AutoChangeStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0xe, 0x0, status
- 0x3B — IllegalUseCommand (commandMode 0x81, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/IllegalUseCommand.smali
  payload order (drop any -1 values at runtime): -0x7f, 0xf, 0x0
- 0x3C — ProjectorOutputSetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorOutputSetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x7, projectorImageSetting, horizontalTiXing, verticalTiXing
- 0x3D — ProjectorImageQualitySetting (commandMode 0x04, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorImageQualitySetting.smali
  payload order (drop any -1 values at runtime): 0x4, 0xa, 0x8, contrast, brightness, chroma_u, chroma_v, saturation_u, saturation_v, acutance
- 0x3E — BlackShieldSwitch (commandMode 0x04, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BlackShieldSwitch.smali
  payload order (drop any -1 values at runtime): 0x4, 0xd, switch_mode
- 0x3F — LiliNormalExpression (commandMode 0x06, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/LiliNormalExpression.smali
  payload order (drop any -1 values at runtime): 0x6, 0x1, expression_type
- 0x40 — AmbientTemperature (commandMode 0x81, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AmbientTemperature.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x10, 0x0
- 0x41 — QueryOptocouplerStatus (commandMode 0x81, target dynamic, point_tag [1, 2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryOptocouplerStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x12, whichPart
- 0x42 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x43 — QueryIRSender (commandMode 0x81, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryIRSender.smali
  payload: (none, command mode only)
- 0x44 — BottomEncoderConnection (commandMode 0x81, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BottomEncoderConnection.smali
  payload: (none, command mode only)
- 0x45 — QuerySPIFLASHStatus (commandMode 0x81, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QuerySPIFLASHStatus.smali
  payload: (none, command mode only)
- 0x46 — QueryUARTConnection (commandMode 0x81, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryUARTConnection.smali
  payload: (none, command mode only)
- 0x47 — QueryProjectorConnection (commandMode 0x81, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryProjectorConnection.smali
  payload: (none, command mode only)
- 0x48 — QueryPhotoelectricSwitch (commandMode 0x81, target broadcast, point_tag [3])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryPhotoelectricSwitch.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x11, retain_data
- 0x49 — FollowSwitch (commandMode 0x04, target bottom, point_tag [2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/FollowSwitch.smali
  payload order (drop any -1 values at runtime): 0x4, 0xe, switch_mode
- 0x4A — QueryButtonStatus (commandMode 0x81, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryButtonStatus.smali
  payload: (none, command mode only)
- 0x4B — QueryProjectorSwitch (commandMode 0x81, target head, point_tag [1])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryProjectorSwitch.smali
  payload: (none, command mode only)
- 0x4C — PhotoelectricAbnormal (commandMode 0x81, target dynamic, point_tag [1, 2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/PhotoelectricAbnormal.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x19, whichPart
- 0x4D — HideModeSwitch (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HideModeSwitch.smali
  payload order (drop any -1 values at runtime): 0x4, 0xf, switchMode
- 0x4E — MotorDefendCommand (commandMode 0x05, target dynamic, point_tag [1, 2])
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MotorDefendCommand.smali
  payload order (drop any -1 values at runtime): 0x5, 0x2, whichPart, switchMode
- 0x4F — QueryHideCatStatus (commandMode 0x81, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryHideCatStatus.smali
  payload order (drop any -1 values at runtime): -0x7f, 0x1a, retain_data, status
- 0x50 — SetWhiteBrightness (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SetWhiteBrightness.smali
  payload order (drop any -1 values at runtime): 0x4, 0x1, setWhiteBrightness, brightness
- 0x51 — QueryWhiteBrightness (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryWhiteBrightness.smali
  payload order (drop any -1 values at runtime): 0x4, 0x1, queryWhiteBrightness
- 0x52 — RingArrayReset (commandMode 0x82, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/RingArrayReset.smali
  payload: (none, command mode only)
- 0x53 — RingArrayAdjust (commandMode 0x82, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/RingArrayAdjust.smali
  payload order (drop any -1 values at runtime): -0x7e, 0x4, 0x2, value
- 0x54 — RingArrayDegree (commandMode 0x82, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/RingArrayDegree.smali
  payload: (none, command mode only)
- 0x55 — QueryExpressionVersion (commandMode 0x81, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryExpressionVersion.smali
  payload: (none, command mode only)
- 0x56 — SetExpressionVersion (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SetExpressionVersion.smali
  payload: (none, command mode only)
- 0x57 — QueryExpressionStatus (commandMode 0x81, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryExpressionStatus.smali
  payload: (none, command mode only)
- 0x58 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x59 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x5A — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x5B — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x5C — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x5D — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x5E — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x5F — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x60 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x61 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x62 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x63 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x64 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x65 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x66 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x67 — — (commandMode None, target unknown, point_tag —)
  payload: (none, command mode only)
- 0x68 — BodyRecover (commandMode 0x04, target passthrough, point_tag —)
  path: tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BodyRecover.smali
  payload order (drop any -1 values at runtime): 0x4, 0x18, switch_mode

# ----------------------------------------------------
# 5) Value reference (no smali needed for common cases)
# ----------------------------------------------------
#
# WheelUSBCommand (ID 0x01, mode byte = 0x01):
#   moveWheelMode:
#     0x01 = time/speed (NoAngleWheelMotion)
#     0x02 = relative turn by angle (RelativeAngleWheelMotion)
#     0x10 = timed move (uses LSB/MSB time + degree)
#     0x11 = distance drive (DistanceWheelMotion)
#   moveWheelDirection (from helper beans):
#     forward 0x01, back 0x02, left 0x03, right 0x04,
#     left-forward 0x05, right-forward 0x06, left-back 0x07, right-back 0x08,
#     left translation 0x0A, right translation 0x0B,
#     turn-left 0x0C, turn-right 0x0D, stop-turn 0xF0, stop 0x00.
#   Distance mode (moveWheelMode=0x11): speed = raw byte; distance = 2 bytes big-endian (msbDistance, lsbDistance).
#   Angle mode (moveWheelMode=0x02): speed = raw byte; angle = 2 bytes big-endian (msbAngle, lsbAngle).
#   Time mode (moveWheelMode=0x10): duration uses moveWheelLSBTime/moveWheelMSBTime; degree used when present; speed raw.
#   isCircle: used only in time/speed branch; 0 = once, 1 = loop.
#
# HeadUSBCommand (ID 0x02, mode byte = 0x02):
#   moveHeadMode selects which fields are meaningful; the stock app sets:
#     0x01: time-based pan/tilt (uses moveHeadLSB/MSBTime, moveHeadSpeed, moveHeadDirection).
#     0x02: absolute degree (uses moveHeadLSB/MSBDegree, moveHeadSpeed, direction).
#     0x03: relative? (same degree fields); 0x10/0x11 follow the same pattern as wheels (time/distance-style).
#   moveHeadDirection: left/right/up/down encoded per mode (raw bytes; app sets from head motion manager).
#   horizontal/vertical LSBDegree/MSBDegree: absolute/relative pan/tilt degrees depending on mode.
#   horizontal_relative_direction / vertical_relative_direction: raw direction flags (0/1) used when relative.
#   Speed bytes are raw; no fixed scaling in smali.
#
# HandUSBCommand (ID 0x03, mode byte = 0x03):
#   moveHandMode: 0x01 time-based, 0x02/0x03 degree-based (mirrors wheel/head pattern: time vs degree).
#   whichHand: 0x01 = left, 0x02 = right, 0x03 = both (set by arm controller).
#   moveHandDirection: open/close/up/down depending on mode (raw byte set by caller).
#   Time fields (LSB/MSBTime) used in time mode; Degree fields (LSB/MSBDegree) in degree mode; speed raw.
#
# LEDLightCommand (ID 0x05):
#   whichLight → point_tag routing:
#     0   = broadcast (point_tag=0x03)
#     4/5/10 = head (point_tag=0x01)
#     else   = bottom (point_tag=0x02)
#   switchMode: raw effect/mode byte the app sets per LED pattern; led_rate and led_random_number are raw.
#
# WhiteLightCommand (ID 0x04):
#   switchMode: 0x00 off, 0x01 on (app sets 1 when turning on white LEDs).
#
# ProjectorCommand (ID 0x06):
#   switchMode: 0x00 off, 0x01 on (head MCU).
#
# SpeakerCommand (ID 0x07):
#   switchMode: 0x00 mute/stop, 0x01 enable (head MCU).
#
# AutoBatteryCommand (ID 0x08):
#   switchMode: 0x00 disable auto, 0x01 enable auto-charge (bottom).
#   threshold: raw byte (battery threshold) when present.
#
# DanceCommand (ID 0x09):
#   switchMode: 0x00 stop, 0x01 start (broadcast).
#
# SelfCheckedCommand (ID 0x0A):
#   type: raw self-check code; switchMode: 0x00 stop, 0x01 start.
#
# HeartBeatCommand (ID 0x0B):
#   switchMode: 0x01 enable heartbeat, 0x00 disable; msb/lsb are interval bytes when switchMode==0.
#
# AutoReportCommand (ID 0x0C):
#   switchMode: 0x00 disable MCU auto-reporting, 0x01 enable.
#
# Battery/Obstacle/Temperature/Gyro/Touch/PIR queries (IDs 0x0D–0x1A, 0x21–0x24):
#   No choice bytes beyond commandMode and sub-ID; any extra fields are returned by MCU, not sent.
#
# WanderCommand (ID 0x1B):
#   switchMode: 0x00 stop, 0x01 start; type: raw wander subtype.
#
# Projector settings group (IDs 0x1C–0x20, 0x25, 0x3C, 0x3D):
#   share commandMode 0x04 and subtype 0x0A.
#   controlContent / sub_type / degree / projector_type / contrast/brightness/etc. are raw bytes matching menu selections; the app passes UI values directly.
#
# Detect3DData (ID 0x26):
#   distance: single byte, raw (0x01 sub-id fixed in payload).
#
# QueryMovementStatus (ID 0x27):
#   which_part and status are returned by MCU; outbound payload has only commandMode/sub-id.
#
# MotorLockSetting (ID 0x29):
#   whichPart: 0x01 head, 0x02 hand/arm, 0x03 wheels (as used in app); switchMode: 0x00 unlock, 0x01 lock.
#
# QueryIRReceiveStatus (ID 0x33):
#   Outbound has no choices; MCU returns receive_headN bytes.
#
# ZigbeeCommand (ID 0x34):
#   No parameters in stock app; commandMode 0xA0 only.
#
# MCUUpgradeCommand (ID 0x35):
#   Fixed payload 0x04 0x0B 0x01; broadcast.
#
# MCUResetCommand (ID 0x36):
#   time: delay byte before reset (raw); mode 0x04, subtype 0x0C.
#
# QueryUpgradeStatus (ID 0x37):
#   type: raw byte from MCU; outbound payload fixed (-0x7f, 0x0c, 0x0, type) where type is zeroed in app.
#
# QueryMCUVersion (ID 0x38):
#   No parameters (commandMode 0x81, sub-id 0x0D).
#
# ChangePileCommand (ID 0x39):
#   No parameters (commandMode 0xA1).
#
# AutoChangeStatus / IllegalUseCommand (IDs 0x3A, 0x3B):
#   status/raw bytes set by app; otherwise no enums.
#
# BlackShieldSwitch (ID 0x3E):
#   switch_mode: 0x00 off, 0x01 on (bottom).
#
# LiliNormalExpression (ID 0x3F):
#   expression_type: raw expression id (head MCU).
#
# AmbientTemperature (ID 0x40):
#   No parameters (query only).
#
# QueryOptocouplerStatus (ID 0x41):
#   whichPart: 0x01 head, 0x02 bottom (app uses these); telemetry query.
#
# FollowSwitch (ID 0x49):
#   switch_mode: 0x00 off, 0x01 on (bottom).
#
# QueryButtonStatus / QueryProjectorSwitch (IDs 0x4A, 0x4B):
#   No parameters (queries).
#
# PhotoelectricAbnormal (ID 0x4C):
#   whichPart: 0x01 head, 0x02 bottom (raw abnormal flag query).
#
# HideModeSwitch (ID 0x4D):
#   switchMode: 0x00 off, 0x01 on (passthrough).
#
# MotorDefendCommand (ID 0x4E):
#   whichPart: 0x01 wheels, 0x02 hands (used in app); switchMode: 0x00 off, 0x01 on.
#
# QueryHideCatStatus (ID 0x4F):
#   retain_data/status returned by MCU; outbound fixed.
#
# SetWhiteBrightness / QueryWhiteBrightness (IDs 0x50/0x51):
#   setWhiteBrightness: 0x00 off, 0x01 on; brightness: 0–100 (raw byte). Query has no choices.
#
# RingArrayReset/Adjust/Degree (IDs 0x52–0x54):
#   Reset/Degree: no parameters. Adjust: value byte (gain); sub-ids fixed in payload.
#
# QueryExpressionVersion/Status, SetExpressionVersion (IDs 0x55–0x57):
#   No parameters; SetExpressionVersion uses commandMode 0x04 with no extra choice in stock smali.
#
# BodyRecover (ID 0x68):
#   switch_mode: 0x00 stop, 0x01 start recovery (passthrough).

# For any field not listed with explicit values above, the stock smali treats it as a raw byte/short with no validation; you can supply any byte and the MCU firmware will interpret it. The send/receive framing and payload order in sections 1–4 remain authoritative.
# -------------------------------------------------------
# 3) Call-site and routing notes (firmware usage hints)
# -------------------------------------------------------
#
# - Wheel/Head/Hand control: WheelMotionManager/HeadMotionManager/HandMotionManager
#   build the respective beans, call getMessageCommand(), then MCUManager.MCUSend(...)
#   (see tools/decompiled/main-release/smali/com/qihan/mcumanager/*MotionManager.smali).
# - LEDLightCommand: LedManager.LedSet maps whichLight → point_tag (0=head lights
#   4/5 head, others bottom; whichLight==0 → broadcast tag 0x03).
# - SpeakerCommand: FunctionManager.setSpeaker() instantiates and sends to head.
# - AutoReportCommand toggled in UsbMessageMrg.openAutoReport() and uses point_tag=-1
#   (passthrough send).
# - Most telemetry beans (0x81/0x82/0x83) set point_tag to the MCU they read from
#   (bottom or head). If point_tag remains -1 (passthrough), the caller chooses
#   the target via MCUSendToHead/MCUSendToBottom.

# --------------------------------------------------
# 4) Inbound decode byte offsets (DecodeCommand.smali)
# --------------------------------------------------
#
# These are the exact bytes the stock DecodeCommand reads into bean fields:
# - QueryBatteryCommand: frame byte 0x17 → currentBattery (0–100%). The bean is
#   instantiated then currentBattery is set from p1[0x17].
# - QueryUpgradeStatus: frame byte 0x18 → type (upgrade progress/state).
# - QueryMovementStatus: p1[0x17] → which_part; p1[0x18] low nibble → status,
#   high nibble → speed.
# - BatteryTemperatureCommand: p1[0x17] → temperature (raw byte).
# - QueryObstacleCommand: many bytes mapped across data1..data17 (see offsets
#   starting at 0x17 through 0x27 in DecodeCommand).
#
# For any other command, consult tools/decompiled/main-release/smali/com/qihan/uvccamera/DecodeCommand.smali;
# each case creates the matching bean and copies explicit byte offsets.
