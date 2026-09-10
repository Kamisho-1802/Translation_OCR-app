"""Streamlit UI（仕様書 §10・最小構成 5 タブ）。

    streamlit run ocr_bench/ui/app.py

タブ: Run / Summary / Breakdown / Sample / Sweep。
差分ビュー（Sample タブ）は「なぜ負けたか」を見るための中核なので色分けを丁寧に行う。
（挿入=緑 / 欠落=赤 / 置換=黄）。装飾は最小限。
"""

from __future__ import annotations

import difflib
import json

import numpy as np

from ocr_bench.core.db import connect
from ocr_bench.eval.normalize import normalize


def _diff_html(gt: str, pred: str) -> str:
    """GT→pred の文字差分を色分け HTML に。挿入=緑/欠落=赤/置換=黄。"""
    sm = difflib.SequenceMatcher(a=gt, b=pred, autojunk=False)
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            out.append(_esc(pred[j1:j2]))
        elif op == "insert":
            out.append(f"<span style='background:#1b5e20;color:#fff'>{_esc(pred[j1:j2])}</span>")
        elif op == "delete":
            out.append(f"<span style='background:#b71c1c;color:#fff'>{_esc(gt[i1:i2])}</span>")
        else:  # replace
            out.append(
                f"<span style='background:#b71c1c;color:#fff'>{_esc(gt[i1:i2])}</span>"
                f"<span style='background:#f9a825;color:#111'>{_esc(pred[j1:j2])}</span>")
    return "".join(out)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace(" ", "&nbsp;"))


