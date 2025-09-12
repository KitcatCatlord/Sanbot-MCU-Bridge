# Audio Bridge (Linux/ALSA)

The MCU USB link does not carry raw audio. On Linux (PiOS), capture audio from
the ALSA device and use the audio bridge tools.

## CLI
```
pip install sanbot-mcu-bridge[audio]
sanbot-audio list
sanbot-audio preview --index 0 --samplerate 16000 --channels 1 --seconds 10
sanbot-audio record --index 0 --seconds 5 --out mic.wav --samplerate 16000 --channels 1
sanbot-audio stream --index 0 --samplerate 16000 --channels 1 --port 8090
```

## Library
```
from sanbot.audio_bridge.audio import Audio
aud = Audio(index=0, samplerate=16000, channels=1)
aud.open()
for chunk in aud.frames():
    pass
aud.close()
```

