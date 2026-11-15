"""機能②：入力フォームへの自動入力。

発話からルールで「用件」「対象商品」「結果」を取り出す。後から話された内容で
上書きするので、「やっぱりやめます」のように話が変わっても追従できる。
自動で登録はせず、最後にオペレーターが確認して直す。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CUSTOMER_RULES = [
    ("解約の相談", r"解約|やめたい|辞めたい"),
    ("登録内容の変更", r"(住所|電話番号|お届け先|支払い|プラン).*(変更|変え)|変更したい"),
    ("注文", r"注文|買いたい|購入|欲しい|ほしい|申し込み|申込"),
    ("配送の確認", r"届かない|届いていない|まだ来|いつ届"),
    ("資料請求", r"資料"),
]
CANCEL_PATTERN = re.compile(r"やっぱり.*(やめ|いい|結構)|キャンセル|取り消")
OPERATOR_RULES = [
    ("注文を受付", r"ご注文.*(承り|受け付け|お受け)"),
    ("折り返し連絡", r"折り返し"),
    ("資料を送付", r"資料.*(お送り|送付)"),
    ("手続きを受付", r"(変更|解約).*(承り|受け付け)"),
]


@dataclass
class CallForm:
    purpose: str = ""
    product: str = ""
    result: str = ""

    def as_dict(self) -> dict:
        return {"用件": self.purpose, "対象商品": self.product, "結果": self.result}


def _first_match(rules: list[tuple[str, str]], text: str) -> str | None:
    for label, pattern in rules:
        if re.search(pattern, text):
            return label
    return None


class FormFiller:
    def __init__(self):
        self.form = CallForm()

    def update(self, role: str, text: str, product_name: str | None,
               is_question: bool) -> CallForm:
        if product_name:
            self.form.product = product_name

        if role == "customer":
            if CANCEL_PATTERN.search(text) and self.form.purpose:
                self.form.result = "お客様の希望で取りやめ"
                return self.form
            purpose = _first_match(CUSTOMER_RULES, text)
            if purpose:
                self.form.purpose = purpose
                self.form.result = "対応中"
            elif is_question and not self.form.purpose:
                self.form.purpose = "商品の問い合わせ"
                self.form.result = "対応中"
        else:
            result = _first_match(OPERATOR_RULES, text)
            if result:
                self.form.result = result
        return self.form

    def mark_answered(self) -> CallForm:
        """オペレーターが回答候補を使ったときに呼ぶ。"""
        if self.form.result in ("", "対応中"):
            self.form.result = "回答済み"
        return self.form
