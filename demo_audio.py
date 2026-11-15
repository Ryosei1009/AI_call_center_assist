"""録音で発表するための処理。録音した音声を再生し、そのまま文字起こしに渡す。

マイクの代わりに WAV ファイルを使うだけで、文字起こしから先の処理は同じである。
1ファイルが1発話なので、音声区間検出（vad.py）は通さない。
"""
from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import config


@dataclass
class DemoStep:
    path: Path
    role: str
    text: str = ""       # 台本の文。表示用で、認識には使わない
    new_call: bool = False
    point: str = ""


def load_steps(folder: Path = config.DEMO_AUDIO_DIR) -> list[DemoStep]:
    """フォルダの WAV を名前順に並べる。話者はファイル名の customer / operator で決める。"""
    script = {}
    script_path = config.DATA_DIR / "demo_script.json"
    if script_path.exists():
        with open(script_path, encoding="utf-8") as f:
            script = {item["file"]: item for item in json.load(f)}

    steps = []
    for path in sorted(folder.glob("*.wav")):
        role = "operator" if "operator" in path.stem else "customer"
        item = script.get(path.name, {})
        steps.append(DemoStep(path, role, item.get("text", ""),
                              item.get("new_call", False), item.get("point", "")))
    return steps


def read_wav(path: Path) -> tuple[bytes, wave._wave_params, np.ndarray]:
    """再生用の元データと、文字起こし用の 16kHz・モノラル・float32 を返す。"""
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        raw = w.readframes(params.nframes)
    if params.sampwidth != 2:
        raise ValueError(f"{path.name} は16bitのWAVではありません")

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if params.nchannels > 1:
        samples = samples.reshape(-1, params.nchannels).mean(axis=1)
    if params.framerate != config.SAMPLE_RATE:  # 線形補間でサンプリング周波数を変える
        duration = len(samples) / params.framerate
        n = int(duration * config.SAMPLE_RATE)
        samples = np.interp(np.linspace(0, len(samples) - 1, n),
                            np.arange(len(samples)), samples).astype(np.float32)
    return raw, params, samples


def play(raw: bytes, params) -> None:
    """スピーカーから再生する。終わるまで戻らない。"""
    import pyaudio
    audio = pyaudio.PyAudio()
    stream = audio.open(format=audio.get_format_from_width(params.sampwidth),
                        channels=params.nchannels, rate=params.framerate, output=True)
    try:
        stream.write(raw)
    finally:
        stream.stop_stream()
        stream.close()
        audio.terminate()


def save_wav(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(config.SAMPLE_RATE)
        w.writeframes(data.tobytes())
