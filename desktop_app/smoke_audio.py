"""Create a tiny synthetic input for packaged engine integration testing."""
import math
import struct
import wave

with wave.open('smoke.wav', 'wb') as output:
    output.setnchannels(2)
    output.setsampwidth(2)
    output.setframerate(44100)
    samples = bytearray()
    for i in range(44100):
        value = int(8000 * math.sin(2 * math.pi * 440 * i / 44100))
        samples.extend(struct.pack('<hh', value, value))
    output.writeframes(samples)
