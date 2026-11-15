"""合成音声で音声区間検出を確認する。実行: python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from vad import UtteranceDetector


def noise(seconds, level=0.002):
    rng = np.random.default_rng(0)
    return (rng.normal(0, level, int(seconds * config.SAMPLE_RATE))).astype(np.float32)


def voice(seconds, level=0.2):
    t = np.arange(int(seconds * config.SAMPLE_RATE)) / config.SAMPLE_RATE
    wave = sum(np.sin(2 * np.pi * f * t) / (i + 1) for i, f in enumerate((150, 300, 900, 2400)))
    return (level * wave).astype(np.float32) + noise(seconds)


def run(signal):
    detector = UtteranceDetector()
    found = []
    for start in range(0, len(signal), config.CHUNK_SAMPLES):  # マイクと同じ単位で渡す
        found += detector.feed(signal[start:start + config.CHUNK_SAMPLES])
    return found


class VadTest(unittest.TestCase):
    def test_no_voice(self):
        self.assertEqual(run(noise(4.0)), [])

    def test_two_utterances(self):
        signal = np.concatenate([noise(1.5), voice(1.0), noise(1.0), voice(2.0), noise(1.0)])
        found = run(signal)
        self.assertEqual(len(found), 2)
        self.assertAlmostEqual(len(found[0].samples) / config.SAMPLE_RATE, 1.9, delta=0.3)
        self.assertAlmostEqual(len(found[1].samples) / config.SAMPLE_RATE, 2.9, delta=0.3)

    def test_short_click_is_ignored(self):
        self.assertEqual(run(np.concatenate([noise(1.5), voice(0.15), noise(1.5)])), [])

    def test_discard_drops_unfinished_speech(self):
        detector = UtteranceDetector()
        detector.feed(np.concatenate([noise(1.5), voice(0.8)]))
        detector.discard()
        self.assertEqual(detector.feed(noise(1.0)), [])
        found = detector.feed(np.concatenate([voice(1.0), noise(1.0)]))
        self.assertEqual(len(found), 1)

    def test_long_speech_is_split(self):
        found = run(np.concatenate([noise(1.5), voice(config.MAX_UTTERANCE_SEC + 3), noise(1.0)]))
        self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
