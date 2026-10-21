"""itch.io 수집기.

목록(browse ?format=json) → 게임 페이지(평점 수, 태그, 엔진, 공개일, 댓글 수, 데브로그, Steam 링크).
"""
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .http import get, get_json

BROWSE = "https://itch.io/games/{name}"
# "popular" 는 /games 기본 목록입니다 (/games/popular 는 404).
LIST_PATH = {"popular": "https://itch.io/games"}
# 셀 시작 태그는 <div class="game_cell ..." data-game_id="..."> 또는 속성 순서가 바뀐 형태 둘 다 옵니다.
# game_cell_tools / game_cell_data 는 셀 시작이 아니므로 class 값 뒤에 공백이나 따옴표가 오는 것만 봅니다.
CELL_START = re.compile(r'<div(?=[^>]*\bclass="game_cell[ "])[^>]*\bdata-game_id="(\d+)"[^>]*>')


def _first(pattern, text, flags=0, default=None):
    m = re.search(pattern, text, flags)
    return html.unescape(m.group(1)).strip() if m else default


def split_cells(content):
    starts = list(CELL_START.finditer(content))
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(content)
        yield m.group(1), content[m.end():end]


def parse_cells(content):
    out = []
    for gid, body in split_cells(content):
        platforms = []
        for icon, name in (("icon-windows8", "win"), ("icon-apple", "mac"), ("icon-tux", "linux"),
                           ("icon-android", "android"), ("web_flag", "web")):
            if icon in body:
                platforms.append(name)
        out.append({
            "id": int(gid),
            "title": _first(r'class="title game_link"[^>]*>([^<]*)<', body),
            "url": _first(r'class="title game_link"[^>]*href="([^"]*)"', body)
                   or _first(r'href="(https://[^"]*\.itch\.io/[^"]*)"', body),
            "author": _first(r'class="game_author"><a[^>]*>([^<]*)<', body),
            "genre": _first(r'class="game_genre">([^<]*)<', body),
            "price": _first(r'class="price_value">([^<]*)<', body),
            "sale": bool(re.search(r'class="sale_tag', body)),
            "short": _first(r'class="game_text">([^<]*)<', body),
            "platforms": platforms,
            # 캡슐 썸네일(315x250)과 썸네일 바탕색. 리포트 카드 이미지와 이미지 없을 때의 색 블록에 씁니다.
            "thumb": _first(r'class="game_thumb"[^>]*>.*?<img[^>]*data-lazy_src="([^"]*)"', body, re.S),
            "thumb_bg": _first(r'<div[^>]*background-color:(#[0-9a-fA-F]{3,6})[^>]*class="game_thumb"', body),
        })
    return out


def fetch_list(name, pages, log):
    out, seen = [], set()
    for page in range(1, pages + 1):
        d = get_json(LIST_PATH.get(name, BROWSE.format(name=name)), {"format": "json", "page": page})
        if not d or not d.get("content"):
            log(f"  {name} p{page}: 응답 실패")
            break
        cells = parse_cells(d["content"])
        if not cells:
            log(f"  {name} p{page}: 셀 0개 (마크업 변경?)")
            break
        for c in cells:
            if c["id"] not in seen:
                seen.add(c["id"])
                out.append(c)
        if len(cells) < 36:
            break
        time.sleep(0.6)
    for i, c in enumerate(out, 1):
        c["rank"] = i
    return out


INFO_ROW = re.compile(r"<tr><td>([^<]+)</td><td>(.*?)</td></tr>", re.S)


