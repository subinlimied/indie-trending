#!/usr/bin/env python3
"""스냅샷 → 리포트 (reports/<platform>/<date>.md + .html).

사용:
  python3 report.py                  # 오늘(KST)
  python3 report.py --date 2026-10-20 --only steam
"""
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market import analyze_itch, analyze_steam, render  # noqa: E402

KST = timezone(timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--only", choices=["steam", "itch"])
    args = ap.parse_args()
    cfg = json.loads((ROOT / "config.json").read_text())
    data_dir, reports_dir = ROOT / "data", ROOT / "reports"

    for name, mod in (("steam", analyze_steam), ("itch", analyze_itch)):
        if args.only and args.only != name:
            continue
        if not (data_dir / name / f"{args.date}.json").exists():
            print(f"[{name}] {args.date} 스냅샷 없음, 건너뜀")
            continue
        rep = mod.analyze(cfg[name], args.date, data_dir, reports_dir)
        out = reports_dir / name
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{args.date}.md").write_text(render.to_md(rep))
        (out / f"{args.date}.html").write_text(render.to_html(rep))
        (out / f"{args.date}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        print(f"[{name}] reports/{name}/{args.date}.md · .html 생성 ({rep['round']}회차)")


if __name__ == "__main__":
    main()
