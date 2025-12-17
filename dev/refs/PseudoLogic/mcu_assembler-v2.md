# Compiled by ChatGPT Codex from original firmware files

# ============================================================
# Sanbot MCU USB Byte Assembler (V2, LOGIC-ONLY PSEUDOCODE)
# ============================================================
#
# Purpose:
#   Assemble the exact USB frame bytes (header + payload + checksum)
#   that the original firmware sends via UsbDeviceConnection.bulkTransfer().
#
# Sources (decompiled firmware):
#   - Framing + checksum:
#       tools/decompiled/main-release/smali/com/qihan/uvccamera/USBCommand.smali
#   - Endianness helpers:
#       tools/decompiled/main-release/smali/com/qihan/uvccamera/ConvertUtils.smali
#   - point_tag routing + stripping before bulkTransfer:
#       tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/UsbMessageMrg.smali
#   - Example of “-1 means omit this byte” payload building:
#       tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/WheelUSBCommand.smali
#
# What this covers (complete for the assembler):
#   - Building datas[] (command payload bytes) using the same “remove -1” rule used by many beans
#   - Building the USBCommand frame bytes exactly (field values, endianness, layout)
#   - Computing checksum exactly as firmware does
#   - Appending point_tag for routing and describing how firmware strips it before sending
#
# What this does NOT cover:
#   - The per-command schemas for datas[] (wheel/head/hand/etc.). You’ll implement those later.

# ------------------------------
# 1. Data definitions / structs
# ------------------------------

struct CommandPayload {
    # First byte in datas[] for this command type (varies per command).
    byte commandMode

    # Subsequent bytes in the exact order required by the command schema.
    # IMPORTANT: in the original bean pattern, any entry equal to -1 is removed.
    # So store these as signed bytes if you want to model -1 explicitly.
    signed_byte[] orderedBytes
}

struct UsbFrameParams {
    # Caller-provided
    byte ack_flg   # many beans default to 0x01

    # Firmware defaults from USBCommand.<init>()
    uint16 type        = 0xA403
    uint16 subtype     = 0x0000
    uint16 frame_head  = 0xFFA5
    byte[7] unuse      = [0x00,0x00,0x00,0x00,0x00,0x00,0x00]
    const int MSG_HEAD_LEN = 0x10
}

# ---------------------------------------------------
# 2. Endianness helpers (ConvertUtils equivalents)
# ---------------------------------------------------

# shortToByteArray(S): 2 bytes, big-endian
function toBytes16BE(value_uint16 : uint16) -> byte[2]:
    b0 = (value_uint16 >> 8) & 0xFF
    b1 = value_uint16 & 0xFF
    return [b0, b1]

# integerToByteArray(I): 4 bytes, big-endian
function toBytes32BE(value_uint32 : uint32) -> byte[4]:
    b0 = (value_uint32 >> 24) & 0xFF
    b1 = (value_uint32 >> 16) & 0xFF
    b2 = (value_uint32 >> 8)  & 0xFF
    b3 = value_uint32 & 0xFF
    return [b0, b1, b2, b3]

# -------------------------------------------------------------
# 3. Build datas[] (command payload bytes) using bean semantics
# -------------------------------------------------------------
#
# Many bean classes:
#   - push commandMode, then fields
#   - remove any entries equal to -1
#   - convert list to byte[]
#
# NOTE: This means a literal 0xFF payload byte cannot be represented via this pattern
#       because 0xFF == -1 as a signed byte and gets removed.

function buildDatas(cmd : CommandPayload) -> byte[]:
    list = empty list of signed_byte

    list.push_back( (signed_byte)cmd.commandMode )

    for each sb in cmd.orderedBytes:
        list.push_back(sb)

    # Firmware: remove all elements where byteValue() == -1
    remove all entries from list where entry == (signed_byte)-1

    datas = empty byte[]
    for each sb in list:
        # convert signed byte to raw byte value 0..255
        datas.push_back( (byte)sb )

    return datas

# ---------------------------------------------------------
# 4. Compute USBCommand derived fields + checksum (exact)
# ---------------------------------------------------------
#
# From USBCommand.setMessageContent([B):
#   content_len = len(datas) + 5 + 1
#     where 5 = frame_head(2) + ack(1) + mmnn(2)
#           1 = checksum(1)
#   mmnn = (short)(len(datas) + 1)
#   msg_size = intToBytesBE(content_len)
#
# Checksum is computed as:
#   data_sum = frame_head_byte0 + frame_head_byte1 + ack_flg + mmnn + sum(datas)
#   checkSum = (byte)data_sum
#
# IMPORTANT: firmware adds mmnn as the numeric 16-bit value, not its two serialized bytes.

