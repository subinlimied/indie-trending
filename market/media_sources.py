"""미디어·밈 트렌드 소스별 수집기 (표준 라이브러리만).

소스: Know Your Meme 뉴스피드 RSS · Google 트렌드 일간 RSS(KR·US) · 위키백과 일간 조회수 상위(en·ko)
      · Reddit top(t=day) RSS · Imgflip 인기 밈 템플릿 100개.
소스 하나가 실패해도 나머지는 계속 가고, 스냅샷의 sources[키] 에 status("ok"/"fail") 와 error 를 남깁니다.
모든 요청에 연락처가 든 User-Agent 를 붙이고 요청 사이 0.5초 쉽니다.
"""
import html as H
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from urllib.parse import quote

from . import http

UA = "indie-trending/1.0 (https://github.com/subinlimied/indie-trending)"
HEADERS = {"User-Agent": UA, "Accept": "*/*"}
SLEEP = 0.5

KYM_RSS = "https://knowyourmeme.com/newsfeed.rss"
TRENDS_RSS = "https://trends.google.com/trending/rss"
WIKI_TOP = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}.wikipedia/all-access/{y}/{m}/{d}"
REDDIT_RSS = "https://www.reddit.com/r/{sub}/top/.rss?t=day"
IMGFLIP = "https://api.imgflip.com/get_memes"

# 제목에서 뽑는 플랫폼 단서. (표시 이름, 정규식)
PLATFORMS = [
    ("TikTok", re.compile(r"tik\s?tok", re.I)),
    ("Twitter/X", re.compile(r"\btwitter\b|\bx\.com\b|\bon X\b|\bX (?:users?|posts?|thread|account)\b|\(X\)", re.I)),
    ("Reddit", re.compile(r"\breddit\b|\br/\w+", re.I)),
    ("YouTube", re.compile(r"you\s?tube|\byoutuber", re.I)),
    ("Instagram", re.compile(r"\binstagram\b|\binsta\b|\breels?\b", re.I)),
    ("Twitch", re.compile(r"\btwitch\b", re.I)),
]
TAG_RX = re.compile(r"<[^>]+>")
IMG_RX = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
WS_RX = re.compile(r"\s+")


def _get(url, params=None, retries=3, timeout=25):
    body = http.get(url, params, headers=HEADERS, retries=retries, timeout=timeout)
    time.sleep(SLEEP)
    return body


def _text(el, tag, ns=None):
    x = el.find(tag, ns) if ns else el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


def plain(s, limit=None):
    s = WS_RX.sub(" ", H.unescape(TAG_RX.sub(" ", s or ""))).strip()
    if limit and len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def platform_tags(title):
    return [name for name, rx in PLATFORMS if rx.search(title or "")]


# ---------- 1. Know Your Meme ----------

