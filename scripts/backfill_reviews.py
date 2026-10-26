#!/usr/bin/env python3
"""일회성 보정: data/steam/<date>.json 의 reviews_total 이 null 인 앱을 SteamSpy 합계 → 검색 집계 → recommendations 순으로 채웁니다.

사용:
  python3 scripts/backfill_reviews.py                     # reviews_total 이 비어 있는 스냅샷 전부
  python3 scripts/backfill_reviews.py --dates 2026-10-23 2026-10-24 [--no-spy]
SteamSpy positive+negative 가 스냅샷에 없는 앱은 한 번씩 더 받아(초당 1회, data/cache/steam_spy_reviews.json 에 저장) 씁니다. 우선순위는 market/steam.REVIEW_SOURCES(SteamSpy → 검색 집계 → recommendations → appreviews).
같은 앱은 전날과 같은 소스를 우선합니다(market/steam.resolve_reviews). 원본은 git 이력으로 남습니다.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from market import steam  # noqa: E402

DATA = ROOT / "data" / "steam"
SPY_CACHE = ROOT / "data" / "cache" / "steam_spy_reviews.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dates", nargs="*")
    ap.add_argument("--no-spy", action="store_true", help="SteamSpy 를 새로 받지 않음")
    ap.add_argument("--redo", action="store_true", help="appreviews 가 아닌 소스로 채운 앱도 다시 고름(우선순위가 바뀌었을 때)")
    args = ap.parse_args()
    paths = sorted(DATA.glob("*.json"))
    if args.dates:
        paths = [p for p in paths if p.stem in set(args.dates)]
    spy_cache = json.loads(SPY_CACHE.read_text()) if SPY_CACHE.exists() else {}
    prev_source = {}
    fixed = 0
    for p in paths:
        snap = json.loads(p.read_text())
        apps = snap.get("apps", {})
        missing = [a for a, v in apps.items() if v.get("reviews_total") is None or (args.redo and v.get("reviews_source") not in (None, "appreviews"))]
        if not missing:
            prev_source = {a: v.get("reviews_source", "appreviews") for a, v in apps.items() if v.get("reviews_total") is not None}
            print(f"{p.stem}: 보정 불필요 (reviews_total {len(apps) - len(missing)}/{len(apps)})")
            continue
        # SteamSpy: 검색 집계가 없는 앱만, 캐시 우선
        need_spy = [a for a in missing if (apps[a].get("spy") or {}).get("positive") is None]
        if need_spy and not args.no_spy:
            todo = [a for a in need_spy if a not in spy_cache]
            print(f"{p.stem}: SteamSpy {len(need_spy)}개 필요 (새로 받을 것 {len(todo)}개, 약 {len(todo)}초)")
            for i, a in enumerate(todo, 1):
                try:
                    d = steam.get_json(steam.SPY, {"request": "appdetails", "appid": a})
                except Exception as e:  # noqa: BLE001
                    d = None
                    print(f"  {a} 실패: {e}")
                spy_cache[a] = {"positive": steam._to_int((d or {}).get("positive")), "negative": steam._to_int((d or {}).get("negative"))}
                time.sleep(1.0)
                if i % 50 == 0:
                    print(f"  {i}/{len(todo)}")
                    SPY_CACHE.write_text(json.dumps(spy_cache, indent=0))
            SPY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            SPY_CACHE.write_text(json.dumps(spy_cache, indent=0))
        counts = Counter()
        for a in missing:
            app = apps[a]
            if (app.get("spy") or {}).get("positive") is None and a in spy_cache:
                app.setdefault("spy", {})
                app["spy"]["positive"], app["spy"]["negative"] = spy_cache[a]["positive"], spy_cache[a]["negative"]
            total, src = steam.resolve_reviews(app, prefer=prev_source.get(a))
            app["reviews_total"] = total
            app["reviews_source"] = src
            counts[src or "없음"] += 1
        for a, v in apps.items():
            if v.get("reviews_total") is not None and not v.get("reviews_source"):
                v["reviews_source"] = "appreviews"
        p.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
        prev_source = {a: v.get("reviews_source") for a, v in apps.items() if v.get("reviews_source")}
        fixed += 1
        print(f"{p.stem}: 보정 {len(missing)}개 → " + " · ".join(f"{k} {v}" for k, v in counts.most_common()))
    print(f"보정한 스냅샷 {fixed}개")


if __name__ == "__main__":
    main()
