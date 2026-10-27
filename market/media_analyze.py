"""미디어·밈 스냅샷 → 리포트 dict (숏폼 중심).

우선순위: ① 틱톡·인스타 트렌드(KYM 네 소스에서 플랫폼 태그 TikTok/Instagram 항목) ①-1 릴스·틱톡 트렌드 정리(유튜브 정리 영상의 제목·설명에서 뽑은 항목, 키 있을 때)
② 새로 등록된 밈(KYM 확정·제출) ③ Threads 키워드 관찰(토큰 있을 때: 키워드별 24시간 게시 수·전날 대비, 새로 뜨는 말, 대표 글) ④ 커뮤니티 베스트(Reddit)
⑤ 유튜브 인기 급상승 Top 10(키 있을 때, 60초 이하는 "쇼츠" 표시) ⑥ 검색 급상승·위키(제외 필터 적용, 접힘)
⑦ 밈 템플릿 변동 ⑧ 게임 교차. "오늘의 트렌드 한 건"은 ①에서 고릅니다.

정치·경제·스포츠·사건사고 제외 필터(config media.exclude_keywords)는 Google 트렌드(제목+관련 뉴스 제목)·위키 제목에 겁니다.
밈 설명(한국어)·인사이트는 ANTHROPIC_API_KEY 가 있을 때 llm_request() 로 요청 본문을 만들고 attach_llm() 으로 리포트에 붙입니다(market/llm.py).
한국어 키워드는 부분 일치, 영어(ASCII) 키워드는 단어 경계 일치(rate 가 pirate 를 거르지 않게). 사람 이름은 못 거르므로 완벽하지 않습니다.
연속 일수는 reports/media/state.json 에 State 로 보관합니다: state["pick"](오늘의 트렌드), state["streaks"][소스][제목].
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

from .common import State, load_snaps, round_no

PLATFORM_ORDER = ["TikTok", "Instagram", "YouTube", "Twitter/X", "Reddit", "Twitch"]
SHORTFORM = ("TikTok", "Instagram")
KYM_KEYS = ("kym_feed", "kym_search", "kym_confirmed", "kym_submissions", "kym")   # "kym" 은 첫 회차(10-22)의 옛 키
KIND_KO = {"newsfeed": "뉴스피드", "search": "검색", "confirmed": "확정 엔트리", "submissions": "제출 엔트리"}


def _src(snap, key):
    return ((snap or {}).get("sources") or {}).get(key) or {"status": "fail", "items": [], "label": key}


def _items(snap, key):
    return _src(snap, key).get("items") or []


# ---------- 제외 필터 ----------

def make_filter(cfg):
    kw = cfg.get("exclude_keywords") or {}
    subs = [k.lower() for k in kw.get("ko", []) if k and not k.isascii()] + [k.lower() for k in kw.get("ko", []) if k and k.isascii() and len(k) < 2]
    words = [k.lower() for k in kw.get("en", []) if k] + [k.lower() for k in kw.get("ko", []) if k and k.isascii() and len(k) >= 2]
    word_rx = [(k, re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])")) for k in words]

    def hit(*texts):
        blob = " ".join(t or "" for t in texts).lower()
        for k in subs:
            if k in blob:
                return k
        for k, rx in word_rx:
            if rx.search(blob):
                return k
        return None
    return hit


# ---------- 게임 이름 사전 (data/steam · data/itch) ----------

WORD_RX = re.compile(r"[A-Za-z0-9가-힣]+")


def _latest_snap(data_dir: Path, platform, date):
    snaps = load_snaps(data_dir, platform, date, days=7)
    return snaps[-1][1] if snaps else None


def game_names(data_dir: Path, date):
    out, seen = [], set()
    steam = _latest_snap(data_dir, "steam", date)
    for appid, a in ((steam or {}).get("apps") or {}).items():
        name = (a.get("name") or "").strip()
        if len(name) >= 3 and name.lower() not in seen:
            seen.add(name.lower())
            out.append((name.lower(), name, "steam", f"https://store.steampowered.com/app/{a.get('appid') or appid}/"))
    itch = _latest_snap(data_dir, "itch", date)
    for g in ((itch or {}).get("games") or {}).values():
        name = (g.get("title") or g.get("name") or "").strip()
        if len(name) >= 3 and name.lower() not in seen:
            seen.add(name.lower())
            out.append((name.lower(), name, "itch", g.get("url") or ""))
    return out


def _allow_partial(lname):
    return len(WORD_RX.findall(lname)) >= 2 or len(lname) >= 8


def match_games(title, games):
    """완전 일치는 항상, 부분 일치는 단어 경계 + 이름이 2단어 이상이거나 8자 이상일 때만."""
    t = (title or "").lower()
    hits = []
    for lname, name, platform, url in games:
        if t == lname:
            hits.append((name, platform, url))
        elif _allow_partial(lname) and re.search(r"(?<![A-Za-z0-9가-힣])" + re.escape(lname) + r"(?![A-Za-z0-9가-힣])", t):
            hits.append((name, platform, url))
    return hits


# ---------- 연속 일수 ----------

def _streaks(state, key, titles, date, prev_date, carry=False):
    all_s = state.d.setdefault("streaks", {})
    cur = all_s.get(key) or {}
    new = {}
    for t in titles:
        rec = cur.get(t)
        if rec and rec.get("date") == date:
            new[t] = rec
        elif rec and prev_date and rec.get("date") == prev_date:
            new[t] = {"n": rec.get("n", 1) + (0 if carry else 1), "date": date}
        else:
            new[t] = {"n": 1, "date": date}
    all_s[key] = new
    return {t: v["n"] for t, v in new.items()}


def _when(x):
    """정렬 기준 = 발행 시각(없으면 수정 시각). 수정만으로 오래된 항목이 위로 오지 않게 합니다."""
    return x.get("published") or x.get("modified") or ""


def _recent(x):
    """48시간 판정 기준 = 발행·수정 중 늦은 쪽(검색으로 찾은 '갱신' 항목을 살리기 위해)."""
    return max(x.get("published") or "", x.get("modified") or "")


def kym_union(snap):
    """KYM 네 소스를 url 로 합칩니다(뉴스피드 > 검색 > 확정 > 제출 순으로 먼저 본 것을 유지, 플랫폼 태그는 합집합)."""
    out = {}
    for key in KYM_KEYS:
        for x in _items(snap, key):
            u = x.get("url")
            if not u:
                continue
            if u in out:
                for p in x.get("platforms") or []:
                    if p not in out[u]["platforms"]:
                        out[u]["platforms"].append(p)
                out[u]["kinds"].append(x.get("kind", key))
                if not out[u].get("status") and x.get("status"):
                    out[u]["status"] = x["status"]
                continue
            out[u] = {**x, "platforms": list(x.get("platforms") or []), "kinds": [x.get("kind", key)]}
    return sorted(out.values(), key=_when, reverse=True)


# ---------- Threads 키워드 관찰 ----------

THREADS_SAMPLE_LEN = 120
HASHTAG_RX = re.compile(r"#([A-Za-z0-9_가-힣]+)")
TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z0-9'’]{2,}|[가-힣]{2,}|[0-9]+[A-Za-z가-힣]+")
URL_RX = re.compile(r"https?://\S+|www\.\S+")
KO_PARTICLES = ("에서는", "으로는", "에게", "에서", "으로", "까지", "부터", "처럼", "이랑", "하고", "한테", "에는", "이나", "밖에",
                "은", "는", "이", "가", "을", "를", "의", "에", "로", "와", "과", "도", "만", "들", "요", "임", "임다")
STOP_EN = set("""the a an and or but if then so of to in on at for from by with without about into over under up down out off as is are was were be been
being am do does did done have has had having will would can could should may might must shall this that these those it its they them their there here
what which who whom whose when where why how all any both each few more most other some such no nor not only own same than too very just also
you your yours we our ours i me my mine he him his she her hers one ones get got like via per vs new now today day days time year years week weeks
really still even ever never always again back much many lot lots thing things way ways make makes made making go going goes went come comes came
see seen say says said know think thought want wants need needs use used using look looks looking take takes took give gives let lets keep keeps
http https com www re ve ll don doesn didn isn aren wasn weren won can't cant dont im ive youre thats whats its""".split())
STOP_KO = set("""그리고 그래서 하지만 그런데 그래도 그러나 또는 또한 그냥 정말 진짜 너무 아주 매우 조금 많이 지금 오늘 내일 어제 이제 아직 계속 이거 저거 그거 이건 저건 그건
이게 저게 그게 여기 저기 거기 우리 저희 당신 여러분 사람 사람들 때문 정도 경우 이번 다음 이런 저런 그런 어떤 무슨 모든 각각 하나 둘 있는 없는 있다 없다 합니다 입니다
했다 한다 하는 하고 해서 해요 했어요 있어요 없어요 같아요 같은 라고 라는 이라고 이라는 그리 아니 아니라 근데 이렇게 저렇게 그렇게 그럼 그러면 바로 혹시 제가 저는
저도 나는 나도 내가 너무나 완전 ㅋㅋ ㅋㅋㅋ ㅎㅎ ㅠㅠ ㅜㅜ 하는데 있는데 없는데 좋아요 좋은 좋다 같다 보다 보고 보면 보는 통해 위해 대해 대한 관련 가능 사용 방법 소개 공유 확인
무료 추천 링크 영상 사진 댓글 팔로우 좋아요 구독 알림 이벤트 모집 참여 문의 안녕하세요 감사합니다 드립니다""".split())


