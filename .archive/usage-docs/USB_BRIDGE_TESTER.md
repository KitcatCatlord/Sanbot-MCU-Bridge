# USB Bridge Tester GUI

The USB Bridge Tester provides an all-in-one GUI for exercising every command
from `sanbot.mcu_bridge.usb_bridge`, previewing camera and microphone streams,
monitoring inbound USB data, and recording any combination of those feeds to
disk. It is meant to be a quick functional test bench when you are bringing up
hardware or validating firmware changes.

For a lightweight console-based check (no GUI), see `transfer/test_bridge.py`.

## Installation

On Raspberry Pi you can run the helper script (installs APT packages, creates
`.venv`, and installs the tester extras):

```
./programs/setup_pi_tester.sh
```

If you prefer manual installation, install the tester extras directly:

```
pip install .[tester]
```

The tester relies on:

- PySide6 (Qt based GUI)
- pyqtgraph (real-time waveform plotting)
- opencv-python (camera capture + recording)
- sounddevice / PortAudio (microphone capture)
- numpy
- pyusb (already required by the core package)

Ensure your OS has working camera and audio backends (e.g. v4l2 on Linux,
DirectShow/CoreAudio on Windows/macOS).

## Launching the GUI

From the repository root:

```
sanbot-bridge-gui
```

The launcher applies a dark Fusion theme, tabs for media tools, and auto-loads
the latest CLI commands. For backwards compatibility you can still run
`python programs/usb_bridge_tester.py`.

For a hardware-free dry run (synthetic camera/audio/USB data), launch the demo
variant:

```
python programs/usb_bridge_tester_demo.py
```

## Layout overview

- **Command panel (left)** – Searchable tree of every Click command/group
  defined in `usb_bridge.py`. Use the filter box to quickly locate commands,
  expand/collapse in one click, and reload definitions if you are editing the
  CLI. Selecting a command exposes all options with type-aware widgets. Use
  **Ctrl+Enter** (or double-click) to trigger the selection. Global CLI options
  such as retries, auto-read, heartbeat, and TX dumping can be toggled from the
  status panel, so the GUI now mirrors all CLI behaviour.
- **Camera pane (top-right)** – Live preview with selectable device index, and
  start/stop controls. Recording writes MJPEG `.avi` clips under
  `recordings/session_*/camera/`.
- **Microphone pane (middle-right)** – Real-time waveform of the chosen input
  device. Recording writes `.wav` files under
  `recordings/session_*/audio/`.
- **USB monitor (bottom-right)** – Continuous read from the bulk IN endpoint for
  the selected MCU (`bottom` or `head`). Raw hex plus a best-effort decoded view
  is shown, and recorded `.bin` dumps are stored under
  `recordings/session_*/usb/`.
- **Log panel (bottom-right)** – Status messages, command execution outcomes,
  and device errors in a dark themed console that retains ~2000 lines.
- **Status strip (bottom)** – Apply the full CLI defaults (log level, retries,
  safety, auto-read, timeouts, heartbeat settings, TX dumping), see how many
  commands are loaded, toggle recording, and trigger the emergency stop.

The GUI watches the CLI module on disk; saving `sanbot/mcu_bridge/usb_bridge.py`
automatically reloads the command tree so you always see the newest options.

Each executed command is captured to `recordings/session_*/commands/commands.jsonl`
when recording is active.

## Recording workflow

1. Click **Start Recording (Ctrl+R)** to open a timestamped session folder under
   `recordings/`.
2. While recording is enabled, camera frames, audio samples, USB payloads, and
   command metadata are saved to per-type files.
3. Stop recording with **Ctrl+Shift+R** (or the button). This closes all open
   files and finalises the session.

You may start/stop camera, microphone, or USB monitoring independently of the
recording state.

## Hotkeys

- `Ctrl+Enter` – Execute the selected USB bridge command
- `Ctrl+K` – Start camera preview
- `Ctrl+M` – Start microphone capture
- `Ctrl+U` – Start USB monitoring
- `Ctrl+R` – Start recording session
- `Ctrl+Shift+R` – Stop recording session
- `Ctrl+L` – Apply CLI global settings (log level, retries, safety, auto read,
  heartbeat, dump TX)
- `Ctrl+Shift+E` – Emergency stop (stops all streams, recording, and command
  threads)

## Emergency stop

The red **EMERGENCY STOP** button (and its hotkey) forcibly halts camera,
audio, USB monitoring, and any in-flight command threads, then tears down open
recording files. Use it whenever hardware misbehaves—no need to hunt individual
stop buttons.

## Tips

- Apply the CLI defaults (log level, retries, safety, auto-read, heartbeat,
  dump TX) before dispatching commands so the underlying globals in
  `usb_bridge.py` match your intent.
- USB decoding uses the same `_decode_known_datas` helper as the CLI; for
  unknown frames you still see the raw hex for manual analysis.
- If a dependency is missing, the program exits with an installation hint so you
  know which package to add.
- Generated files live under `recordings/`; clean up old sessions periodically
  if you are running many tests.

## Troubleshooting

- **Camera/mic not listed** – verify the OS sees the devices. Restart the GUI
  after connecting hardware so the device list refreshes.
- **USB monitor errors** – confirm you have permission to access the Sanbot USB
  device (`pytest` udev rules on Linux, no driver conflict on Windows).
- **Safety limit failures** – either change your inputs or enable the `unsafe`
  checkbox before executing commands (not recommended on live hardware unless
  you are sure).

Enjoy experimenting with the bridge! Contributions to refine the tester are
welcome.
