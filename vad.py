"""音声区間検出（VAD）。第15,16回の内容をそのまま実装している。

処理の流れ:
  1. 波形を25msのフレームに切り、10msずつずらす
  2. 高域強調 H(z) = 1 - 0.97z^-1 をかける
  3. フレームごとに「音声パワー」と「ゼロ交差率」を計算する
  4. 開始直後に測った雑音より十分大きいフレームを音声とみなす
  5. 音声が続いたら発話開始、無音が続いたら発話終了とする

パワーの小さい無声子音（サ行など）はパワーだけだと切れやすいので、
ゼロ交差率が高いフレームは少し低いパワーでも音声として扱う。
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

import config


@dataclass
class Utterance:
    """検出した1発話。samples は -1.0〜1.0 の float32。"""
    samples: np.ndarray
    ended_at: float = field(default_factory=time.time)


def pre_emphasis(frame: np.ndarray, coef: float = config.PRE_EMPHASIS) -> np.ndarray:
    return np.append(frame[0], frame[1:] - coef * frame[:-1])


def frame_power_db(frame: np.ndarray) -> float:
    return float(10.0 * np.log10(np.mean(frame ** 2) + 1e-10))


def zero_crossing_rate(frame: np.ndarray) -> float:
    return float(np.mean(np.abs(np.diff(np.sign(frame))) > 0))


class UtteranceDetector:
    """音声を少しずつ受け取り、発話が終わるたびに Utterance を返す。"""

    def __init__(self, sample_rate: int = config.SAMPLE_RATE):
        self.frame_len = sample_rate * config.FRAME_MS // 1000
        self.shift = sample_rate * config.SHIFT_MS // 1000
        self.start_frames = config.SPEECH_START_MS // config.SHIFT_MS
        self.end_frames = config.SPEECH_END_MS // config.SHIFT_MS
        self.calibration_frames = int(config.CALIBRATION_SEC * 1000 / config.SHIFT_MS)
        self.max_frames = int(config.MAX_UTTERANCE_SEC * 1000 / config.SHIFT_MS)
        self.min_voiced_frames = config.MIN_VOICED_MS // config.SHIFT_MS
        self.pre_roll = deque(maxlen=config.PRE_ROLL_MS // config.SHIFT_MS)

        self.buffer = np.zeros(0, dtype=np.float32)
        self.noise_powers: list[float] = []
        self.threshold_db: float | None = None

        self.in_speech = False
        self.speech_run = 0
        self.silence_run = 0
        self.voiced_frames = 0
        self.current: list[np.ndarray] = []

    def feed(self, samples: np.ndarray) -> list[Utterance]:
        """新しい音声を追加し、この時点で確定した発話を返す。"""
        self.buffer = np.concatenate([self.buffer, samples])
        finished: list[Utterance] = []
        while len(self.buffer) >= self.frame_len:
            frame = self.buffer[: self.frame_len]
            hop = self.buffer[: self.shift].copy()
            self.buffer = self.buffer[self.shift :]
            utterance = self._process_frame(frame, hop)
            if utterance is not None:
                finished.append(utterance)
        return finished

    def _is_speech(self, frame: np.ndarray) -> bool:
        emphasized = pre_emphasis(frame)
        power = frame_power_db(emphasized)

        if self.threshold_db is None:
            self.noise_powers.append(power)
            if len(self.noise_powers) >= self.calibration_frames:
                # 雑音の大きさを中央値で求める。少し声が入っても外れにくい。
                self.threshold_db = float(np.median(self.noise_powers)) + config.POWER_MARGIN_DB
            return False

        if power >= self.threshold_db:
            return True
        return (
            power >= self.threshold_db - 5.0
            and zero_crossing_rate(emphasized) >= config.ZCR_THRESHOLD
        )

    def _process_frame(self, frame: np.ndarray, hop: np.ndarray) -> Utterance | None:
        speech = self._is_speech(frame)

        if not self.in_speech:
            self.pre_roll.append(hop)
            self.speech_run = self.speech_run + 1 if speech else 0
            if self.speech_run >= self.start_frames:
                self.in_speech = True
                self.silence_run = 0
                self.voiced_frames = self.speech_run
                self.current = list(self.pre_roll)
                self.pre_roll.clear()
            return None

        self.current.append(hop)
        self.silence_run = 0 if speech else self.silence_run + 1
        self.voiced_frames += speech
        if self.silence_run >= self.end_frames or len(self.current) >= self.max_frames:
            return self._finish()
        return None

    def discard(self) -> None:
        """話している途中の音声を捨てる（ミュートしたとき用）。雑音の測定結果は残す。"""
        self.buffer = np.zeros(0, dtype=np.float32)
        self.pre_roll.clear()
        self.in_speech = False
        self.speech_run = 0
        self.silence_run = 0
        self.voiced_frames = 0
        self.current = []

    def _finish(self) -> Utterance | None:
        samples = np.concatenate(self.current).astype(np.float32)
        enough_voice = self.voiced_frames >= self.min_voiced_frames
        self.in_speech = False
        self.speech_run = 0
        self.silence_run = 0
        self.current = []
        # 物音のような短い音は文字起こしへ渡さない
        return Utterance(samples=samples) if enough_voice else None
