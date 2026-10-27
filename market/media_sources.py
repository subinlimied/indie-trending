"""미디어·밈 트렌드 소스별 수집기 (표준 라이브러리만).

소스: Know Your Meme(뉴스피드 RSS · 확정 엔트리 RSS · 제출 엔트리 RSS · 검색 "tiktok/instagram/reels" 최신순 + 엔트리 페이지)
      · Reddit top(t=day) RSS · YouTube 인기 급상승(API 키가 있을 때만, 60초 이하는 "쇼츠" 표시)
      · Google 트렌드 일간 RSS(KR·US) · 위키백과 일간 조회수 상위(en·ko) · Imgflip 인기 밈 템플릿 100개
      · Threads 키워드 검색(THREADS_ACCESS_TOKEN 이 있을 때만, market/threads_source.py → 스냅샷 최상위 "threads" 키).
소스 하나가 실패해도 나머지는 계속 가고, 스냅샷의 sources[키] 에 status("ok"/"fail"/"skip") 와 error 를 남깁니다.
모든 요청에 연락처가 든 User-Agent 를 붙이고 요청 사이 0.5초 쉽니다. 정치·경제 제외 필터는 분석 단계(media_analyze)에서 겁니다.
"""
import html as H
import json
import os
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from . import http, threads_source

UA = "indie-trending/1.0 (https://github.com/subinlimied/indie-trending)"
HEADERS = {"User-Agent": UA, "Accept": "*/*"}
SLEEP = 0.5

KYM_NEWSFEED = "https://knowyourmeme.com/newsfeed.rss"
KYM_CONFIRMED = "https://knowyourmeme.com/memes.rss"
KYM_SUBMISSIONS = "https://knowyourmeme.com/memes/submissions.rss"
KYM_SEARCH = "https://knowyourmeme.com/search"
TRENDS_RSS = "https://trends.google.com/trending/rss"
WIKI_TOP = "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}.wikipedia/all-access/{y}/{m}/{d}"
REDDIT_RSS = "https://www.reddit.com/r/{sub}/top/.rss?t=day"
IMGFLIP = "https://api.imgflip.com/get_memes"
YOUTUBE = "https://www.googleapis.com/youtube/v3/videos"

# 제목·요약에서 뽑는 플랫폼 단서. (표시 이름, 정규식)
PLATFORMS = [
    ("TikTok", re.compile(r"tik\s?tok", re.I)),
    ("Instagram", re.compile(r"\binstagram\b|\binsta\b|\breels?\b|\big\b", re.I)),
    ("YouTube", re.compile(r"you\s?tube|\byoutuber|\bshorts\b", re.I)),
    ("Twitter/X", re.compile(r"\btwitter\b|\bx\.com\b|\bon X\b|\bX (?:users?|posts?|thread|account)\b|\(X\)", re.I)),
    ("Reddit", re.compile(r"\breddit\b|\br/\w+", re.I)),
    ("Twitch", re.compile(r"\btwitch\b", re.I)),
]
TAG_RX = re.compile(r"<[^>]+>")
IMG_RX = re.compile(r'<img[^>]+src="([^"]+)"', re.I)
WS_RX = re.compile(r"\s+")
GENERIC_SLUGS = {"memes", "cultures", "subcultures", "events", "people", "sites", "confirmed", "submissions"}


def _get(url, params=None, retries=3, timeout=25):
    body = http.get(url, params, headers=HEADERS, retries=retries, timeout=timeout)
    time.sleep(SLEEP)
    return body


def _text(el, tag, ns=None):
    x = el.find(tag, ns) if ns else el.find(tag)
    return (x.text or "").strip() if x is not None and x.text else ""


PUNCT_RX = re.compile(r"\s+([,.;:!?)\]])")


def plain(s, limit=None):
    s = WS_RX.sub(" ", H.unescape(TAG_RX.sub(" ", s or ""))).strip()
    s = PUNCT_RX.sub(r"\1", s).replace("( ", "(").replace("[ ", "[")
    if limit and len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def platform_tags(*texts):
    blob = " ".join(t or "" for t in texts)
    return [name for name, rx in PLATFORMS if rx.search(blob)]


