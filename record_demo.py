"""発表用の音声を、台本（data/demo_script.json）に沿って1発話ずつ録音する。

実行:  python record_demo.py        … 全部録音する
       python record_demo.py 3      … 3番だけ録り直す
Enter で録音開始、もう一度 Enter で停止。確認で再生し、よければ保存する。
"""
from __future__ import annotations

import json
import sys
import threading

import numpy as np

import config
from demo_audio import play, read_wav, save_wav

TRIM_DB = -40.0  # 前後の無音を削るしきい値


def record_until_enter() -> np.ndarray:
    import pyaudio
    audio = pyaudio.PyAudio()
    stream = audio.open(format=pyaudio.paInt16, channels=1, rate=config.SAMPLE_RATE,
                        input=True, frames_per_buffer=config.CHUNK_SAMPLES)
    chunks, stop = [], threading.Event()

    def loop():
        while not stop.is_set():
            chunks.append(stream.read(config.CHUNK_SAMPLES, exception_on_overflow=False))

    thread = threading.Thread(target=loop)
    thread.start()
    input("  録音中… 話し終えたら Enter")
    stop.set()
    thread.join()
    stream.stop_stream()
    stream.close()
    audio.terminate()
    return np.frombuffer(b"".join(chunks), dtype=np.int16).astype(np.float32) / 32768.0


def trim(samples: np.ndarray) -> np.ndarray:
    """前後の無音を削り、0.2秒ずつ余白を付ける。"""
    frame = config.SAMPLE_RATE // 100
    n = len(samples) // frame
    if n == 0:
        return samples
    power = 10 * np.log10(np.mean(samples[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-10)
    voiced = np.where(power > TRIM_DB)[0]
    if len(voiced) == 0:
        return samples
    margin = 20
    start = max(voiced[0] - margin, 0) * frame
    end = min(voiced[-1] + margin + 1, n) * frame
    return samples[start:end]


def main() -> None:
    with open(config.DATA_DIR / "demo_script.json", encoding="utf-8") as f:
        script = json.load(f)
    targets = range(len(script))
    if len(sys.argv) > 1:
        targets = [int(sys.argv[1]) - 1]

    for i in targets:
        item = script[i]
        who = "お客様" if item["role"] == "customer" else "オペレーター"
        print(f"\n[{i + 1}/{len(script)}] {who}：「{item['text']}」")
        while True:
            input("  Enter で録音開始")
            samples = trim(record_until_enter())
            path = config.DEMO_AUDIO_DIR / item["file"]
            save_wav(path, samples)
            print(f"  {len(samples) / config.SAMPLE_RATE:.1f}秒。確認のため再生します。")
            play(*read_wav(path)[:2])
            if input("  よければ Enter、録り直すなら r：").strip().lower() != "r":
                print(f"  保存しました：{path.name}")
                break
    print("\n完了しました。python main.py で起動し、「録音で発表」を押してください。")


if __name__ == "__main__":
    main()
