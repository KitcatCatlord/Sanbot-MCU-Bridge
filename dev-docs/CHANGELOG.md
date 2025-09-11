# Changelog

All notable changes to this project’s Python library are documented here.

## [1.0.0] - 2025-09-11
- Package renamed to `sanbot-mcu-bridge`; canonical import path `sanbot.mcu_bridge`.
- Console scripts: `sanbot-usb` (MCU CLI), `sanbot-camera` (UVC camera CLI).
- Added safety validator and conservative motion limits (can be disabled via `unsafe=True` or `--unsafe`).
- Implemented labeled decoders for sensors (obstacle/PIR/touch/gyro); improved button status.
- MCU upgrade (YMODEM) helpers and CLI flow included.
- Background listener with decoded events; high-level `Sanbot` API.
- CI workflow for tests; packaging metadata and extras (`camera`, `dev`).
- Documentation: usage guides and conformance notes (in repo only; not bundled with wheel).
