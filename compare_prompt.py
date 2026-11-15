"""録音（demo_audio/）を、ヒントの渡し方を変えて文字起こしし、比べる。

実行: python compare_prompt.py
結果を見て、正しく認識できた方を config.py の WHISPER_PROMPT_MODE に設定する。
"""
from __future__ import annotations

import time

from demo_audio import load_steps, read_wav
from faq_search import FaqSearcher
from speech_to_text import Transcriber


def main() -> None:
    steps = load_steps()
    if not steps:
        print("demo_audio/ に録音がありません。先に python record_demo.py を実行してください。")
        return
    searcher = FaqSearcher.from_files()
    def product_name(text):
        product = searcher.detect_product(text)
        return product["name"] if product else None

    transcribers = {mode: Transcriber(searcher.vocabulary(), mode, product_name)
                    for mode in ("auto", "list", "none")}
    print("モデルを読み込んでいます…")
    model_owner = transcribers["auto"]
    model_owner.load()
    for transcriber in transcribers.values():
        transcriber.model = model_owner.model  # 同じモデルを使い回す

    for step in steps:
        _, _, samples = read_wav(step.path)
        print(f"\n{step.path.name}  台本：{step.text or '（なし）'}")
        for mode, transcriber in transcribers.items():
            start = time.time()
            text = transcriber.transcribe(samples)
            product = searcher.detect_product(text)
            print(f"  {mode:4}  {time.time() - start:4.1f}秒  {text}"
                  f"  → 商品：{product['name'] if product else '判定なし'}")


if __name__ == "__main__":
    main()
