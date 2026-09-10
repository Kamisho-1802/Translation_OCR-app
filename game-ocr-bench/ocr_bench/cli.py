"""CLI エントリポイント（仕様書 §9）。console_scripts の `ocr-bench` から呼ばれる。

M1 で機能するのは `run`（最小経路）と `info`。sweep/eval/report/gt は後続フェーズで実装。
"""

from __future__ import annotations

import argparse
import sys

from . import adapters  # noqa: F401  アダプタ登録の副作用
from .core import registry


def _cmd_info(args: argparse.Namespace) -> int:
    from .preprocess.pipeline import available_ops

    print("登録済みエンジン:", ", ".join(registry.available_ids()) or "(なし)")
    print("利用可能な前処理 op:", ", ".join(available_ops()))
    return 0


def _cmd_annotate(args: argparse.Namespace) -> int:
    import webbrowser
    from pathlib import Path

    tool = Path(__file__).resolve().parents[1] / "tools" / "annotate.html"
    if not tool.exists():
        print(f"アノテーションツールが見つかりません: {tool}")
        return 1
    url = tool.as_uri()
    print("領域アノテーションツールをブラウザで開きます。")
    print(f"  {url}")
    print("手順: 画像(PNG)を読み込み → ドラッグで矩形 → text/タグを入力 →")
    print(f"      『regions JSON を保存』で NNNN.json を {args.regions_dir}/ に置く → `ocr-bench ingest`")
    if not args.no_open:
        webbrowser.open(url)
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    from .core.db import connect
    from .runner.ingest import ingest_dataset

    conn = connect(args.db)
    ids = ingest_dataset(conn, args.images_dir, args.regions_dir)
    print(f"[ingest] {len(ids)} サンプルを登録（regions/GT があれば取り込み済み）")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from .core.db import connect
    from .runner.runner import run_batch, run_single

    engine_ids = registry.resolve_ids(args.engines)
    modes = [m.strip() for m in args.mode.split(",") if m.strip()]
    presets = [p.strip() for p in args.preprocess.split(",") if p.strip()]
    conn = connect(args.db)

    # --image 指定時は単発クイック実行（fullscreen のみ）。
    if args.image:
        for engine_id in engine_ids:
            for preset in presets:
                summary = run_single(conn, engine_id=engine_id, image_path=args.image,
                                     mode="fullscreen", preprocess=preset, device=args.device)
                tag = "cache" if summary["cached"] else "run  "
                if summary["error"]:
                    print(f"[{tag}] {engine_id}/fullscreen/{preset} ERROR: {summary['error']}")
                else:
                    preview = (summary["text"] or "").replace("\n", " ")[:80]
                    print(f"[{tag}] {engine_id}/fullscreen/{preset} -> \"{preview}\"")
        return 0

    # データセット一括実行（エンジン使い回し・ウォームアップ・FPS）。
    if args.ingest:
        from .runner.ingest import ingest_dataset
        ingest_dataset(conn, args.images_dir, args.regions_dir)

    out = run_batch(conn, engine_ids=engine_ids, modes=modes, presets=presets,
                    limit=args.limit, warmup_iters=args.warmup, device=args.device)
    c = out["counters"]
    print(f"[run] 推論={c['inferences']} キャッシュ命中={c['cache_hits']} "
          f"エラー={c['errors']} 保存={c['results']}")
    for key, st in out["stats"].items():
        if st["n"]:
            print(f"  {key:32} n={st['n']:3} p50={st['p50']:.0f}ms "
                  f"p95={st['p95']:.0f}ms FPS={st['fps']:.2f}")
        else:
            print(f"  {key:32} (全てキャッシュ命中 / 対象なし)")
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from .core.db import connect
    from .eval.evaluator import evaluate

    run_ids = None
    if args.run_ids:
        run_ids = [int(x) for x in args.run_ids.split(",") if x.strip()]
    profiles = [p.strip() for p in args.norm.split(",") if p.strip()]

    conn = connect(args.db)
    for profile in profiles:
        summary = evaluate(conn, run_ids=run_ids, norm_profile=profile)
        print(
            f"[eval] norm={summary['norm_profile']} "
            f"evaluated={summary['evaluated']} skipped(GT未確定/error)={summary['skipped']}"
        )
    return 0


