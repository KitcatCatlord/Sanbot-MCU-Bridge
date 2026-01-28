# Catalogue

File locations were found by Codex, but all of the logic and data here was pulled
by me from the smali.
Codex also wrote all the descriptions from bullet points I gave it.

## Sources

- tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/*.smali
- tools/decompiled/main-release/smali/com/qihan/uvccamera/USBCommand.smali
- tools/decompiled/main-release/smali/com/qihan/uvccamera/DecodeCommand.smali
- MCU command switch table: MCUCmdGetByte in UsbMessageMrg.smali

## Notes

- Payload orders match each bean’s getCommandBytes() output. Fields set to -1 are
removed before sending.
- ack_flag defaults to 0x01 unless set otherwise in the bean.
- point_tag is appended inside getMessageCommand(). 1=head, 2=bottom,
  3=broadcast. Some beans leave point_tag as -1.
- command_mode_hex is the first payload byte from getCommandBytes().

## Sending

1) Instantiate the bean and set its public fields.
2) Call getMessageCommand() → USBCommand frame + trailing point_tag.
3) UsbMessageMrg.sendMessageToPoint() strips point_tag and routes. If you bulk
Transfer directly, drop the trailing point_tag yourself.

## Receive

- ConvertUtils.returnListByte() / isComplete() split and checksum frames.
- DecodeCommand.smali maps inbound frames back to bean objects.

## 1) Command map (0x01–0x68)

MCU target column reflects the tag/route chosen in the bean:

- head = point_tag 0x01
- bottom = point_tag 0x02
- broadcast = point_tag 0x03 (head then bottom)
- dynamic/passthrough = tag set by bean logic or left -1

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

## 2) Payload skeletons

- Order is exactly as added in getCommandBytes() before -1 stripping.
- Any byte set to -1 is removed at runtime (see iterator().remove()).
- Paths point to the authoritative smali file.

| ID | Class | commandMode | target | point_tag | path | payload order (drop any -1 values at runtime) |
|---|---|---|---|---|---|---|
| 0x01 | WheelUSBCommand | 0x01 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WheelUSBCommand.smali | 0x1, moveWheelMode, moveWheelDirection, moveWheelLSBTime, moveWheelMSBTime, moveWheelDegree, moveWheelSpeed, moveWheelLSBDegree, moveWheelMSBDegree, moveWheelSpeed, moveWheelLSBTime, moveWheelMSBTime, isCircle, moveWheelSpeed, moveWheelLSBDistance, moveWheelMSBDistance |
| 0x02 | HeadUSBCommand | 0x02 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HeadUSBCommand.smali | 0x2, moveHeadMode, moveHeadDirection, moveHeadLSBTime, moveHeadMSBTime, moveHeadDegree, moveHeadSpeed, moveHeadLSBDegree, moveHeadMSBDegree, moveHeadSpeed, horizontalLSBDegree, horizontalMSBDegree, verticalLSBDegree, verticalMSBDegree, horizontal_relative_direction, horizontalDegree, vertical_relative_direction, verticalDegree |
| 0x03 | HandUSBCommand | 0x03 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HandUSBCommand.smali | 0x3, moveHandMode, whichHand, moveHandLSBTime, moveHandMSBTime, moveHandLSBDegree, moveHandMSBDegree, moveHandSpeed, moveHandDirection, moveHandLSBDegree, moveHandMSBDegree, moveHandSpeed, moveHandDirection |
| 0x04 | WhiteLightCommand | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WhiteLightCommand.smali | 0x4, 0x1, switchMode |
| 0x05 | LEDLightCommand | 0x04 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/LEDLightCommand.smali | 0x4, 0x2, 0x0, switchMode, led_rate, led_random_number, whichLight |
| 0x06 | ProjectorCommand | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorCommand.smali | 0x4, 0x3, switchMode |
| 0x07 | SpeakerCommand | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SpeakerCommand.smali | 0x4, 0x4, switchMode |
| 0x08 | AutoBatteryCommand | 0x04 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AutoBatteryCommand.smali | 0x4, 0x5, switchMode, 0x4, 0x5, switchMode, threshold |
| 0x09 | DanceCommand | 0x04 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/DanceCommand.smali | 0x4, 0x6, switchMode |
| 0x0A | SelfCheckedCommand | 0x04 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SelfCheckedCommand.smali | 0x4, 0x7, type, switchMode |
| 0x0B | HeartBeatCommand | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HeartBeatCommand.smali | 0x4, 0x8, switchMode, 0x4, 0x8, switchMode, lsb, msb |
| 0x0C | AutoReportCommand | 0x80 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AutoReportCommand.smali | -0x80, switchMode |
| 0x0D | QueryBatteryCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryBatteryCommand.smali | -0x7f, battery, currentBattery |
| 0x0E | QueryObstacleCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryObstacleCommand.smali | -0x7f, 0x2, obstacleDirection, distance, data1, data2, data3, data4, data5, data6, data7, data8, data9, data10, data11, data12, data13, data14, data15, data16, data17 |
| 0x0F | BatteryChangeCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BatteryChangeCommand.smali | -0x7f, BatteryChange, batteryStatus |
| 0x10 | QueryBatteryCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryBatteryCommand.smali | -0x7f, battery, currentBattery |
| 0x11 | QueryObstacleCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryObstacleCommand.smali | -0x7f, 0x2, obstacleDirection, distance, data1, data2, data3, data4, data5, data6, data7, data8, data9, data10, data11, data12, data13, data14, data15, data16, data17 |
| 0x12 | BatteryChangeCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BatteryChangeCommand.smali | -0x7f, BatteryChange, batteryStatus |
| 0x13 | BatteryTemperatureCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BatteryTemperatureCommand.smali | -0x7f, 0x4, temperature |
| 0x14 | GyroscopeCommand | 0x82 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/GyroscopeCommand.smali | -0x7e, 0x1, LSBDriftAngle, MSBDriftAngle, LSBElevation, MSBElevation, LSBRollAngle, MSBRollAngle |
| 0x15 | VoiceLocation | 0x82 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/VoiceLocation.smali | -0x7e, 0x2, horizontalLSBAngle, horizontalMSBAngle, verticalLSBAngle, verticalMSBAngle |
| 0x16 | TouchSwitch | 0x83 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/TouchSwitch.smali | -0x7d, 0x1, touchTurnal, touchInformation |
| 0x17 | MotorSelfCheck | 0x83 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MotorSelfCheck.smali | -0x7d, -0x7f, 0x1, selfCheckContent, selfCheckInformation |
| 0x18 | IRSensor | 0x83 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/IRSensor.smali | -0x7d, -0x7f, 0x2, sensorContent, sensorInformation |
| 0x19 | TouchSensor | 0x83 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/TouchSensor.smali | -0x7d, -0x7f, 0x3, sensorContent, sensorInformation |
| 0x1A | AccelerateSensor | 0x83 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AccelerateSensor.smali | -0x7d, -0x7f, 0x1, sensorContent, sensorInformation |
| 0x1B | WanderCommand | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WanderCommand.smali | 0x4, 0x9, switchMode, type |
| 0x1C | ProjectorImageSetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorImageSetting.smali | 0x4, 0xa, 0x1, controlContent |
| 0x1D | ProjectorTiXingSetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorTiXingSetting.smali | 0x4, 0xa, 0x2, switchMode, controlContent, horizontalDegree, verticalDegree |
| 0x1E | ProjectorPictureSetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorPictureSetting.smali | 0x4, 0xa, 0x3, controlContent, sub_type, degree |
| 0x1F | ProjectorExpertMode | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorExpertMode.smali | 0x4, 0xa, 0x4, adjustMode, controlMode, controlContent |
| 0x20 | ProjectorOtherSetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorOtherSetting.smali | 0x4, 0xa, 0x5, switchMode |
| 0x21 | QueryPIRCommand | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryPIRCommand.smali | -0x7f, 0x6, pir_type, pir_status |
| 0x22 | QueryMotorStatus | 0x81 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryMotorStatus.smali | -0x7f, 0x7, which_part, motor_status |
| 0x23 | QueryGyroscopeStatus | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryGyroscopeStatus.smali | -0x7f, 0x8, accelerometer_status, compass_status |
| 0x24 | QueryTouchSwitch | 0x81 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryTouchSwitch.smali | -0x7f, 0x5, touchTurnal, touchInformation |
| 0x25 | ProjectorTypeSetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorTypeSetting.smali | 0x4, 0xa, 0x6, projector_type |
| 0x26 | Detect3DData | 0x82 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/Detect3DData.smali | -0x7e, 0x3, 0x1, distance |
| 0x27 | QueryMovementStatus | 0x81 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryMovementStatus.smali | -0x7f, 0x9, which_part, status |
| 0x28 | QueryHideObstacleStatus | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryHideObstacleStatus.smali | -0x7f, 0xa, which, status |
| 0x29 | MotorLockSetting | 0x05 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MotorLockSetting.smali | 0x5, 0x1, whichPart, switchMode |
| 0x2A | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x2B | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x2C | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x2D | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x2E | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x2F | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x30 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x31 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x32 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x33 | QueryIRReceiveStatus | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryIRReceiveStatus.smali | -0x7f, 0xb, receive_number, receive_head1, receive_head2, receive_head3, receive_head4, receive_head5, receive_head6 |
| 0x34 | ZigbeeCommand | 0xA0 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ZigbeeCommand.smali | payload: (none, command mode only) |
| 0x35 | MCUUpgradeCommand | 0x04 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MCUUpgradeCommand.smali | 0x4, 0xb, 0x1 |
| 0x36 | MCUResetCommand | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MCUResetCommand.smali | 0x4, 0xc, 0x1, time |
| 0x37 | QueryUpgradeStatus | 0x81 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryUpgradeStatus.smali | -0x7f, 0xc, 0x0, type |
| 0x38 | QueryMCUVersion | 0x81 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryMCUVersion.smali | payload: (none, command mode only) |
| 0x39 | ChangePileCommand | 0xA1 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ChangePileCommand.smali | payload: (none, command mode only) |
| 0x3A | AutoChangeStatus | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AutoChangeStatus.smali | -0x7f, 0xe, 0x0, status |
| 0x3B | IllegalUseCommand | 0x81 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/IllegalUseCommand.smali | -0x7f, 0xf, 0x0 |
| 0x3C | ProjectorOutputSetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorOutputSetting.smali | 0x4, 0xa, 0x7, projectorImageSetting, horizontalTiXing, verticalTiXing |
| 0x3D | ProjectorImageQualitySetting | 0x04 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/ProjectorImageQualitySetting.smali | 0x4, 0xa, 0x8, contrast, brightness, chroma_u, chroma_v, saturation_u, saturation_v, acutance |
| 0x3E | BlackShieldSwitch | 0x04 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BlackShieldSwitch.smali | 0x4, 0xd, switch_mode |
| 0x3F | LiliNormalExpression | 0x06 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/LiliNormalExpression.smali | 0x6, 0x1, expression_type |
| 0x40 | AmbientTemperature | 0x81 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/AmbientTemperature.smali | -0x7f, 0x10, 0x0 |
| 0x41 | QueryOptocouplerStatus | 0x81 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryOptocouplerStatus.smali | -0x7f, 0x12, whichPart |
| 0x42 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x43 | QueryIRSender | 0x81 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryIRSender.smali | payload: (none, command mode only) |
| 0x44 | BottomEncoderConnection | 0x81 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BottomEncoderConnection.smali | payload: (none, command mode only) |
| 0x45 | QuerySPIFLASHStatus | 0x81 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QuerySPIFLASHStatus.smali | payload: (none, command mode only) |
| 0x46 | QueryUARTConnection | 0x81 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryUARTConnection.smali | payload: (none, command mode only) |
| 0x47 | QueryProjectorConnection | 0x81 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryProjectorConnection.smali | payload: (none, command mode only) |
| 0x48 | QueryPhotoelectricSwitch | 0x81 | broadcast | [3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryPhotoelectricSwitch.smali | -0x7f, 0x11, retain_data |
| 0x49 | FollowSwitch | 0x04 | bottom | [2] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/FollowSwitch.smali | 0x4, 0xe, switch_mode |
| 0x4A | QueryButtonStatus | 0x81 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryButtonStatus.smali | payload: (none, command mode only) |
| 0x4B | QueryProjectorSwitch | 0x81 | head | [1] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryProjectorSwitch.smali | payload: (none, command mode only) |
| 0x4C | PhotoelectricAbnormal | 0x81 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/PhotoelectricAbnormal.smali | -0x7f, 0x19, whichPart |
| 0x4D | HideModeSwitch | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/HideModeSwitch.smali | 0x4, 0xf, switchMode |
| 0x4E | MotorDefendCommand | 0x05 | dynamic | [1, 2, 3] | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/MotorDefendCommand.smali | 0x5, 0x2, whichPart, switchMode |
| 0x4F | QueryHideCatStatus | 0x81 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryHideCatStatus.smali | -0x7f, 0x1a, retain_data, status |
| 0x50 | SetWhiteBrightness | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SetWhiteBrightness.smali | 0x4, 0x1, setWhiteBrightness, brightness |
| 0x51 | QueryWhiteBrightness | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryWhiteBrightness.smali | 0x4, 0x1, queryWhiteBrightness |
| 0x52 | RingArrayReset | 0x82 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/RingArrayReset.smali | payload: (none, command mode only) |
| 0x53 | RingArrayAdjust | 0x82 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/RingArrayAdjust.smali | -0x7e, 0x4, 0x2, value |
| 0x54 | RingArrayDegree | 0x82 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/RingArrayDegree.smali | payload: (none, command mode only) |
| 0x55 | QueryExpressionVersion | 0x81 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryExpressionVersion.smali | payload: (none, command mode only) |
| 0x56 | SetExpressionVersion | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/SetExpressionVersion.smali | payload: (none, command mode only) |
| 0x57 | QueryExpressionStatus | 0x81 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/QueryExpressionStatus.smali | payload: (none, command mode only) |
| 0x58 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x59 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x5A | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x5B | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x5C | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x5D | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x5E | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x5F | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x60 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x61 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x62 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x63 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x64 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x65 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x66 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x67 | — | None | unknown | — |  | payload: (none, command mode only) |
| 0x68 | BodyRecover | 0x04 | passthrough | — | tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/BodyRecover.smali | 0x4, 0x18, switch_mode |
## 5) Value reference

| Item | Details |
|---|---|
| WheelUSBCommand (ID 0x01, mode byte = 0x01) |  |
| moveWheelMode | 0x01 = time/speed (NoAngleWheelMotion)<br>0x02 = relative turn by angle (RelativeAngleWheelMotion)<br>0x10 = timed move (uses LSB/MSB time + degree)<br>0x11 = distance drive (DistanceWheelMotion) |
| moveWheelDirection (from helper beans) | forward 0x01, back 0x02, left 0x03, right 0x04,<br>left-forward 0x05, right-forward 0x06, left-back 0x07, right-back 0x08,<br>left translation 0x0A, right translation 0x0B,<br>turn-left 0x0C, turn-right 0x0D, stop-turn 0xF0, stop 0x00.<br>Distance mode (moveWheelMode=0x11): speed = raw byte; distance = 2 bytes big-endian (msbDistance, lsbDistance).<br>Angle mode (moveWheelMode=0x02): speed = raw byte; angle = 2 bytes big-endian (msbAngle, lsbAngle).<br>Time mode (moveWheelMode=0x10): duration uses moveWheelLSBTime/moveWheelMSBTime; degree used when present; speed raw.<br>isCircle: used only in time/speed branch; 0 = once, 1 = loop. |
| HeadUSBCommand (ID 0x02, mode byte = 0x02) |  |
| moveHeadMode selects which fields are meaningful; the stock app sets | 0x01: time-based pan/tilt (uses moveHeadLSB/MSBTime, moveHeadSpeed, moveHeadDirection).<br>0x02: absolute degree (uses moveHeadLSB/MSBDegree, moveHeadSpeed, direction).<br>0x03: relative? (same degree fields); 0x10/0x11 follow the same pattern as wheels (time/distance-style).<br>moveHeadDirection: left/right/up/down encoded per mode (raw bytes; app sets from head motion manager).<br>horizontal/vertical LSBDegree/MSBDegree: absolute/relative pan/tilt degrees depending on mode.<br>horizontal_relative_direction / vertical_relative_direction: raw direction flags (0/1) used when relative.<br>Speed bytes are raw; no fixed scaling in smali. |
| HandUSBCommand (ID 0x03, mode byte = 0x03) | moveHandMode: 0x01 time-based, 0x02/0x03 degree-based (mirrors wheel/head pattern: time vs degree).<br>whichHand: 0x01 = left, 0x02 = right, 0x03 = both (set by arm controller).<br>moveHandDirection: open/close/up/down depending on mode (raw byte set by caller).<br>Time fields (LSB/MSBTime) used in time mode; Degree fields (LSB/MSBDegree) in degree mode; speed raw. |
| LEDLightCommand (ID 0x05) |  |
| whichLight → point_tag routing | 0   = broadcast (point_tag=0x03)<br>4/5/10 = head (point_tag=0x01)<br>else   = bottom (point_tag=0x02)<br>switchMode: raw effect/mode byte the app sets per LED pattern; led_rate and led_random_number are raw. |
| WhiteLightCommand (ID 0x04) | switchMode: 0x00 off, 0x01 on (app sets 1 when turning on white LEDs). |
| ProjectorCommand (ID 0x06) | switchMode: 0x00 off, 0x01 on (head MCU). |
| SpeakerCommand (ID 0x07) | switchMode: 0x00 mute/stop, 0x01 enable (head MCU). |
| AutoBatteryCommand (ID 0x08) | switchMode: 0x00 disable auto, 0x01 enable auto-charge (bottom).<br>threshold: raw byte (battery threshold) when present. |
| DanceCommand (ID 0x09) | switchMode: 0x00 stop, 0x01 start (broadcast). |
| SelfCheckedCommand (ID 0x0A) | type: raw self-check code; switchMode: 0x00 stop, 0x01 start. |
| HeartBeatCommand (ID 0x0B) | switchMode: 0x01 enable heartbeat, 0x00 disable; msb/lsb are interval bytes when switchMode==0. |
| AutoReportCommand (ID 0x0C) | switchMode: 0x00 disable MCU auto-reporting, 0x01 enable. |
| Battery/Obstacle/Temperature/Gyro/Touch/PIR queries (IDs 0x0D–0x1A, 0x21–0x24) | No choice bytes beyond commandMode and sub-ID; any extra fields are returned by MCU, not sent. |
| WanderCommand (ID 0x1B) | switchMode: 0x00 stop, 0x01 start; type: raw wander subtype. |
| Projector settings group (IDs 0x1C–0x20, 0x25, 0x3C, 0x3D) | share commandMode 0x04 and subtype 0x0A.<br>controlContent / sub_type / degree / projector_type / contrast/brightness/etc. are raw bytes matching menu selections; the app passes UI values directly. |
| Detect3DData (ID 0x26) | distance: single byte, raw (0x01 sub-id fixed in payload). |
| QueryMovementStatus (ID 0x27) | which_part and status are returned by MCU; outbound payload has only commandMode/sub-id. |
| MotorLockSetting (ID 0x29) | whichPart: 0x01 head, 0x02 hand/arm, 0x03 wheels (as used in app); switchMode: 0x00 unlock, 0x01 lock. |
| QueryIRReceiveStatus (ID 0x33) | Outbound has no choices; MCU returns receive_headN bytes. |
| ZigbeeCommand (ID 0x34) | No parameters in stock app; commandMode 0xA0 only. |
| MCUUpgradeCommand (ID 0x35) | Fixed payload 0x04 0x0B 0x01; broadcast. |
| MCUResetCommand (ID 0x36) | time: delay byte before reset (raw); mode 0x04, subtype 0x0C. |
| QueryUpgradeStatus (ID 0x37) | type: raw byte from MCU; outbound payload fixed (-0x7f, 0x0c, 0x0, type) where type is zeroed in app. |
| QueryMCUVersion (ID 0x38) | No parameters (commandMode 0x81, sub-id 0x0D). |
| ChangePileCommand (ID 0x39) | No parameters (commandMode 0xA1). |
| AutoChangeStatus / IllegalUseCommand (IDs 0x3A, 0x3B) | status/raw bytes set by app; otherwise no enums. |
| BlackShieldSwitch (ID 0x3E) | switch_mode: 0x00 off, 0x01 on (bottom). |
| LiliNormalExpression (ID 0x3F) | expression_type: raw expression id (head MCU). |
| AmbientTemperature (ID 0x40) | No parameters (query only). |
| QueryOptocouplerStatus (ID 0x41) | whichPart: 0x01 head, 0x02 bottom (app uses these); telemetry query. |
| FollowSwitch (ID 0x49) | switch_mode: 0x00 off, 0x01 on (bottom). |
| QueryButtonStatus / QueryProjectorSwitch (IDs 0x4A, 0x4B) | No parameters (queries). |
| PhotoelectricAbnormal (ID 0x4C) | whichPart: 0x01 head, 0x02 bottom (raw abnormal flag query). |
| HideModeSwitch (ID 0x4D) | switchMode: 0x00 off, 0x01 on (passthrough). |
| MotorDefendCommand (ID 0x4E) | whichPart: 0x01 wheels, 0x02 hands (used in app); switchMode: 0x00 off, 0x01 on. |
| QueryHideCatStatus (ID 0x4F) | retain_data/status returned by MCU; outbound fixed. |
| SetWhiteBrightness / QueryWhiteBrightness (IDs 0x50/0x51) | setWhiteBrightness: 0x00 off, 0x01 on; brightness: 0–100 (raw byte). Query has no choices. |
| RingArrayReset/Adjust/Degree (IDs 0x52–0x54) | Reset/Degree: no parameters. Adjust: value byte (gain); sub-ids fixed in payload. |
| QueryExpressionVersion/Status, SetExpressionVersion (IDs 0x55–0x57) | No parameters; SetExpressionVersion uses commandMode 0x04 with no extra choice in stock smali. |
| BodyRecover (ID 0x68) | switch_mode: 0x00 stop, 0x01 start recovery (passthrough).<br>For any field not listed with explicit values above, the stock smali treats it as a raw byte/short with no validation; you can supply any byte and the MCU firmware will interpret it. The send/receive framing and payload order in sections 1–4 remain authoritative. |
## 6) Call-site and routing notes
| Item | Details |
|---|---|
| Wheel/Head/Hand control: WheelMotionManager/HeadMotionManager/HandMotionManager | build the respective beans, call getMessageCommand(), then MCUManager.MCUSend(...) (see tools/decompiled/main-release/smali/com/qihan/mcumanager/*MotionManager.smali). |
| LEDLightCommand: LedManager.LedSet maps whichLight → point_tag (0=head lights | 4/5 head, others bottom; whichLight==0 → broadcast tag 0x03). |
| SpeakerCommand: FunctionManager.setSpeaker() instantiates and sends to head. |  |
| AutoReportCommand toggled in UsbMessageMrg.openAutoReport() and uses point_tag=-1 | (passthrough send). |
| Most telemetry beans (0x81/0x82/0x83) set point_tag to the MCU they read from | (bottom or head). If point_tag remains -1 (passthrough), the caller chooses the target via MCUSendToHead/MCUSendToBottom. |
## 7) Inbound decode byte offsets
| Item | Details |
|---|---|
| General | These are the exact bytes the stock DecodeCommand reads into bean fields: |
| QueryBatteryCommand: frame byte 0x17 → currentBattery (0–100%). The bean is | instantiated then currentBattery is set from p1[0x17]. |
| QueryUpgradeStatus: frame byte 0x18 → type (upgrade progress/state). |  |
| QueryMovementStatus: p1[0x17] → which_part; p1[0x18] low nibble → status, | high nibble → speed. |
| BatteryTemperatureCommand: p1[0x17] → temperature (raw byte). |  |
| QueryObstacleCommand: many bytes mapped across data1..data17 (see offsets | starting at 0x17 through 0x27 in DecodeCommand). For any other command, consult tools/decompiled/main-release/smali/com/qihan/uvccamera/DecodeCommand.smali; each case creates the matching bean and copies explicit byte offsets. |
