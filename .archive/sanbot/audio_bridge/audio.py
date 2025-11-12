#!/usr/bin/env python3
import queue
import time
from dataclasses import dataclass
from typing import Iterator, Optional, List

import click

try:
    import sounddevice as sd  # type: ignore
    import soundfile as sf    # type: ignore
except Exception as e:  # pragma: no cover
    sd = None  # type: ignore
    sf = None  # type: ignore


@dataclass
class AudioDevice:
    index: int
    name: str
    inputs: int
    samplerates: Optional[str]


class Audio:
    def __init__(self, index: int, samplerate: int = 16000, channels: int = 1, blocksize: int = 1024):
        self.index = index
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._stream = None

    def open(self):
        if sd is None:
            raise RuntimeError("sounddevice is required. Install with: pip install sanbot-mcu-bridge[audio]")
        def _callback(indata, frames, time_info, status):  # type: ignore
            if status:
                pass
            self._q.put(bytes(indata.tobytes()))
        self._stream = sd.InputStream(device=self.index, channels=self.channels,
                                      samplerate=self.samplerate, blocksize=self.blocksize,
                                      dtype='int16', callback=_callback)
        self._stream.start()

    def close(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def frames(self) -> Iterator[bytes]:
        while True:
            try:
                chunk = self._q.get(timeout=1.0)
                yield chunk
            except queue.Empty:
                break


def list_devices() -> List[AudioDevice]:
    if sd is None:
        raise RuntimeError("sounddevice is required. Install with: pip install sanbot-mcu-bridge[audio]")
    devices = []
    for idx, d in enumerate(sd.query_devices()):  # type: ignore
        if int(d.get('max_input_channels', 0)) > 0:
            sr = None
            devices.append(AudioDevice(index=idx, name=d.get('name', f'dev{idx}'),
                                       inputs=int(d.get('max_input_channels', 0)),
                                       samplerates=sr))
    return devices


@click.group()
def cli():
    """Audio capture helper (Linux/ALSA): list/preview/record/stream."""


@cli.command('list')
def list_cmd():
    devs = list_devices()
    if not devs:
        print("No audio input devices found")
        return
    for d in devs:
        print(f"[{d.index}] {d.name} (inputs={d.inputs})")


@cli.command('preview')
@click.option('--index', type=int, required=True)
@click.option('--samplerate', type=int, default=16000)
@click.option('--channels', type=int, default=1)
@click.option('--seconds', type=int, default=10)
def preview_cmd(index: int, samplerate: int, channels: int, seconds: int):
    import numpy as np
    aud = Audio(index=index, samplerate=samplerate, channels=channels)
    aud.open()
    print(f"Preview device {index} {samplerate}Hz ch={channels} for {seconds}s (Ctrl-C to stop)")
    start = time.time()
    try:
        while time.time() - start < seconds:
            data = next(aud.frames(), None)
            if not data:
                continue
            arr = np.frombuffer(data, dtype=np.int16)
            rms = float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))
            print(f"RMS: {rms:.1f}")
    except KeyboardInterrupt:
        pass
    finally:
        aud.close()


@cli.command('record')
@click.option('--index', type=int, required=True)
@click.option('--out', 'out_path', type=str, required=True)
@click.option('--seconds', type=int, required=True)
@click.option('--samplerate', type=int, default=16000)
@click.option('--channels', type=int, default=1)
def record_cmd(index: int, out_path: str, seconds: int, samplerate: int, channels: int):
    if sf is None:
        raise click.ClickException("soundfile is required. Install with: pip install sanbot-mcu-bridge[audio]")
    aud = Audio(index=index, samplerate=samplerate, channels=channels)
    aud.open()
    print(f"Recording {seconds}s to {out_path} ...")
    frames = []
    start = time.time()
    try:
        while time.time() - start < seconds:
            data = next(aud.frames(), None)
            if data:
                frames.append(data)
    except KeyboardInterrupt:
        pass
    finally:
        aud.close()
    if frames:
        import numpy as np
        arr = np.frombuffer(b"".join(frames), dtype=np.int16)
        sf.write(out_path, arr, samplerate, subtype='PCM_16')
        print(f"Saved: {out_path}")
    else:
        print("No frames captured.")


@cli.command('stream')
@click.option('--index', type=int, required=True)
@click.option('--samplerate', type=int, default=16000)
@click.option('--channels', type=int, default=1)
@click.option('--port', type=int, default=8090)
def stream_cmd(index: int, samplerate: int, channels: int, port: int):
    from flask import Flask, Response
    aud = Audio(index=index, samplerate=samplerate, channels=channels)
    aud.open()
    app = Flask(__name__)

    @app.route('/stream.pcm')
    def stream_pcm():
        def gen():
            try:
                while True:
                    data = next(aud.frames(), None)
                    if not data:
                        time.sleep(0.01)
                        continue
                    yield data
            except GeneratorExit:
                pass
        return Response(gen(), mimetype='application/octet-stream')

    print(f"Serving raw PCM at http://localhost:{port}/stream.pcm (s16le {samplerate}Hz ch={channels})")
    try:
        app.run(host='0.0.0.0', port=port, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        aud.close()


if __name__ == '__main__':
    cli()
