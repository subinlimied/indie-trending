"""Steam 수집기.

목록(검색 JSON) → 앱별 리뷰 수·동접(공식 API) → SteamSpy → 메타(appdetails, 캐시).
결과는 하루 하나의 스냅샷 dict 로 돌려줍니다.
"""
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .http import get, get_json

SEARCH = "https://store.steampowered.com/search/results/"
REVIEWS = "https://store.steampowered.com/appreviews/{appid}"
PLAYERS = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
DETAILS = "https://store.steampowered.com/api/appdetails"
SPY = "https://steamspy.com/api.php"

ROW = re.compile(r'<a href="https://store\.steampowered\.com/(app|sub|bundle)/(\d+)/[^"]*"(.*?)</a>', re.S)


def _first(pattern, text, flags=0, default=None):
    m = re.search(pattern, text, flags)
    return html.unescape(m.group(1)).strip() if m else default


def parse_rows(results_html):
    rows = []
    for kind, sid, body in ROW.findall(results_html):
        if kind != "app":
            continue
        tooltip = _first(r'data-tooltip-html="([^"]*)"', body, default="")
        pct = count = None
        m = re.search(r"(\d+)% of the ([\d,]+) user reviews", tooltip)
        if m:
            pct, count = int(m.group(1)), int(m.group(2).replace(",", ""))
        rows.append({
            "appid": int(sid),
            "name": _first(r'<span class="title">([^<]*)</span>', body),
            "tagids": json.loads(_first(r'data-ds-tagids="([^"]*)"', body, default="[]") or "[]"),
            "released": _first(r'<div class="search_released[^"]*">\s*([^<]*?)\s*</div>', body, re.S, default=""),
            "review_desc": tooltip.split("<br>")[0] if tooltip else None,
            "review_pct": pct,
            "review_count": count,
            "price_final": _to_int(_first(r'data-price-final="(\d+)"', body)),
            "price_original": _first(r'<div class="discount_original_price">([^<]*)</div>', body),
            "discount_pct": abs(_to_int(_first(r'data-discount="(-?\d+)"', body)) or 0),
        })
    return rows


def _to_int(s):
    try:
        return int(s) if s is not None else None
    except ValueError:
        return None


def fetch_list(filter_name, want, cc, indie_tag, log):
    out, start, page = [], 0, 0
    while len(out) < want:
        step = min(100, want - len(out))
        d = get_json(SEARCH, {
            "filter": filter_name, "tags": indie_tag, "category1": 998,
            "start": start, "count": step, "infinite": 1, "cc": cc, "l": "english",
        })
        if not d or not d.get("success"):
            log(f"  {filter_name}: 응답 실패 (start={start})")
            break
        rows = parse_rows(d["results_html"])
        if not rows:
            break
        out.extend(rows)
        start += step
        page += 1
        if start >= int(d.get("total_count") or 0):
            break
        time.sleep(0.8)
    for i, r in enumerate(out[:want], 1):
        r["rank"] = i
    return out[:want]


REGIONAL = ("topsellers", "popularnew", "comingsoon")  # 지역마다 순위가 다른 목록. New Releases 는 출시일 정렬이라 지역 무관.


def merge_regions(per_region, want, primary):
    """지역별 목록 → 글로벌 합성 목록.

    합집합을 만들고 각 앱의 지역별 순위 평균(그 지역 목록에 없으면 목록 크기+1)으로 오름차순 정렬해 1..want 를 매깁니다.
    이름·태그·가격은 primary(us) 행에서, 없으면 다른 지역 행에서 가져오되 가격은 USD 가 아닐 수 있어 비웁니다.
    """
    size = max((len(rows) for rows in per_region.values()), default=0)
    by_app = {}
    for rg, rows in per_region.items():
        for r in rows:
            e = by_app.setdefault(r["appid"], {"regions": {}, "rows": {}})
            e["regions"][rg] = r["rank"]
            e["rows"][rg] = r
    out = []
    for appid, e in by_app.items():
        avg = sum(e["regions"].get(rg, size + 1) for rg in per_region) / len(per_region)
        if primary in e["rows"]:
            row = dict(e["rows"][primary])
        else:
            row = dict(next(iter(e["rows"].values())))
            row["price_final"] = None
            row["price_original"] = None
        row["regions"] = e["regions"]
        row["_avg"] = avg
        out.append(row)
    out.sort(key=lambda r: (r["_avg"], min(r["regions"].values()), r["appid"]))
    out = out[:want]
    for i, r in enumerate(out, 1):
        r["rank"] = i
        r.pop("_avg")
    return out


def fetch_reviews(appid):
    d = get_json(REVIEWS.format(appid=appid), {
        "json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0, "filter": "all",
    })
    q = (d or {}).get("query_summary") or {}
    return {
        "reviews_total": q.get("total_reviews"),
        "reviews_pos": q.get("total_positive"),
        "reviews_neg": q.get("total_negative"),
        "review_score_desc": q.get("review_score_desc"),
    }


