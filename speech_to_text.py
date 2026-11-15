"""文字起こし。faster-whisper（Whisper の高速版）を PC 内で実行する。

Whisper は授業で学んだ End-to-End 型の音声認識で、内部でメル尺度の特徴量を
作ってから深層学習モデルで文字列へ変換する。
initial_prompt に商品名を渡すと、それらの語が出やすくなる。これがレポートの
「商材辞書」に当たる。

ただし Whisper は無音や雑音を渡されると、ヒントの文をそのまま出力することがある。
そのため次の3段階で、話していないのに文字が出る誤りを防ぐ。
  1. Silero VAD（faster-whisper に同梱）で、人の声がない音声を除く
  2. Whisper が「音声ではなさそう」と判断した区間を捨てる
  3. ヒントをそのまま繰り返しただけの結果を捨てる
"""
from __future__ import annotations

import re

import config
from word_spotting import normalize

ECHO_ENDINGS = re.compile(r"(の通話です|こーるせんたー.*)$")
JAPANESE = r"[぀-ヿ一-鿿々ー、。？！]"


def tidy(text: str) -> str:
    """日本語の間に入った空白を除き、日本語の後の ? ! を全角にそろえる。"""
    text = re.sub(rf"(?<={JAPANESE})\s+(?={JAPANESE})", "", text)
    return re.sub(rf"(?<={JAPANESE})\?", "？", re.sub(rf"(?<={JAPANESE})!", "！", text))


def is_prompt_echo(text: str, vocabulary: list[str]) -> bool:
    """ヒントの繰り返しに見える文字列なら True を返す。"""
    remainder = normalize(text)
    found = 0
    for word in sorted(vocabulary, key=len, reverse=True):
        normalized_word = normalize(word)
        if normalized_word in remainder:
            remainder = remainder.replace(normalized_word, "")
            found += 1
    if found == 0:
        return False
    # 商品名だけが2つ以上並ぶ文や、「〜の通話です」は実際の発話らしくない
    return (found >= 2 and remainder == "") or bool(ECHO_ENDINGS.fullmatch(remainder))


def is_reliable(segment) -> bool:
    return (segment.no_speech_prob < config.WHISPER_NO_SPEECH_MAX
            and segment.avg_logprob > config.WHISPER_LOGPROB_MIN)


def build_prompt(vocabulary: list[str], mode: str) -> str | None:
    if mode == "none":
        return None
    return "、".join(vocabulary) + "。"


class Transcriber:
    """prompt_mode が "auto" のときは2回認識する。

    1回目：ヒントなし。商品名の表記は崩れても、ワード・スポッティングで商品は判定できる
           （例：「サヌキヨドンセット」→ 讃岐うどんセット）。
    2回目：判定した商品名だけをヒントにする。ほかの商品名へ引き寄せられずに、
           表記を正しく直せる。商品が分からなければ一覧をヒントにする。
    """

    def __init__(self, vocabulary: list[str], prompt_mode: str = config.WHISPER_PROMPT_MODE,
                 detect_product=None):
        self.vocabulary = vocabulary
        self.prompt_mode = prompt_mode
        self.prompt = build_prompt(vocabulary, prompt_mode)
        self.detect_product = detect_product  # 文字列 → 商品名（見つからなければ None）
        self.model = None

    def load(self) -> None:
        """初回はモデルをダウンロードするので時間がかかる。"""
        from faster_whisper import WhisperModel
        self.model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
        )

    def transcribe(self, samples) -> str:
        if self.model is None:
            self.load()
        if self.prompt_mode != "auto":
            return self._transcribe_once(samples, self.prompt)
        first = self._transcribe_once(samples, None)
        if not first:
            return ""
        product = self.detect_product(first) if self.detect_product else None
        prompt = f"{product}。" if product else build_prompt(self.vocabulary, "list")
        return self._transcribe_once(samples, prompt) or first

    def _transcribe_once(self, samples, prompt: str | None) -> str:
        segments, _ = self.model.transcribe(
            samples,
            language=config.WHISPER_LANGUAGE,
            beam_size=config.WHISPER_BEAM_SIZE,
            initial_prompt=prompt,
            condition_on_previous_text=False,  # 前の発話に引きずられる誤りを防ぐ
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = tidy("".join(s.text for s in segments if is_reliable(s)).strip())
        return "" if is_prompt_echo(text, self.vocabulary) else text