def _cmd_gt(args: argparse.Namespace) -> int:
    from .core.db import connect
    from .gt import audit as A
    from .gt import bootstrap as B
    from .gt import review as R

    conn = connect(args.db)
    if args.action == "bootstrap":
        engine_ids = registry.resolve_ids(args.engines)
        summary = B.bootstrap_gt(conn, engine_ids, preprocess=args.preprocess)
        print(f"[gt bootstrap] engines={summary['engines']} 領域={summary['regions']} "
              f"一致={summary['agreed']} 要レビュー={summary['needs_review']}")
        if args.accept_agreed:
            n = R.accept_agreed(conn)
            print(f"  一致 {n} 件を確定（voted_text）。")
    elif args.action == "review":
        if args.accept_agreed:
            n = R.accept_agreed(conn)
            print(f"[gt review] 一致 {n} 件を確定。")
        pending = R.list_needs_review(conn)
        if not pending:
            print("[gt review] 要レビューの領域はありません。")
        else:
            print(f"[gt review] 要レビュー {len(pending)} 件を対話確定します。")
            n = R.interactive_review(conn)
            print(f"  {n} 件を確定。")
    elif args.action == "audit":
        rows = A.select_for_audit(conn, sample_rate=args.sample_rate)
        print(f"[gt audit] 監査対象 {len(rows)} 件（rate={args.sample_rate}, fantasy/pixel 優先）:")
        for r in rows:
            print(f"    sample {r['sample_id']} / {r['region_key']}: {r['gt_text']!r}")
    else:
        print(f"未知の gt アクション: {args.action}")
        return 2
    return 0