def collect_kym(hours=48, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    body = _get(KYM_RSS)
    if not body:
        raise RuntimeError("빈 응답")
    root = ET.fromstring(body)
    items = []
    for it in root.iter("item"):
        title = plain(_text(it, "title"))
        link = _text(it, "link")
        pub_raw = _text(it, "pubDate")
        try:
            pub = parsedate_to_datetime(pub_raw).astimezone(timezone.utc)
        except (TypeError, ValueError):
            pub = None
        if pub and pub < cutoff:
            continue
        desc_raw = _text(it, "description")
        m = IMG_RX.search(desc_raw)
        items.append({
            "title": title,
            "url": link,
            "published": pub.strftime("%Y-%m-%dT%H:%M:%SZ") if pub else pub_raw,
            "summary": plain(desc_raw, 300),
            "image": m.group(1) if m else "",
            "platforms": platform_tags(title),
            "guid": _text(it, "guid") or link,
        })
    items.sort(key=lambda x: x["published"], reverse=True)
    return items


# ---------- 2. Google 트렌드 ----------

def traffic_num(s):
    """'2000+' · '20K+' · '1M+' → 정수. 못 읽으면 0."""
    m = re.match(r"\s*([\d.,]+)\s*([KkMm]?)", s or "")
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    mult = {"k": 1_000, "m": 1_000_000}.get(m.group(2).lower(), 1)
    return int(n * mult)


def collect_trends(geo):
    body = _get(TRENDS_RSS, {"geo": geo})
    if not body:
        raise RuntimeError("빈 응답")
    root = ET.fromstring(body)
    ns = {"ht": "https://trends.google.com/trending/rss"}
    items = []
    for i, it in enumerate(root.iter("item"), 1):
        title = plain(_text(it, "title"))
        traffic_raw = _text(it, "ht:approx_traffic", ns)
        news = it.find("ht:news_item", ns)
        news_title = plain(_text(news, "ht:news_item_title", ns)) if news is not None else ""
        news_url = _text(news, "ht:news_item_url", ns) if news is not None else ""
        items.append({
            "rank": i,
            "title": title,
            "traffic": traffic_num(traffic_raw),
            "traffic_raw": traffic_raw,
            "news_title": news_title,
            "news_url": news_url,
            "url": news_url or f"https://trends.google.com/trends/explore?geo={geo}&q={quote(title)}",
            "picture": _text(it, "ht:picture", ns),
        })
    return items


# ---------- 3. 위키백과 ----------

EXCLUDE_PREFIX = ("Main_Page", "Special:", "Wikipedia:", "File:", "Category:", "Portal:", "Help:", "Template:", "Talk:",
                  "위키백과:", "특수:", "파일:", "분류:", "포털:", "도움말:", "틀:", "토론:")


def collect_wiki(project, date, top=20, pool=40):
    """전날 집계가 가장 최근이지만 09:30 KST 에는 아직 안 올라온 날이 많아(UTC 기준 집계) 2~3일 전까지 거슬러 찾습니다."""
    data, d = None, None
    for back in (1, 2, 3):
        d = datetime.strptime(date, "%Y-%m-%d") - timedelta(days=back)
        url = WIKI_TOP.format(project=project, y=d.year, m=f"{d.month:02d}", d=f"{d.day:02d}")
        data = http.get_json(url, headers=HEADERS, retries=2)
        time.sleep(SLEEP)
        if data and data.get("items"):
            break
    if not data or not data.get("items"):
        raise RuntimeError("최근 3일 집계 없음")
    arts = data["items"][0].get("articles") or []
    items = []
    for a in arts[:pool]:
        name = a.get("article") or ""
        if name.startswith(EXCLUDE_PREFIX) or name.startswith("-"):
            continue
        items.append({
            "title": name.replace("_", " "),
            "views": int(a.get("views") or 0),
            "rank": len(items) + 1,
            "src_rank": a.get("rank"),
            "url": f"https://{project}.wikipedia.org/wiki/{quote(name)}",
        })
        if len(items) >= top:
            break
    return {"day": d.strftime("%Y-%m-%d"), "items": items}


# ---------- 4. Reddit ----------

REDDIT_GAP = 62.0      # 익명 RSS 는 IP 당 약 1분에 1회만 허용됩니다(그 안에 보내면 429)
_reddit_last_ok = [0.0]


def _reddit_get(url):
    """reddit 은 직전 성공 뒤 1분 안의 요청에 429 를 냅니다. 간격을 맞춰 보내고, 429 면 20초씩 쉬며 세 번까지 시도합니다."""
    import urllib.error
    import urllib.request
    last = None
    for attempt in range(3):
        wait = REDDIT_GAP - (time.time() - _reddit_last_ok[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25, context=http._CTX) as r:
                body = r.read().decode("utf-8", "replace")
            _reddit_last_ok[0] = time.time()
            return body
        except urllib.error.HTTPError as e:
            last = e
            try:
                e.close()
            except Exception:  # noqa: BLE001
                pass
            if e.code in (403, 429) and attempt < 2:
                time.sleep(20.0)
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(5.0)
    raise RuntimeError(f"reddit 실패: {last}")


def collect_reddit(sub, top=8):
    url = REDDIT_RSS.format(sub=sub)
    body = _reddit_get(url)
    if not body:
        raise RuntimeError("빈 응답")
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for e in root.findall("a:entry", ns):
        title = plain(_text(e, "a:title", ns))
        link = e.find("a:link", ns)
        href = link.get("href") if link is not None else ""
        if not title:
            continue
        items.append({"rank": len(items) + 1, "title": title, "url": href})
        if len(items) >= top:
            break
    if not items:
        raise RuntimeError("항목 0개")
    return items


# ---------- 5. Imgflip ----------

def collect_imgflip():
    data = http.get_json(IMGFLIP, headers=HEADERS, retries=3)
    time.sleep(SLEEP)
    if not data or not data.get("success"):
        raise RuntimeError("success=false")
    out = []
    for i, m in enumerate((data.get("data") or {}).get("memes") or [], 1):
        out.append({"rank": i, "id": str(m.get("id")), "name": m.get("name") or "", "url": m.get("url") or "",
                    "box_count": m.get("box_count"), "captions": m.get("captions")})
    return out


# ---------- 전체 ----------

def _run(snap, key, label, fn, log):
    t0 = time.time()
    try:
        items = fn()
        extra = {}
        if isinstance(items, dict):            # 위키: {"day", "items"}
            extra = {k: v for k, v in items.items() if k != "items"}
            items = items["items"]
        snap["sources"][key] = {"label": label, "status": "ok", "count": len(items), "items": items, **extra}
        log(f"[media] {label}: {len(items)}개 · {time.time() - t0:.1f}초")
    except Exception as e:  # noqa: BLE001  소스 하나가 죽어도 나머지는 계속
        msg = f"{type(e).__name__}: {e}"[:200]
        snap["sources"][key] = {"label": label, "status": "fail", "error": msg, "count": 0, "items": []}
        log(f"[media] {label}: 실패 — {msg}")


def collect(cfg, date, log=print, only=None, base=None):
    """cfg = config.json 의 "media". 반환: 스냅샷 dict (data/media/<date>.json 에 저장).
    only = {"kym", "trends", "wiki", "reddit", "imgflip"} 의 부분집합이면 그 소스만 받아 base(기존 스냅샷)에 합칩니다."""
    snap = {"date": date, "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "params": {"kym_hours": cfg.get("kym_hours", 48), "wiki_top": cfg.get("wiki_top", 20),
                       "reddit_subs": cfg.get("reddit_subs", [])},
            "sources": dict((base or {}).get("sources") or {})}

    def want(group):
        return not only or group in only

    if want("kym"):
        _run(snap, "kym", "KYM 뉴스피드", lambda: collect_kym(cfg.get("kym_hours", 48)), log)
    if want("trends"):
        for geo in ("KR", "US"):
            _run(snap, f"trends_{geo.lower()}", f"Google 트렌드 {geo}", lambda g=geo: collect_trends(g), log)
    if want("wiki"):
        for proj in ("en", "ko"):
            _run(snap, f"wiki_{proj}", f"위키백과 {proj}", lambda p=proj: collect_wiki(p, date, cfg.get("wiki_top", 20)), log)
    if want("reddit"):
        for sub in cfg.get("reddit_subs", []):
            _run(snap, f"reddit_{sub.lower()}", f"Reddit r/{sub}", lambda s=sub: collect_reddit(s), log)
    if want("imgflip"):
        _run(snap, "imgflip", "Imgflip 템플릿", collect_imgflip, log)
    return snap