def fetch_players(appid):
    d = get_json(PLAYERS, {"appid": appid})
    return ((d or {}).get("response") or {}).get("player_count")


def fetch_spy(appid):
    d = get_json(SPY, {"request": "appdetails", "appid": appid})
    if not d or "name" not in d:
        return None
    tags = d.get("tags") or {}
    if isinstance(tags, dict):
        tags = dict(sorted(tags.items(), key=lambda kv: -kv[1])[:10])
    else:
        tags = {}
    return {
        "developer": d.get("developer"), "publisher": d.get("publisher"),
        "owners": d.get("owners"), "ccu_spy": d.get("ccu"),
        "avg_2weeks": d.get("average_2weeks"), "median_2weeks": d.get("median_2weeks"),
        "price": _to_int(d.get("price")), "initialprice": _to_int(d.get("initialprice")),
        "discount": _to_int(d.get("discount")), "genre": d.get("genre"), "tags": tags,
    }


def fetch_details(appid, cc):
    d = get_json(DETAILS, {
        "appids": appid, "cc": cc, "l": "english",
        "filters": "basic,developers,publishers,price_overview,release_date,genres,categories,demos,recommendations",
    })
    entry = (d or {}).get(str(appid)) or {}
    if not entry.get("success"):
        return None
    x = entry["data"]
    rd = x.get("release_date") or {}
    po = x.get("price_overview") or {}
    return {
        "name": x.get("name"), "type": x.get("type"),
        "release_date_raw": rd.get("date"), "release_date": parse_date(rd.get("date")),
        "coming_soon": bool(rd.get("coming_soon")),
        "developers": x.get("developers") or [], "publishers": x.get("publishers") or [],
        "genres": [g.get("description") for g in x.get("genres") or []],
        "is_free": bool(x.get("is_free")),
        "price_initial": po.get("initial"), "currency": po.get("currency"),
        "has_demo": bool(x.get("demos")),
        "recommendations": (x.get("recommendations") or {}).get("total"),
        # 스토어 짧은 설명(태그 제거, 600자)과 헤더 이미지. 리포트의 "desc" 와 루틴 썸네일 근거입니다.
        "short_description": re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x.get("short_description") or ""))).strip()[:600],
        "header_image": x.get("header_image"),
        "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    }


