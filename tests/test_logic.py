"""マイクや Whisper なしで動く部分のテスト。実行: python -m unittest discover tests"""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from call_session import CallSession
from faq_search import FaqSearcher
from word_spotting import endpoint_free_distance, normalize, spot


class WordSpottingTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("カタカナ、ＡＢＣ！"), "かたかなabc")

    def test_distance_ignores_surrounding_text(self):
        self.assertEqual(endpoint_free_distance("うどん", "さぬきうどんです"), 0)

    def test_spot_allows_small_error(self):
        self.assertTrue(spot("さぬきうどんセット", normalize("さぬきうろんセットについて")))

    def test_short_word_must_match_exactly(self):
        self.assertFalse(spot("送料", normalize("相量について")))


class SearchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.searcher = FaqSearcher.from_files()

    def test_each_faq_is_found_from_its_own_question(self):
        for faq in self.searcher.faqs:
            product = self.searcher.products_by_id[faq["product_id"]]
            result = self.searcher.search(product["name"] + "の" + faq["question"])
            self.assertTrue(result.confident, faq["id"])
            self.assertEqual(result.candidates[0].faq["id"], faq["id"], faq["question"])

    def test_same_question_changes_with_product(self):
        first = self.searcher.search("瀬戸内海鮮セットの賞味期限はいつまでですか")
        second = self.searcher.search("讃岐うどんセットの賞味期限はいつまでですか")
        self.assertIn("90日", first.candidates[0].faq["answer"])
        self.assertIn("180日", second.candidates[0].faq["answer"])

    def test_closest_product_is_selected(self):
        product = self.searcher.detect_product("みらいニューインプランは何歳まで入れますか")
        self.assertEqual(product["id"], "mirai")

    def test_misrecognized_product_and_short_question(self):
        result = self.searcher.search("さぬきうろんセットの賞味期限は")
        self.assertTrue(result.confident)
        self.assertIn("180日", result.candidates[0].faq["answer"])

    def test_paraphrased_questions(self):
        for text in ("うどんセットって何人前入ってるんですか",
                     "すき焼きセットのしは付けられますか",
                     "やすらぎがんプランはいつから保障が始まりますか"):
            self.assertTrue(self.searcher.search(text).confident, text)

    def test_product_switches_without_set_word(self):
        session = CallSession(self.searcher)
        session.handle("customer", "瀬戸内海鮮セットのことで電話しました")
        turn = session.handle("customer", "讃岐うどんの賞味期限はいつまでですか")
        self.assertEqual(turn.form.product, "讃岐うどんセット")
        self.assertIn("180日", turn.search.candidates[0].faq["answer"])

    def test_not_a_question(self):
        self.assertFalse(self.searcher.search("こんにちは、よろしくお願いします").is_question)

    def test_unknown_question_gives_no_candidates(self):
        result = self.searcher.search("瀬戸内海鮮セットの工場は見学できますか")
        self.assertTrue(result.is_question)
        self.assertFalse(result.confident)

    def test_small_talk_is_not_a_question(self):
        self.assertFalse(self.searcher.search("いつもありがとうございます").is_question)


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.session = CallSession(FaqSearcher.from_files())

    def test_product_is_kept_across_turns(self):
        self.session.handle("customer", "先日テレビで見た瀬戸内海鮮セットのことで")
        turn = self.session.handle("customer", "賞味期限はいつまでですか")
        self.assertTrue(turn.search.confident)
        self.assertIn("90日", turn.search.candidates[0].faq["answer"])
        self.assertEqual(turn.form.purpose, "商品の問い合わせ")
        self.assertEqual(turn.form.product, "瀬戸内海鮮セット")
        self.assertEqual(self.session.adopt_answer().result, "回答済み")

    def test_order_then_cancel(self):
        self.session.handle("customer", "和牛すき焼きセットを注文したいです")
        turn = self.session.handle("operator", "ご注文を承りました")
        self.assertEqual(turn.form.purpose, "注文")
        self.assertEqual(turn.form.result, "注文を受付")
        turn = self.session.handle("customer", "やっぱりやめます")
        self.assertEqual(turn.form.result, "お客様の希望で取りやめ")

    def test_elapsed_time(self):
        turn = self.session.handle("customer", "こんにちは", ended_at=time.time() - 1.0)
        self.assertGreaterEqual(turn.elapsed_sec, 1.0)


if __name__ == "__main__":
    unittest.main()
