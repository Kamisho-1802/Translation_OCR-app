"""HTML レポート出力（仕様書 §10 / §11 M7）。推論は行わない。

Summary（エンジン別）と Breakdown（条件タグ × エンジンの micro CER）を、外部依存の
無い自己完結 HTML に書き出す。使い分け表（§5.3）の根拠となる表を中心に据える。
"""

from __future__ import annotations

import html
from pathlib import Path

from .aggregate import breakdown_by_tag, summary_by_engine

_SUMMARY_COLS = [
    ("engine_id", "engine", "{}"),
    ("n", "n", "{}"),
    ("micro_cer", "micro CER", "{:.3f}"),
    ("macro_cer", "macro CER", "{:.3f}"),
    ("wer", "WER", "{:.3f}"),
    ("exact_match_rate", "完全一致率", "{:.3f}"),
    ("ins_rate", "挿入率", "{:.3f}"),
    ("spurious_total", "誤検出量", "{}"),
    ("det_recall", "検出Recall", "{:.3f}"),
    ("det_precision", "検出Prec", "{:.3f}"),
    ("proper_noun_acc", "固有名詞", "{:.3f}"),
    ("lat_p95", "p95(ms)", "{:.0f}"),
    ("fps", "FPS", "{:.2f}"),
]


def _fmt(val, spec):
    if val is None:
        return "—"
    try:
        return spec.format(val)
    except (ValueError, TypeError):
        return html.escape(str(val))


def _cer_color(v):
    """micro CER を緑(良)→赤(悪) に着色するための背景色。"""
    if v is None:
        return "transparent"
    v = max(0.0, min(1.0, v))
    r = int(200 * v + 40)
    g = int(200 * (1 - v) + 40)
    return f"rgb({r},{g},60)"


def _summary_table(conn, norm_profile, mode):
    rows = summary_by_engine(conn, norm_profile, mode)
    head = "".join(f"<th>{html.escape(lbl)}</th>" for _, lbl, _ in _SUMMARY_COLS)
    body = []
    for r in rows:
        tds = "".join(f"<td>{_fmt(r.get(k), spec)}</td>" for k, _, spec in _SUMMARY_COLS)
        body.append(f"<tr>{tds}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def _breakdown_table(conn, tag, norm_profile, mode):
    bd = breakdown_by_tag(conn, tag, norm_profile, mode)
    if not bd["rows"]:
        return f"<p>タグ <code>{html.escape(tag)}</code>: データなし</p>"
    head = "<th>{}</th>".format(html.escape(tag)) + "".join(
        f"<th>{html.escape(e)}</th>" for e in bd["engines"])
    body = []
    for row in bd["rows"]:
        cells = [f"<td>{html.escape(row['value'])}</td>"]
        for e in bd["engines"]:
            v = row["cells"].get(e)
            cells.append(
                f"<td style='background:{_cer_color(v)};color:#111'>{_fmt(v, '{:.3f}')}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def render_html(
    conn, norm_profile: str = "strict", mode: str | None = None,
    tags: list[str] | None = None, title: str = "game-ocr-bench レポート",
) -> str:
    tags = tags or ["font_style", "text_type", "text_color"]
    parts = [
        f"<h1>{html.escape(title)}</h1>",
        f"<p>norm_profile=<b>{html.escape(norm_profile)}</b>"
        f" / mode=<b>{html.escape(mode or 'all')}</b></p>",
        "<h2>Summary（エンジン別・micro CER 昇順）</h2>",
        _summary_table(conn, norm_profile, mode),
        "<h2>Breakdown（条件タグ × エンジンの micro CER）</h2>",
    ]
    for tag in tags:
        parts.append(f"<h3>{html.escape(tag)}</h3>")
        parts.append(_breakdown_table(conn, tag, norm_profile, mode))

    style = (
        "body{font-family:system-ui,'Segoe UI',sans-serif;margin:24px;"
        "background:#1e1e1e;color:#eee}"
        "table{border-collapse:collapse;margin:8px 0 20px}"
        "th,td{border:1px solid #555;padding:4px 8px;text-align:right;font-size:13px}"
        "th{background:#333}h1,h2,h3{color:#fff}code{background:#333;padding:1px 4px}"
    )
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{html.escape(title)}</title><style>{style}</style></head>"
            f"<body>{''.join(parts)}</body></html>")


def write_report(conn, out_path: str | Path, **kwargs) -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_html(conn, **kwargs), encoding="utf-8")
    return out
