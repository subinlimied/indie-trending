"""헤드라인 규칙 문장 (3단계 '뉴스 제목 문장' 전까지의 규칙 기반 버전).

모든 리포트가 같은 형식을 씁니다: Barlow Condensed 대문자 2줄, 게임 이름은 연초록(.hi), 핵심 수치는 초록 밑줄(.ul, 하락은 .dn).
문장은 조각 목록 [(글, 클래스)] 로 만들고 to_html 이 <span> 으로 바꿉니다. 클래스: "" 보통, "hi" 이름, "ul" 상승 수치, "dn" 하락 수치, "br" 줄바꿈 자리.

    from market import headline
    segs = headline.game_pick(pick)                 # 일간: "<장르> <이름>, <목록> +n계단 상승"
    segs = headline.weekly_niche(tag_row)           # 주간: "Cozy, 출시 48개 중 성공률 18%"
    segs = headline.media_pick(pick)                # 미디어: "틱톡 'I'm So Sorry' 트렌드, KYM 2일 연속"
    segs = headline.personal_top(top_item, rank=1)  # 개인: "내 범위 1위 Tiny Bastion, New & Popular +70계단"
    html = headline.to_html(segs, link=url)         # <span class="hi">…</span>, <br class="hb">
    headline.direction(segs) → "up" | "down" | ""
"""
import html as H
import re

# 장르 태그 → 한국어 한 단어. 없으면 원어. 장르가 아닌 태그는 GENRE_SKIP 으로 건너뜀.
GENRE_KO = {"Roguelike": "로그라이크", "Roguelite": "로그라이트", "Action Roguelike": "액션 로그라이크", "Deckbuilding": "덱빌딩", "Deckbuilder": "덱빌딩",
            "Card Game": "카드 게임", "Cozy": "코지", "Simulation": "시뮬레이션", "Casual": "캐주얼", "Adventure": "어드벤처", "Action": "액션",
            "Strategy": "전략", "RPG": "RPG", "Puzzle": "퍼즐", "Horror": "호러", "Psychological Horror": "심리 호러", "Survival Horror": "서바이벌 호러",
            "Survival": "서바이벌", "Platformer": "플랫포머", "2D Platformer": "2D 플랫포머", "Visual Novel": "비주얼 노벨", "Dating Sim": "연애 시뮬",
            "Idle": "방치형", "Incremental": "방치형", "Tower Defense": "타워 디펜스", "Shooter": "슈터", "FPS": "FPS", "Shoot 'Em Up": "슈팅",
            "Bullet Hell": "탄막", "Open World Survival Craft": "오픈월드 생존", "Open World": "오픈월드", "Farming Sim": "농장 시뮬", "City Builder": "도시 건설",
            "Base Building": "기지 건설", "Colony Sim": "콜로니 심", "Management": "경영", "Automation": "자동화", "Metroidvania": "메트로배니아",
            "Rhythm": "리듬", "Racing": "레이싱", "Sports": "스포츠", "Sandbox": "샌드박스", "Point & Click": "포인트 앤 클릭", "Walking Simulator": "워킹 심",
            "Interactive Fiction": "인터랙티브 픽션", "Souls-like": "소울라이크", "Turn-Based Strategy": "턴제 전략", "Turn-Based Tactics": "턴제 택틱스",
            "JRPG": "JRPG", "Action RPG": "액션 RPG", "Strategy RPG": "전략 RPG", "Dungeon Crawler": "던전 크롤러", "Auto Battler": "오토 배틀러",
            "Life Sim": "라이프 심", "Hidden Object": "숨은그림찾기", "Fantasy": "판타지", "Fighting": "격투", "Stealth": "잠입", "Crafting": "제작",
            "Exploration": "탐험", "Mystery": "미스터리", "Comedy": "코미디", "Educational": "교육", "Arcade": "아케이드", "Clicker": "클리커", "Cards": "카드",
            "Tactical": "택티컬", "Physics": "물리", "Driving": "드라이빙", "Pinball": "핀볼", "Board Game": "보드 게임", "Trivia": "퀴즈", "Word Game": "단어 게임",
            "Amare": "아마레", "castle": "성채", "Minigames": "미니게임", "Multiplayer": "멀티플레이", "Co-op": "협동", "Tycoon": "타이쿤", "Shop Simulator": "상점 경영",
            "Sokoban": "소코반", "Match 3": "매치 3", "Hack and Slash": "핵 앤 슬래시", "Beat 'em up": "벨트스크롤", "Space": "우주", "Sci-fi": "SF",
            "Cyberpunk": "사이버펑크", "Post-apocalyptic": "포스트 아포칼립스", "Zombies": "좀비", "Vampire Survivors-like": "뱀서라이크", "Bullet Heaven": "뱀서라이크",
            "Tabletop": "테이블탑", "Trading Card Game": "TCG", "Otome": "오토메", "Romance": "로맨스", "Drama": "드라마", "Thriller": "스릴러", "Detective": "추리",
            "Escape Room": "방탈출", "Cooking": "요리", "Fishing": "낚시", "Farming": "농장", "Building": "건설", "Wholesome": "힐링", "Relaxing": "힐링"}
