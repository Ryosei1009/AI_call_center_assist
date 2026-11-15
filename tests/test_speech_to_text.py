"""文字起こしの誤出力を除く処理のテスト。Whisper 本体は偽物に置き換える。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as Segment

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speech_to_text import Transcriber, is_prompt_echo, tidy

WORDS = ["瀬戸内海鮮セット", "讃岐うどんセット", "和牛すき焼きセット"]


class FakeModel:
    def __init__(self, segments, by_prompt=None):
        self.segments = segments
        self.by_prompt = by_prompt or {}
        self.options = None
        self.prompts = []

    def transcribe(self, samples, **options):
        self.options = options
        self.prompts.append(options["initial_prompt"])
        return iter(self.by_prompt.get(options["initial_prompt"], self.segments)), None


def transcribe(*segments):
    transcriber = Transcriber(WORDS, "list")
    transcriber.model = FakeModel(list(segments))
    return transcriber.transcribe(None), transcriber.model.options


def segment(text, no_speech=0.1, logprob=-0.3):
    return Segment(text=text, no_speech_prob=no_speech, avg_logprob=logprob)


class EchoTest(unittest.TestCase):
    def test_reported_echo(self):
        self.assertTrue(is_prompt_echo("瀬戸内海鮮セットの通話です。", WORDS))

    def test_product_list(self):
        self.assertTrue(is_prompt_echo("瀬戸内海鮮セット、讃岐うどんセット。", WORDS))

    def test_real_utterances_are_kept(self):
        for text in ("瀬戸内海鮮セットです", "瀬戸内海鮮セットの賞味期限はいつまでですか",
                     "瀬戸内海鮮セットのことで電話しました", "こんにちは"):
            self.assertFalse(is_prompt_echo(text, WORDS), text)


class TidyTest(unittest.TestCase):
    def test_space_between_japanese_is_removed(self):
        self.assertEqual(tidy("讃岐うどんセットの 消耗期限はいつまでですか?"),
                         "讃岐うどんセットの消耗期限はいつまでですか？")

    def test_space_in_english_is_kept(self):
        self.assertEqual(tidy("Whisper small です"), "Whisper small です")


class TranscribeTest(unittest.TestCase):
    def test_echo_becomes_empty(self):
        self.assertEqual(transcribe(segment("瀬戸内海鮮セットの通話です。"))[0], "")

    def test_no_speech_segment_is_dropped(self):
        text, _ = transcribe(segment("ありがとうございました", no_speech=0.9), segment("賞味期限は"))
        self.assertEqual(text, "賞味期限は")

    def test_prompt_can_be_disabled(self):
        transcriber = Transcriber(WORDS, "none")
        transcriber.model = FakeModel([segment("はい")])
        transcriber.transcribe(None)
        self.assertIsNone(transcriber.model.options["initial_prompt"])

    def test_auto_uses_only_detected_product_as_hint(self):
        transcriber = Transcriber(WORDS, "auto",
                                  lambda text: "讃岐うどんセット" if "ヨドン" in text else None)
        transcriber.model = FakeModel(
            [segment("サヌキヨドンセットの賞味期限は")],
            {"讃岐うどんセット。": [segment("讃岐うどんセットの賞味期限は")]})
        self.assertEqual(transcriber.transcribe(None), "讃岐うどんセットの賞味期限は")
        self.assertEqual(transcriber.model.prompts, [None, "讃岐うどんセット。"])

    def test_auto_falls_back_to_list(self):
        transcriber = Transcriber(WORDS, "auto", lambda text: None)
        transcriber.model = FakeModel([segment("やっぱりやめます")])
        transcriber.transcribe(None)
        self.assertEqual(transcriber.model.prompts[1], "、".join(WORDS) + "。")

    def test_silero_vad_is_enabled(self):
        self.assertTrue(transcribe(segment("はい"))[1]["vad_filter"])


if __name__ == "__main__":
    unittest.main()
