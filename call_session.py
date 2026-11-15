"""1通話分の処理をまとめる。画面やマイクに依存しないのでテストしやすい。"""
from __future__ import annotations

import csv
import time
from dataclasses import dataclass

import config
from faq_search import FaqSearcher, SearchResult
from form_filler import CallForm, FormFiller


@dataclass
class TurnResult:
    role: str
    text: str
    search: SearchResult | None
    form: CallForm
    elapsed_sec: float | None  # 発話の終わりから結果が出るまでの時間


class CallSession:
    def __init__(self, searcher: FaqSearcher):
        self.searcher = searcher
        self.filler = FormFiller()
        self.current_product: dict | None = None
        self.turns: list[tuple[str, str]] = []

    def handle(self, role: str, text: str, ended_at: float | None = None) -> TurnResult:
        self.turns.append((role, text))
        search = None
        product_name = None

        if role == "customer":
            search = self.searcher.search(text, self.current_product)
            if search.product is not None:
                self.current_product = search.product
        else:
            product = self.searcher.detect_product(text)
            if product is not None:
                self.current_product = product
        if self.current_product is not None:
            product_name = self.current_product["name"]

        form = self.filler.update(role, text, product_name,
                                  bool(search and search.is_question))
        elapsed = time.time() - ended_at if ended_at is not None else None
        return TurnResult(role, text, search, form, elapsed)

    def adopt_answer(self) -> CallForm:
        return self.filler.mark_answered()

    def save(self, fields: dict) -> str:
        """確認済みの内容をCSVへ保存する（デモ用の登録処理）。"""
        config.OUTPUT_DIR.mkdir(exist_ok=True)
        path = config.OUTPUT_DIR / "registered_calls.csv"
        is_new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            if is_new:
                writer.writerow(["登録日時", "用件", "対象商品", "結果", "文字起こし"])
            transcript = " / ".join(
                f"{'客' if role == 'customer' else '担'}:{text}" for role, text in self.turns
            )
            writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), fields["用件"],
                             fields["対象商品"], fields["結果"], transcript])
        return str(path)