def _cmd_sweep(args: argparse.Namespace) -> int:
    from .core.db import connect
    from .runner.sweep import sweep_param

    conn = connect(args.db)
    values = [v.strip() for v in args.values.split(",") if v.strip()]
    rows = sweep_param(conn, engine_id=args.engine, param=args.param, values=values,
                       tag_filter=args.filter, mode=args.mode, preprocess=args.preprocess,
                       norm_profile=args.norm, warmup_iters=args.warmup)
    print(f"[sweep] {args.engine} {args.param} filter={args.filter or '(none)'}")
    for r in rows:
        mc = "—" if r["micro_cer"] is None else f"{r['micro_cer']:.3f}"
        fps = "—" if r["fps"] is None else f"{r['fps']:.2f}"
        print(f"    {args.param}={r['value']:<8} micro_CER={mc:6}  FPS={fps}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .core.db import connect
    from .report.export import write_report

    conn = connect(args.db)
    tags = [t.strip() for t in args.group_by.split(",") if t.strip()]
    out = write_report(conn, args.out, norm_profile=args.norm,
                       mode=(args.mode or None), tags=tags)
    print(f"[report] {out} を書き出しました（tags={tags}, norm={args.norm}）")
    return 0


def _cmd_todo(args: argparse.Namespace) -> int:
    print(f"サブコマンド '{args._name}' は後続フェーズで実装予定です。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ocr-bench", description="ゲーム画面 OCR 精度比較")
    parser.add_argument("--db", default=None, help="SQLite パス（既定: db/bench.sqlite）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="登録エンジン・前処理一覧を表示")
    p_info.set_defaults(func=_cmd_info)

    p_run = sub.add_parser("run", help="認識を実行し DB に保存")
    p_run.add_argument("--engines", default="all", help="all | tesseract,easyocr,...")
    p_run.add_argument("--mode", default="fullscreen", help="fullscreen,roi")
    p_run.add_argument("--preprocess", default="raw", help="raw,tuned,...")
    p_run.add_argument("--image", default=None, help="単発クイック実行する画像（PNG）")
    p_run.add_argument("--limit", type=int, default=None, help="データセット実行時の件数上限")
    p_run.add_argument("--warmup", type=int, default=3, help="ウォームアップ回数（統計から除外）")
    p_run.add_argument("--ingest", action="store_true", help="実行前に images/ を取り込む")
    p_run.add_argument("--images-dir", default="data/game/images")
    p_run.add_argument("--regions-dir", default="data/game/regions")
    p_run.add_argument("--device", default="cpu", help="cpu | cuda")
    p_run.set_defaults(func=_cmd_run)

    p_ing = sub.add_parser("ingest", help="images/ を samples に登録し regions/GT を取り込む")
    p_ing.add_argument("--images-dir", default="data/game/images")
    p_ing.add_argument("--regions-dir", default="data/game/regions")
    p_ing.set_defaults(func=_cmd_ingest)

    p_ann = sub.add_parser("annotate", help="領域(box)描画ツールをブラウザで開く")
    p_ann.add_argument("--regions-dir", default="data/game/regions")
    p_ann.add_argument("--no-open", action="store_true", help="URL 表示のみ（自動で開かない）")
    p_ann.set_defaults(func=_cmd_annotate)

    p_eval = sub.add_parser("eval", help="評価指標を計算して metrics に保存（推論しない）")
    p_eval.add_argument("--run-ids", dest="run_ids", default=None, help="1,2,3（省略で全 run）")
    p_eval.add_argument("--norm", default="strict", help="strict,loose")
    p_eval.set_defaults(func=_cmd_eval)

    p_gt = sub.add_parser("gt", help="GT ブートストラップ/レビュー/監査")
    p_gt.add_argument("action", choices=["bootstrap", "review", "audit"])
    p_gt.add_argument("--engines", default="all", help="bootstrap: 使用エンジン")
    p_gt.add_argument("--preprocess", default="raw", help="bootstrap: 前処理")
    p_gt.add_argument("--accept-agreed", action="store_true",
                      help="多数決一致の領域を voted_text で確定")
    p_gt.add_argument("--sample-rate", type=float, default=0.2, help="audit: 監査率")
    p_gt.set_defaults(func=_cmd_gt)

    p_sw = sub.add_parser("sweep", help="パラメータスイープ（条件タグ別に最適値探索）")
    p_sw.add_argument("--engine", required=True)
    p_sw.add_argument("--param", required=True)
    p_sw.add_argument("--values", required=True, help="カンマ区切り（例: 1.6,2.0,2.5）")
    p_sw.add_argument("--filter", default=None, help="条件タグ（例: font_style=fantasy）")
    p_sw.add_argument("--mode", default="fullscreen")
    p_sw.add_argument("--preprocess", default="raw")
    p_sw.add_argument("--norm", default="strict")
    p_sw.add_argument("--warmup", type=int, default=3)
    p_sw.set_defaults(func=_cmd_sweep)

    p_rep = sub.add_parser("report", help="HTML レポートを書き出す（推論しない）")
    p_rep.add_argument("--group-by", dest="group_by", default="font_style,text_type,text_color")
    p_rep.add_argument("--mode", default="", help="fullscreen/roi（空で全モード）")
    p_rep.add_argument("--norm", default="strict")
    p_rep.add_argument("--out", default="out/report.html")
    p_rep.set_defaults(func=_cmd_report)

    return parser


def _force_utf8_stdio() -> None:
    """stdout/stderr を UTF-8 に再構成（Windows の cp932 コンソールでの

    UnicodeEncodeError クラッシュを防ぐ。EasyOCR の進捗バー(█)や日本語出力対策）。
    """
    for stream in ("stdout", "stderr"):
        s = getattr(sys, stream, None)
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
