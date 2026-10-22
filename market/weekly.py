"""주간 분석 자료 수집.

A. 태그별 성공률 (Steam): Indie + 태그 X 를 가진 최근 1년 출시작을 Steam 검색 JSON(출시일 내림차순)으로 모아
   리뷰 500+ · 100+ · 10 미만 비율, 중앙값, 대표작 3개를 계산합니다.
B. 캡슐 아트 보드: 최근 7일 일간 리포트(reports/<platform>/<date>.json)의 선정 게임 · 큰 폭 변화 · 급상승 블록에
   나온 게임을 모으고, 캡슐 이미지를 받아 data URI 로 넘깁니다(스크린샷 때 네트워크 대기가 없도록).

기존 모듈은 import 만 합니다: market/http.py(get_json), market/steam.py(parse_rows, ROW), market/render.py(key_metric 등).
"""
import base64
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import render
from .http import _CTX, UA, get_json
from .steam import DETAILS, ROW, SEARCH, parse_rows

KST = timezone(timedelta(hours=9))
TAGDATA = "https://store.steampowered.com/tagdata/populartags/english"
STEAM_HEADER = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"
SLEEP = 0.8
MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}
RX_IMG = re.compile(r'<img src="([^"]+)"')
RX_LISTNAME = re.compile(r"^(.*?) \d+→\d+위$")
RX_FROM = re.compile(r"^(.*?) · (\d+)위에서$")
RX_OG = re.compile(r'<meta[^>]*property=["\']og:image["\'][^>]*>')
RX_CONTENT = re.compile(r'content=["\']([^"\']+)["\']')


# ====================================================================
# A. 태그별 성공률
# ====================================================================

def parse_date(s):
    """검색 행의 출시일 'Oct 22, 2026' / '22 Oct, 2026' → date. 'Coming soon', 'Q4 2026' 처럼 날짜가 아니면 None."""
    s = (s or "").strip().replace(",", "")
    parts = s.split()
    if len(parts) != 3:
        return None
    try:
        if parts[0] in MONTHS:
            return date(int(parts[2]), MONTHS[parts[0]], int(parts[1]))
        if parts[1] in MONTHS:
            return date(int(parts[2]), MONTHS[parts[1]], int(parts[0]))
    except ValueError:
        return None
    return None


def resolve_tags(names, log):
    """config 의 태그 이름 → [{name, id}] (Steam populartags 로 id 를 찾습니다. 없는 이름은 경고 후 제외)."""
    data = get_json(TAGDATA) or []
    by_name = {t["name"].lower(): (t["tagid"], t["name"]) for t in data if "tagid" in t and "name" in t}
    out = []
    for n in names:
        hit = by_name.get(n.lower())
        if not hit:
            log(f"  경고: 태그 '{n}' 을 populartags 에서 찾지 못해 건너뜁니다")
            continue
        out.append({"name": hit[1], "id": hit[0]})
    return out


def _row_images(results_html):
    """검색 행의 작은 캡슐(231×87, 해시 경로) 주소. appid → url."""
    out = {}
    for kind, sid, body in ROW.findall(results_html):
        if kind != "app":
            continue
        m = RX_IMG.search(body)
        if m:
            out[int(sid)] = m.group(1).split("?")[0]
    return out