def _overlay_boxes(image_bgr, gt_boxes, pred_boxes):
    import cv2

    img = image_bgr.copy()
    for (x, y, w, h) in gt_boxes:
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)      # GT=緑
    for (x, y, w, h) in pred_boxes:
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 165, 255), 1)    # 予測=橙
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def main() -> None:
    import pandas as pd
    import streamlit as st

    from ocr_bench.core import registry
    from ocr_bench.core.images import load_bgr
    from ocr_bench.report.aggregate import breakdown_by_tag, summary_by_engine
    import ocr_bench.adapters  # noqa: F401 登録

    st.set_page_config(page_title="game-ocr-bench", layout="wide")
    st.title("game-ocr-bench — OCR 精度比較")

    db = st.sidebar.text_input("DB パス", "db/bench.sqlite")
    norm = st.sidebar.selectbox("正規化", ["strict", "loose"], index=0)
    conn = connect(db)

    tab_run, tab_sum, tab_bd, tab_sample, tab_sweep = st.tabs(
        ["Run", "Summary", "Breakdown", "Sample", "Sweep"])

    # ---- Run ----
    with tab_run:
        engines = st.multiselect("エンジン", registry.available_ids(),
                                 default=registry.available_ids())
        modes = st.multiselect("モード", ["fullscreen", "roi"], default=["fullscreen"])
        presets = st.text_input("前処理（カンマ区切り）", "raw,tuned")
        limit = st.number_input("件数上限（0=全件）", 0, 10000, 0)
        if st.button("実行") and engines:
            from ocr_bench.runner.runner import run_batch
            with st.spinner("実行中..."):
                out = run_batch(conn, engine_ids=engines, modes=modes,
                                presets=[p.strip() for p in presets.split(",") if p.strip()],
                                limit=(limit or None))
            st.json(out["counters"])
            st.dataframe(pd.DataFrame(out["stats"]).T)

    # ---- Summary ----
    with tab_sum:
        mode = st.selectbox("モード", ["(all)", "fullscreen", "roi"], key="sum_mode")
        rows = summary_by_engine(conn, norm, None if mode == "(all)" else mode)
        if rows:
            st.dataframe(pd.DataFrame(rows).set_index("engine_id"))
        else:
            st.info("metrics がありません。Run と `eval` を先に実行してください。")

    # ---- Breakdown ----
    with tab_bd:
        tag = st.selectbox("条件タグ", ["font_style", "text_type", "text_color",
                                     "outline", "overlay", "contrast", "resolution", "density"])
        mode = st.selectbox("モード", ["(all)", "fullscreen", "roi"], key="bd_mode")
        bd = breakdown_by_tag(conn, tag, norm, None if mode == "(all)" else mode)
        if bd["rows"]:
            df = pd.DataFrame(
                [{"value": r["value"], **{e: r["cells"].get(e) for e in bd["engines"]}}
                 for r in bd["rows"]]).set_index("value")
            st.caption("セル = micro CER（低いほど良い）。使い分け表の根拠。")
            st.dataframe(df.style.background_gradient(cmap="RdYlGn_r", axis=None))
        else:
            st.info("該当タグのデータがありません。")

    # ---- Sample ----
    with tab_sample:
        samples = conn.execute("SELECT id, file_path FROM samples ORDER BY id").fetchall()
        if not samples:
            st.info("サンプルがありません。`ingest` を実行してください。")
        else:
            sid = st.selectbox("サンプル", [s["id"] for s in samples])
            srow = conn.execute("SELECT file_path, gt_text FROM samples WHERE id=?",
                                (sid,)).fetchone()
            regions = conn.execute(
                "SELECT box_json, gt_text FROM regions WHERE sample_id=? ORDER BY order_index",
                (sid,)).fetchall()
            col1, col2 = st.columns([1, 1])
            with col1:
                try:
                    img = load_bgr(srow["file_path"])
                    gt_boxes = [tuple(json.loads(r["box_json"])) for r in regions]
                    results = conn.execute(
                        """SELECT run.engine_id, res.blocks_json FROM results res
                           JOIN runs run ON run.id=res.run_id
                           WHERE res.sample_id=? AND res.region_id IS NULL""", (sid,)).fetchall()
                    pred_boxes = []
                    for rr in results:
                        for b in json.loads(rr["blocks_json"] or "[]"):
                            if b.get("box"):
                                pred_boxes.append(tuple(b["box"]))
                    st.image(_overlay_boxes(img, gt_boxes, pred_boxes),
                             caption="緑=GT領域 / 橙=検出枠", use_container_width=True)
                except Exception as exc:  # noqa: BLE001
                    st.warning(f"画像表示に失敗: {exc}")
            with col2:
                gt = srow["gt_text"] or ""
                st.markdown("**GT**")
                st.code(gt or "(未確定)")
                res = conn.execute(
                    """SELECT run.engine_id, run.mode, run.preprocess_json, res.pred_text
                       FROM results res JOIN runs run ON run.id=res.run_id
                       WHERE res.sample_id=? AND res.region_id IS NULL
                       ORDER BY run.engine_id""", (sid,)).fetchall()
                for r in res:
                    st.markdown(f"**{r['engine_id']}** ({r['mode']})")
                    diff = _diff_html(normalize(gt, norm), normalize(r["pred_text"] or "", norm))
                    st.markdown(f"<div style='font-family:monospace'>{diff}</div>",
                                unsafe_allow_html=True)

    # ---- Sweep ----
    with tab_sweep:
        engine = st.selectbox("エンジン", registry.available_ids(), key="sw_eng")
        param = st.text_input("パラメータ", "mag_ratio")
        values = st.text_input("値（カンマ区切り）", "1.0,2.0")
        tag_filter = st.text_input("条件フィルタ（例 font_style=hud）", "")
        if st.button("スイープ実行"):
            from ocr_bench.runner.sweep import sweep_param
            with st.spinner("スイープ中..."):
                rows = sweep_param(conn, engine_id=engine, param=param,
                                   values=[v.strip() for v in values.split(",") if v.strip()],
                                   tag_filter=tag_filter or None, norm_profile=norm)
            df = pd.DataFrame(rows)
            st.dataframe(df)
            if not df.empty and df["micro_cer"].notna().any():
                st.line_chart(df.set_index("value")["micro_cer"])


if __name__ == "__main__":
    main()
