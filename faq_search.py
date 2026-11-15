"""機能①：質問の検出、商材の判定、マニュアル検索。

スコアの考え方:
  ・キーワードが見つかるほど高くする（ワード・スポッティング）
  ・文字の2-gramで、質問文とFAQの質問の似ている度合いも足す
  ・話題の商材が分かっていれば、その商材のFAQだけを候補にする
最高スコアが低いときは、誤った案内を防ぐため「候補なし」にする。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import config
from word_spotting import match_error, normalize, spot

QUESTION_PATTERN = re.compile(
    r"(ですか|ますか|でしょうか|ませんか|のか|かな|教えて|知りたい|聞きたい|"
    r"いくら|いつ|どれくらい|どのくらい|何日|何歳|何か月|どこ|どう|どなた|"
    r"大丈夫|できる|入って|は$|って$|\?|？)"
)

CLEAR_QUESTION_PATTERN = re.compile(r"(ですか|ますか|でしょうか|ませんか|\?|？)[。.\s]*$")


@dataclass
class Candidate:
    faq: dict
    product: dict
    score: float


@dataclass
class SearchResult:
    is_question: bool
    product: dict | None
    candidates: list[Candidate] = field(default_factory=list)
    confident: bool = False


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


def _dice(a: str, b: str) -> float:
    grams_a, grams_b = _bigrams(a), _bigrams(b)
    return 2 * len(grams_a & grams_b) / (len(grams_a) + len(grams_b))


class FaqSearcher:
    def __init__(self, products: list[dict], faqs: list[dict]):
        self.products = products
        self.faqs = faqs
        self.products_by_id = {p["id"]: p for p in products}

    @classmethod
    def from_files(cls) -> "FaqSearcher":
        with open(config.DATA_DIR / "products.json", encoding="utf-8") as f:
            products = json.load(f)
        with open(config.DATA_DIR / "faq.json", encoding="utf-8") as f:
            faqs = json.load(f)
        return cls(products, faqs)

    def vocabulary(self) -> list[str]:
        """商材辞書。文字起こしのヒントとして Whisper に渡す語の一覧。"""
        return [p["name"] for p in self.products]

    def detect_product(self, text: str) -> dict | None:
        normalized = normalize(text)
        best, best_error = None, None
        for product in self.products:
            for word in [product["name"], *product["aliases"]]:
                error = match_error(word, normalized)
                if error is not None and (best_error is None or error < best_error):
                    best, best_error = product, error  # 最も誤りの少ない商材を選ぶ
        return best

    def _score(self, faq: dict, normalized: str) -> tuple[float, int]:
        hits = sum(spot(word, normalized) for word in faq["keywords"])
        if hits == 0:
            return 0.0, 0
        keyword_score = min(0.45 + 0.15 * (hits - 1), 0.7)
        return keyword_score + 0.3 * _dice(normalized, normalize(faq["question"])), hits

    def search(self, text: str, current_product: dict | None = None) -> SearchResult:
        normalized = normalize(text)
        product = self.detect_product(text) or current_product

        scored = []
        for faq in self.faqs:
            if product is not None and faq["product_id"] != product["id"]:
                continue
            score, hits = self._score(faq, normalized)
            if hits == 0:
                continue
            # 商材が分かっていれば確信度を上げ、不明なら下げる
            score = min(score + 0.1, 1.0) if product is not None else score * 0.8
            scored.append(Candidate(faq, self.products_by_id[faq["product_id"]], round(score, 2)))
        scored.sort(key=lambda c: c.score, reverse=True)

        # 文末が質問の形なら、FAQになくても質問として扱い「候補なし」を示す
        is_question = bool(CLEAR_QUESTION_PATTERN.search(text)) or (
            bool(QUESTION_PATTERN.search(text)) and bool(scored))
        candidates = scored[: config.TOP_K]
        confident = is_question and bool(candidates) and (
            candidates[0].score >= config.CONFIDENCE_THRESHOLD)
        return SearchResult(is_question, product, candidates if is_question else [], confident)
