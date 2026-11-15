"""録音で発表する処理のテスト。再生と Whisper は使わない。"""
import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from demo_audio import load_steps, read_wav, save_wav
from record_demo import trim


class DemoAudioTest(unittest.TestCase):
    def test_steps_use_file_name_and_script(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("02_operator.wav", "01_customer.wav", "05_customer.wav"):
                save_wav(Path(folder) / name, np.zeros(1600, np.float32))
            steps = load_steps(Path(folder))
        self.assertEqual([s.path.name for s in steps],
                         ["01_customer.wav", "02_operator.wav", "05_customer.wav"])
        self.assertEqual([s.role for s in steps], ["customer", "operator", "customer"])
        self.assertIn("瀬戸内海鮮セット", steps[0].text)
        self.assertTrue(steps[2].new_call)

    def test_stereo_44k_is_converted(self):
        t = np.arange(44100) / 44100
        tone = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "a.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44100)
                w.writeframes(np.repeat(tone, 2).tobytes())
            _, params, samples = read_wav(path)
        self.assertEqual(params.framerate, 44100)
        self.assertAlmostEqual(len(samples), config.SAMPLE_RATE, delta=2)
        self.assertAlmostEqual(float(np.max(samples)), 0.3, delta=0.02)

    def test_trim_removes_silence(self):
        silence = np.zeros(config.SAMPLE_RATE, np.float32)
        voice = 0.2 * np.ones(config.SAMPLE_RATE // 2, np.float32)
        trimmed = trim(np.concatenate([silence, voice, silence]))
        self.assertAlmostEqual(len(trimmed) / config.SAMPLE_RATE, 0.9, delta=0.05)


if __name__ == "__main__":
    unittest.main()