def fetch_page(url):
    body = get(url)
    if not body:
        return None
    info = {}
    for label, val in INFO_ROW.findall(body):
        abbr = re.search(r'<abbr title="([^"]+)"', val)
        text = re.sub(r"<[^>]+>", "", val)
        info[label.strip()] = (abbr.group(1) if abbr else html.unescape(text).strip())
    links = lambda key: [html.unescape(t) for t in re.findall(r'href="https://itch\.io/games/' + key + r'-[^"]*">([^<]*)<', body)]
    comments = _first(r"<nobr><span>\d+</span> to <span>\d+</span> of (\d+)</nobr>", body)
    if comments is None:
        comments = str(len(re.findall(r'class="community_post ', body)))
    devlog = re.findall(r'class="post_date"><abbr title="([^"]+)"', body)
    # 잼 출품은 "Submission to ..." 버튼(jam_entry)만 셉니다. 본문·댓글에 적힌 잼 링크는 제외.
    jam = re.findall(r'class="jam_entry"><a href="(https://itch\.io/jam/[^"/]+)', body)
    rating_count = _to_int(_first(r'"ratingCount":"?(\d+)', body))
    if rating_count is None:
        rating_count = _to_int((_first(r"\(([\d,]+) total ratings?\)", info.get("Rating", "")) or "").replace(",", "") or None)
    return {
        "rating_value": _to_float(_first(r'"ratingValue":"?([\d.]+)', body)),
        "rating_count": rating_count,
        "tags": links("tag"),
        "made_with": links("made-with"),
        "genre": list(dict.fromkeys(links("genre"))),
        "status": info.get("Status"),
        "published": _iso(info.get("Published") or info.get("Release date")),
        "updated": _iso(info.get("Updated")),
        "session": info.get("Average session"),
        "comments": _to_int(comments),
        "devlog_latest": _iso(devlog[0]) if devlog else None,
        "devlog_count": len(devlog),
        "steam_url": _first(r'href="(https://store\.steampowered\.com/app/\d+)[^"]*"', body),
        "jam": sorted(set(jam))[:3],
        "nyop": "Name your own price" in body,
        "price_text": _first(r'<span class="buy_message"><span class="sub">([^<]*)</span>', body)
                      or _first(r'class="buy_btn"[^>]*>([^<]*)<', body),
    }


def _iso(s):
    """'30 May 2016 @ 22:00 UTC' (abbr title) 또는 'May 30, 2016' (표시 텍스트) → ISO."""
    if not s:
        return None
    s = s.strip()
    for pat, fmt in ((r"(\d{1,2}) (\w+) (\d{4})", "%d %B %Y"), (r"(\w+) (\d{1,2}), (\d{4})", "%B %d %Y")):
        m = re.match(pat, s)
        if m:
            try:
                return datetime.strptime(" ".join(m.groups()), fmt).strftime("%Y-%m-%d")
            except ValueError:
                return None
    return None


def _to_int(s):
    try:
        return int(s) if s is not None else None
    except ValueError:
        return None


def _to_float(s):
    try:
        return float(s) if s is not None else None
    except ValueError:
        return None


def collect(cfg, date, data_dir, log=print):
    log("[itch] 목록 수집")
    lists, games = {}, {}
    for name, pages in cfg["lists"].items():
        cells = fetch_list(name, pages, log)
        log(f"  {name}: {len(cells)}개")
        if not cells:
            # 빈 목록을 스냅샷에 남기면 다음 회차 비교가 전부 "이탈"이 됩니다. 저장하지 않고 끝냅니다.
            raise RuntimeError(f"[itch] 목록 {name} 이 0행입니다. 스냅샷을 저장하지 않습니다.")
        lists[name] = [{"rank": c["rank"], "id": c["id"]} for c in cells]
        for c in cells:
            g = games.setdefault(c["id"], {})
            for k, v in c.items():
                if k != "rank" and v not in (None, [], ""):
                    g[k] = v

    ids = [i for i in games if games[i].get("url")]
    log(f"[itch] 게임 페이지 {len(ids)}개")

    def work(i):
        try:
            d = fetch_page(games[i]["url"])
        except Exception as e:  # 한 페이지 실패가 전체를 막지 않게
            d = {"error": str(e)[:120]}
        time.sleep(0.4)
        return i, d

    with ThreadPoolExecutor(max_workers=3) as ex:
        for n, (i, d) in enumerate(ex.map(work, ids), 1):
            if d:
                games[i]["page"] = d
            if n % 100 == 0:
                log(f"  {n}/{len(ids)}")

    return {
        "platform": "itch", "date": date,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "params": {"lists": cfg["lists"]},
        "lists": lists,
        "games": {str(k): v for k, v in games.items()},
    }
