# Compiled by ChatGPT Codex from original firmware files

# =========================================================
# Sanbot USB Receive / Frame Parse (LOGIC-ONLY PSEUDOCODE)
# =========================================================
#
# Purpose:
#   How the original firmware reads from USB bulk IN endpoints,
#   splits the stream into complete frames, and verifies checksum.
#
# Key sources (smali):
#   - tools/decompiled/main-release/smali/com/qihan/uvccamera/ConvertUtils.smali
#       * isComplete([B)
#       * returnListByte([B)
#       * returnBytes([B)
#   - tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/UsbMessageMrg.smali
#       * startReceiveBottomMessage / startReceiveHeadMessage / decodeBtmData / decodeTopData
#   - Frame format itself: see packet assembler guide for field meanings.
#
# Header constants (checked by parsers):
#   type bytes (big-endian) = 0xA4 0x03   # matches USBCommand type 0xA403
#   USB_HEAD_LENGTH         = 0x10        # 16-byte fixed header

# ----------------------------
# 1. Frame boundary detection
# ----------------------------
#
# Helpers scan an accumulated byte buffer that may contain 0..N whole frames plus a partial tail.
#
# Common steps in both returnListByte() and returnBytes():
#   - Require buffer length >= minimum (0x15 for returnListByte, 0x10 for returnBytes).
#   - Verify header bytes: buf[0] == 0xA4 (-0x5c), buf[1] == 0x03.
#   - Read msg_size (4 bytes, big-endian) from buf[4..7]; call it messageLength.
#   - totalFrameLen = messageLength + 0x10 (header size).
#   - If totalFrameLen > available buffer: stop (leave data for next read).
#   - Else: slice that many bytes as one frame, append to output list, and remove them from the front of the buffer; loop.
#
# returnListByte(totalMessage : byte[]) -> List<Byte[]>:
#   - Uses threshold len >= 0x15 before attempting parse.
#   - Expects header bytes 0xA4, 0x03.
#   - Extracts frames as described above; if not enough bytes for a full frame, flag=false and exit.
#
# returnBytes(totalMessage : byte[]) -> List<Byte[]>:
#   - Similar logic but minimum length check is len >= 0x10.
#   - Also checks header bytes and uses msg_size to carve frames.
#   - If totalFrameLen exceeds available bytes, stops and leaves remainder.

# ---------------------
# 2. Checksum validate
# ---------------------
#
# isComplete(frame : byte[]) -> bool
#   - Expects full frame including header and checksum.
#   - Copies bytes from index 0x10 to end into temp_command (i.e., frame_head, ack, mmnn, datas..., checksum).
#   - Sums all bytes of temp_command except its last byte (checksum position).
#   - Computes low 8 bits of that sum (via binary string padding, but equivalent to sum & 0xFF).
#   - Compares to the last byte of the original frame. Returns true if equal.
#
# Interpretation:
#   This matches the send-side checksum: sum(frame_head bytes + ack + mmnn value + datas) mod 256.
#   Note: because it sums raw bytes as signed, the final &0xFF behavior is equivalent for verification.

# --------------------------------------
# 3. Receive loop (UsbMessageMrg tasks)
# --------------------------------------
#
# In firmware, dedicated BaseTask runnables do:
#   - bulkTransfer(IN_endpoint, buffer, maxLen, timeout)
#   - append received bytes to an accumulation buffer (top_total_byte / btm_total_byte)
#   - use ConvertUtils.returnListByte(...) to split into complete frames
#   - for each frame: isComplete(frame) check; if valid, dispatch to higher-level decoder (DecodeCommand, etc.)
#   - manages separate queues for head and bottom (top_queue / btm_queue) and status tags to track partial data
#
# The exact thread/queue management is internal, but the essential parsing steps are:
#   1) accumulate stream bytes
#   2) carve complete frames using header check + msg_size length
#   3) verify checksum with isComplete
#   4) hand off good frames; keep any tail bytes for the next read

# -----------------------------------------
# 4. How to replicate in your own receiver
# -----------------------------------------
#
# Maintain a per-endpoint byte buffer.
# On each bulk IN read:
#   buffer.append(newBytes)
#   frames = returnListByte(buffer)
#   for each f in frames:
#       if isComplete(f): handleFrame(f)
#   # rebuild buffer with any leftover tail bytes that weren’t part of a complete frame
#
# Frame fields (for your downstream decoder):
#   offset 0-1   : type (0xA403)
#   offset 2-3   : subtype
#   offset 4-7   : msg_size (content_len, big-endian)
#   offset 8     : ack_flg
#   offset 9-15  : unuse[7]
#   offset 16-17 : frame_head (0xFFA5)
#   offset 18    : ack_flg (again)
#   offset 19-20 : mmnn (little-endian on send side; carried verbatim here)
#   offset 21..-2: datas[]
#   offset -1    : checkSum

# -------------------------------------------------
# 5. Notes on routing / point_tag (receive side)
# -------------------------------------------------
#
# The receive parser does NOT handle point_tag. The routed byte is only appended on send;
# it is stripped before bulkTransfer. So received frames are plain USBCommand frames with no trailing tag.