def _iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else ""


def _parse_rfc(s):
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


# ---------- 1. Know Your Meme: RSS 세 개 (뉴스피드 · 확정 · 제출) ----------

def _kym_rss(url, kind, hours, now):
    cutoff = now - timedelta(hours=hours)
    body = _get(url)
    if not body:
        raise RuntimeError("빈 응답")
    root = ET.fromstring(body)
    items = []
    for it in root.iter("item"):
        title = plain(_text(it, "title"))
        link = _text(it, "link")
        pub = _parse_rfc(_text(it, "pubDate"))
        if pub and pub < cutoff:
            continue
        desc_raw = _text(it, "description")
        m = IMG_RX.search(desc_raw)
        summary = plain(desc_raw, 300)
        item = {"kind": kind, "title": title, "url": link, "published": _iso(pub), "summary": summary,
                "platforms": platform_tags(title, summary),
                "status": {"confirmed": "confirmed", "submissions": "submission"}.get(kind, "")}
        if m:
            item["image"] = m.group(1)          # 대표 이미지(RSS 설명의 img). 엔트리 페이지 og:image 가 있으면 enrich 에서 바꿉니다
        items.append(item)
    items.sort(key=lambda x: x["published"], reverse=True)
    return items


def collect_kym_feed(hours=48, now=None):
    return _kym_rss(KYM_NEWSFEED, "newsfeed", hours, now or datetime.now(timezone.utc))


def collect_kym_confirmed(hours=48, now=None):
    return _kym_rss(KYM_CONFIRMED, "confirmed", hours, now or datetime.now(timezone.utc))


def collect_kym_submissions(hours=48, now=None):
    return _kym_rss(KYM_SUBMISSIONS, "submissions", hours, now or datetime.now(timezone.utc))


# ---------- 2. Know Your Meme 검색 (tiktok · instagram · reels 최신순) + 엔트리 페이지 ----------

RESULT_RX = re.compile(r'<a class="result" href="(/memes/[^"]+)">\s*<img[^>]*?alt="([^"]*)"[^>]*?src="([^"]+)"[^>]*>\s*<span>\s*(.*?)\s*</span>', re.S)
META_RX = re.compile(r"<meta property='([^']+)' content='([^']*)'")
STATUS_RX = re.compile(r"<dt>\s*Status\s*</dt>\s*<dd>\s*([^<]+?)\s*</dd>", re.S)
MODIFIED_RX = re.compile(r'"dateModified":"([^"]+)"')
ABOUT_RX = re.compile(r'<h2 id="about">\s*About\s*</h2>(.*?)(?=<h2|<aside|</section|$)', re.S | re.I)
P_RX = re.compile(r"<p[^>]*>(.*?)</p>", re.S)
ABOUT_LEN = 600


def kym_about(body, limit=ABOUT_LEN):
    """엔트리 페이지의 About 문단(영어 원문) 앞부분. 없으면 빈 문자열."""
    m = ABOUT_RX.search(body)
    if not m:
        return ""
    paras = [plain(x) for x in P_RX.findall(m.group(1))]
    text = " ".join(x for x in paras if x)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def kym_entry(url):
    """엔트리 페이지 → 발행·수정 시각, 요약(og:description), About 문단, 이미지, 상태(Confirmed/Submission…)."""
    body = _get(url, retries=2)
    if not body:
        raise RuntimeError("엔트리 페이지 없음")
    meta = dict(META_RX.findall(body))
    m = STATUS_RX.search(body)
    mod = MODIFIED_RX.search(body)
    return {"published": _iso(_parse_iso(meta.get("article:published_time", ""))),
            "modified": _iso(_parse_iso(mod.group(1))) if mod else "",
            "summary": plain(meta.get("og:description", ""), 300), "image": meta.get("og:image", ""),
            "status": (m.group(1).strip().lower() if m else ""), "about": kym_about(body)}