GENRE_SKIP = {"Indie", "Singleplayer", "2D", "3D", "Early Access", "Pixel Graphics", "Cute", "Atmospheric", "Colorful", "Free to Play",
              "Female Protagonist", "No AI", "No generative AI was used", "Short", "Story Rich", "Difficult", "Anime", "Retro", "Dark", "Funny",
              "Controller", "Family Friendly", "Great Soundtrack", "Moddable", "Procedural Generation", "Hand-drawn", "Stylized", "Minimalist",
              "Top-Down", "Isometric", "Third Person", "First-Person", "Side Scroller", "3D Platformer"}

RX_RANK = re.compile(r"^(.+?) (?:(\d+)→)?(\d+)위$")
RX_PCT = re.compile(r"^([+−]\d[\d,.]*%)")
RX_SIGNED = re.compile(r"^([+−]\d[\d,]*)")


def split_dots(s):
    """' · ' 로 나누되 괄호 안은 나누지 않습니다 (render.split_dots 와 같음)."""
    out, cur, depth, i = [], "", 0, 0
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if depth == 0 and s.startswith(" · ", i):
            out.append(cur)
            cur = ""
            i += 3
            continue
        cur += ch
        i += 1
    if cur:
        out.append(cur)
    return [x.strip() for x in out if x.strip()]


def genre_word(tags, sub=""):
    """태그 목록 중 장르로 쓸 첫 단어(한국어). 없으면 빈 문자열."""
    tags = list(tags or [])
    if not tags and sub:
        tags = [t.strip() for seg in split_dots(sub) for t in seg.split(",") if t.strip()]
    first_sub = (sub or "").split(" · ")[0]
    for t in tags:
        if t in GENRE_SKIP or re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
            continue
        if t in GENRE_KO:
            return GENRE_KO[t]
        if re.search(r"[A-Za-z가-힣]", t) and len(t) <= 24 and t != first_sub:
            return t
    return ""


def rank_move(line):
    """'Top Sellers 178→115위 · …' → (목록, 전, 후) 또는 None."""
    segs = split_dots(line or "")
    m = RX_RANK.match(segs[0]) if segs else None
    if not m:
        return None
    return m.group(1), (int(m.group(2)) if m.group(2) else None), int(m.group(3))


def _move_segs(lead, a, b, suffix="계단 상승", suffix_down="계단 하락", keep="위 유지"):
    d = (a - b) if a is not None else None
    if d is None:
        return [(f"{lead} ", ""), (f"{b}위", "ul")]
    if d > 0:
        return [(f"{lead} ", ""), (f"+{d}{suffix}", "ul")]
    if d < 0:
        return [(f"{lead} ", ""), (f"{-d}{suffix_down}", "dn")]
    return [(f"{lead} ", ""), (f"{b}{keep}", "ul")]