def _strip_particle(w):
    for suf in KO_PARTICLES:
        if len(w) - len(suf) >= 2 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def threads_terms(text, keywords_lc):
    """글 하나 → 등장 용어 집합(해시태그는 # 붙여 구분, 단어는 소문자·조사 제거). 관찰 키워드 자체와 불용어는 뺍니다."""
    out = set()
    text = URL_RX.sub(" ", text or "")
    for h in HASHTAG_RX.findall(text):
        t = h.lower()
        if t not in STOP_EN and t not in STOP_KO and t not in keywords_lc and not t.isdigit():
            out.add("#" + t)
    body = HASHTAG_RX.sub(" ", text)
    for w in TOKEN_RX.findall(body):
        t = w.lower().strip("'’")
        if not t.isascii():
            t = _strip_particle(t)
        if len(t) < (3 if t.isascii() else 2) or t in STOP_EN or t in STOP_KO or t in keywords_lc or t.isdigit():
            continue
        out.add(t)
    return out


def _threads_counts(block, hours):
    """키워드별 RECENT 중 수집 시각 기준 hours 안 게시 수 + 전체 글 용어 집계. block 이 정상이 아니면 (None, {})."""
    if not block or block.get("status") != "ok":
        return None, {}, 0
    posts = block.get("posts") or {}
    try:
        cutoff = (datetime.strptime(block.get("collected_at", ""), "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        cutoff = ""
    counts = {}
    for kw, r in (block.get("results") or {}).items():
        if r.get("error") and not (r.get("top") or r.get("recent")):
            counts[kw] = None
            continue
        counts[kw] = sum(1 for i in r.get("recent") or [] if (posts.get(i) or {}).get("timestamp", "") >= cutoff)
    kws_lc = {k.lower() for k in block.get("keywords") or []}
    kws_lc |= {w for k in list(kws_lc) for w in TOKEN_RX.findall(k)}      # "game jam" 의 game · jam 도 관찰 키워드로 취급해 뺍니다
    terms = {}
    for p in posts.values():
        for t in threads_terms(p.get("text"), kws_lc):
            terms[t] = terms.get(t, 0) + 1
    return counts, terms, len(posts)


def analyze_threads(today, prev, cfg_threads):
    """스냅샷 "threads" 블록 → 리포트 "threads": status · note · token · keywords(게시량·전날 대비·대표 글) · rising(새로 뜨는 말) · 요약."""
    block = today.get("threads") or {}
    tok = {k: v for k, v in (block.get("token") or {}).items() if k != "scopes"}
    out = {"status": block.get("status", "skip"), "error": block.get("error", ""), "token": tok, "note": tok.get("note", ""),
           "keywords": [], "rising": [], "total_posts": 0, "n_ok": 0, "failed": [], "calls": block.get("calls", 0),
           "hours": (block.get("params") or {}).get("hours", 24), "limit": (block.get("params") or {}).get("limit", 100), "compared": False}
    if out["status"] == "skip":
        out["note"] = out["note"] or "Threads: 토큰 없음"
        return out
    if out["status"] != "ok":
        return out
    hours = out["hours"]
    counts, terms, n_posts = _threads_counts(block, hours)
    prev_block = (prev or {}).get("threads") if prev else None
    prev_counts, prev_terms, _ = _threads_counts(prev_block, hours)
    out["compared"] = prev_counts is not None
    posts = block.get("posts") or {}
    rows = []
    for kw in block.get("keywords") or []:
        r = (block.get("results") or {}).get(kw) or {}
        n = counts.get(kw)
        if n is None:
            out["failed"].append({"keyword": kw, "error": r.get("error", "")})
            continue
        pn = (prev_counts or {}).get(kw) if prev_counts else None
        delta = (n - pn) if pn is not None else None
        lift = round(n / pn, 2) if pn else (None if pn is None else (None if n == 0 else 9.99))
        sample = []
        seen = set()
        for i in list(r.get("top") or []) + list(r.get("recent") or []):
            p = posts.get(i)
            if not p or i in seen or p.get("is_reply") or not p.get("text"):
                continue
            seen.add(i)
            text = p["text"] if len(p["text"]) <= THREADS_SAMPLE_LEN else p["text"][: THREADS_SAMPLE_LEN - 1].rstrip() + "…"
            sample.append({"id": i, "text": text, "username": p.get("username", ""), "url": p.get("permalink", ""),
                           "timestamp": p.get("timestamp", ""), "media_type": p.get("media_type", ""), "from": "top" if i in (r.get("top") or []) else "recent"})
            if len(sample) >= 3:
                break
        rows.append({"keyword": kw, "recent": n, "prev": pn, "delta": delta, "lift": lift, "saturated": n >= out["limit"],
                     "top_n": len(r.get("top") or []), "recent_n": len(r.get("recent") or []), "sample": sample})
    rows.sort(key=lambda x: (-x["recent"], -(x["delta"] or 0), x["keyword"]))
    out["keywords"] = rows
    out["n_ok"] = len(rows)
    out["total_posts"] = n_posts
    out["recent_total"] = sum(x["recent"] for x in rows)
    rising = []
    for t, n in terms.items():
        if n < 3:
            continue
        pn = (prev_terms or {}).get(t, 0) if prev_counts is not None else None
        rising.append({"term": t, "n": n, "prev": pn, "delta": (n - pn) if pn is not None else None})
    rising.sort(key=lambda x: (-(x["delta"] if x["delta"] is not None else x["n"]), -x["n"], x["term"]))
    out["rising"] = rising[:15]
    out["top_terms"] = sorted(((t, n) for t, n in terms.items() if n >= 2), key=lambda x: (-x[1], x[0]))[:15]
    return out


# ---------- 릴스·틱톡 트렌드 정리 (유튜브 정리 영상의 제목·설명 → 트렌드 항목) ----------

REELS_LIST_RX = re.compile(r"^\s*(?:\d{1,2}:\d{2}(?::\d{2})?\s*[-–—:|]?|\(?\d{1,2}[.)\]:](?!\d)|[-•*▪◾►▶➤✔✅☑️①②③④⑤⑥⑦⑧⑨⑩])\s*(.+?)\s*$")
REELS_TS_INLINE_RX = re.compile(r"(?:^|\s)\d{1,2}:\d{2}(?::\d{2})?(?:\s|$)")
REELS_KEY_EN = ("sound", "sounds", "audio", "song", "songs", "music", "challenge", "dance", "dances", "filter", "filters", "transition", "transitions",
                "effect", "effects", "template", "templates", "trend", "trends", "edit", "edits", "meme", "memes", "remix", "lipsync")
REELS_KEY_KO = ("챌린지", "댄스", "필터", "트랜지션", "음원", "사운드", "템플릿", "효과", "밈", "편집", "트렌드", "노래", "포즈", "안무")
REELS_PHRASE_EN_RX = re.compile(r"((?:[A-Za-z0-9'’]+\s+){1,2}(?:" + "|".join(REELS_KEY_EN) + r"))(?![A-Za-z0-9])", re.I)   # 앞 단어 2개까지(문장 조각 방지)
REELS_PHRASE_KO_RX = re.compile(r"([가-힣A-Za-z0-9'’]+(?:\s[가-힣A-Za-z0-9'’]+)?\s?(?:" + "|".join(REELS_KEY_KO) + r"))(?![가-힣])")   # 앞 단어 1개까지(문장 조각 방지)
REELS_GENERIC = set("""this that the a an of for and or to in on with at by from your my our you we is are be new best top latest hot biggest current popular
viral trending trend trends week weekly weeks month monthly today tonight daily now all every more most other another same next last first ft feat
hottest funniest funny which what these those here there right some have has had discover get got make making want need use using check out watch see find learn try
their its about into than can will who how where when why also just only even very really still
tiktok tik tok instagram insta ig reels reel shorts short youtube video videos ep episode part vol compilation list roundup recap wrap tutorial
fyp foryou foryoupage explore explorepage instagood reelsinstagram reelsvideo reelitfeelit viralvideo viralreels tiktokviral youtubeshorts
2024 2025 2026 2027 october november december january february march april may june july august september oct nov dec jan feb mar apr jun jul aug sep sept
이번주 이번 주 금주 주간 매주 오늘 요즘 최신 인기 유행 핫한 뜨는 뜬 모음 정리 총정리 추천 소개 베스트 탑 신상 지금 틱톡 릴스 인스타 인스타그램 쇼츠 유튜브 영상 편 주차
챌린지 댄스 필터 트랜지션 음원 사운드 템플릿 효과 밈 편집 트렌드 노래 포즈 안무""".split()) | set(REELS_KEY_EN)
REELS_PROMO = ("구독", "subscribe", "link in bio", "linkinbio", "follow", "팔로우", "좋아요", "like and", "like &", "comment", "댓글", "share this", "공유해",
               "discount", "coupon", "promo", "use code", "% off", "sponsor", "협찬", "광고", "제휴", "business", "contact", "문의", "email", "e-mail", "이메일", "gmail", "http", "www.", ".com",
               "intro", "outro", "인트로", "아웃트로", "오프닝", "마무리", "thanks for watching", "시청해", "patreon", "merch", "shop", "download", "다운로드",
               "join", "membership", "멤버십", "channel", "채널", "playlist", "재생목록", "credit", "copyright", "저작권", "disclaimer", "timestamps", "타임라인",
               "@", "instagram.com", "tiktok.com", "youtube.com", "youtu.be", "bit.ly", "linktr")
REELS_EMOJI_RX = re.compile(r"[\U0001F000-\U0001FAFF☀-➿️‍]+")
REELS_PAREN_RX = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|【[^】]*】")
# "정리 영상" 판정: 제목에 트렌드·사운드·챌린지 계열 말이 있어야 하고, 리믹스·매시업·DJ 는 음악 모음이라 제외, 제목 해시태그 4개 이상은 스팸으로 제외
REELS_TITLE_RX = re.compile(r"trend|trending|sound|audio|challenge|viral|밈|meme|트렌드|챌린지|음원|사운드|유행|모음|정리|필터|filter|transition|트랜지션", re.I)
REELS_TITLE_EXCL_RX = re.compile(r"\bremix|mashup|\bdj\b|nonstop|\bbass\b|party music|리믹스|매시업|디제이", re.I)
REELS_TITLE_MAX_TAGS = 3
REELS_WORD_RX = re.compile(r"[a-z0-9'’]+|[가-힣]+")
REELS_TERM_LEN = 48
REELS_KIND_RANK = {"list": 0, "phrase": 1, "hashtag": 2}


def _reels_clean(text):
    """줄 하나 → 표시용 항목 문자열. 괄호·따옴표·이모지·해시태그 기호·꼬리 문장부호를 떼고 공백을 정리합니다(단어 속 아포스트로피는 둡니다)."""
    t = URL_RX.sub(" ", text or "")
    t = REELS_EMOJI_RX.sub(" ", t)
    t = REELS_PAREN_RX.sub(" ", t)             # "(Peak, 334K Reels)" 같은 괄호 설명은 통째로
    t = re.sub(r"[\"“”«»\[\]()【】「」『』]", " ", t)
    t = t.replace("#", " ")
    t = re.sub(r"\s+", " ", t).strip(" -–—:|·.,;!?~>'‘’")
    return t


def _reels_key(t):
    return re.sub(r"[^a-z0-9가-힣]+", " ", t.lower().replace("'", "").replace("’", "")).strip()


def _generic_concat(w, _memo={}):
    """해시태그처럼 붙어 쓴 단어가 일반어만으로 쪼개지는지(reelstrends = reels + trends)."""
    if w in _memo:
        return _memo[w]
    n = len(w)
    ok = [False] * (n + 1)
    ok[0] = True
    for i in range(1, n + 1):
        for j in range(max(0, i - 14), i):
            if ok[j] and i - j >= 2 and w[j:i] in REELS_GENERIC:
                ok[i] = True
                break
    _memo[w] = ok[n]
    return ok[n]


def _reels_ok(t):
    """항목으로 쓸 만한가: 2~48자, 홍보·연락처·구간 안내 문구가 아니고, 일반어(이번주·trending·reels…)만으로 된 구절이 아닐 것."""
    if not t or len(t) < 2 or len(t) > REELS_TERM_LEN:
        return False
    lo = t.lower()
    if any(w in lo for w in REELS_PROMO):
        return False
    words = REELS_WORD_RX.findall(lo)
    if not words or all(w in REELS_GENERIC or w.isdigit() or _generic_concat(w) for w in words):
        return False
    return True


def _trim_generic_head(t):
    """구절 앞의 일반어(by · this week · the …)를 떼어 'by Charli XCX dance' → 'Charli XCX dance'."""
    parts = t.split(" ")
    while len(parts) > 1 and (parts[0].lower().replace("'", "") in REELS_GENERIC or parts[0].isdigit()):
        parts.pop(0)
    return " ".join(parts)


def reels_roundup(video):
    """이 영상이 '트렌드 정리 영상'인가 → (True/False, 이유). 제목 키워드 · 해시태그 스팸 · 리믹스/매시업 제외 · 길이 0(라이브·미공개) 제외."""
    title = video.get("title") or ""
    if title.count("#") > REELS_TITLE_MAX_TAGS:
        return False, "제목 해시태그 스팸"
    if REELS_TITLE_EXCL_RX.search(title):
        return False, "리믹스·매시업"
    if not REELS_TITLE_RX.search(HASHTAG_RX.sub(" ", title)):
        return False, "제목에 트렌드·사운드·챌린지 없음"
    if not video.get("duration"):
        return False, "길이 없음"
    return True, ""


def reels_items(video):
    """영상 하나 → {키: (표시 문자열, 종류)}. 종류: list(설명의 번호·글머리·타임스탬프 줄) · phrase(sound/challenge/챌린지… 가 붙은 구절) · hashtag."""
    out = {}
    desc = video.get("description") or ""
    for line in desc.splitlines():
        m = REELS_LIST_RX.match(line)
        if not m:
            continue
        t = _reels_clean(m.group(1))
        t = REELS_TS_INLINE_RX.sub(" ", t).strip()
        if len(t) > REELS_TERM_LEN:
            t = t[:REELS_TERM_LEN].rsplit(" ", 1)[0].strip() if " " in t[:REELS_TERM_LEN] else t[:REELS_TERM_LEN]
        if _reels_ok(t):
            out.setdefault(_reels_key(t), (t, "list"))
    blob = (video.get("title") or "") + "\n" + desc + "\n" + " ".join("#" + x for x in video.get("tags") or [] if " " not in x)
    plain_blob = URL_RX.sub(" ", HASHTAG_RX.sub(" ", blob))
    for rx in (REELS_PHRASE_EN_RX, REELS_PHRASE_KO_RX):
        for ph in rx.findall(plain_blob):
            t = _trim_generic_head(_reels_clean(ph))
            k = _reels_key(t)
            if k and k not in out and _reels_ok(t) and len(k.split()) >= 2:
                out[k] = (t, "phrase")
    for h in HASHTAG_RX.findall(blob):
        t = h.strip("_")
        k = _reels_key(t)
        if k and k not in out and not t.isdigit() and _reels_ok(t):
            out[k] = ("#" + t, "hashtag")
    return out


def _reels_merge(agg):
    """비슷한 항목 합치기: 단어 집합이 다른 항목의 부분집합이면('Apple dance' ⊆ 'Apple by Charli XCX dance') 큰 쪽으로,
    해시태그는 띄어쓰기를 뺀 다른 항목 키에 들어 있으면('#mobwife' ⊆ 'mob wife aesthetic transition') 그쪽으로 합칩니다. 영상 집합을 합쳐 n 을 다시 셉니다."""
    items = list(agg.values())
    for a in items:
        a["_w"] = set(a["key"].split())
        a["_ns"] = a["key"].replace(" ", "")
    alive = {a["key"]: a for a in items}
    for a in sorted(items, key=lambda x: (len(x["_w"]), len(x["key"]))):
        if a["key"] not in alive:
            continue
        small = len(a["_w"]) == 1 and len(a["_ns"]) < 5
        best = None
        for b in alive.values():
            if b is a or len(b["_w"]) < len(a["_w"]):
                continue
            if a["kind"] == "hashtag" and len(a["_ns"]) >= (5 if a["_ns"].isascii() else 4) and a["_ns"] in b["_ns"] and b["_ns"] != a["_ns"]:
                hit = True
            elif not small and a["_w"] <= b["_w"] and (b["_w"] != a["_w"] or b["kind"] != "hashtag"):
                hit = True
            else:
                hit = False
            if hit and (best is None or (len(b["_vids"]), len(b["_w"])) > (len(best["_vids"]), len(best["_w"]))):
                best = b
        if best is not None:
            best["_vids"] |= a["_vids"]
            if REELS_KIND_RANK.get(a["kind"], 9) < REELS_KIND_RANK.get(best["kind"], 9):
                best["term"], best["kind"] = a["term"], a["kind"]
            del alive[a["key"]]
    return list(alive.values())


def _reels_rank(block, top_items, videos=None):
    """블록(또는 videos dict) → (항목 목록[{key, term, kind, n, channels, views, videos}], 영상 수).
    n = 그 항목이 나온 **서로 다른 채널 수**(한 채널의 반복 문구·해시태그 도배가 상위에 오지 않게), 비슷한 항목은 합침.
    순서: 채널 수 → (1채널짜리는 영상을 조회수순으로 돌아가며 하나씩) → 종류(목록 줄 > 구절 > 해시태그) → 조회수."""
    videos = videos if videos is not None else ((block or {}).get("videos") or {})
    agg = {}
    order = sorted(videos, key=lambda i: -(videos[i].get("views") or 0))
    for vid in order:
        v = videos[vid]
        for k, (term, kind) in reels_items(v).items():
            a = agg.setdefault(k, {"key": k, "term": term, "kind": kind, "_vids": set()})
            a["_vids"].add(vid)
            if REELS_KIND_RANK.get(kind, 9) < REELS_KIND_RANK.get(a["kind"], 9):      # 사람이 적은 목록 줄 형태를 표시명으로 우선
                a["term"], a["kind"] = term, kind
    pos = {vid: i for i, vid in enumerate(order)}
    rows = []
    for a in _reels_merge(agg):
        vids = sorted(a["_vids"], key=lambda i: pos.get(i, 9999))
        chans = {videos[i].get("channel_id") or videos[i].get("channel") or i for i in vids}
        rows.append({"key": a["key"], "term": a["term"], "kind": a["kind"], "n": len(chans), "n_videos": len(vids),
                     "views": sum(int(videos[i].get("views") or 0) for i in vids), "videos": vids[:3]})
    rows.sort(key=lambda a: (-a["n"], REELS_KIND_RANK.get(a["kind"], 9), -a["views"], a["term"].lower()))
    multi = [a for a in rows if a["n"] >= 2]
    single = [a for a in rows if a["n"] < 2]
    by_video = {}
    for a in single:
        by_video.setdefault(a["videos"][0] if a["videos"] else "", []).append(a)
    lanes = [by_video[i] for i in order if i in by_video]
    mixed = []
    while lanes:
        for lane in lanes:
            mixed.append(lane.pop(0))
        lanes = [ln for ln in lanes if ln]
    return (multi + mixed)[:top_items], len(videos)


def _reels_pick(block, per_channel):
    """정리 영상만 남기고(reels_roundup) 조회수순. 반환 ({id: video}, 제외 사유 집계, 채널당 per_channel 편으로 자른 순서 목록)."""
    allv = (block or {}).get("videos") or {}
    kept, dropped = {}, {}
    for i, v in allv.items():
        ok, why = reels_roundup(v)
        if ok:
            kept[i] = v
        else:
            dropped[why] = dropped.get(why, 0) + 1
    order = sorted(kept.values(), key=lambda v: (-(v.get("views") or 0), v.get("published") or ""))
    seen, ranked = {}, []
    for v in order:
        ch = v.get("channel_id") or v.get("channel") or ""
        seen[ch] = seen.get(ch, 0) + 1
        if seen[ch] <= per_channel:
            ranked.append(v)
    return kept, dropped, ranked


def analyze_reels(today, prev, cfg_reels):
    """스냅샷 "reels" 블록 → 리포트 "reels": status · note · videos(조회수순 Top, NEW) · items(트렌드 항목, 등장 영상 수순, NEW) · 호출·유닛 요약."""
    block = today.get("reels") or {}
    top_videos, top_items, per_channel = int(cfg_reels.get("top_videos", 10)), int(cfg_reels.get("top_items", 30)), int(cfg_reels.get("per_channel", 2))
    calls = block.get("calls") or {}
    out = {"status": block.get("status", "skip"), "error": block.get("error", ""), "note": "", "videos": [], "items": [], "n_videos": 0, "n_items": 0,
           "n_found": len(block.get("videos") or {}), "n_roundup": 0, "dropped": {},
           "queries": [{"q": r.get("q", ""), "region": r.get("region", ""), "duration": r.get("duration", "any"), "n": r.get("n", 0), "error": r.get("error", "")} for r in block.get("queries") or []],
           "n_queries_ok": sum(1 for r in block.get("queries") or [] if not r.get("error")),
           "calls": {"search": calls.get("search", 0), "videos": calls.get("videos", 0), "units": calls.get("units", 0)},
           "days": (block.get("params") or {}).get("days", cfg_reels.get("days", 14)), "order": (block.get("params") or {}).get("order", ""),
           "published_after": block.get("published_after", ""), "compared": False}
    if out["status"] == "skip":
        if not block:
            out["note"] = "릴스·틱톡 정리: 이 스냅샷에는 없음 (collect --only reels 로 추가)"
        elif "YOUTUBE_API_KEY" in (out["error"] or ""):
            out["note"] = "릴스·틱톡 정리: YouTube 키 없음"
        else:
            out["note"] = f"릴스·틱톡 정리: 건너뜀 ({out['error']})"
        return out
    if out["status"] != "ok":
        out["note"] = f"릴스·틱톡 정리: 수집 실패 ({out['error'][:80]})"
        return out
    prev_block = (prev or {}).get("reels") if prev else None
    prev_ok = bool(prev_block) and prev_block.get("status") == "ok"
    out["compared"] = prev_ok
    prev_videos = set((prev_block.get("videos") or {}).keys()) if prev_ok else set()
    hit = {}
    for r in block.get("queries") or []:
        for i in r.get("ids") or []:
            hit.setdefault(i, []).append(r.get("q", ""))
    kept, dropped, ranked = _reels_pick(block, per_channel)
    out["n_videos"] = len(ranked)
    out["n_roundup"] = len(kept)
    out["dropped"] = dropped
    out["videos"] = [{"rank": i, "id": v.get("id"), "title": v.get("title", ""), "channel": v.get("channel", ""), "views": v.get("views", 0), "likes": v.get("likes"),
                      "duration": v.get("duration"), "shorts": bool(v.get("shorts")), "published": v.get("published", ""), "url": v.get("url", ""), "thumb": v.get("thumb", ""),
                      "query": (hit.get(v.get("id")) or [""])[0], "queries": hit.get(v.get("id"), [])[:3], "new": prev_ok and v.get("id") not in prev_videos}
                     for i, v in enumerate(ranked[:top_videos], 1)]
    items, _ = _reels_rank(block, top_items, videos={v["id"]: v for v in ranked})
    prev_kept = _reels_pick(prev_block, per_channel)[2] if prev_ok else []
    prev_items = {a["key"]: a["n"] for a in _reels_rank(prev_block, 10_000, videos={v["id"]: v for v in prev_kept})[0]} if prev_ok else {}
    for a in items:
        pn = prev_items.get(a["key"]) if prev_ok else None
        a["prev"] = pn
        a["new"] = prev_ok and pn is None
        a["lift"] = (round(a["n"] / pn, 2) if pn else None)
    out["items"] = items
    out["n_items"] = len(items)
    return out


# ---------- 분석 ----------

def analyze(cfg, date, data_dir: Path, reports_dir: Path):
    snaps = load_snaps(data_dir, "media", date, days=35)
    today = next((s for d, s in snaps if d == date), None)
    if today is None:
        raise FileNotFoundError(f"data/media/{date}.json 없음")
    prior = [(d, s) for d, s in snaps if d < date]
    prev_date, prev = prior[-1] if prior else (None, None)
    rnd = round_no(data_dir, "media", date)
    state = State(reports_dir / "media" / "state.json")
    hit = make_filter(cfg)
    trends_top, imgflip_top = cfg.get("trends_top", 10), cfg.get("imgflip_top", 30)
    sources = today.get("sources") or {}
    filtered = {}

    # ① 틱톡·인스타 트렌드 + 플랫폼 집계
    kym_all = kym_union(today)
    prev_urls = {x["url"] for x in kym_union(prev)} if prev else set()
    for x in kym_all:
        x["new"] = bool(prev) and x["url"] not in prev_urls
    hours = (today.get("params") or {}).get("kym_hours", 48)
    try:
        cutoff = (datetime.strptime(today.get("collected_at", ""), "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        cutoff = ""
    shortform = [x for x in kym_all if any(p in SHORTFORM for p in x["platforms"]) and (not _recent(x) or _recent(x) >= cutoff)]
    counts = {}
    for x in kym_all:
        for p in x["platforms"]:
            counts[p] = counts.get(p, 0) + 1
    platform_counts = [(p, counts[p]) for p in PLATFORM_ORDER if p in counts]
    platform_counts += sorted(((p, n) for p, n in counts.items() if p not in PLATFORM_ORDER), key=lambda x: -x[1])

    pick = None
    for want in ("TikTok", "Instagram", None):
        cand = [x for x in shortform if want is None or want in x["platforms"]] or ([x for x in kym_all] if want is None else [])
        if cand:
            x = cand[0]
            n, since = state.bump("pick", x["url"], date, prev_date)
            reason = {"TikTok": "KYM 최신 TikTok 항목", "Instagram": "KYM 최신 Instagram 항목"}.get(want, "KYM 최신 항목 (틱톡·인스타 태그 없음)")
            pick = {**x, "streak": n, "since": since, "reason": reason}
            break

    # ② 새로 등록된 밈 (확정 · 제출)
    new_memes = [x for x in kym_all if any(k in ("confirmed", "submissions") for k in x["kinds"])]
    new_memes.sort(key=lambda x: (0 if x.get("status") == "confirmed" else 1, -(_when(x) > "")))
    new_memes.sort(key=_when, reverse=True)

    # ③ Reddit
    reddit = []
    for sub in (today.get("params") or {}).get("reddit_subs") or []:
        s = _src(today, f"reddit_{sub.lower()}")
        reddit.append({"sub": sub, "status": s.get("status"), "error": s.get("error", ""), "items": (s.get("items") or [])[:8]})

    # ③-1 Threads 키워드 관찰 (토큰 있을 때만; 없으면 status "skip" + 메모)
    threads = analyze_threads(today, prev, cfg.get("threads") or {})

    # ①-1 릴스·틱톡 트렌드 정리 (YouTube 키 있을 때만; 없으면 status "skip" + "YouTube 키 없음" 메모)
    reels = analyze_reels(today, prev, cfg.get("reels") or {})

    # ④ 유튜브 인기 급상승 Top 10 (60초 이하는 shorts=True)
    youtube = {}
    for region in ("KR", "US"):
        key = f"youtube_{region.lower()}"
        s = _src(today, key)
        items = s.get("items") or []
        youtube[region] = {"status": s.get("status"), "error": s.get("error", ""), "items": items[:10], "total": len(items),
                           "shorts": sum(1 for v in items if v.get("shorts"))}

    # ⑤ 검색 급상승 · 위키 (제외 필터)
    trends = {}
    for geo in ("KR", "US"):
        key = f"trends_{geo.lower()}"
        kept, dropped = [], 0
        for x in _items(today, key):
            k = hit(x["title"], x.get("news_title"))
            if k:
                dropped += 1
                continue
            kept.append({**x, "rank": len(kept) + 1})
        st = _streaks(state, key, [x["title"] for x in kept], date, prev_date)
        trends[geo] = [{**x, "days": st.get(x["title"], 1)} for x in kept[:trends_top]]
        filtered[key] = dropped
    wiki = {}
    for proj in ("en", "ko"):
        key = f"wiki_{proj}"
        day, prev_day = _src(today, key).get("day", ""), _src(prev, key).get("day", "") if prev else ""
        same = bool(day) and day == prev_day
        prev_rank = {x["title"]: x["rank"] for x in _items(prev, key)} if prev and not same else {}
        kept, dropped = [], 0
        for x in _items(today, key):
            if hit(x["title"]):
                dropped += 1
                continue
            kept.append(x)
        st = _streaks(state, key, [x["title"] for x in kept], date, prev_date, carry=same)
        wiki[proj] = [{**x, "days": st.get(x["title"], 1), "prev_rank": prev_rank.get(x["title"])} for x in kept]
        wiki[f"{proj}_day"], wiki[f"{proj}_same"] = day, same
        filtered[key] = dropped

    # ⑥ Imgflip 순위 변동
    cur_all = _items(today, "imgflip")
    prev_all = _items(prev, "imgflip") if prev else []
    prev_rank = {x["id"]: x["rank"] for x in prev_all}
    prev_name = {x["id"]: x["name"] for x in prev_all}
    cur_ids = {x["id"] for x in cur_all}
    imgflip_items = [{**x, "prev_rank": prev_rank.get(x["id"]), "delta": (prev_rank[x["id"]] - x["rank"]) if x["id"] in prev_rank else None,
                      "new": bool(prev) and x["id"] not in prev_rank} for x in cur_all[:imgflip_top]]
    entered = [x for x in cur_all if prev and x["id"] not in prev_rank]
    exited = [{"id": i, "name": prev_name[i], "prev_rank": r} for i, r in sorted(prev_rank.items(), key=lambda kv: kv[1]) if i not in cur_ids]
    movers = sorted([x for x in imgflip_items if x["delta"]], key=lambda x: (-abs(x["delta"]), x["rank"]))
    imgflip = {"items": imgflip_items, "entered": entered, "exited": exited, "movers": movers[:10], "total": len(cur_all),
               "compared": bool(prev) and bool(prev_all)}

    # ⑦ 게임 ↔ 밈 교차 (검색 · 위키 · Reddit · 유튜브 · 숏폼 제목)
    games = game_names(data_dir, date)
    cross, seen = [], set()

    def _cross(title, source, url):
        for name, platform, gurl in match_games(title, games):
            k = (name.lower(), source)
            if k in seen:
                continue
            seen.add(k)
            cross.append({"term": title, "source": source, "game": name, "platform": platform, "game_url": gurl, "url": url})

    for x in shortform:
        _cross(x["title"], "KYM", x["url"])
    for geo in ("KR", "US"):
        for x in trends[geo]:
            _cross(x["title"], f"검색 {geo}", x.get("url", ""))
    for proj in ("en", "ko"):
        for x in wiki[proj]:
            _cross(x["title"], f"위키 {proj}", x.get("url", ""))
    for r in reddit:
        for x in r["items"]:
            _cross(x["title"], f"r/{r['sub']}", x.get("url", ""))
    for region in ("KR", "US"):
        for v in youtube[region]["items"]:
            _cross(v["title"], f"유튜브 {region}", v.get("url", ""))
    for row in threads["keywords"]:
        for sp in row["sample"]:
            _cross(sp["text"], f"Threads · {row['keyword']}", sp.get("url", ""))
    for v in reels["videos"]:
        _cross(v["title"], "릴스·틱톡 정리", v.get("url", ""))

    # 수집 상태
    status_rows = []
    for key, s in sources.items():
        status_rows.append({"key": key, "label": s.get("label", key), "status": s.get("status"), "count": s.get("count", 0),
                            "error": s.get("error", ""), "filtered": filtered.get(key, 0)})
    ok = sum(1 for s in status_rows if s["status"] == "ok")
    skipped = sum(1 for s in status_rows if s["status"] == "skip")
    failed = [s["label"] for s in status_rows if s["status"] == "fail"]
    reddit_ok = [r["sub"] for r in reddit if r["status"] == "ok"]
    n_filtered = sum(filtered.values())
    collect_line = (f"소스 {ok}/{len(status_rows) - skipped} 정상" + (f" · 건너뜀 {skipped}" if skipped else "")
                    + f" · KYM {len(kym_all)}건(틱톡·인스타 {len(shortform)}) · 새 밈 {len(new_memes)} · Reddit {len(reddit_ok)}/{len(reddit)}"
                    + f" · 검색 {len(trends['KR'])}/{len(trends['US'])} · 위키 {len(wiki['en'])}/{len(wiki['ko'])}"
                    + f" · 제외 필터 {n_filtered}건")
    if failed:
        collect_line += " · 실패: " + ", ".join(failed)
    if threads["status"] == "ok":
        collect_line += f" · Threads {threads['n_ok']}개 키워드 · 글 {threads['total_posts']}건"
    if threads.get("note"):
        collect_line += f" · {threads['note']}"
    if reels["status"] == "ok":
        collect_line += f" · 릴스 정리 영상 {reels['n_videos']}개 · 항목 {reels['n_items']}"
    elif reels.get("note"):
        collect_line += f" · {reels['note']}"
    state.save()
    status = [["회차", f"{rnd}회차"], ["비교 대상", f"{prev_date} · 1일치" if prev_date else "없음"],
              ["틱톡·인스타", f"{len(shortform)}건 / KYM {len(kym_all)}"], ["새 밈", f"{len(new_memes)}건"],
              ["제외 필터", f"{n_filtered}건"], ["게임 교차", f"{len(cross)}건"],
              ["Threads", (f"{threads['n_ok']}개 키워드 · 24시간 {threads.get('recent_total', 0)}건" if threads["status"] == "ok"
                           else ("토큰 없음" if threads["status"] == "skip" else "실패"))],
              ["릴스·틱톡 정리", (f"영상 {reels['n_videos']}개 · 항목 {reels['n_items']}" if reels["status"] == "ok"
                             else ("YouTube 키 없음" if reels["status"] == "skip" else "실패"))],
              ["수집", (today.get("collected_at") or "").replace("T", " ").replace("Z", " UTC")]]
    return {
        "kind": "media", "platform": "media", "platform_ko": "미디어·밈", "date": date, "round": rnd, "prev_date": prev_date,
        "status": status, "collect_line": collect_line,
        "basis_line": (f"KYM 뉴스피드·확정·제출 RSS + 검색 tiktok/instagram/reels (최근 {hours}시간) · Reddit top(t=day) 8개 × {len(reddit)}개 서브레딧 · "
                       f"YouTube 인기 급상승 KR·US Top 10(60초 이하는 쇼츠 표시, 키 있을 때) · Google 트렌드 일간 KR·US · 위키백과 조회수 상위 en·ko · "
                       f"릴스·틱톡 트렌드 정리 = YouTube 검색 {len(reels['queries']) or len((cfg.get('reels') or {}).get('queries') or [])}개 검색어 × 최근 {reels['days']}일 조회수순 10개(키 있을 때, 제목·설명의 목록 줄·해시태그·챌린지/사운드 구절을 항목으로) · "
                       f"Imgflip 인기 템플릿 100개 중 상위 {imgflip_top} · Threads 키워드 검색 TOP·RECENT 각 {threads['limit']}건(토큰 있을 때, 24시간 게시 수는 RECENT 기준이라 {threads['limit']}건에서 포화) · "
                       f"제외 필터 = config media.exclude_keywords (정치·경제·스포츠·사건사고, 사람 이름은 못 거름) · "
                       f"게임 교차 = Steam·itch 스냅샷 게임 이름과 대조"),
        "pick": pick, "platform_counts": platform_counts, "shortform": shortform, "kym_all": kym_all,
        "kym_new": sum(1 for x in kym_all if x["new"]), "new_memes": new_memes, "reddit": reddit, "youtube": youtube,
        "trends": trends, "wiki": wiki, "imgflip": imgflip, "cross": cross, "filtered": filtered, "sources": status_rows,
        "threads": threads, "reels": reels,
    }


# ---------- 밈 설명(한국어) · 인사이트: Claude 요청 본문과 결합 ----------

LLM_SYSTEM = """당신은 밈·숏폼 트렌드를 게임 제작자에게 설명하는 한국어 편집자입니다. 독자는 모바일 게임 UI 디자이너이며 혼자 만들 인디게임과 콘텐츠 소재를 찾고 있습니다.

한국어 문장 규칙:
- 조사와 어미를 생략하지 않고 완결된 문장으로 씁니다. 명사만 나열하지 않습니다.
- 엠대시(—)를 쓰지 않습니다. 과장하거나 단정하지 않고, 추측은 "~로 보입니다"처럼 추측임을 밝힙니다.
- 밈 이름, 플랫폼 이름, 계정 이름은 원어 그대로 둡니다.
- 숫자를 반복해서 나열하지 않습니다.
- 각 밈 설명(ko_what)은 두세 문장으로, 무엇인지·어디서 시작됐는지·어떻게 쓰이는지를 적습니다. 자료에 없는 사실을 지어내지 않습니다.
- ko_idea 는 게임이나 콘텐츠 소재로 쓸 아이디어 한 문장입니다.
- insight 는 리포트 전체를 보고 쓰는 한 문단(4~6문장)입니다. 대중문화·숏폼·과거 성공작의 계보와 연결하고, 추측은 추측이라고 표시합니다."""

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "memes": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "ko_what": {"type": "string"}, "ko_idea": {"type": "string"}},
            "required": ["id", "ko_what", "ko_idea"], "additionalProperties": False}},
        "insight": {"type": "string"},
    },
    "required": ["memes", "insight"], "additionalProperties": False,
}