struct UsbComputed {
    uint32 content_len
    uint16 mmnn
    byte[4] msg_size
    byte checkSum
}

function computeUsbFieldsAndChecksum(params : UsbFrameParams, datas : byte[]) -> UsbComputed:
    out = UsbComputed()

    out.content_len = (uint32)(len(datas) + 5 + 1)
    out.mmnn = (uint16)(len(datas) + 1)
    out.msg_size = toBytes32BE(out.content_len)

    fh = toBytes16BE(params.frame_head)   # 0xFFA5 -> [0xFF, 0xA5]

    data_sum = 0
    data_sum += fh[0]
    data_sum += fh[1]
    data_sum += params.ack_flg
    data_sum += out.mmnn                  # numeric value (0..65535)
    for each b in datas:
        data_sum += b

    out.checkSum = (byte)(data_sum & 0xFF)
    return out

# ---------------------------------------------------------
# 5. Build final USB frame bytes (USBCommand.getMessage)
# ---------------------------------------------------------
#
# Layout returned by USBCommand.getMessage():
#   [type:2][subtype:2][msg_size:4][ack_flg:1][unuse:7]
#   [frame_head:2][ack_flg:1][mmnn:2][datas:N][checkSum:1]
#
# Endianness:
#   - type/subtype/frame_head/mmnn are big-endian (shortToByteArray)
#   - msg_size is big-endian (integerToByteArray)

function buildUsbFrame(params : UsbFrameParams, datas : byte[]) -> byte[]:
    computed = computeUsbFieldsAndChecksum(params, datas)

    frame = empty byte[]

    frame.extend( toBytes16BE(params.type) )
    frame.extend( toBytes16BE(params.subtype) )
    frame.extend( computed.msg_size )
    frame.push_back( params.ack_flg )
    frame.extend( params.unuse )

    frame.extend( toBytes16BE(params.frame_head) )
    frame.push_back( params.ack_flg )
    frame.extend( toBytes16BE(computed.mmnn) )

    frame.extend( datas )
    frame.push_back( computed.checkSum )

    # total length in firmware: MSG_HEAD_LEN + content_len
    # (this should equal len(frame) here)
    return frame

# ---------------------------------------------------------
# 6. point_tag routing byte (used by UsbMessageMrg)
# ---------------------------------------------------------
#
# Many command beans build:
#   routed = usb_frame + [point_tag]
#
# point_tag values used for routing:
#   0x01 = head
#   0x02 = bottom
#   0x03 = both (head then bottom)
#
# CRITICAL BEHAVIOR (UsbMessageMrg.sendMessageToMcu what=4):
#   The firmware strips the final routing byte before bulkTransfer:
#     temp = routed[0 : len-1]
#     tag  = routed[len-1]
#   Then uses tag to choose where to bulkTransfer(temp).
#
# Therefore: the MCU receives the USB frame only (no point_tag) in this path.

function appendPointTagForRouting(usbFrame : byte[], point_tag : byte) -> byte[]:
    routed = copy of usbFrame
    routed.push_back(point_tag)
    return routed

# ----------------------------------------------------------------
# 7. High-level assembler (what you’ll call from your command code)
# ----------------------------------------------------------------

# If you are producing bytes that will be sent directly via bulkTransfer:
#   send buildUsbFrame(...) result.
function assembleUsbFrameFromCommand(cmd : CommandPayload, ack_flg : byte) -> byte[]:
    params = UsbFrameParams()
    params.ack_flg = ack_flg

    datas = buildDatas(cmd)
    return buildUsbFrame(params, datas)

# If you are producing bytes intended for the firmware-style routing path:
#   (i.e., something like UsbMessageMrg “send to point”), append point_tag.
#   Note: firmware will strip this byte before bulkTransfer when using that path.
function assembleRoutedBuffer(cmd : CommandPayload, ack_flg : byte, point_tag : byte) -> byte[]:
    usbFrame = assembleUsbFrameFromCommand(cmd, ack_flg)
    return appendPointTagForRouting(usbFrame, point_tag)
