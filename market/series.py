"""최근 7일 스냅샷 → 게임별 시계열 (순위 · 리뷰(평점) 수 · 동접).

플랫폼 차이는 여기서만 흡수합니다.
  steam: snap["lists"][목록][i] = {"rank", "appid"}, snap["apps"][appid] = {"name", "reviews_total", "ccu_now"}
  itch : snap["lists"][목록][i] = {"rank", "id"},    snap["games"][id]   = {"title", "page": {"rating_count"}}

쓰는 법:
    from market import series
    win = series.window(data_dir, "steam", "2026-10-26", days=7)      # [(date, snap)] 오름차순, 있는 만큼
    ts  = series.app_series(win, "steam")                             # {id: {"name", "dates", "ranks": {목록: [r|None]}, "reviews": [...], "ccu": [...]}}
    bump = series.top_bump(win, "steam", "topsellers", n=10)         # {"dates", "days"(MM-DD), "n_days", "list", "series": {이름: [순위|None]}, "ids": {이름: id}}
    blk = series.report_block(data_dir, "steam", date, list_name, pick_id)   # 리포트 JSON 에 넣을 덩어리 (아래)
"""
from datetime import datetime, timedelta

from .common import load_snaps

ID_KEY = {"steam": "appid", "itch": "id"}
APPS_KEY = {"steam": "apps", "itch": "games"}
LIST_KO = {"steam": {"topsellers": "Top Sellers", "popularnew": "New & Trending", "comingsoon": "Popular Upcoming", "newreleases": "New Releases"},
           "itch": {"new-and-popular": "New & Popular", "top-sellers": "Top Sellers", "popular": "Popular", "top-rated": "Top Rated", "newest": "Newest"}}


def window(data_dir, platform, date, days=7):
    """date 까지 days 일(포함) 안의 스냅샷을 날짜 오름차순으로. 7일 미만이면 있는 만큼."""
    return load_snaps(data_dir, platform, date, days=days - 1)


def _name(platform, snap, gid):
    a = snap.get(APPS_KEY[platform], {}).get(str(gid)) or {}
    return a.get("name") or a.get("title") or str(gid)


def _reviews(platform, snap, gid, source=None):
    """리뷰(평점) 수. Steam 은 reviews_total(소스가 source 와 같을 때만) → 검색 집계 review_count → SteamSpy positive+negative → recommendations 순 폴백."""
    a = snap.get(APPS_KEY[platform], {}).get(str(gid)) or {}
    if platform != "steam":
        return (a.get("page") or {}).get("rating_count")
    if a.get("reviews_total") is not None:
        if source and (a.get("reviews_source") or "appreviews") != source:
            return None
        return a["reviews_total"]
    if a.get("review_count") is not None:
        return a["review_count"]
    spy = a.get("spy") or {}
    sp = (spy.get("positive") or 0) + (spy.get("negative") or 0)
    if sp > 0:
        return sp
    return (a.get("meta") or {}).get("recommendations")


def _ccu(platform, snap, gid):
    if platform != "steam":
        return None
    return (snap.get("apps", {}).get(str(gid)) or {}).get("ccu_now")


def _rank_map(platform, snap, only_ids=None):
    """{목록: {id: rank}}. only_ids 를 주면 그 게임만 남기고 목록 순서대로 1부터 다시 매깁니다(본문 포함 게임 기준 순위).
    only_ids 는 id 집합 또는 callable(snap, date) → 집합(그날 스냅샷의 리뷰 수·출시일로 판정)."""
    out = {}
    key = ID_KEY[platform]
    if callable(only_ids):
        only_ids = {str(x) for x in only_ids(snap, snap.get("date"))}
    for ln, rows in (snap.get("lists") or {}).items():
        if only_ids is None:
            out[ln] = {str(r[key]): r["rank"] for r in rows}
        else:
            kept = [r for r in sorted(rows, key=lambda r: r["rank"]) if str(r[key]) in only_ids]
            out[ln] = {str(r[key]): i for i, r in enumerate(kept, 1)}
    return out


def app_series(win, platform, ids=None, only_ids=None):
    """게임별 시계열. ids 가 None 이면 창 안에 한 번이라도 목록에 든 게임 전부.
    목록에 없던 날은 None. 스냅샷이 없는 날짜는 아예 열에 없습니다(dates 참고). only_ids 는 _rank_map 참고."""
    dates = [d for d, _ in win]
    maps = [_rank_map(platform, s, only_ids) for _, s in win]
    lists = sorted({ln for m in maps for ln in m})
    if ids is None:
        ids = sorted({gid for m in maps for ln in m for gid in m[ln]})
    out = {}
    for gid in ids:
        gid = str(gid)
        name = next((_name(platform, s, gid) for _, s in reversed(win) if gid in s.get(APPS_KEY[platform], {})), gid)
        out[gid] = {
            "name": name, "dates": dates,
            "ranks": {ln: [m.get(ln, {}).get(gid) for m in maps] for ln in lists},
            "reviews": [_reviews(platform, s, gid, source=(win[-1][1].get(APPS_KEY[platform], {}).get(gid) or {}).get("reviews_source")) for _, s in win],
            "ccu": [_ccu(platform, s, gid) for _, s in win],
        }
    return out


