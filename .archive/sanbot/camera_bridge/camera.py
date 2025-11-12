#!/usr/bin/env python3
import os
import time
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple, Iterator

import click
import cv2
from flask import Flask, Response


@dataclass
class CameraInfo:
    index: int
    name: Optional[str]
    size: Optional[Tuple[int, int]]


class Camera:
    def __init__(self, index: int, width: Optional[int] = None, height: Optional[int] = None):
        self.index = index
        self.width = width
        self.height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()

    def open(self):
        cap = cv2.VideoCapture(self.index)
        if self.width:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open camera index {self.index}")
        self.cap = cap

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def read(self) -> Optional[Tuple[bool, 'cv2.Mat']]:
        if self.cap is None:
            raise RuntimeError('Camera not opened')
        with self._lock:
            ok, frame = self.cap.read()
        return (ok, frame) if ok else None

    def frames(self) -> Iterator['cv2.Mat']:
        while True:
            r = self.read()
            if not r:
                break
            _, frame = r
            yield frame


def _linux_v4l2_names() -> dict:
    names = {}
    sysdir = '/sys/class/video4linux'
    if os.path.isdir(sysdir):
        for entry in os.listdir(sysdir):
            name_path = os.path.join(sysdir, entry, 'name')
            dev = os.path.join('/dev', entry)
            if os.path.isfile(name_path) and os.path.exists(dev):
                try:
                    with open(name_path, 'r') as f:
                        names[dev] = f.read().strip()
                except Exception:
                    pass
    return names


def list_cameras(max_index: int = 10) -> List[CameraInfo]:
    infos: List[CameraInfo] = []
    v4l2_names = _linux_v4l2_names()
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if not cap.isOpened():
            cap.release()
            continue
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        # Try to map index->device name on Linux
        name = None
        dev = f"/dev/video{idx}"
        if dev in v4l2_names:
            name = v4l2_names[dev]
        infos.append(CameraInfo(index=idx, name=name, size=(w, h) if w and h else None))
    return infos


def mjpeg_stream(cam: Camera, quality: int = 80) -> Iterator[bytes]:
    for frame in cam.frames():
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            continue
        jpg = buf.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")


@click.group()
def cli():
    """UVC Camera helper (list/preview/stream)."""


@cli.command('list')
@click.option('--max', 'max_index', type=int, default=10)
def list_cmd(max_index: int):
    infos = list_cameras(max_index=max_index)
    if not infos:
        print("No cameras found")
        return
    for info in infos:
        size = f"{info.size[0]}x{info.size[1]}" if info.size else "?"
        name = info.name or "(unknown)"
        print(f"[{info.index}] {name} {size}")


@cli.command('preview')
@click.option('--index', type=int, required=True)
@click.option('--width', type=int, default=None)
@click.option('--height', type=int, default=None)
@click.option('--headless', is_flag=True, help='No window; print FPS')
def preview_cmd(index: int, width: Optional[int], height: Optional[int], headless: bool):
    cam = Camera(index, width, height)
    cam.open()
    print(f"Opened camera index {index}")
    start = time.time()
    frames = 0
    try:
        if headless:
            for _ in cam.frames():
                frames += 1
                if frames % 60 == 0:
                    elapsed = time.time() - start
                    fps = frames / elapsed if elapsed > 0 else 0
                    print(f"{frames} frames, {fps:.1f} FPS")
        else:
            while True:
                r = cam.read()
                if not r:
                    break
                _, frame = r
                frames += 1
                cv2.imshow('preview', frame)
                if cv2.waitKey(1) & 0xFF in (27,):  # Esc
                    break
    except KeyboardInterrupt:
        pass
    finally:
        cam.close()
        cv2.destroyAllWindows()
        elapsed = time.time() - start
        fps = frames / elapsed if elapsed > 0 else 0
        print(f"Closed camera. {frames} frames, {fps:.1f} FPS")


@cli.command('snapshot')
@click.option('--index', type=int, required=True)
@click.option('--out', 'out_path', type=str, required=True)
@click.option('--width', type=int, default=None)
@click.option('--height', type=int, default=None)
def snapshot_cmd(index: int, out_path: str, width: Optional[int], height: Optional[int]):
    cam = Camera(index, width, height)
    cam.open()
    try:
        r = cam.read()
        if not r:
            raise click.ClickException('Failed to read frame')
        _, frame = r
        ok = cv2.imwrite(out_path, frame)
        if not ok:
            raise click.ClickException('Failed to write file')
        print(f"Saved snapshot to {out_path}")
    finally:
        cam.close()


@cli.command('stream')
@click.option('--index', type=int, required=True)
@click.option('--port', type=int, default=8080)
@click.option('--width', type=int, default=None)
@click.option('--height', type=int, default=None)
@click.option('--quality', type=int, default=80)
def stream_cmd(index: int, port: int, width: Optional[int], height: Optional[int], quality: int):
    cam = Camera(index, width, height)
    cam.open()
    app = Flask(__name__)

    @app.route('/stream')
    def stream():
        return Response(mjpeg_stream(cam, quality=quality), mimetype='multipart/x-mixed-replace; boundary=frame')

    print(f"Serving MJPEG on http://localhost:{port}/stream (Ctrl-C to stop)")
    try:
        app.run(host='0.0.0.0', port=port, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        cam.close()


if __name__ == '__main__':
    cli()

