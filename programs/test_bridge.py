#!/usr/bin/env python3
"""Interactive Sanbot MCU bridge exerciser.

This script steps through a small suite of motions / queries and prompts the
user to confirm whether each action completed successfully.  It is designed for
quick bench checks; mount the robot safely (or skip wheel tests) before running.
"""

from __future__ import annotations

import sys
import time
import struct
import logging
from pathlib import Path
from typing import List, Tuple

import click

# Ensure repo root is importable when running from source checkout
ROOT = Path(__file__).resolve().parent
if str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

try:
    from sanbot.mcu_bridge import usb_bridge as bridge  # type: ignore
except Exception as exc:  # pragma: no cover - defensive runtime import
    raise click.ClickException(f"Unable to import sanbot.mcu_bridge.usb_bridge: {exc}")


def _prompt(label: str) -> bool:
    response = input(f"✔︎ {label} (y/N): ").strip().lower()
    return response in {"y", "yes"}


def _print_header(title: str) -> None:
    click.echo(click.style(f"\n=== {title} ===", fg="cyan"))


@click.command()
@click.option('--include-wheels/--skip-wheels', default=False,
              help='Exercise wheel motions (ensure the robot is safely raised).')
@click.option('--wheel-speed', type=int, default=80, show_default=True,
              help='Speed byte for the wheel test when enabled (0-255).')
@click.option('--head-speed', type=int, default=40, show_default=True,
              help='Speed byte for head tests (0-255).')
@click.option('--arm-speed', type=int, default=60, show_default=True,
              help='Speed byte for arm exercise (0-255).')
@click.option('--duration', type=int, default=600, show_default=True,
              help='Duration in milliseconds for timed tests.')
def main(include_wheels: bool, wheel_speed: int, head_speed: int,
         arm_speed: int, duration: int) -> None:
    """Run the interactive MCU bridge tester."""
    # Configure global CLI defaults
    bridge.CLI_DUMP_TX = True
    bridge.CLI_AUTO_READ = True
    bridge.CLI_READ_TIMEOUT_MS = max(100, bridge.CLI_READ_TIMEOUT_MS)
    bridge.CLI_AUTO_HEARTBEAT = True
    bridge.CLI_HEARTBEAT_INTERVAL_MS = max(500, bridge.CLI_HEARTBEAT_INTERVAL_MS)
    bridge.CLI_HEARTBEAT_HEAD = True
    bridge.HEARTBEAT_MANAGER.configure(
        enabled=True,
        interval_ms=bridge.CLI_HEARTBEAT_INTERVAL_MS,
        head_enabled=True,
    )
    logging.getLogger("mcu_bridge").setLevel(logging.INFO)

    click.echo("Attempting to connect to Sanbot MCUs…")
    bottom_dev = bridge.find_device(bridge.VID, bridge.PID_BOTTOM)
    head_dev = bridge.find_device(bridge.VID, bridge.PID_HEAD)
    if bottom_dev is None or head_dev is None:
        raise click.ClickException("Unable to locate head and/or bottom MCU over USB")

    bottom = bridge.claim_bulk_endpoints(bottom_dev)
    head = bridge.claim_bulk_endpoints(head_dev)
    results: List[Tuple[str, bool]] = []

    try:
        _print_header('Heartbeat')
        for tag, eps, label in ((bridge.POINT_BOTTOM, bottom, 'bottom'),
                                (bridge.POINT_HEAD, head, 'head')):
            frame = bridge.build_usb_frame(bridge.heartbeat_payload()) + struct.pack('B', tag)
            bridge.send_command(eps, frame, label=f'heartbeat_{label}')
        results.append(('Heartbeat acknowledged', _prompt('Heartbeat responses looked OK?')))

        if include_wheels:
            _print_header('Wheels')
            bridge._unlock_wheels(bottom)
            wheels_frame = bridge.build_usb_frame(
                bridge.wheel_payload(
                    0x01,
                    bridge.WHEEL_RUN_ACTIONS['forward'],
                    speed=wheel_speed,
                    ms=duration,
                )
            ) + struct.pack('B', bridge.POINT_BOTTOM)
            bridge.send_command(bottom, wheels_frame, label='wheels_forward')
            results.append(('Wheel forward run', _prompt('Wheels spun briefly without issues?')))
        else:
            results.append(('Wheel test skipped', True))

        _print_header('Head vertical nod')
        bridge._unlock_head(head)
        head_down = bridge.build_usb_frame(
            bridge.head_payload(
                0x03,
                bridge.HEAD_ABSOLUTE_AXES['vertical'],
                speed=head_speed,
                deg=-10,
            )
        ) + struct.pack('B', bridge.POINT_HEAD)
        bridge.send_command(head, head_down, label='head_down')
        results.append(('Head vertical move', _prompt('Head nodded downwards?')))

        _print_header('Left arm')
        arm_frame = bridge.build_usb_frame(
            bridge.hand_payload(0x02, 0x11, direction=0x01, speed=arm_speed, deg=20)
        ) + struct.pack('B', bridge.POINT_BOTTOM)
        bridge.send_command(bottom, arm_frame, label='left_arm_angle')
        results.append(('Left arm lift', _prompt('Left arm raised slightly?')))

        _print_header('Sensors (battery / gyro / touch)')
        sensor_frames = [
            (bridge.battery_query_payload(), bridge.POINT_BOTTOM, 'battery'),
            (bridge.gyro_query_payload(), bridge.POINT_BOTTOM, 'gyro'),
            (bytes([0x81, 0x05, 0x01, 0x00]), bridge.POINT_HEAD, 'touch'),
        ]
        for payload, tag, label in sensor_frames:
            frame = bridge.build_usb_frame(payload) + struct.pack('B', tag)
            bridge.send_command(bottom if tag == bridge.POINT_BOTTOM else head,
                                 frame, label=f'sensor_{label}', expect_response=True)
            time.sleep(0.2)
        results.append(('Sensor responses', _prompt('Decoded sensor replies looked correct?')))

    finally:
        bridge.release_endpoints(bottom)
        bridge.release_endpoints(head)
        bridge.HEARTBEAT_MANAGER.stop()

    _print_header('Summary')
    for label, success in results:
        status = 'PASS' if success else 'FAIL'
        colour = 'green' if success else 'red'
        click.echo(f"{label:<30} {click.style(status, fg=colour)}")
    failures = [label for label, ok in results if not ok]
    if failures:
        raise click.ClickException(f"Issues observed: {', '.join(failures)}")
    click.echo(click.style('All checks passed!', fg='green'))


if __name__ == '__main__':
    main()