DATE_FORMATS = ("%b %d, %Y", "%d %b, %Y", "%B %d, %Y", "%d %B, %Y", "%b %Y", "%B %Y")


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def collect(cfg, date, data_dir: Path, log=print):
    cc, tag = cfg["cc"], cfg["indie_tag"]
    cache_path = data_dir / "cache" / "steam_meta.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    regions = [r.lower() for r in (cfg.get("regions") or [cc])]
    log(f"[steam] 목록 수집 (지역 {len(regions)}개: {' '.join(regions)})")
    lists, apps = {}, {}
    for name, want in cfg["lists"].items():
        if name in REGIONAL and len(regions) > 1:
            per_region = {}
            for i, rg in enumerate(regions):
                if i:
                    time.sleep(0.8)
                rows = fetch_list(name, want, rg, tag, log)
                if rows:
                    per_region[rg] = rows
                else:
                    log(f"  {name} {rg}: 0행, 합성에서 제외")
            rows = merge_regions(per_region, want, cc) if per_region else []
            log(f"  {name}: 합성 {len(rows)}개 (지역별 " + " ".join(f"{rg} {len(v)}" for rg, v in per_region.items()) + ")")
        else:
            rows = fetch_list(name, want, cc, tag, log)
            log(f"  {name}: {len(rows)}개")
        if len(rows) < min(want, 20):
            raise RuntimeError(f"[steam] 목록 {name} 이 {len(rows)}행뿐입니다. 스냅샷을 저장하지 않습니다.")
        lists[name] = [{"rank": r["rank"], "appid": r["appid"], **({"regions": r["regions"]} if r.get("regions") else {})} for r in rows]
        for r in rows:
            a = apps.setdefault(r["appid"], {})
            for k, v in r.items():
                if k not in ("rank", "regions") and v is not None:
                    a[k] = v

    # 최근 14일 안에 목록에 있었던 앱도 계속 추적
    tracked = recent_tracked(data_dir, date, cfg.get("track_days_after_exit", 14))
    extra = [a for a in tracked if a not in apps]
    for a in extra:
        apps[a] = {"name": tracked[a], "tracked_only": True}
    log(f"  고유 앱 {len(apps)}개 (목록 밖 추적 {len(extra)}개)")

    ids = sorted(apps)
    failed = []

    def safe(fn, appid, default):
        """한 앱의 실패(429 소진 등)가 전체 수집을 멈추지 않게 합니다."""
        try:
            return fn(appid)
        except Exception as e:  # noqa: BLE001
            failed.append((appid, fn.__name__, str(e)[:80]))
            return default

    def reviews_and_players(appid):
        rv = safe(fetch_reviews, appid, {})
        pc = safe(fetch_players, appid, None)
        time.sleep(0.5)
        return rv, pc

    log("[steam] 리뷰·동접 (동시 2개)")
    with ThreadPoolExecutor(max_workers=2) as ex:
        for i, (appid, (rv, pc)) in enumerate(zip(ids, ex.map(reviews_and_players, ids)), 1):
            apps[appid].update(rv)
            apps[appid]["ccu_now"] = pc
            if i % 100 == 0:
                log(f"  {i}/{len(ids)}")
    if failed:
        log(f"  실패 {len(failed)}건 (예: {failed[0]})")

    log("[steam] SteamSpy (초당 1회)")
    for i, appid in enumerate(ids):
        spy = safe(fetch_spy, appid, None)
        if spy:
            apps[appid]["spy"] = spy
        time.sleep(1.0)
        if (i + 1) % 100 == 0:
            log(f"  {i + 1}/{len(ids)}")

    log("[steam] 메타 (appdetails, 캐시 밖만)")
    today = datetime.strptime(date, "%Y-%m-%d")
    need = []
    for appid in ids:
        c = cache.get(str(appid))
        stale = (not c) or c.get("coming_soon") or (today - datetime.strptime(c["fetched"], "%Y-%m-%d")).days > 30
        if stale:
            need.append(appid)
    log(f"  조회 필요 {len(need)}개")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    for i, appid in enumerate(need):
        d = safe(lambda a: fetch_details(a, cc), appid, None)
        if d:
            cache[str(appid)] = d
        time.sleep(1.6)  # 약 200회/5분 제한
        if (i + 1) % 50 == 0:
            log(f"  {i + 1}/{len(need)}")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1))  # 중단돼도 캐시는 남게
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    if failed:
        log(f"  누적 실패 {len(failed)}건")

    for appid in ids:
        meta = cache.get(str(appid))
        if meta:
            apps[appid]["meta"] = {k: v for k, v in meta.items() if k != "fetched"}

    return {
        "platform": "steam", "date": date,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {"cc": cc, "regions": regions, "indie_tag": tag, "lists": cfg["lists"]},
        "lists": lists,
        "failed": [list(f) for f in failed],
        "apps": {str(k): v for k, v in apps.items()},
    }


def refresh_meta(cfg, date, data_dir: Path, log=print):
    """일회성: 오늘 자 스냅샷의 앱 중 캐시에 short_description 이 없는 것만 appdetails 로 다시 받아
    캐시(data/cache/steam_meta.json)와 스냅샷 apps[*].meta 를 갱신합니다. fetched 날짜는 무시합니다. 1.6초 간격."""
    snap_path = data_dir / "steam" / f"{date}.json"
    if not snap_path.exists():
        log(f"[steam] {snap_path.name} 없음 — 먼저 수집하세요")
        return 0
    snap = json.loads(snap_path.read_text())
    cache_path = data_dir / "cache" / "steam_meta.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    need = [appid for appid in snap["apps"] if not (cache.get(str(appid)) or {}).get("short_description")]
    log(f"[steam] 메타 설명 보강: {len(need)}/{len(snap['apps'])}개 조회 (약 {len(need) * 1.6 / 60:.0f}분)")
    done = 0
    for i, appid in enumerate(need):
        try:
            d = fetch_details(appid, cfg["cc"])
        except Exception as e:  # noqa: BLE001
            d = None
            log(f"  {appid} 실패: {e}")
        if d:
            cache[str(appid)] = d
            done += 1
        time.sleep(1.6)
        if (i + 1) % 50 == 0:
            log(f"  {i + 1}/{len(need)}")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
    for appid in snap["apps"]:
        meta = cache.get(str(appid))
        if meta:
            snap["apps"][appid]["meta"] = {k: v for k, v in meta.items() if k != "fetched"}
    snap_path.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    log(f"[steam] 설명 채움 {done}개 · 스냅샷 {snap_path.name} 갱신")
    return done


def recent_tracked(data_dir: Path, date, days):
    """최근 n일 스냅샷의 목록에 있던 appid → 이름."""
    out = {}
    today = datetime.strptime(date, "%Y-%m-%d")
    for p in sorted((data_dir / "steam").glob("*.json")):
        try:
            d = datetime.strptime(p.stem, "%Y-%m-%d")
        except ValueError:
            continue
        if 0 < (today - d).days <= days:
            snap = json.loads(p.read_text())
            for rows in snap.get("lists", {}).values():
                for r in rows:
                    a = snap["apps"].get(str(r["appid"]), {})
                    out[r["appid"]] = a.get("name")
    return out