def llm_targets(rep, limit=12):
    """설명 대상 = 01 틱톡·인스타 + 02 새 밈 (url 로 중복 제거, 최대 limit)."""
    out, seen = [], set()
    for x in list(rep.get("shortform") or []) + list(rep.get("new_memes") or []):
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        out.append(x)
        if len(out) >= limit:
            break
    return out


def llm_request(rep):
    """→ (system, user) 문자열. 하루 1회: 밈 설명 전부 + 인사이트를 한 요청에서 JSON 으로 받습니다."""
    targets = llm_targets(rep)
    lines = [f"날짜: {rep['date']} · {rep['round']}회차", "", "## 설명할 밈 (id 는 그대로 돌려주십시오)"]
    for i, x in enumerate(targets, 1):
        lines.append(f"### id={x['url']}")
        lines.append(f"제목: {x['title']}")
        if x.get("platforms"):
            lines.append("플랫폼 단서: " + ", ".join(x["platforms"]))
        if x.get("status"):
            lines.append(f"KYM 상태: {x['status']}")
        lines.append("About: " + (x.get("about") or x.get("summary") or "(자료 없음)"))
        lines.append("")
    lines.append("## 리포트 요약 (insight 용)")
    lines.append("플랫폼 집계: " + (", ".join(f"{a} {n}건" for a, n in rep.get("platform_counts") or []) or "없음"))
    for r in rep.get("reddit") or []:
        if r["status"] == "ok" and r["items"]:
            lines.append(f"r/{r['sub']} 상위: " + " / ".join(x["title"][:80] for x in r["items"][:3]))
    for region in ("KR", "US"):
        y = (rep.get("youtube") or {}).get(region) or {}
        if y.get("status") == "ok" and y.get("items"):
            lines.append(f"유튜브 인기 {region}: " + " / ".join(f"{v['title'][:60]}{' (쇼츠)' if v.get('shorts') else ''}" for v in y["items"][:5]))
    for geo in ("KR", "US"):
        t = (rep.get("trends") or {}).get(geo) or []
        if t:
            lines.append(f"검색 급상승 {geo}: " + " / ".join(x["title"] for x in t[:5]))
    th = rep.get("threads") or {}
    if th.get("status") == "ok" and th.get("keywords"):
        lines.append("Threads 키워드 24시간 게시량: " + " / ".join(f"{x['keyword']} {x['recent']}건" + (f"({x['delta']:+d})" if x.get("delta") is not None else "") for x in th["keywords"][:6]))
        if th.get("rising"):
            lines.append("Threads 에서 새로 뜨는 말: " + " / ".join(x["term"] for x in th["rising"][:8]))
    rl = rep.get("reels") or {}
    if rl.get("status") == "ok" and rl.get("items"):
        lines.append("릴스·틱톡 트렌드 정리(유튜브 정리 영상에서 뽑은 항목): " + " / ".join(f"{x['term']}({x['n']}채널)" for x in rl["items"][:8]))
        if rl.get("videos"):
            lines.append("정리 영상 제목: " + " / ".join(v["title"][:60] for v in rl["videos"][:3]))
    im = rep.get("imgflip") or {}
    if im.get("compared"):
        lines.append("밈 템플릿 변동: " + (" / ".join(f"{x['name']} {x['prev_rank']}→{x['rank']}위" for x in im.get("movers", [])[:5]) or "상위 30 변동 없음"))
    if rep.get("cross"):
        lines.append("게임 교차: " + " / ".join(f"{c['term'][:50]} → {c['game']}" for c in rep["cross"][:5]))
    lines.append("")
    lines.append("위 자료만 근거로 memes 배열(각 id 마다 ko_what, ko_idea)과 insight 를 한국어로 작성하십시오.")
    return LLM_SYSTEM, "\n".join(lines)


