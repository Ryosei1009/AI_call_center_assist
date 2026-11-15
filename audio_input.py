"""マイク入力。授業の onsei_nyuryoku.py と同じく PyAudio を使う。

文字起こしは時間がかかるので、録音を止めないように別スレッドで受け取り、
発話が確定したらキューへ渡す。
"""
from __future__ import annotations

import queue
import threading
from typing import Callable

import numpy as np

import config
from vad import Utterance, UtteranceDetector, frame_power_db


class MicrophoneListener:
    def __init__(self, utterances: "queue.Queue[Utterance]",
                 on_level: Callable[[float], None] | None = None):
        self.utterances = utterances
        self.on_level = on_level
        self._stop = threading.Event()
        self.muted = threading.Event()  # セットされている間は音声を捨てる
        self._thread: threading.Thread | None = None
        self.error: Exception | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        try:
            import pyaudio
            audio = pyaudio.PyAudio()
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=config.CHANNELS,
                rate=config.SAMPLE_RATE,
                input=True,
                frames_per_buffer=config.CHUNK_SAMPLES,
            )
        except Exception as exc:  # マイクがない場合などは画面に表示する
            self.error = exc
            return

        detector = UtteranceDetector()
        was_muted = False
        try:
            while not self._stop.is_set():
                data = stream.read(config.CHUNK_SAMPLES, exception_on_overflow=False)
                if self.muted.is_set():
                    # 録音は続けるが使わない。止めると再開時に音が途切れやすいため
                    if not was_muted:
                        detector.discard()  # 話していた途中の音声も捨てる
                        was_muted = True
                    continue
                was_muted = False
                samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                if self.on_level is not None:
                    self.on_level(frame_power_db(samples))
                for utterance in detector.feed(samples):
                    self.utterances.put(utterance)
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
