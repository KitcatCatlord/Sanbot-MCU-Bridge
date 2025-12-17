# Compiled by ChatGPT Codex from original firmware files

# ======================================================
# Sanbot USB Send Pipeline (LOGIC-ONLY PSEUDOCODE GUIDE)
# ======================================================
#
# Purpose:
#   How the original firmware queues/routs outbound USB messages
#   (head/bottom/broadcast) and calls UsbDeviceConnection.bulkTransfer().
#
# Key sources (smali):
#   - tools/decompiled/main-release/smali/com/qihan/uvccamera/bean/UsbMessageMrg.smali
#   - tools/decompiled/main-release/smali/com/qihan/mcumanager/MCUManager.smali
#   - For the frame bytes themselves, see the separate packet assembler guide.
#
# Terminology:
#   - "head"  = point_tag 0x01
#   - "bottom"= point_tag 0x02
#   - "both"  = point_tag 0x03 (head then bottom)

# ------------------------------
# 1. Handler/queue setup (send)
# ------------------------------
#
# UsbMessageMrg.initSendThread():
#   - Starts HandlerThread sendMessageThread
#   - subThreadHandler = Handler tied to that thread
#
# Message.what values (switch in sendMessageToMcu):
#   WHAT_SEND_TO_HEAD   = 0x01
#   WHAT_SEND_TO_BOTTOM = 0x02
#   WHAT_SEND_TO_ALL    = 0x04   # “send to point/broadcast” path
#
# Public entrypoints (MCUManager):
#   MCUSendToHead(buffer)   -> UsbMessageMrg.sendMessageToHead(buffer)
#   MCUSendToBottom(buffer) -> UsbMessageMrg.sendMessageToBottom(buffer)
#   MCUSendToPoint(buffer)  -> UsbMessageMrg.sendMessageToPoint(buffer)
#   (Each wraps the buffer in a Message with a Bundle, posts to subThreadHandler.)

# -------------------------------------
# 2. Message handlers → bulkTransfer()
# -------------------------------------
#
# UsbMessageMrg.sendMessageToMcu(Message msg) switch-cases on msg.what:
#
# Case WHAT_SEND_TO_BOTTOM (0x02):
#   buffer = msg.data["data"]            # full USB frame (no point_tag here)
#   if bottom connection + OUT endpoint exist:
#       bulkTransfer(out_bottom, buffer, len(buffer), 0)
#   else: try enumerate/open bottom every 10th failure
#
# Case WHAT_SEND_TO_HEAD (0x01):
#   buffer = msg.data["data"]
#   if head connection + OUT endpoint exist:
#       bulkTransfer(out_head, buffer, len(buffer), 0)
#   else: try enumerate/open head every 10th failure
#
# Case WHAT_SEND_TO_ALL / “point” (0x04):
#   buffers = msg.data["data"]           # routed = usb_frame + [point_tag]
#   temp    = buffers[0 : len-1]         # strip trailing point_tag
#   tag     = buffers[len-1]
#   switch(tag):
#     0x01: send temp to HEAD (bulkTransfer head)
#     0x02: send temp to BOTTOM (bulkTransfer bottom)
#     0x03: send temp to HEAD, then send temp to BOTTOM
#   (If endpoints missing, same retry/enumerate/open logic as above.)
#
# Case WHAT_SEND_TO_ALL (0x03) in pswitch_data_0 was a fallthrough no-op in smali.
#
# Notes on failure handling:
#   - bottom_fail_time / head_fail_time increment; every 10th failure triggers openXxxConnection()
#   - TAG logs errors like “Head Send Message Failure!” or “…bulkOut return negative”

# ----------------------------------
# 3. Endpoints / device selection
# ----------------------------------
#
# UsbMessageMrg.enumerateBottomDevice / enumerateHeadDevice:
#   VendorID  = 0x0483
#   ProductID = 0x5740 (bottom), 0x5741 (head)
#   Chooses interface/endpoint pairs (mEpBulkOut_* and mEpBulkIn_*)
#   Uses UsbManager.requestPermission via PendingIntent (ACTION_USB_PERMISSION)
#
# openBottomConnection() / openHeadConnection():
#   - claim interface(s), find bulk IN/OUT endpoints
#   - assign mBottomConnection / mHeadConnection and endpoints
#
# closeBottomMCUConnection() / closeHeadMCUConnection():
#   - close connection, null out endpoints

# ------------------------------------------------------
# 4. How to use this from your own control application
# ------------------------------------------------------
#
# a) Build the USB frame bytes (see packet assembler guide).
# b) Choose routing:
#    - If you talk directly to a specific OUT endpoint yourself, send the frame as-is.
#    - If you mimic firmware’s “point” path:
#         routed = usb_frame + [point_tag]
#         sendMessageToPoint(routed)    # firmware strips point_tag before bulkTransfer
# c) Ensure you’ve opened the correct device/interface/endpoint (IDs above).
# d) bulkTransfer(out_endpoint, frame, frame.length, timeout_ms) to send.

