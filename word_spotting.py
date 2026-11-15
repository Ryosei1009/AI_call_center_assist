"""ワード・スポッティング。第19,20回の考え方を文字列に応用している。

授業では、音声の特徴量に対して「両端点フリーDPマッチング」を行い、累積距離が
しきい値より小さければキーワードを検出したとみなす方法を学んだ。
ここでは同じDPを文字起こしの文字列に使う。文章の途中のどこからでも照合を
始められるので、「さぬきうろんセット」のような少しの誤りがあっても
「讃岐うどんセット」の別名「さぬきうどんセット」を見つけられる。
"""
from __future__ import annotations

import re
import unicodedata

import config


def normalize(text: str) -> str:
    """全角半角をそろえ、カタカナをひらがなにし、記号と空白を除く。"""
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(
        chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
        for c in text
    )
    return re.sub(r"[\s、。,.!?！？「」『』()（）・]", "", text)


def endpoint_free_distance(keyword: str, text: str) -> int:
    """keyword と text の一部分との最小編集距離（両端点フリーDP）。

    先頭行を 0 にすると text のどこからでも開始でき、最終行の最小値を取ると
    どこで終わってもよいことになる。これが「両端点フリー」の意味である。
    """
    if not keyword:
        return 0
    previous = [0] * (len(text) + 1)
    for i, k in enumerate(keyword, start=1):
        current = [i] + [0] * len(text)
        for j, t in enumerate(text, start=1):
            current[j] = min(
                previous[j - 1] + (k != t),  # 一致 / 置換
                previous[j] + 1,             # 脱落
                current[j - 1] + 1,          # 挿入
            )
        previous = current
    return min(previous)


def match_error(keyword: str, text: str,
                max_error_rate: float = config.SPOTTING_MAX_ERROR_RATE) -> float | None:
    """正規化済みの text に対する誤りの割合を返す。見つからなければ None。"""
    word = normalize(keyword)
    if word in text:
        return 0.0
    if len(word) < 4:  # 短い語は誤検出しやすいので完全一致だけを認める
        return None
    distance = endpoint_free_distance(word, text)
    return distance / len(word) if distance <= int(len(word) * max_error_rate) else None


def spot(keyword: str, text: str) -> bool:
    return match_error(keyword, text) is not None
