"""精度指標（仕様書 §4）。

CER/WER・編集内訳（挿入/削除/置換）・完全一致・固有名詞一致率。
マイクロ平均を主指標とする（§4.1）ため、集計に必要な素の値（編集距離と GT 長）も返す。

編集距離は Levenshtein（python-Levenshtein / Levenshtein パッケージ）を用いる。
editops で挿入/削除/置換の内訳を取り、CER の分解を可能にする。
"""

from __future__ import annotations

from dataclasses import dataclass

import Levenshtein

from .normalize import normalize


@dataclass
class EditCounts:
    ins: int  # 挿入（pred に余分）
    dele: int  # 削除（pred に欠落）
    sub: int  # 置換
    ref_len: int  # 参照（GT）の長さ

    @property
    def distance(self) -> int:
        return self.ins + self.dele + self.sub


def _edit_counts(ref: str, hyp: str) -> EditCounts:
    """ref→hyp の編集操作を数える。

    Levenshtein.editops は ('insert'|'delete'|'replace', i, j) を返す。
    ここで insert は「ref に無く hyp にある」= 余分な出力（挿入誤り）。
    delete は「ref にあり hyp に無い」= 欠落誤り。
    """
    ins = dele = sub = 0
    for op, _i, _j in Levenshtein.editops(ref, hyp):
        if op == "insert":
            ins += 1
        elif op == "delete":
            dele += 1
        else:  # replace
            sub += 1
    return EditCounts(ins=ins, dele=dele, sub=sub, ref_len=len(ref))


def cer_counts(gt: str, pred: str, profile: str | dict = "strict") -> EditCounts:
    """文字レベルの編集内訳（正規化後）。"""
    g = normalize(gt, profile)
    p = normalize(pred, profile)
    return _edit_counts(g, p)


def wer_counts(gt: str, pred: str, profile: str | dict = "strict") -> EditCounts:
    """単語レベルの編集内訳（空白区切り・正規化後）。

    Levenshtein は文字列前提なので、単語をユニーク文字へ写像してから距離を取る。
    """
    g_words = normalize(gt, profile).split()
    p_words = normalize(pred, profile).split()
    vocab: dict[str, str] = {}

    def encode(words: list[str]) -> str:
        out = []
        for w in words:
            if w not in vocab:
                vocab[w] = chr(0xE000 + len(vocab))  # private use area
            out.append(vocab[w])
        return "".join(out)

    return _edit_counts(encode(g_words), encode(p_words))


def cer(gt: str, pred: str, profile: str | dict = "strict") -> float:
    """CER = 編集距離 / GT 文字数（GT 長 0 のときは pred 長 0 で 0.0、非0で 1.0）。"""
    c = cer_counts(gt, pred, profile)
    if c.ref_len == 0:
        return 0.0 if c.distance == 0 else 1.0
    return c.distance / c.ref_len


def wer(gt: str, pred: str, profile: str | dict = "strict") -> float:
    c = wer_counts(gt, pred, profile)
    if c.ref_len == 0:
        return 0.0 if c.distance == 0 else 1.0
    return c.distance / c.ref_len


def exact_match(gt: str, pred: str, profile: str | dict = "strict") -> int:
    """正規化後に完全一致すれば 1（§4.2 完全一致率の素）。"""
    return int(normalize(gt, profile) == normalize(pred, profile))


def proper_noun_accuracy(
    pred: str, proper_nouns: list[str], profile: str | dict = "strict"
) -> float | None:
    """proper_nouns の完全一致率（正規化後に pred へ部分文字列として現れる割合）。

    固有名詞が無い領域では None（集計から除外する）。辞書バイアス検出用（§4.2）。
    """
    if not proper_nouns:
        return None
    p = normalize(pred, profile)
    hit = sum(1 for pn in proper_nouns if normalize(pn, profile) in p)
    return hit / len(proper_nouns)


def micro_cer(pairs: list[tuple[str, str]], profile: str | dict = "strict") -> float:
    """マイクロ平均 CER = Σ編集距離 / ΣGT文字数（§4.1 主指標）。"""
    total_dist = 0
    total_ref = 0
    for gt, pred in pairs:
        c = cer_counts(gt, pred, profile)
        total_dist += c.distance
        total_ref += c.ref_len
    if total_ref == 0:
        return 0.0
    return total_dist / total_ref


def macro_cer(pairs: list[tuple[str, str]], profile: str | dict = "strict") -> float:
    """マクロ平均 CER = サンプル毎 CER の単純平均（参考値・§4.1）。"""
    if not pairs:
        return 0.0
    return sum(cer(gt, pred, profile) for gt, pred in pairs) / len(pairs)