def attach_llm(rep, result):
    """complete_json 결과를 리포트에 붙입니다: 항목별 ko_what·ko_idea, rep["insight"], rep["llm_usage"]."""
    rep["llm_usage"] = {**(result.get("usage") or {}), "model": result.get("model", ""), "stop_reason": result.get("stop_reason", ""),
                        "error": result.get("error", ""), "ok": bool(result.get("ok"))}
    data = result.get("data") or {}
    if not result.get("ok") or not isinstance(data, dict):
        return 0
    by_id = {m.get("id"): m for m in data.get("memes") or [] if isinstance(m, dict)}
    n = 0
    for key in ("shortform", "new_memes", "kym_all"):
        for x in rep.get(key) or []:
            m = by_id.get(x["url"])
            if m and (m.get("ko_what") or m.get("ko_idea")):
                x["ko_what"], x["ko_idea"] = (m.get("ko_what") or "").strip(), (m.get("ko_idea") or "").strip()
                n += key == "kym_all"
    p = rep.get("pick")
    if p and by_id.get(p["url"]):
        p["ko_what"], p["ko_idea"] = (by_id[p["url"]].get("ko_what") or "").strip(), (by_id[p["url"]].get("ko_idea") or "").strip()
    rep["insight"] = (data.get("insight") or "").strip()
    return n
