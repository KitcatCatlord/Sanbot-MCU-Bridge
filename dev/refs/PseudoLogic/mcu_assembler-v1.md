# Compiled by ChatGPT Codex from original firmware files

# ============================================================
# Sanbot MCU Message Assembler (PSEUDOCODE FOR C++ TRANSLATION)
# ============================================================
#
# This file is ordered so you can translate top-to-bottom into
# a single C++ source file without forward-declaration issues.
# Just replace `byte` with e.g. uint8_t and convert arrays to
# std::vector<uint8_t> (or similar).

# ------------------------------
# 1. CommandPayload definition
# ------------------------------

struct CommandPayload {
    # First byte of the payload for this command type.
    # In C++: uint8_t commandMode;
    byte commandMode

    # Remaining bytes, in the EXACT order the firmware expects.
    # Use 0xFF as a placeholder for "no byte here" (gets dropped).
    # In C++: std::vector<uint8_t> orderedBytes;
    byte[] orderedBytes
}


# -----------------------------------------
# 2. Integer → byte-array helper functions
# -----------------------------------------

# Convert 16-bit integer to 2 bytes, big-endian
function toBytes16BE(value : uint16) -> byte[2]:
    hi = (value >> 8) & 0xFF
    lo = value & 0xFF
    return [hi, lo]


# Convert 16-bit integer to 2 bytes, little-endian
function toBytes16LE(value : uint16) -> byte[2]:
    lo = value & 0xFF
    hi = (value >> 8) & 0xFF
    return [lo, hi]


# Convert 32-bit integer to 4 bytes, big-endian
function toBytes32BE(value : uint32) -> byte[4]:
    b0 = (value >> 24) & 0xFF
    b1 = (value >> 16) & 0xFF
    b2 = (value >> 8)  & 0xFF
    b3 = value & 0xFF
    return [b0, b1, b2, b3]


# -------------------------------------------
# 3. Build raw MCU payload (before USB frame)
# -------------------------------------------

# Input:
#   cmd : CommandPayload
# Output:
#   payload : byte[]  (what firmware calls the "command" array)
function buildPayload(cmd : CommandPayload) -> byte[]:
    payload = empty byte[]

    # First byte is always the commandMode.
    payload.push_back(cmd.commandMode)

    # Then each subsequent byte in the firmware's required order.
    for each b in cmd.orderedBytes:
        # In original code, -1 means "drop this".
        # Here we use 0xFF as the placeholder.
        if b != 0xFF:
            payload.push_back(b)

    return payload


# -------------------------------------------------
# 4. Frame payload into USB packet (no point_tag)
# -------------------------------------------------
#
# This reproduces USBCommand.setMessageContent() + getMessage().

# Input:
#   payload : byte[]   (from buildPayload)
#   ackFlag : byte     (usually 0x01)
# Output:
#   framed  : byte[]   (USB-framed message WITHOUT point_tag)
function frameUsb(payload : byte[], ackFlag : byte) -> byte[]:
    # Firmware constants
    const uint16 TYPE       = 0xA505   # serialized big-endian
    const uint16 SUBTYPE    = 0x0000   # serialized big-endian
    const uint16 FRAME_HEAD = 0xA5A5   # serialized big-endian
    const int    UNUSE_LEN  = 7        # seven 0x00 bytes

    # Derived fields (matching the smali exactly)
    mmnn        = (uint16)( len(payload) + 1 )     # 2 bytes, LE
    contentLen  = (uint32)( len(payload) + 6 )     # used for msg_size
    msgSize[4]  = toBytes32BE(contentLen)          # 4 bytes, BE
    mmnnBytes[2]= toBytes16LE(mmnn)                # 2 bytes, LE

    framed = empty byte[]

    # --- Header Part 1 (before frame_head) ---
    framed.extend( toBytes16BE(TYPE) )             # type (2 bytes, BE)
    framed.extend( toBytes16BE(SUBTYPE) )          # subtype (2 bytes, BE)
    framed.extend( msgSize )                       # msg_size (4 bytes, BE)
    framed.push_back( ackFlag )                    # ack_flg (1 byte)

    for i from 0 to UNUSE_LEN - 1:
        framed.push_back( 0x00 )                   # unuse[7]

    # --- Header Part 2 (frame_head, mmnn) ---
    framed.extend( toBytes16BE(FRAME_HEAD) )       # frame_head (2 bytes, BE)
    framed.push_back( ackFlag )                    # ack_flg again
    framed.extend( mmnnBytes )                     # mmnn (2 bytes, LE)

    # --- Payload bytes ---
    framed.extend( payload )

    # --- Checksum (sum of all previous bytes, modulo 256) ---
    checksum = 0
    for each b in framed:
        checksum = (checksum + b) & 0xFF           # keep low 8 bits

    framed.push_back( checksum )

    return framed


# ----------------------------------------------------
# 5. Append point_tag (head / bottom / broadcast flag)
# ----------------------------------------------------

# Input:
#   framed   : byte[] (from frameUsb)
#   pointTag : byte   (0x01=head, 0x02=bottom, 0x03=broadcast)
# Output:
#   finalBuf : byte[] (ready to send via USB bulk transfer)
function appendPointTag(framed : byte[], pointTag : byte) -> byte[]:
    finalBuf = copy of framed
    finalBuf.push_back(pointTag)
    return finalBuf


# ---------------------------------------------------------
# 6. High-level assembler: one call to get bytes to send
# ---------------------------------------------------------

# Input:
#   cmd      : CommandPayload
#   ackFlag  : byte          (usually 0x01)
#   pointTag : byte          (routing: 0x01=head, 0x02=bottom, 0x03=broadcast)
# Output:
#   bytesToSend : byte[]     (exact buffer firmware sends over USB)
function assembleMcuMessage(cmd      : CommandPayload,
                            ackFlag  : byte,
                            pointTag : byte) -> byte[]:
    payload     = buildPayload(cmd)
    framed      = frameUsb(payload, ackFlag)
    bytesToSend = appendPointTag(framed, pointTag)
    return bytesToSend