def fetch_tag_rows(tagid, indie_tag, since, max_pages, log, counter):
    """Indie + tagid 교집합을 출시일 내림차순으로 넘기며 since 이후 출시작을 모읍니다.
    돌려주는 값: (rows, pages, truncated). truncated 는 max_pages 안에 since 까지 못 간 경우."""
    rows, seen, start, pages, truncated = [], set(), 0, 0, False
    while True:
        d = get_json(SEARCH, {
            "sort_by": "Released_DESC", "tags": f"{indie_tag},{tagid}", "category1": 998,
            "start": start, "count": 100, "infinite": 1, "cc": "us", "l": "english",
        })
        counter["requests"] += 1
        pages += 1
        if not d or not d.get("success"):
            log(f"    응답 실패 (start={start})")
            break
        parsed = parse_rows(d["results_html"])
        imgs = _row_images(d["results_html"])
        if not parsed:
            break
        done = False
        for r in parsed:
            rd = parse_date(r["released"])
            if rd is None:
                continue
            if rd < since:
                done = True
                break
            if r["appid"] in seen:
                continue
            seen.add(r["appid"])
            rows.append({"appid": r["appid"], "name": r["name"], "released": rd.isoformat(),
                         "reviews": r["review_count"] or 0, "pct": r["review_pct"],
                         "price": r["price_final"], "img": imgs.get(r["appid"])})
        if done:
            break
        start += 100
        if start >= int(d.get("total_count") or 0):
            break
        if pages >= max_pages:
            truncated = True
            break
        time.sleep(SLEEP)
    return rows, pages, truncated