# ---------- 리포트별 문장 ----------

def game_pick(p):
    """일간 선정 게임 → '<장르> <이름>, <목록> +n계단 상승'. 순위 변화가 없으면 '<목록> n위 유지', 순위가 없으면 다음 수치."""
    g = genre_word(p.get("tags"), p.get("sub", ""))
    segs = ([(g + " ", "")] if g else []) + [(p["name"], "hi")]
    mv = rank_move(p.get("line", ""))
    if mv:
        lead, a, b = mv
        return segs + [(",", ""), ("", "br")] + _move_segs(lead, a, b)
    rest = split_dots(p.get("line", ""))
    for seg in rest:
        m = RX_PCT.match(seg) or RX_SIGNED.match(seg)
        if m:
            return segs + [(",", ""), ("", "br"), ("리뷰 ", ""), (m.group(1), "up" if not m.group(1).startswith("−") else "dn")]
    return segs


def weekly_niche(t, success_reviews=500):
    """주간 틈새 1위 태그 → 'Cozy, 출시 48개 중 성공률 18%'."""
    return [(t["name"], "hi"), (",", ""), ("", "br"), (f"출시 {t['n']:,}개 중 성공률 ", ""), (f"{t['p_success']:.0f}%", "ul")]


MEDIA_PLATFORM_KO = {"TikTok": "틱톡", "Instagram": "인스타", "YouTube": "유튜브", "Twitter/X": "X", "Reddit": "레딧", "Twitch": "트위치"}


def media_pick(p):
    """오늘의 트렌드 → \"틱톡 'I'm So Sorry' 트렌드, KYM 2일 연속\" (연속이 아니면 '오늘 등록'·'오늘 갱신')."""
    plat = next((MEDIA_PLATFORM_KO.get(x, x) for x in (p.get("platforms") or [])), "숏폼")
    title = p["title"].split(" / ")[0].strip()
    if len(title) > 28:
        title = title[:27].rstrip() + "…"
    segs = [(f"{plat} ", ""), (f"'{title}'", "hi"), (" 트렌드,", ""), ("", "br"), ("KYM ", "")]
    n = p.get("streak", 1) or 1
    if n > 1:
        segs.append((f"{n}일 연속", "ul"))
    elif p.get("new"):
        segs.append(("오늘 등록", "ul"))
    else:
        segs.append(("오늘 갱신", "ul"))
    return segs


def personal_top(t, rank=1):
    """내 범위 1위 → '내 범위 1위 Tiny Bastion, New & Popular +70계단'."""
    segs = [(f"내 범위 {rank}위 ", ""), (t["name"], "hi")]
    mv = rank_move(t.get("line", ""))
    if mv:
        lead, a, b = mv
        return segs + [(",", ""), ("", "br")] + _move_segs(lead, a, b, suffix="계단", suffix_down="계단 하락")
    for seg in split_dots(t.get("line", ""))[1:]:
        m = RX_PCT.match(seg) or RX_SIGNED.match(seg)
        if m:
            return segs + [(",", ""), ("", "br"), ("리뷰 ", ""), (m.group(1), "ul")]
    return segs


# ---------- HTML ----------

def to_html(segs, link=None, br=True):
    out = []
    for text, cls in segs:
        if cls == "br":
            out.append('<br class="hb">' if br else " ")
            continue
        t = H.escape(text)
        if cls == "hi":
            out.append(f'<a href="{H.escape(link, quote=True)}" target="_blank" rel="noopener" class="hi">{t}</a>' if link else f'<span class="hi">{t}</span>')
        elif cls in ("ul", "dn", "up"):
            out.append(f'<span class="{"ul" if cls == "up" else cls}" style="white-space:nowrap">{t}</span>')
        else:
            out.append(t)
    return "".join(out)


def to_text(segs):
    return "".join(" " if cls == "br" else text for text, cls in segs)


def direction(segs):
    for _, cls in segs:
        if cls in ("ul", "up"):
            return "up"
        if cls == "dn":
            return "down"
    return ""