def enrich_kym(snap, keys=("kym_feed", "kym_submissions", "kym_confirmed", "kym_search"), max_fetch=30, log=print):
    """KYM 항목(01·02 대상)의 엔트리 페이지를 한 번씩 열어 about(About 문단)과 빈 발행·상태·이미지를 채웁니다."""
    cache, fetched, ok = {}, 0, 0
    for key in keys:
        for x in (snap["sources"].get(key) or {}).get("items") or []:
            url = x.get("url")
            if not url or "/memes/" not in url:
                continue
            if x.get("about"):          # 검색 경로에서 이미 페이지를 연 항목
                ok += 1
                continue
            if url not in cache:
                if fetched >= max_fetch:
                    continue
                fetched += 1
                try:
                    cache[url] = kym_entry(url)
                except Exception as ex:  # noqa: BLE001
                    cache[url] = {"error": str(ex)[:80]}
            e = cache[url]
            if e.get("about"):
                x["about"] = e["about"]
                ok += 1
            if e.get("image"):
                x["image"] = e["image"]          # 엔트리 페이지 og:image(원본 크기)를 RSS 의 작은 아이콘보다 우선
            for f in ("published", "modified", "status", "summary"):
                if not x.get(f) and e.get(f):
                    x[f] = e[f]
            for f in ("image", "about"):
                if f in x and not x[f]:
                    del x[f]
    log(f"[media] KYM About 문단: 페이지 {fetched}개 열어 {ok}개 항목에 저장")
    return ok