def summarize_tag(tag, rows, pages, truncated, w, until):
    n = len(rows)
    succ, mid = int(w.get("success_reviews", 500)), int(w.get("mid_reviews", 100))
    revs = sorted(r["reviews"] for r in rows)
    n_succ = sum(1 for x in revs if x >= succ)
    n_mid = sum(1 for x in revs if x >= mid)
    n_low = sum(1 for x in revs if x < 10)
    median = (revs[n // 2] if n % 2 else (revs[n // 2 - 1] + revs[n // 2]) / 2) if n else 0
    oldest = min((r["released"] for r in rows), default=None)
    window_days = (until - date.fromisoformat(oldest)).days + 1 if (truncated and oldest) else int(w.get("window_days", 365))
    top = sorted(rows, key=lambda r: (-r["reviews"], r["released"]))[:3]
    pct = lambda k: round(100 * k / n, 1) if n else 0.0  # noqa: E731
    min_games = int(w.get("min_games", 30))
    niche = round(pct(n_mid) * math.log10(int(w.get("niche_base", 10000)) / n), 1) if n >= min_games else None
    return {
        "name": tag["name"], "id": tag["id"], "n": n, "n_success": n_succ, "n_mid": n_mid, "n_low": n_low,
        "p_success": pct(n_succ), "p_mid": pct(n_mid), "p_low": pct(n_low), "median": median,
        "top": [{"appid": r["appid"], "name": r["name"], "reviews": r["reviews"], "released": r["released"],
                 "url": f"https://store.steampowered.com/app/{r['appid']}/", "img": r["img"]} for r in top],
        "pages": pages, "truncated": truncated, "window_days": window_days, "oldest": oldest,
        "niche": niche, "ranked": n >= min_games,
    }


def collect_tags(cfg, run_date, log):
    """config 의 weekly.tags 전체 → {date, since, until, tags: [...], requests, games_total}."""
    w = cfg["weekly"]
    indie_tag = cfg["steam"].get("indie_tag", 492)
    until = date.fromisoformat(run_date)
    since = until - timedelta(days=int(w.get("window_days", 365)) - 1)
    max_pages = int(w.get("max_pages_per_tag", 24))
    counter = {"requests": 1}
    tags = resolve_tags(w["tags"], log)
    log(f"[weekly] 태그 {len(tags)}개 · 기간 {since} ~ {until} · 태그당 최대 {max_pages}페이지")
    out, all_apps = [], set()
    for i, tag in enumerate(tags, 1):
        t0 = time.time()
        rows, pages, truncated = fetch_tag_rows(tag["id"], indie_tag, since, max_pages, log, counter)
        s = summarize_tag(tag, rows, pages, truncated, w, until)
        out.append(s)
        all_apps.update(r["appid"] for r in rows)
        log(f"  {i:2d}/{len(tags)} {tag['name']}: {s['n']}개 · 500+ {s['p_success']}% · 100+ {s['p_mid']}% · {pages}p"
            + (f" · 잘림(최근 {s['window_days']}일)" if truncated else "") + f" · {time.time() - t0:.0f}초 · 누적 요청 {counter['requests']}")
        time.sleep(SLEEP)
    return {"date": run_date, "since": since.isoformat(), "until": until.isoformat(), "window_days": int(w.get("window_days", 365)),
            "success_reviews": int(w.get("success_reviews", 500)), "mid_reviews": int(w.get("mid_reviews", 100)),
            "min_games": int(w.get("min_games", 30)), "niche_base": int(w.get("niche_base", 10000)),
            "requests": counter["requests"], "games_total": len(all_apps), "tags": out,
            "generated": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}


def rank_tags(data, n_top=5, n_niche=3):
    """표·임베드용 순위: 성공률(500+ 비율) 상위, 틈 지수 상위. 둘 다 min_games 를 넘긴 태그만."""
    ranked = [t for t in data["tags"] if t.get("ranked")]
    top = sorted(ranked, key=lambda t: (-t["p_success"], -t["p_mid"], -t["n"]))[:n_top]
    niche = sorted([t for t in ranked if t.get("niche") is not None], key=lambda t: (-t["niche"], -t["p_mid"]))[:n_niche]
    return top, niche


# ====================================================================
# B. 캡슐 아트 보드 자료
# ====================================================================

def metric_text(hero, cap, platform):
    """key_metric 결과 → 'Top Sellers ▲48' · '리뷰 +50.8%' 같은 한 줄."""
    if not hero:
        return ""
    unit = "리뷰" if platform == "steam" else "평점"
    m = RX_LISTNAME.match(cap or "")
    if m:
        return f"{m.group(1)} {hero}"
    m = RX_FROM.match(cap or "")
    if m and hero.endswith("위"):
        try:
            delta = int(m.group(2)) - int(hero[:-1])
            return f"{m.group(1)} {'▲' if delta > 0 else '▼'}{abs(delta)}" if delta else f"{m.group(1)} {hero}"
        except ValueError:
            pass
    if cap.startswith("증가율"):
        return f"{unit} 증가율 {hero}"
    if cap.startswith("증가 수"):
        return f"{unit} {hero}"
    if cap.startswith("연속 상승"):
        return f"{hero} 연속 상승"
    label = (cap or "").split(" (")[0].split(" · ")[0]
    return f"{label} {hero}".strip()


def board_games(platform, dates, reports_dir):
    """최근 dates 의 일간 리포트에서 게임을 모읍니다. url 기준으로 합치고 등장 횟수·대표 수치를 둡니다.
    대표 수치 우선순위: 선정 게임(3) > 큰 폭 변화(2) > 급상승 블록(1), 같은 급이면 늦은 날짜."""
    games = {}

    def add(name, url, line_or_metric, d, prio, it=None, rep=None, parsed=None):
        if not url or not name:
            return
        if parsed is None:
            hero, cap, _, _ = render.key_metric(line_or_metric)
            metric = metric_text(hero, cap, platform)
        else:
            metric = parsed
        g = games.setdefault(url, {"name": name, "url": url, "metric": "", "prio": 0, "date": "", "hits": 0, "dates": set(),
                                   "thumb": None, "thumb_bg": None})
        g["hits"] += 1
        g["dates"].add(d)
        if (prio, d) >= (g["prio"], g["date"]) and metric:
            g["metric"], g["prio"], g["date"] = metric, prio, d
        thumb = (it or {}).get("thumb") or ((rep or {}).get("thumbs") or {}).get(url, {}).get("src")
        if thumb and not g["thumb"]:
            g["thumb"] = thumb
            g["thumb_bg"] = (it or {}).get("thumb_bg") or ((rep or {}).get("thumbs") or {}).get(url, {}).get("bg")

    for d in dates:
        src = reports_dir / platform / f"{d}.json"
        if not src.exists():
            continue
        rep = json.loads(src.read_text())
        p = rep.get("pick")
        if p:
            add(p["name"], p.get("url"), p.get("line", ""), d, 3, it=p, rep=rep)
        for h in rep.get("headline") or []:
            info = render.headline_info(h)
            add(info["name"], info["url"], None, d, 2, rep=rep, parsed=metric_text(info["hero"], info["cap"], platform))
        secs = rep.get("sections") or []
        for b in (secs[0].get("blocks") or []) if secs else []:
            for it in b.get("items") or []:
                add(it["name"], it.get("url"), it.get("line", ""), d, 1, it=it, rep=rep)
    out = sorted(games.values(), key=lambda g: (g["hits"], g["prio"], g["date"]), reverse=True)
    for g in out:
        g["dates"] = sorted(g["dates"])
        g["days"] = len(g["dates"])
    return out


def fetch_bytes(url, timeout=25):
    """이미지 바이트. 404 등 실패는 None (스크린샷을 막지 않도록 예외를 삼킵니다)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            return r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return None


def _mime(b):
    if b[:4] == b"\x89PNG":
        return "image/png"
    if b[:3] == b"GIF":
        return "image/gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def steam_header_url(appid, cache, log):
    """appid → header 이미지 주소. 신작은 해시 경로라 appid 경로가 404 라서 appdetails 의 header_image 를 받아 캐시합니다."""
    key = str(appid)
    if key in cache:
        return cache[key]
    url = None
    d = get_json(DETAILS, {"appids": appid, "cc": "us", "l": "english", "filters": "basic"})
    data = ((d or {}).get(key) or {}).get("data") or {}
    if data.get("header_image"):
        url = data["header_image"].split("?")[0]
    else:
        log(f"    appdetails 에 header_image 없음: {appid} → appid 경로로 시도")
        url = STEAM_HEADER.format(appid=appid)
    cache[key] = url
    time.sleep(SLEEP)
    return url


def itch_thumb(url, dates, data_dir, cache, log):
    """thumb 가 없는 itch 게임(옛 리포트): 스냅샷의 thumb → 게임 페이지 og:image(캐시) 순서로 찾습니다."""
    for d in reversed(dates):
        p = data_dir / "itch" / f"{d}.json"
        if not p.exists():
            continue
        try:
            games = json.loads(p.read_text()).get("games") or {}
        except (OSError, ValueError):
            continue
        for g in games.values():
            if g.get("url") == url and g.get("thumb"):
                return g["thumb"], g.get("thumb_bg")
    key = "itch:" + url
    if key in cache:
        return cache[key], None
    b = fetch_bytes(url)
    m = RX_OG.search(b.decode("utf-8", "replace")) if b else None
    m = RX_CONTENT.search(m.group(0)) if m else None
    cache[key] = m.group(1) if m else None
    if not m:
        log(f"    itch 페이지에서 og:image 를 못 찾음: {url}")
    time.sleep(SLEEP)
    return cache[key], None


def attach_images(games, platform, cache, log, dates=(), data_dir=None):
    """각 게임에 image_url 과 data(data URI) 를 넣습니다. 못 받으면 data=None 으로 두어 머리글자 블록이 보입니다."""
    ok = 0
    for g in games:
        url = g.get("thumb")
        if platform == "itch" and not url and data_dir is not None:
            url, bg = itch_thumb(g["url"], dates, data_dir, cache, log)
            g["thumb_bg"] = g.get("thumb_bg") or bg
        if platform == "steam":
            m = render.STEAM_APP.search(g["url"])
            if m:
                url = steam_header_url(m.group(1), cache, log)
        g["image_url"] = url
        b = fetch_bytes(url) if url else None
        if b and len(b) > 200:
            g["data"] = f"data:{_mime(b)};base64,{base64.b64encode(b).decode()}"
            ok += 1
        else:
            g["data"] = None
            log(f"    이미지 실패: {g['name']} ({url})")
    return ok
