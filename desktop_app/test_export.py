"""Verify the audible stem selection is rendered into a complete WAV."""
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from app import write_mix

with tempfile.TemporaryDirectory() as folder:
    out = Path(folder) / 'backing.wav'
    voice = np.full((1000, 2), 0.2, dtype=np.float32)
    drums = np.full((1000, 2), 0.1, dtype=np.float32)
    write_mix([drums], 44100, out)
    audio, rate = sf.read(out)
    assert rate == 44100 and audio.shape == (1000, 2)
    assert np.max(np.abs(audio - 0.1)) < 0.0001
    write_mix([voice, drums], 44100, out)
    audio, _ = sf.read(out)
    assert np.max(np.abs(audio - 0.3)) < 0.0001
print('export mix check OK')
