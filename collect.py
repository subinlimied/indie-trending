#!/usr/bin/env python3
"""일간 스냅샷 수집기.

사용:
  python3 collect.py                 # 오늘 날짜(KST), Steam + itch
  python3 collect.py --only steam    # 한 플랫폼만
  python3 collect.py --date 2026-10-20
  python3 collect.py --date 2026-10-23 --refresh-meta   # (일회성) Steam 설명(short_description) 이 없는 앱만 메타 재조회
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from market import steam, itch  # noqa: E402

KST = timezone(timedelta(hours=9))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--only", choices=["steam", "itch"])
    ap.add_argument("--force", action="store_true", help="같은 날짜 스냅샷이 있어도 다시 수집")
    ap.add_argument("--refresh-meta", action="store_true",
                    help="(일회성) Steam 메타 캐시에 short_description 이 없는 앱만 appdetails 로 다시 받아 오늘 자 스냅샷에 반영하고 끝냄")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    data_dir = ROOT / "data"

    def log(msg):
        print(f"{datetime.now(KST).strftime('%H:%M:%S')} {msg}", flush=True)

    if args.refresh_meta:
        steam.refresh_meta(cfg["steam"], args.date, data_dir, log)
        return

    for name, mod in (("steam", steam), ("itch", itch)):
        if args.only and args.only != name:
            continue
        out = data_dir / name / f"{args.date}.json"
        if out.exists() and not args.force:
            log(f"[{name}] {out.name} 이미 있음, 건너뜀 (--force 로 재수집)")
            continue
        t0 = time.time()
        snap = mod.collect(cfg[name], args.date, data_dir, log)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
        n = len(snap.get("apps") or snap.get("games") or {})
        log(f"[{name}] 저장 {out.relative_to(ROOT)} · {n}개 · {time.time() - t0:.0f}초")


if __name__ == "__main__":
    main()