def collect_kym_search(queries, hours=48, per_query=7, max_fetch=12, known=(), now=None):
    """검색 결과(최신순) 상위 per_query 개 중 known 에 없는 엔트리의 페이지를 열어(최대 max_fetch) 발행·수정이 hours 안인 것만."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    seen, cands = set(known), []
    for q in queries:
        body = _get(KYM_SEARCH, {"q": q, "sort": "newest"})
        if not body:
            continue
        for href, alt, img, title in RESULT_RX.findall(body)[:per_query]:
            slug = href.split("/")[2] if href.count("/") >= 2 else ""
            url = "https://knowyourmeme.com" + href
            if not slug or slug in GENERIC_SLUGS or url in seen:
                continue
            seen.add(url)
            c = {"kind": "search", "query": q, "title": plain(title), "url": url}
            if img:
                c["image"] = img
            cands.append(c)
    items, fetched = [], 0
    for c in cands:
        if fetched >= max_fetch:
            break
        fetched += 1
        try:
            e = kym_entry(c["url"])
        except Exception as ex:  # noqa: BLE001  엔트리 하나가 안 열려도 계속
            c["error"] = str(ex)[:80]
            continue
        pub, mod = _parse_iso(e["published"]), _parse_iso(e["modified"])
        if not ((pub and pub >= cutoff) or (mod and mod >= cutoff)):
            continue
        c.update({k: v for k, v in e.items() if v})   # 빈 값(이미지·About 없음)은 키를 넣지 않습니다
        c.setdefault("summary", "")
        c["platforms"] = platform_tags(c["title"], c["summary"], c["query"])
        c["updated_only"] = not (pub and pub >= cutoff)
        items.append(c)
    items.sort(key=lambda x: max(x.get("published", ""), x.get("modified", "")), reverse=True)
    return items


# ---------- 3. Google 트렌드 ----------

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
        items.append({"rank": i, "title": title, "traffic": traffic_num(traffic_raw), "traffic_raw": traffic_raw,
                      "news_title": news_title, "news_url": news_url,
                      "url": news_url or f"https://trends.google.com/trends/explore?geo={geo}&q={quote(title)}",
                      "picture": _text(it, "ht:picture", ns)})
    return items


# ---------- 4. 위키백과 ----------

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
        items.append({"title": name.replace("_", " "), "views": int(a.get("views") or 0), "rank": len(items) + 1,
                      "src_rank": a.get("rank"), "url": f"https://{project}.wikipedia.org/wiki/{quote(name)}"})
        if len(items) >= top:
            break
    return {"day": d.strftime("%Y-%m-%d"), "items": items}


# ---------- 5. Reddit ----------

REDDIT_GAP = 62.0      # 익명 RSS 는 IP 당 약 1분에 1회만 허용됩니다(그 안에 보내면 429)
_reddit_last_ok = [0.0]


def _reddit_get(url):
    """reddit 은 직전 성공 뒤 1분 안의 요청에 429 를 냅니다. 간격을 맞춰 보내고, 429 면 20초씩 쉬며 세 번까지 시도합니다."""
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
    body = _reddit_get(REDDIT_RSS.format(sub=sub))
    if not body:
        raise RuntimeError("빈 응답")
    root = ET.fromstring(body)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    items = []
    for e in root.findall("a:entry", ns):
        title = plain(_text(e, "a:title", ns))
        link = e.find("a:link", ns)
        if not title:
            continue
        items.append({"rank": len(items) + 1, "title": title, "url": link.get("href") if link is not None else ""})
        if len(items) >= top:
            break
    if not items:
        raise RuntimeError("항목 0개 (비공개·빈 서브레딧)")
    return items


# ---------- 6. YouTube 인기 급상승 (키가 있을 때만) ----------

DUR_RX = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def duration_sec(s):
    m = DUR_RX.match(s or "")
    if not m:
        return None
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def collect_youtube(region, key, shorts_max=60):
    data = http.get_json(YOUTUBE, {"part": "snippet,contentDetails,statistics", "chart": "mostPopular", "regionCode": region,
                                   "maxResults": 50, "key": key}, headers=HEADERS, retries=1)   # 지역당 1회, 429·5xx 때만 한 번 더
    time.sleep(SLEEP)
    if not data or "items" not in data:
        raise RuntimeError(f"응답 오류: {json.dumps(data)[:120] if data else '없음'}")
    items = []
    for i, v in enumerate(data["items"], 1):
        sn, cd, st = v.get("snippet") or {}, v.get("contentDetails") or {}, v.get("statistics") or {}
        sec = duration_sec(cd.get("duration"))
        items.append({"rank": i, "id": v.get("id"), "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
                      "views": int(st.get("viewCount") or 0), "likes": int(st.get("likeCount") or 0) if st.get("likeCount") else None,
                      "duration": sec, "shorts": sec is not None and sec <= shorts_max,
                      "url": f"https://www.youtube.com/shorts/{v.get('id')}" if sec is not None and sec <= shorts_max else f"https://www.youtube.com/watch?v={v.get('id')}",
                      "thumb": ((sn.get("thumbnails") or {}).get("medium") or {}).get("url", ""), "published": sn.get("publishedAt", "")})
    return items


# ---------- 7. Imgflip ----------

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
        if isinstance(items, dict):            # 위키 {"day"}
            extra = {k: v for k, v in items.items() if k != "items"}
            items = items["items"]
        snap["sources"][key] = {"label": label, "status": "ok", "count": len(items), "items": items, **extra}
        log(f"[media] {label}: {len(items)}개 · {time.time() - t0:.1f}초")
    except Exception as e:  # noqa: BLE001  소스 하나가 죽어도 나머지는 계속
        msg = f"{type(e).__name__}: {e}"[:200]
        snap["sources"][key] = {"label": label, "status": "fail", "error": msg, "count": 0, "items": []}
        log(f"[media] {label}: 실패 — {msg}")


def _skip(snap, key, label, why, log):
    snap["sources"][key] = {"label": label, "status": "skip", "error": why, "count": 0, "items": []}
    log(f"[media] {label}: 건너뜀 — {why}")


GROUPS = ("kym", "trends", "wiki", "reddit", "youtube", "imgflip", "threads")


def collect(cfg, date, log=print, only=None, base=None):
    """cfg = config.json 의 "media". 반환: 스냅샷 dict (data/media/<date>.json 에 저장).
    only = GROUPS 의 부분집합이면 그 소스만 받아 base(기존 스냅샷)에 합칩니다."""
    hours = cfg.get("kym_hours", 48)
    snap = {"date": date, "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "params": {"kym_hours": hours, "kym_confirmed_hours": cfg.get("kym_confirmed_hours", 168), "kym_queries": cfg.get("kym_queries", []), "wiki_top": cfg.get("wiki_top", 20),
                       "reddit_subs": cfg.get("reddit_subs", [])},
            "sources": dict((base or {}).get("sources") or {})}
    if base and base.get("threads"):       # --only 로 일부만 다시 받을 때 Threads 블록도 유지
        snap["threads"] = base["threads"]

    def want(group):
        return not only or group in only

    if want("kym"):
        _run(snap, "kym_feed", "KYM 뉴스피드", lambda: collect_kym_feed(hours), log)
        _run(snap, "kym_confirmed", "KYM 확정 엔트리", lambda: collect_kym_confirmed(cfg.get("kym_confirmed_hours", 168)), log)   # 확정은 드물어 7일
        _run(snap, "kym_submissions", "KYM 제출 엔트리", lambda: collect_kym_submissions(hours), log)
        known = {x["url"] for k in ("kym_feed", "kym_confirmed", "kym_submissions") for x in snap["sources"].get(k, {}).get("items", [])}
        _run(snap, "kym_search", "KYM 검색 (tiktok·instagram·reels)",
             lambda: collect_kym_search(cfg.get("kym_queries") or ["tiktok", "instagram", "reels"], hours, known=known), log)
        try:
            enrich_kym(snap, log=log)
        except Exception as ex:  # noqa: BLE001  About 수집이 실패해도 항목은 남깁니다
            log(f"[media] KYM About 문단: 실패 — {ex}")
    if want("youtube"):
        key = (os.environ.get("YOUTUBE_API_KEY") or "").strip()
        for region in ("KR", "US"):
            if key:
                _run(snap, f"youtube_{region.lower()}", f"YouTube 인기 {region}", lambda r=region: collect_youtube(r, key), log)
            else:
                _skip(snap, f"youtube_{region.lower()}", f"YouTube 인기 {region}", "YOUTUBE_API_KEY 없음", log)
    if want("trends"):
        for geo in ("KR", "US"):
            _run(snap, f"trends_{geo.lower()}", f"Google 트렌드 {geo}", lambda g=geo: collect_trends(g), log)
    if want("wiki"):
        for proj in ("en", "ko"):
            _run(snap, f"wiki_{proj}", f"위키백과 {proj}", lambda p=proj: collect_wiki(p, date, cfg.get("wiki_top", 20)), log)
    if want("imgflip"):
        _run(snap, "imgflip", "Imgflip 템플릿", collect_imgflip, log)
    if want("threads"):   # 토큰이 없으면 skip 블록만 남습니다. 상태표에는 sources["threads"] 한 줄로 요약
        try:
            snap["threads"] = threads_source.collect(cfg.get("threads") or {}, log)
        except Exception as ex:  # noqa: BLE001
            snap["threads"] = {"status": "fail", "error": threads_source._redact(f"{type(ex).__name__}: {ex}")[:200], "results": {}, "posts": {}, "failed": [], "token": {"present": False}}
            log(f"[media] Threads 키워드: 실패 — {snap['threads']['error']}")
        th = snap["threads"]
        snap["sources"]["threads"] = {"label": "Threads 키워드", "status": th.get("status", "skip"), "error": th.get("error", ""),
                                      "count": len(th.get("posts") or {}), "items": []}
    if want("reddit"):   # 분당 1회라 가장 오래 걸리므로 맨 뒤
        for sub in cfg.get("reddit_subs", []):
            _run(snap, f"reddit_{sub.lower()}", f"Reddit r/{sub}", lambda s=sub: collect_reddit(s), log)
    for k in list(snap["sources"]):        # 더 이상 받지 않는 소스(예: 예전 X 트렌드)는 기존 스냅샷에서도 지웁니다
        if not k.startswith(("kym_", "trends_", "wiki_", "reddit_", "youtube_", "imgflip", "threads")):
            del snap["sources"][k]
    return snap