def mmdd(date):
    return date[5:].replace("-", "-")


def top_bump(win, platform, list_name, n=10, only_ids=None, list_ko=None):
    """오늘 Top n 에 든 게임의 창 안 순위 시계열. n 밖이면 실제 순위를 그대로 두고(차트가 '밖' 줄로 그림), 목록에 없으면 None.
    only_ids 를 주면 그 게임들만으로 다시 매긴 순위를 씁니다(일간 리포트: 본문 포함 게임 = 소형 인디)."""
    list_ko = list_ko or LIST_KO[platform].get(list_name, list_name)
    if not win:
        return {"dates": [], "days": [], "n_days": 0, "list": list_name, "list_ko": list_ko, "n": n, "series": {}, "ids": {}}
    today_map = _rank_map(platform, win[-1][1], only_ids).get(list_name, {})
    top = sorted(today_map.items(), key=lambda kv: kv[1])[:n]
    ts = app_series(win, platform, [gid for gid, _ in top], only_ids)
    series, ids = {}, {}
    for gid, _ in top:
        name = ts[gid]["name"]
        base, k = name, 2
        while name in series:  # 같은 이름이 둘이면 뒤에 번호
            name = f"{base} ({k})"
            k += 1
        series[name] = ts[gid]["ranks"].get(list_name, [None] * len(win))
        ids[name] = gid
    return {"dates": [d for d, _ in win], "days": [mmdd(d) for d, _ in win], "n_days": len(win),
            "list": list_name, "list_ko": list_ko, "n": n, "series": series, "ids": ids}


def movers(win, platform, list_name, limit_rank=None, only_ids=None):
    """창 안에서 처음 목록에 보인 날 → 오늘의 순위 변화가 가장 큰 게임. (이름, 전, 후, 변화).
    오늘 목록에 있고 창 안에 하루 이상 더 보였어야 합니다. limit_rank 를 주면 오늘 순위가 그 안인 게임만."""
    if len(win) < 2:
        return None, None
    maps = [_rank_map(platform, s, only_ids).get(list_name, {}) for _, s in win]
    last = maps[-1]
    rows = []
    for gid, r1 in last.items():
        if limit_rank and r1 > limit_rank:
            continue
        r0 = next((m[gid] for m in maps[:-1] if gid in m), None)
        if r0 is None:
            continue
        rows.append((_name(platform, win[-1][1], gid), r0, r1, r0 - r1))
    if not rows:
        return None, None
    up = max(rows, key=lambda x: x[3])
    down = min(rows, key=lambda x: x[3])
    return (up if up[3] > 0 else None), (down if down[3] < 0 else None)


def report_block(data_dir, platform, date, list_name, pick_id=None, pick_list=None, days=7, n=10, only_ids=None, list_ko=None):
    """리포트 JSON 의 "series" 키. 카드·HTML 렌더러가 이걸로 스파크라인과 범프 차트를 그립니다.
    {
      "n_days": 6, "dates": [...], "days": ["10-21", ...],
      "bump": {"list": "topsellers", "list_ko": "인디 Top Sellers", "n": 10, "series": {이름: [순위|None]}, "ids": {...}},
      "biggest_up":   [이름, 전, 후, +변화]  또는 None   (창 전체, 오늘 Top 50 안; only_ids 가 있으면 그 안에서 다시 매긴 순위),
      "biggest_down": [이름, 전, 후, −변화]  또는 None,
      "pick": {"list": "topsellers", "list_ko": ..., "ranks": [..], "reviews": [..], "ccu": [..]}  또는 None
    }"""
    win = window(data_dir, platform, date, days)
    if only_ids is not None and not callable(only_ids):
        only_ids = {str(x) for x in only_ids}
    bump = top_bump(win, platform, list_name, n, only_ids, list_ko)
    up, down = movers(win, platform, list_name, limit_rank=50, only_ids=only_ids)
    pick = None
    if pick_id is not None and win:
        ts = app_series(win, platform, [str(pick_id)]).get(str(pick_id))
        if ts:
            pl = pick_list or list_name
            if pl not in ts["ranks"] or all(v is None for v in ts["ranks"][pl]):
                # 선정 게임이 그 목록에 없으면 값이 있는 목록 중 첫 번째
                pl = next((ln for ln, vs in ts["ranks"].items() if any(v is not None for v in vs)), pl)
            pick = {"list": pl, "list_ko": LIST_KO[platform].get(pl, pl), "ranks": ts["ranks"].get(pl, []),
                    "reviews": ts["reviews"], "ccu": ts["ccu"]}
    return {"n_days": len(win), "dates": [d for d, _ in win], "days": [mmdd(d) for d, _ in win],
            "bump": bump, "biggest_up": list(up) if up else None, "biggest_down": list(down) if down else None, "pick": pick}
