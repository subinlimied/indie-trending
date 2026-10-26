"""리포트 dict → Discord 본문(markdown) 과 HTML.

HTML 은 Discord 첨부로 열리는 정적 파일이라 스크립트 없이 CSS 만 씁니다.
게임 이미지: Steam 은 url 의 appid 로 캡슐 주소를 만들고, itch 는 분석기가 넘긴 "thumb" 를 씁니다.
"""
import html as H
import re
from datetime import datetime
from urllib.parse import quote

from . import charts, headline, ui

WEEK = "월화수목금토일"
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
STEAM_APP = re.compile(r"store\.steampowered\.com/app/(\d+)")
STEAM_IMG = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/{name}.jpg"


def date_ko(date):
    d = datetime.strptime(date, "%Y-%m-%d")
    return f"{d.month}월 {d.day}일 ({WEEK[d.weekday()]})"


def split_dots(s):
    """' · ' 로 나누되 괄호 안의 ' · ' 는 나누지 않습니다."""
    out, cur, depth = [], "", 0
    i = 0
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


# ---------- 핵심 수치 파싱 ----------
# 각 항목의 line 은 "핵심 수치 · 보조 수치 · ..." 꼴입니다. 첫 조각을 큰 숫자로 떼어 냅니다.
RX_CLIMB = re.compile(r"^(.+?) (\d+)→(\d+)위 ([▲▼])(\d[\d,]*)$")
RX_PCT = re.compile(r"^([+−]\d[\d,.]*%)(?: \(([+−]\d[\d,]*)\))?$")
RX_SIGNED = re.compile(r"^([+−]\d[\d,]*)$")
RX_STREAK = re.compile(r"^(\d+)회차 연속$")
RX_RANK = re.compile(r"^(.+?) (?:(\d+)→)?(\d+)위$")
RX_SEG_NUM = re.compile(r"^(리뷰|평점|동접|댓글|추정 판매) ([\d,]+)개?(?:\(([^)]*)\))?$")
RX_SEG_STAR = re.compile(r"^([\d.]+)★$")
RX_SEG_PRICE = re.compile(r"^(\$[\d,.]+|무료|NYOP|유료)( −\d+%| 세일)?$")
RX_SEG_WIN = re.compile(r"^(\d+일) ([+−][\d,]+)$")


def direction(s):
    if s.startswith(("▲", "+")):
        return "up"
    if s.startswith(("▼", "−")):
        return "down"
    return ""


def key_metric(line):
    """line → (큰 숫자, 설명, 방향, 나머지 조각). 큰 숫자가 없으면 ("", "", "", 전체 조각)."""
    segs = split_dots(line or "")
    if not segs:
        return "", "", "", []
    first, rest = segs[0], segs[1:]
    m = RX_CLIMB.match(first)
    if m:
        return f"{m.group(4)}{m.group(5)}", f"{m.group(1)} {m.group(2)}→{m.group(3)}위", "up" if m.group(4) == "▲" else "down", rest
    m = RX_PCT.match(first)
    if m:
        return m.group(1), (f"증가율 ({m.group(2)})" if m.group(2) else "증가율"), direction(m.group(1)), rest
    m = RX_SIGNED.match(first)
    if m:
        return m.group(1), "증가 수", direction(m.group(1)), rest
    m = RX_STREAK.match(first)
    if m:
        return f"{m.group(1)}회차", "연속 상승", "up", rest
    m = RX_RANK.match(first)
    if m:
        cap = m.group(1) + (f" · {m.group(2)}위에서" if m.group(2) else "")
        return f"{m.group(3)}위", cap, "", rest
    return "", "", "", segs


def seg_tile(seg):
    """보조 조각 하나 → (라벨, 값, 비고). 스탯 타일과 보조 줄에서 같이 씁니다."""
    m = RX_RANK.match(seg)
    if m:
        return m.group(1), f"{m.group(3)}위", (f"{m.group(2)}위에서" if m.group(2) else "")
    m = RX_SEG_NUM.match(seg)
    if m:
        return m.group(1), m.group(2), m.group(3) or ""
    m = RX_SEG_STAR.match(seg)
    if m:
        return "평점", f"{m.group(1)}★", ""
    m = RX_SEG_PRICE.match(seg)
    if m:
        return "가격", m.group(1), (m.group(2) or "").strip()
    m = RX_SEG_WIN.match(seg)
    if m:
        return f"{m.group(1)} 변화", m.group(2), ""
    return "", seg, ""


# ---------- Discord ----------

def _md_break(text, limit=72):
    """긴 줄은 첫 조각만 본문에 두고 나머지는 작은 글씨(-#) 줄로 내립니다."""
    segs = split_dots(text)
    if len(text) <= limit or len(segs) < 2:
        return f"• {text}"
    head, rest = segs[0], segs[1:]
    if ": [" in head and all(x.startswith("[") for x in rest):
        label, first = head.split(": ", 1)
        head, rest = label + ":", [first] + rest
    return f"• {head}\n-# {' · '.join(rest)}"


def to_md(rep):
    L = [f"**{rep['platform_ko']} 트렌딩 · {date_ko(rep['date'])} · {rep['round']}회차**"]
    p = rep.get("pick")
    if p:
        hero, cap, _, _ = key_metric(p["line"])
        metric = f"{cap} **{hero}**" if hero else split_dots(p["line"])[0]
        head = f"**오늘의 선정 게임 → [{p['name']}]({p['url']})**" + (f" · {p['streak']}일 연속" if p["streak"] > 1 else "")
        lines = [head]
        if p.get("sub"):
            lines.append(f"-# {p['sub']}")
        lines.append(metric + ("" if not p["badges"] else " · " + " · ".join(p["badges"][:3])))
        lines.append(" · ".join(f"[{t}]({u})" for t, u in p["links"]))
        L.append("\n".join(lines))
    L.append("**큰 폭 변화**\n" + ("\n".join(_md_break(h) for h in rep["headline"]) if rep["headline"] else "• 없음"))
    L.append("**특이사항**\n" + ("\n".join(_md_break(n) for n in rep["notes"]) if rep["notes"] else "• 없음"))
    L.append(f"-# {rep['collect_line']}")
    return "\n\n".join(L)


# ---------- HTML ----------

# 옛 페이지 CSS (주간·미디어 렌더러가 render.CSS 로 가져다 씀). 값은 tokens.json → ui.css_vars 에서만 옵니다.
# 일간 리포트 자체는 아래 DAILY_CSS 를 씁니다.
LEGACY_RULES = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:16px;line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:1160px;margin:0 auto;padding-block:0 80px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
h1,h2,h3,h4{text-wrap:balance}
small{font-size:14px}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--rise)}.down{color:var(--fall)}

/* 머리 */
header{padding:40px 0 20px;border-bottom:2px solid var(--ink)}
.eyebrow{font-family:var(--mono);font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:var(--accent);margin:0 0 10px}
h1{font-family:var(--serif);font-weight:700;font-size:clamp(30px,4.6vw,46px);line-height:1.15;margin:0 0 14px;letter-spacing:-.01em}
ul.basis{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px 0;font-size:14px;color:var(--muted);max-width:90ch}
ul.basis li{padding-right:10px;margin-right:10px;border-right:1px solid var(--line-strong);line-height:1.5}ul.basis li:last-child{border:0}
.status{display:flex;flex-wrap:wrap;gap:10px 28px;margin:22px 0 0;padding:0}
.status div{display:flex;flex-direction:column;gap:2px}
.status dt{font-family:var(--mono);font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0}
.status dd{margin:0;font-size:17px;font-weight:600;font-variant-numeric:tabular-nums;line-height:1.3}
nav.toc{display:flex;flex-wrap:wrap;gap:4px 18px;padding:12px 0;border-bottom:1px solid var(--line);font-size:14px}
nav.toc a{color:var(--muted)}nav.toc a b{font-family:var(--mono);font-weight:500;color:var(--accent);margin-right:5px}

/* 상단: 선정 게임 + 변화 요약 */
.top{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(0,1fr);gap:18px;margin-top:26px}
@media(max-width:860px){.top{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow)}
.lbl{margin:0 0 8px;font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.pick{display:grid;grid-template-columns:272px minmax(0,1fr);overflow:hidden}
@media(max-width:620px){.pick{grid-template-columns:1fr}}
.pick .pk-img{background:var(--surface-2);border-right:1px solid var(--line);display:flex;align-items:center;justify-content:center;padding:16px}
@media(max-width:620px){.pick .pk-img{border-right:0;border-bottom:1px solid var(--line)}}
.pick .pk-img .th{width:100%;max-width:360px;border-radius:6px}
.pick .pk-body{padding:20px 22px 22px;display:flex;flex-direction:column;gap:10px;min-width:0}
.pk-name{font-family:var(--serif);font-size:30px;line-height:1.2;margin:0;font-weight:700}
.pk-sub{margin:0;color:var(--muted);font-size:15px}
.pk-links{margin:0;font-size:14px;display:flex;gap:14px;flex-wrap:wrap}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-top:4px}
.tile{background:var(--surface-2);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.tile dt{font-size:12.5px;color:var(--muted);margin:0 0 2px;letter-spacing:.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile dd{margin:0;font-size:24px;font-weight:700;line-height:1.15;font-variant-numeric:tabular-nums;letter-spacing:-.01em}
.tile dd small{display:block;font-size:13px;font-weight:500;color:var(--muted);margin-top:2px}
.side{padding:18px 22px 20px;display:flex;flex-direction:column;gap:16px}
.side h3{margin:0}
ul.hl{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
ul.hl li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:10px;align-items:start}
ul.hl li .th{width:64px}body.itch ul.hl li .th{width:48px}
ul.hl li.nothumb{grid-template-columns:1fr}
ul.hl .h1{font-weight:600;line-height:1.45}
ul.hl .h2{color:var(--muted);font-size:14px;line-height:1.5;margin-top:2px;display:flex;flex-wrap:wrap;gap:0 12px}ul.hl .h2 span{white-space:nowrap}
.empty{color:var(--muted);font-size:15px;margin:0}

/* 썸네일: CSS 배경 여러 장(캡슐 → header → 머리글자 SVG). 이미지가 없으면 이름 해시 색 블록 위에 머리글자만 남습니다. */
.th{display:block;border-radius:5px;background-color:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;background-repeat:no-repeat;flex:none;width:120px;aspect-ratio:231/87;max-width:100%}
body.itch .th{aspect-ratio:315/250;width:84px;background-size:cover}
.th.xs{width:44px;border-radius:3px}body.itch .th.xs{width:36px}

/* 배지 */
.pills{display:inline-flex;flex-wrap:wrap;gap:4px;vertical-align:middle}
.badge{display:inline-block;font-size:12.5px;font-weight:500;line-height:1.5;padding:1px 8px;border:1px solid var(--line-strong);border-radius:999px;color:var(--muted);white-space:nowrap}
.badge.new{color:var(--rise);border-color:transparent;background:var(--rise-soft)}
.badge.excl{color:var(--fall);border-color:transparent;background:var(--fall-soft)}
.badge.disc{color:var(--warn);border-color:transparent;background:var(--warn-soft)}
.badge.acc{color:var(--accent);border-color:transparent;background:var(--accent-soft)}

/* 섹션 */
section{margin-top:52px}
h2{font-family:var(--serif);font-weight:700;font-size:26px;line-height:1.3;margin:0 0 6px}
h2 .no{font-family:var(--mono);font-size:14px;font-weight:500;color:var(--accent);margin-right:12px;vertical-align:middle}
.sbasis{color:var(--muted);font-size:15px;margin:0 0 18px;max-width:80ch}
.stext{margin:0 0 16px;font-size:16px}
.blocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:16px;align-items:start}
.block{padding:16px 18px 6px}
.block h4{margin:0 0 12px;font-size:15px;font-weight:600;color:var(--accent)}
.block .empty{padding-bottom:10px}
ul.bul{margin:0;padding-left:20px}ul.bul li{margin:6px 0}

/* 게임 카드: 썸네일 | 본문. 본문 첫 줄 오른쪽에 큰 숫자. */
.g{display:grid;grid-template-columns:auto minmax(0,1fr);gap:12px;align-items:start;padding:12px 0;border-top:1px solid var(--line)}
.block .g:first-of-type{border-top:0;padding-top:4px}
.g .gb{min-width:0;display:flex;flex-direction:column;gap:4px}
.g .gh{display:flex;gap:10px;align-items:flex-start;justify-content:space-between}
.g .nm{font-weight:600;font-size:16px;line-height:1.35;color:var(--ink);min-width:0;overflow-wrap:anywhere}
.g .sub{font-size:14px;color:var(--muted);line-height:1.45}
.g .meta{font-size:14px;color:var(--muted);line-height:1.5;display:flex;flex-wrap:wrap;gap:0 14px}
.g .meta span{white-space:nowrap}
.kpi{text-align:right;flex:none}
.kpi b{display:block;font-size:24px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.01em;white-space:nowrap}
.kpi small{display:block;font-size:12.5px;color:var(--muted);margin-top:3px;line-height:1.35;max-width:14ch;margin-left:auto}
.kpi.up b{color:var(--rise)}.kpi.down b{color:var(--fall)}
@media(max-width:520px){.th{width:96px}body.itch .th{width:72px}}

/* 03 태그 표 */
.tg-head{display:grid;grid-template-columns:minmax(110px,1.1fr) minmax(160px,2fr) 72px minmax(150px,1.3fr);gap:0 14px;padding:0 4px 8px;font-family:var(--mono);font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--line-strong)}
.tg-head.st,.tg.st{grid-template-columns:minmax(110px,1.1fr) minmax(160px,2fr) 72px minmax(150px,1.3fr) 64px}
.tg{display:grid;grid-template-columns:minmax(110px,1.1fr) minmax(160px,2fr) 72px minmax(150px,1.3fr);gap:6px 14px;align-items:center;padding:10px 4px;border-bottom:1px solid var(--line)}
.tg-name{font-weight:600;font-size:16px;min-width:0;overflow-wrap:anywhere}
.tg-bars{display:flex;flex-direction:column;gap:4px;min-width:0}
.bar{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}
.bar i{display:block;height:10px;border-radius:2px;background:var(--line);position:relative;overflow:hidden}
.bar i::after{content:"";position:absolute;inset:0;width:var(--w);background:var(--accent);border-radius:2px}
.bar.b i{height:6px}.bar.b i::after{background:var(--line-strong)}
.bar span{white-space:nowrap;min-width:9ch;text-align:right}
.tg-mult{font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;text-align:right;letter-spacing:-.01em}
.tg-mult.hot{color:var(--rise)}
.tg-ex{display:flex;gap:6px;flex-wrap:wrap}
.tg-ex .th{width:72px}body.itch .tg-ex .th{width:48px}
.tg-st{font-size:14px;color:var(--muted);text-align:right;white-space:nowrap}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:0 0 10px}
.legend i{display:inline-block;width:14px;height:8px;border-radius:2px;vertical-align:middle;margin-right:6px;background:var(--accent)}.legend i.b{background:var(--line-strong);height:6px}
h4.tt{margin:22px 0 10px;font-size:17px}
@media(max-width:640px){.tg-head{display:none}.tg,.tg.st{grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"name mult" "bars bars" "ex ex" "st st"}.tg-name{grid-area:name}.tg-bars{grid-area:bars}.tg-mult{grid-area:mult}.tg-ex{grid-area:ex}.tg-st{grid-area:st;text-align:left}}

/* 06 상세 표 */
details.dt{margin:12px 0}
details.dt>summary{cursor:pointer;font-weight:600;font-size:16px;padding:10px 12px;background:var(--surface);border:1px solid var(--line);border-radius:8px;list-style:none;display:flex;justify-content:space-between;gap:10px}
details.dt>summary::-webkit-details-marker{display:none}
details.dt>summary::after{content:"펼치기";font-size:13px;font-weight:500;color:var(--accent);flex:none}
details.dt[open]>summary::after{content:"접기"}
details.dt[open]>summary{border-radius:8px 8px 0 0}
.tbl{overflow-x:auto;border:1px solid var(--line);border-top:0;border-radius:0 0 8px 8px;background:var(--surface);max-height:80vh;overflow-y:auto}
.tbl.solo{border-top:1px solid var(--line);border-radius:8px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:14px;background:var(--surface)}
th,td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:left;vertical-align:top;background:var(--surface)}
th{font-family:var(--mono);font-size:12px;letter-spacing:.06em;color:var(--muted);background:var(--surface-2);white-space:nowrap;position:sticky;top:0;z-index:2;font-weight:500}
td{font-variant-numeric:tabular-nums;white-space:nowrap}
td.num{text-align:right}th.num{text-align:right}
table.detail th:nth-child(1),table.detail td:nth-child(1){position:sticky;left:0;z-index:1;width:52px;min-width:52px;max-width:52px;text-align:center;padding-left:6px;padding-right:6px}
table.detail th:nth-child(2),table.detail td:nth-child(2){position:sticky;left:52px;z-index:1;border-right:1px solid var(--line-strong);min-width:200px;max-width:280px;white-space:normal}
table.detail th:nth-child(1),table.detail th:nth-child(2){z-index:3}
td.rk b{font-weight:600}td.rk small{display:block;font-size:11.5px;color:var(--muted);line-height:1.2}
td.gm details summary{cursor:pointer;list-style:none;display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}
td.gm details summary::-webkit-details-marker{display:none}
td.gm details summary::before{content:"▸";color:var(--faint);font-size:12px;flex:none}
td.gm details[open] summary::before{content:"▾"}
td.gm .nm{font-weight:600;line-height:1.35}
td.gm .ex{font-size:12px;color:var(--fall);font-weight:600}
td.gm dl{margin:8px 0 2px 16px;display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;font-size:13px;white-space:normal}
td.gm dl dt{color:var(--muted);white-space:nowrap}td.gm dl dd{margin:0;overflow-wrap:anywhere}
td.gm dl .th{grid-column:1/-1;margin-bottom:4px}
.vd{display:inline-block;font-size:12.5px;font-weight:600;padding:1px 8px;border-radius:999px;background:var(--surface-2);border:1px solid var(--line-strong);color:var(--muted);white-space:nowrap}
.vd.up{color:var(--rise);background:var(--rise-soft);border-color:transparent}.vd.down{color:var(--fall);background:var(--fall-soft);border-color:transparent}.vd.acc{color:var(--accent);background:var(--accent-soft);border-color:transparent}
td .vd+small{color:var(--muted);margin-left:6px}
td .d{font-size:12.5px;margin-left:4px}

footer{margin-top:60px;padding-top:16px;border-top:1px solid var(--line);color:var(--muted);font-size:13px;font-family:var(--mono);line-height:1.6}
@media (prefers-reduced-motion:no-preference){details.dt>summary{transition:background .15s}}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""
CSS = ui.css_vars("steam", scale="web") + LEGACY_RULES


def esc(s):
    return H.escape(str(s if s is not None else ""), quote=False)


def md_links(s):
    s = esc(s)
    s = LINK.sub(lambda m: f'<a href="{H.escape(m.group(2), quote=True)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
    s = re.sub(r"(▲\d[\d,]*)", r'<span class="up">\1</span>', s)
    s = re.sub(r"(▼\d[\d,]*)", r'<span class="down">\1</span>', s)
    s = re.sub(r"(?<![\w$])(\+\d[\d,.]*%?)", r'<span class="up">\1</span>', s)
    s = re.sub(r"(?<![\w$])(−\d[\d,.]*%?)", r'<span class="down">\1</span>', s)
    return s


def dots_html(segs):
    """보조 수치 조각들. 조각 안에서는 줄이 바뀌지 않고 조각 사이에서만 바뀝니다."""
    return "".join(f"<span>{md_links(x)}</span>" for x in segs)


# ---------- 썸네일 ----------

def hue(name):
    h = 0
    for ch in name or "":
        h = (h * 31 + ord(ch)) % 360
    return h


def thumb_srcs(url, rep, it=None, big=False):
    """이미지 후보(앞이 우선)와 바탕색. 분석기가 넘긴 thumb 가 있으면 먼저, Steam 은 appid 경로를 시도합니다.
    Steam 의 appid 경로는 오래된 앱에만 있고 최신 앱은 해시가 든 경로를 써서 절반쯤 404 가 납니다.
    그래서 캡슐 → header → 색 블록 순서로 CSS 배경 여러 장을 겹쳐 두고, 열리는 것이 보이게 합니다."""
    srcs, bg = [], None
    if it and it.get("thumb"):
        srcs.append(it["thumb"])
        bg = it.get("thumb_bg")
    t = (rep.get("thumbs") or {}).get(url) or {}
    if t.get("src") and t["src"] not in srcs:
        srcs.append(t["src"])
        bg = bg or t.get("bg")
    m = STEAM_APP.search(url or "")
    if m:
        srcs.append(STEAM_IMG.format(appid=m.group(1), name="capsule_616x353" if big else "capsule_231x87"))
        srcs.append(STEAM_IMG.format(appid=m.group(1), name="header"))
    return srcs, bg


def letter_svg(ch, big=False):
    """이미지가 없을 때 보일 머리글자. 맨 아래 배경 층이라 이미지가 열리면 가려집니다."""
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text x="50" y="50" dy=".36em" text-anchor="middle" '
           f'font-family="Georgia,serif" font-weight="700" font-size="{40 if big else 46}" fill="rgba(0,0,0,.45)">{H.escape(ch)}</text></svg>')
    return "data:image/svg+xml," + quote(svg, safe="")


def thumb_html(name, url, rep, it=None, cls="th", big=False):
    srcs, bg = thumb_srcs(url, rep, it, big)
    initial = (name or "?").strip()[:1].upper()
    # url() 은 따옴표 없이 씁니다 (style 속성의 따옴표와 겹치지 않게). 주소의 괄호·따옴표·공백은 퍼센트 인코딩.
    layers = [f"url({quote(u, safe=':/%?=&#.-_~')})" for u in srcs] + [f"url({letter_svg(initial, big)})"]
    style = (f"background-color:{H.escape(bg, quote=True)};" if bg else f"--h:{hue(name)};") + "background-image:" + ",".join(layers)
    return (f'<a class="{cls}" style="{style}" href="{H.escape(url or "#", quote=True)}" target="_blank" rel="noopener" '
            f'title="{H.escape(name or "", quote=True)}" aria-label="{H.escape(name or "", quote=True)}"></a>')


# ---------- 배지 ----------

def badge_cls(b):
    if b in ("신작", "출시 예정"):
        return "new"
    if b == "본문 제외":
        return "excl"
    if b.startswith("할인") or b == "세일":
        return "disc"
    if b in ("데모", "게임잼", "Steam 있음"):
        return "acc"
    return ""


def badges_html(badges, limit=3):
    """최대 limit 개만 배지로, 나머지는 글자로 돌려줍니다."""
    shown = badges[:limit]
    rest = badges[limit:]
    pills = "".join(f'<span class="badge {badge_cls(b)}">{esc(b)}</span>' for b in shown)
    return (f'<span class="pills">{pills}</span>' if pills else ""), rest


RX_CNT = re.compile(r"^(\d+)개 \((\d+)%\)$")


def is_tag_table(t):
    return t["cols"][1:4] == ["상승 묶음", "전체 비율", "배율"]


# ---------- 표 ----------

def verdict_html(v):
    segs = split_dots(v)
    if not segs:
        return ""
    if segs[0] == "회차 1":
        pill, rest = "비교 없음", segs[2:]
    else:
        pill, rest = segs[0], segs[1:]
    cls = "up" if any(k in pill for k in ("상승", "신규 진입", "승격", "증가")) else "down" if any(k in pill for k in ("하락", "이탈", "정체")) else "acc" if "추적" in pill else ""
    return f'<span class="vd {cls}">{esc(pill)}</span>' + (f"<small>{esc(' · '.join(rest))}</small>" if rest else "")


RX_NUM_D = re.compile(r"^([\d,—]+) \(([+−][\d,.]*%?)\)$")


def cell_html(col, v):
    if col == "판정":
        return verdict_html(v)
    m = RX_NUM_D.match(v)
    if m:
        return f'{esc(m.group(1))}<span class="d {direction(m.group(2))}">{esc(m.group(2))}</span>'
    return md_links(v)


NUM_COLS = {"리뷰 (1일)", "평점 수 (1일)", "동접", "오너 구간", "추정 판매", "댓글", "평점 수", "점수"}


def table_html(t, solo=True):
    def cls(c):
        return ' class="num"' if c in NUM_COLS or re.fullmatch(r"\d+일", c) else ""
    head = "".join(f"<th{cls(c)}>{esc(c)}</th>" for c in t["cols"])
    rows = "".join("<tr>" + "".join(f"<td{cls(c)}>{cell_html(c, v)}</td>" for c, v in zip(t["cols"], r)) + "</tr>" for r in t["rows"])
    return f'<div class="tbl{" solo" if solo else ""}"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


KEY_COLS = ["#", "게임", "지역 순위", "가격", "리뷰 (1일)", "평점 수 (1일)", "동접", "점수", "판정"]
RX_RK = re.compile(r"^(\d+)(?: \((\d+)→\))?$")


def detail_table_html(t, rep):
    """06 상세: 핵심 열만 보이고 나머지는 게임 칸을 펼치면 나옵니다. 처음 두 열은 고정."""
    cols = t["cols"]
    if "#" not in cols or "게임" not in cols:
        return table_html(t)
    idx = {c: i for i, c in enumerate(cols)}

    def has_value(c):
        i = idx[c]
        return any((r[i] not in ("", "—")) for r in t["rows"] if i < len(r))
    win = [c for c in cols if re.fullmatch(r"\d+일", c) and has_value(c)]
    # 순위·게임을 맨 앞에 고정하고, 나머지 핵심 열은 값이 하나라도 있을 때만 보입니다.
    key = ["#", "게임"] + [c for c in cols if c in KEY_COLS and c not in ("#", "게임") and has_value(c)]
    if win:
        key.insert(key.index("판정") if "판정" in key else len(key), win[0])
    extra = [c for c in cols if c not in key and has_value(c)]
    head = "".join(f'<th{" class=num" if c in NUM_COLS or c in win else ""}>{esc(c)}</th>' for c in key)
    body = []
    for r in t["rows"]:
        cells = []
        for c in key:
            v = r[idx[c]] if idx[c] < len(r) else ""
            if c == "#":
                m = RX_RK.match(v)
                cells.append(f'<td class="rk"><b>{esc(m.group(1))}</b>' + (f"<small>{esc(m.group(2))}→</small>" if m.group(2) else "") + "</td>" if m else f'<td class="rk">{esc(v)}</td>')
            elif c == "게임":
                lm = LINK.search(v)
                name, url = (lm.group(1), lm.group(2)) if lm else (v, "")
                excl = "⊘" in v
                dl = "".join(f"<dt>{esc(ec)}</dt><dd>{md_links(r[idx[ec]])}</dd>" for ec in extra if idx[ec] < len(r) and r[idx[ec]] not in ("", "—"))
                th = thumb_html(name, url, rep) if url else ""
                cells.append(f'<td class="gm"><details><summary><a class="nm" href="{H.escape(url or "#", quote=True)}" target="_blank" rel="noopener">{esc(name)}</a>'
                             + ('<span class="ex" title="본문 제외">⊘ 제외</span>' if excl else "") + f"</summary><dl>{th}{dl}</dl></details></td>")
            else:
                cells.append(f'<td{" class=num" if c in NUM_COLS or c in win else ""}>{cell_html(c, v)}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="tbl"><table class="detail"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


# ---------- 일간 리포트 페이지 (다크 전용, 'Terminal Editorial' 시안. 값은 tokens.json 변수만) ----------
# 첫 화면: 선정 게임 60%(헤드라인 문장 · 캡슐 · 칩 3 · 7일 스파크라인 패널) + 큰 폭 변화 40%. 그 아래 범프 차트 → 01~06.
DAILY_CSS = """
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:var(--t-body-lg-w) var(--t-body-lg) var(--font-body);-webkit-font-smoothing:antialiased}
.wrap{max-width:var(--content-max);margin:0 auto;padding-block:0 64px;padding-left:max(var(--margin),env(safe-area-inset-left,0px));padding-right:max(var(--margin),env(safe-area-inset-right,0px))}
@media(max-width:767px){.wrap{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}}
a{color:var(--primary-light);text-decoration:none}a:hover{text-decoration:underline}
h1,h2,h3,h4{text-wrap:balance}
small{font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body)}

/* 상단 바 */
.appbar{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-lg);height:56px;background:var(--surface);border-bottom:var(--bw) solid var(--line);margin:0 calc(-1*var(--margin));padding:0 var(--margin)}
@media(max-width:767px){.appbar{margin:0 -16px;padding:0 16px}}
.appbar .brand{font:700 var(--t-headline-md) var(--font-display);letter-spacing:var(--t-headline-md-ls);text-transform:uppercase;color:var(--ink)}
.appbar nav{display:flex;gap:var(--sp-lg);height:100%}
.appbar nav a{display:flex;align-items:center;font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);border-bottom:2px solid transparent;margin-bottom:-1px}
.appbar nav a.on{color:var(--rise);border-color:var(--rise)}
.appbar .when{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2);white-space:nowrap}

/* 리포트 머리 */
header.rh{padding:var(--sp-xl) 0 var(--sp-lg);border-bottom:var(--bw) solid var(--line)}
.hrow{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-md);flex-wrap:wrap;margin-bottom:var(--sp-lg)}
.hrow .l,.hrow .r{display:flex;align-items:center;gap:var(--sp-md);flex-wrap:wrap}
.hrow .when{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2)}
h1{margin:0 0 var(--sp-md);font:var(--t-headline-xl-w) var(--t-headline-xl) var(--font-display);letter-spacing:var(--t-headline-xl-ls);text-transform:uppercase;font-synthesis:none}
@media(max-width:767px){h1{font:var(--t-headline-xl-mobile-w) var(--t-headline-xl-mobile) var(--font-display)}}
ul.basis{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:var(--sp-xs) 0;font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);color:var(--ink-2);max-width:100ch}
ul.basis li{padding-right:var(--sp-sm);margin-right:var(--sp-sm);border-right:var(--bw) solid var(--line-strong)}ul.basis li:last-child{border:0}
.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0;margin:var(--sp-lg) 0 0;padding:0;border:var(--bw) solid var(--line)}
.status div{display:flex;flex-direction:column;gap:2px;padding:var(--sp-md);border-right:var(--bw) solid var(--line);min-width:0}
.status div:last-child{border-right:0}
.status dt{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);margin:0}
.status dd{margin:0;font:var(--t-data-lg-w) var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav.toc{display:flex;flex-wrap:wrap;gap:var(--sp-xs) var(--sp-lg);padding:var(--sp-md) 0;border-bottom:var(--bw) solid var(--line)}
nav.toc a{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2)}nav.toc a b{color:var(--rise);margin-right:5px}

/* 첫 화면 */
.top{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:var(--gutter);margin-top:var(--sp-xl);align-items:start}
@media(max-width:1023px){.top{grid-template-columns:1fr}}
.pick{padding:var(--sp-lg);display:flex;flex-direction:column;gap:var(--sp-lg);min-width:0}
.kick{display:flex;align-items:center;gap:var(--sp-sm);flex-wrap:wrap}
h1.hl,h2.hl{display:block;margin:0;font:var(--t-headline-xl-w) var(--t-headline-xl) var(--font-display);letter-spacing:var(--t-headline-xl-ls);text-transform:uppercase;font-synthesis:none;text-wrap:balance}
@media(max-width:767px){h1.hl,h2.hl{font:var(--t-headline-xl-mobile-w) var(--t-headline-xl-mobile) var(--font-display)}.hl br.hb{display:none}}
@media(max-width:600px){.appbar .when{display:none}.appbar{min-width:0}.appbar .brand{white-space:nowrap}.status{grid-template-columns:1fr 1fr}.status dd{white-space:normal;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono)}.hrow .r{width:100%;justify-content:space-between}.chips{grid-template-columns:1fr}.chip{flex-direction:row;align-items:center;gap:var(--sp-md);flex-wrap:wrap}.chip .lbl{flex:1 1 100%}.chip .row{margin:0;flex:1 1 auto}.chip .sub{margin:0;flex:0 0 auto}}
.hl .hi{color:var(--primary-light)}
.hl .ul{color:var(--rise);text-decoration:underline;text-decoration-color:var(--rise-line);text-decoration-thickness:4px;text-underline-offset:5px}
.hl a{color:inherit}
.hero{position:relative;overflow:hidden;border:var(--bw) solid var(--line-strong);background:var(--bg);aspect-ratio:16/9;max-height:460px;max-width:100%;display:block}
.hero .bgl{position:absolute;inset:-10%;background-size:cover;background-position:center;filter:blur(24px) brightness(.6);transform:scale(1.15)}
.hero .img{position:absolute;inset:0;background-size:contain;background-position:center;background-repeat:no-repeat}
body.steam .hero .img{background-size:cover}
.hero .ov{position:absolute;display:flex;gap:var(--sp-sm);flex-wrap:wrap;max-width:calc(100% - 32px)}
.hero .ov.tl{top:var(--sp-lg);left:var(--sp-lg)}.hero .ov.br{bottom:var(--sp-lg);right:var(--sp-lg);justify-content:flex-end}
.hero .ov .lchip{background:rgba(13,17,23,.9)}
.hero .ov .lchip.score{text-transform:none;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);gap:var(--sp-sm)}
.hero .ov .lchip.score::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--rise)}
.hero .ov .lchip.score b{color:var(--rise)}
.pk-sub{margin:0;display:flex;flex-wrap:wrap;gap:var(--sp-sm) var(--sp-md);align-items:center;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink-2)}
.pk-links{margin:0;display:flex;gap:var(--sp-md);flex-wrap:wrap;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono)}
/* 스파크라인 패널 */
.sparkp{background:var(--surface);border:var(--bw) solid var(--line);padding:var(--sp-lg);display:flex;flex-direction:column;gap:var(--sp-md)}
.sparkp .ph{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-md);flex-wrap:wrap;padding-bottom:var(--sp-md);border-bottom:var(--bw) solid var(--line)}
.sparkp .ph .l{display:flex;align-items:center;gap:var(--sp-sm)}
.sparkp .ph .l::before{content:"↗";color:var(--rise);font-weight:700}
.sparkp .ph .r{display:flex;align-items:center;gap:var(--sp-md)}
.sparkp .ph .seclabel.strong{color:var(--ink)}
.side{padding:var(--sp-lg);display:flex;flex-direction:column;gap:var(--sp-lg);min-width:0}
ul.hl{list-style:none;margin:0;padding:0;display:flex;flex-direction:column}
ul.hl li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:var(--sp-md);align-items:center;padding:var(--sp-md) 0;border-top:var(--bw) solid var(--line)}
ul.hl li:first-child{border-top:0;padding-top:0}
ul.hl li.nothumb{grid-template-columns:minmax(0,1fr) auto}
ul.hl .h1{font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display);letter-spacing:var(--t-headline-md-ls);overflow-wrap:break-word;word-break:keep-all}
ul.hl .h1 a{color:var(--ink)}
ul.hl .h2{color:var(--ink-2);font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);margin-top:var(--sp-xs);display:flex;flex-wrap:wrap;gap:0 var(--sp-sm)}ul.hl .h2 span{white-space:nowrap}
ul.hl .big{display:flex;flex-direction:column;align-items:flex-end;gap:var(--sp-xs)}
ul.hl .big .delta{font:700 var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls);padding:var(--sp-xs) var(--sp-sm)}
ul.hl .big small{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);text-align:right;max-width:12ch}
@media(max-width:1200px){ul.hl li .th{width:96px}body.itch ul.hl li .th{width:64px}}
ul.notes{margin:0;padding-left:18px;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink-2)}ul.notes li{margin:var(--sp-xs) 0}
.empty{color:var(--ink-3);font:var(--t-body-md-w) var(--t-body-md) var(--font-body);margin:0}

/* 썸네일: CSS 배경 여러 장(캡슐 → header → 머리글자 SVG). 1px 선, 반지름 0 */
.th{display:block;border:var(--bw) solid var(--line);background-color:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;background-repeat:no-repeat;flex:none;width:120px;aspect-ratio:231/87;max-width:100%}
body.itch .th{aspect-ratio:315/250;width:84px}
.th.xs{width:44px}body.itch .th.xs{width:36px}
@media(max-width:520px){.th{width:96px}body.itch .th{width:72px}}

/* 섹션 */
section{margin-top:var(--section-gap);padding-top:var(--section-gap);border-top:var(--bw) solid var(--line)}
h2{margin:0 0 var(--sp-sm);font:var(--t-headline-lg-w) var(--t-headline-lg) var(--font-display);letter-spacing:var(--t-headline-lg-ls);font-synthesis:none;display:flex;align-items:baseline;gap:var(--sp-md);flex-wrap:wrap}
h2 .no{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);color:var(--rise);border:var(--bw) solid var(--rise-line);background:var(--rise-soft);padding:2px 6px}
.sbasis{color:var(--ink-2);font:var(--t-body-md-w) var(--t-body-md) var(--font-body);margin:0 0 var(--sp-lg);max-width:90ch}
.stext{margin:0 0 var(--sp-md)}
.blocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:var(--gutter);align-items:start}
.block{padding:var(--sp-md) var(--sp-lg) var(--sp-xs)}
.block h4{margin:0 0 var(--sp-sm);font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--rise)}
.block .empty{padding-bottom:var(--sp-sm)}
ul.bul{margin:0;padding-left:20px}ul.bul li{margin:var(--sp-xs) 0}

/* 범프 차트 */
.chartbox{overflow-x:auto;padding-bottom:4px}
.chartbox svg.bump{min-width:720px}
.chartbox svg.lift{min-width:480px}
.movers{display:flex;flex-wrap:wrap;gap:var(--sp-sm) var(--sp-xl);margin:var(--sp-md) 0 0;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2);align-items:center}
.movers>span{display:inline-flex;align-items:center;gap:var(--sp-sm)}
.movers .nm{color:var(--ink);font-weight:600;font-family:var(--font-body)}
.movers b.num{color:var(--ink)}

/* 게임 카드: 썸네일 | 본문. 본문 첫 줄 오른쪽에 델타 칩. */
.g{display:grid;grid-template-columns:auto minmax(0,1fr);gap:var(--sp-md);align-items:start;padding:var(--sp-md) 0;border-top:var(--bw) solid var(--line)}
.block .g:first-of-type{border-top:0;padding-top:var(--sp-xs)}
.g .gb{min-width:0;display:flex;flex-direction:column;gap:var(--sp-xs)}
.g .gh{display:flex;gap:var(--sp-sm);align-items:flex-start;justify-content:space-between}
.g .nm{font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display);letter-spacing:var(--t-headline-md-ls);color:var(--ink);min-width:0;overflow-wrap:break-word;word-break:keep-all}
.g .sub{font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);color:var(--ink-2)}
.g .meta{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2);display:flex;flex-wrap:wrap;gap:0 var(--sp-md)}
.g .meta span{white-space:nowrap}
.kpi{text-align:right;flex:none;display:flex;flex-direction:column;align-items:flex-end;gap:var(--sp-xs)}
.kpi .delta{font:700 var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls)}
.kpi small{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);max-width:16ch;text-align:right}

/* 03 소재·장르: 막대 차트 + 예시 */
.lifts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:var(--gutter)}
.lift{padding:var(--sp-lg);min-width:0}
.lift h4{margin:0 0 var(--sp-xs);font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink)}
.lift .legend{font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);color:var(--ink-2);margin:0 0 var(--sp-md)}
.lift .legend i{display:inline-block;width:12px;height:8px;vertical-align:middle;margin-right:5px;background:var(--line-strong)}
.lift .legend i.hot{background:var(--rise)}
ul.tg-ex{list-style:none;margin:var(--sp-md) 0 0;padding:0;display:flex;flex-direction:column;gap:var(--sp-xs)}
ul.tg-ex li{display:flex;gap:var(--sp-sm);align-items:center;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink-2);padding-top:var(--sp-xs);border-top:var(--bw) solid var(--line)}
ul.tg-ex li b{min-width:9ch;color:var(--ink);font-weight:600}
ul.tg-ex li small{white-space:nowrap;color:var(--ink-3);font-family:var(--font-mono)}

/* 표 (04 · 06): 줄무늬 없음, 1px 선, 숫자 우측 정렬 */
h4.tt{margin:var(--sp-lg) 0 var(--sp-sm);font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display)}
details.dt{margin:var(--sp-md) 0}
details.dt>summary{cursor:pointer;font:600 var(--t-body-md) var(--font-body);padding:var(--sp-sm) var(--sp-md);background:var(--surface);border:var(--bw) solid var(--line);list-style:none;display:flex;justify-content:space-between;gap:var(--sp-sm)}
details.dt>summary::-webkit-details-marker{display:none}
details.dt>summary::after{content:"펼치기";font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);color:var(--rise);flex:none}
details.dt[open]>summary::after{content:"접기"}
.tbl{overflow-x:auto;border:var(--bw) solid var(--line);border-top:0;background:var(--surface);max-height:80vh;overflow-y:auto}
.tbl.solo{border-top:var(--bw) solid var(--line)}
table{border-collapse:separate;border-spacing:0;width:100%;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);background:var(--surface)}
th,td{border-bottom:var(--bw) solid var(--line);padding:var(--sp-sm) var(--sp-md);text-align:left;vertical-align:top;background:var(--surface)}
th{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);background:var(--surface-2);white-space:nowrap;position:sticky;top:0;z-index:2}
td{font-family:var(--font-mono);font-variant-numeric:tabular-nums;white-space:nowrap}
td.num{text-align:right}th.num{text-align:right}
tr:hover td{background:var(--surface-2)}
table.detail th:nth-child(1),table.detail td:nth-child(1){position:sticky;left:0;z-index:1;width:52px;min-width:52px;max-width:52px;text-align:center;padding-left:6px;padding-right:6px}
table.detail th:nth-child(2),table.detail td:nth-child(2){position:sticky;left:52px;z-index:1;border-right:var(--bw) solid var(--line-strong);min-width:200px;max-width:280px;white-space:normal;font-family:var(--font-body)}
table.detail th:nth-child(1),table.detail th:nth-child(2){z-index:3}
td.rk b{font-weight:700}td.rk small{display:block;font-size:11px;color:var(--ink-2);line-height:1.2;font-family:var(--font-mono)}
td.gm details summary{cursor:pointer;list-style:none;display:flex;gap:6px;align-items:baseline;flex-wrap:wrap}
td.gm details summary::-webkit-details-marker{display:none}
td.gm details summary::before{content:"▸";color:var(--ink-3);font-size:12px;flex:none}
td.gm details[open] summary::before{content:"▾"}
td.gm .nm{font-weight:600;line-height:1.35;color:var(--ink)}
td.gm .ex{font-size:12px;color:var(--fall);font-weight:600}
td.gm dl{margin:8px 0 2px 16px;display:grid;grid-template-columns:auto minmax(0,1fr);gap:3px 10px;font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);white-space:normal}
td.gm dl dt{color:var(--ink-2);white-space:nowrap}td.gm dl dd{margin:0;overflow-wrap:anywhere}
td.gm dl .th{grid-column:1/-1;margin-bottom:4px}
.vd{display:inline-block;font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);padding:2px 6px;background:var(--bg);border:var(--bw) solid var(--line);color:var(--ink-2);white-space:nowrap}
.vd.up{color:var(--rise);background:var(--rise-soft);border-color:var(--rise-line)}.vd.down{color:var(--fall);background:var(--fall-soft);border-color:var(--fall-line)}.vd.acc{color:var(--primary-light)}
td .vd+small{color:var(--ink-2);margin-left:6px}
td .d{font-size:12px;margin-left:4px}

footer.pf{margin-top:var(--sp-xl);padding-top:var(--sp-lg);border-top:var(--bw) solid var(--line);color:var(--ink-2);font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls)}
:focus-visible{outline:2px solid var(--rise);outline-offset:2px}
"""


def daily_css(platform):
    return ui.css_vars(platform) + ui.components_css() + DAILY_CSS


# ---------- 헤드라인 문장 · 스탯 칩 ----------

RX_FROM = re.compile(r"^(\d+)위에서$")
GENRE_KO, GENRE_SKIP = headline.GENRE_KO, headline.GENRE_SKIP  # 하위 호환 (사전은 market/headline.py)


def headline_parts(p):
    """선정 게임 헤드라인 조각 (market/headline.game_pick). 방향은 headline.direction 으로."""
    return headline.game_pick(p)


def headline_html(p, link=True):
    return headline.to_html(headline.game_pick(p), link=p.get("url") if link else None)


def pick_chips(p):
    """선정 게임 → 스탯 칩 3개 [(라벨, 값, 단위, 델타 칩 문구, 방향, 보조 줄)].
    우선순위: 순위(+델타) → 동접 또는 리뷰·평점 수 → 가격(+할인)."""
    tiles = pick_tiles(p)
    rank = [t for t in tiles if t[1].endswith("위")]
    vol = [t for t in tiles if t[0] in ("동접", "리뷰", "평점") and not t[1].endswith("★")]
    price = [t for t in tiles if t[0] == "가격"]
    chosen = rank[:1] + vol[:1] + price[:1]
    for t in tiles:
        if len(chosen) >= 3:
            break
        if t not in chosen:
            chosen.append(t)
    out = []
    for lab, val, note in chosen[:3]:
        unit, delta, dirn, sub = "", "", "", ""
        m = RX_FROM.match(note or "")
        if val.endswith("위") and val[:-1].isdigit():
            unit, val = "위", val[:-1]
            lab = f"{lab} RANK"
            if m:
                d = int(m.group(1)) - int(val)
                delta = f"▲ +{d}" if d > 0 else f"▼ {d}" if d < 0 else "변화 없음"
                dirn = "up" if d > 0 else "down" if d < 0 else ""
                sub = f"{m.group(1)}위에서 {'상승' if d > 0 else '하락' if d < 0 else '유지'}"
            else:
                sub = "오늘 순위"
        elif lab == "가격":
            lab = "PRICE"
            if note.startswith("−"):
                delta, dirn, sub = f"할인 {note.lstrip('−')}", "warn", "세일 가격"
            elif note == "세일":
                delta, dirn, sub = "세일", "warn", "세일 중"
            else:
                delta, dirn, sub = "정상가", "", "할인 없음"
        else:
            if lab == "동접":
                lab, unit = "CONCURRENT", "명"
            elif lab in ("리뷰", "평점"):
                lab, unit = ("REVIEWS" if lab == "리뷰" else "RATINGS"), "개"
            elif lab == "댓글":
                unit = "개"
            if note and note != "변화 없음":
                delta = ("▲ " if direction(note) == "up" else "▼ " if direction(note) == "down" else "") + note
                dirn = direction(note)
                sub = "전일 대비"
            else:
                delta, sub = "변화 없음", "전일 대비"
        out.append((lab, val, unit, delta, dirn, sub))
    return out


def chips_html(chips):
    return '<div class="chips">' + "".join(
        f'<div class="chip"><span class="lbl">{esc(l)}</span><div class="row"><span class="val">{esc(v)}' + (f"<small>{esc(u)}</small>" if u else "") + "</span>"
        + (f'<span class="delta {d if d in ("up", "down", "warn") else ""}">{esc(t)}</span>' if t else "")
        + f'</div><p class="sub">{esc(sb)}</p></div>' for l, v, u, t, d, sb in chips) + "</div>"


def hero_html(name, url, rep, it=None, overlays=""):
    """캡슐 이미지 프레임(16:9, 1px 선): 흐린 배경 + 원본, 위에 칩 오버레이. 이미지가 없으면 머리글자 색 블록."""
    srcs, bg = thumb_srcs(url, rep, it, big=True)
    initial = (name or "?").strip()[:1].upper()
    layers = [f"url({quote(u, safe=':/%?=&#.-_~')})" for u in srcs] + [f"url({letter_svg(initial, True)})"]
    base = (f"background-color:{H.escape(bg, quote=True)};" if bg else f"--h:{hue(name)};")
    img = base + "background-image:" + ",".join(layers)
    return (f'<a class="hero" href="{H.escape(url or "#", quote=True)}" target="_blank" rel="noopener" aria-label="{H.escape(name or "", quote=True)}">'
            f'<span class="bgl" style="{img}"></span><span class="img" style="{img}"></span>{overlays}</a>')


def image_hero_html(src, overlays="", name="", url=None, bg=None, cls="hero"):
    """이미지 주소 하나로 만드는 프레임(미디어·주간 등): 흐린 배경 + 원본 가운데. 이미지가 없으면 머리글자 색 블록."""
    initial = (name or "?").strip()[:1].upper()
    layers = ([f"url({quote(src, safe=':/%?=&#.-_~')})"] if src else []) + [f"url({letter_svg(initial, True)})"]
    base = (f"background-color:{H.escape(bg, quote=True)};" if bg else f"--h:{hue(name)};")
    img = base + "background-image:" + ",".join(layers)
    tag = "a" if url else "div"
    href = f' href="{H.escape(url, quote=True)}" target="_blank" rel="noopener"' if url else ""
    return (f'<{tag} class="{cls}"{href} aria-label="{H.escape(name or "", quote=True)}">'
            f'<span class="bgl" style="{img}"></span><span class="img" style="{img}"></span>{overlays}</{tag}>')


def hero_overlays(p):
    """이미지 위 칩: 왼쪽 위 태그 2개 + 배지(초록), 오른쪽 아래 값 칩(7일 리뷰·평점 증가가 있을 때만)."""
    tags = [t for t in (p.get("tags") or []) if t not in headline.GENRE_SKIP][:2]
    chips = []
    if tags:
        chips.append(f'<span class="lchip">{esc(" · ".join(tags))}</span>')
    badges = [b for b in (p.get("badges") or []) if b not in ("본문 제외",)][:2]
    if badges:
        chips.append(f'<span class="lchip" style="color:var(--primary-light)">{esc(" · ".join(badges))}</span>')
    tl = f'<span class="ov tl">{"".join(chips)}</span>' if chips else ""
    br = ""
    for seg in split_dots(p.get("line", "")):
        m = RX_SEG_WIN.match(seg)
        if m:
            kind = "리뷰" if any(x.startswith("리뷰") for x in split_dots(p.get("line", ""))) else "평점"
            br = f'<span class="ov br"><span class="lchip score">{esc(m.group(1))} {kind} <b>{esc(m.group(2))}</b></span></span>'
            break
    return tl + br


def day_labels(n):
    return [f"D-{n - 1 - i}" if i < n - 1 else "TODAY" for i in range(n)]


def spark_panel_html(rep, scale="web", width=700, height=170, uid="sp"):
    """7일 스파크라인 패널: 머리(라벨 · 단위 · NEW PEAK) + 차트(점 아래 순위·D-n 라벨)."""
    sr = (rep.get("series") or {}).get("pick")
    if not sr or not any(v is not None for v in sr.get("ranks") or []):
        return ""
    ranks = sr["ranks"]
    vals = [v for v in ranks if v is not None]
    n = len(ranks)
    peak = len(vals) >= 2 and ranks[-1] is not None and ranks[-1] == min(vals) and ranks[-1] < vals[-2] if len(vals) >= 2 else False
    svg = charts.sparkline(ranks, width=width, height=height, scale=scale, invert=True, labels=day_labels(n), uid=uid,
                           title=f"{sr['list_ko']} {n}일 순위")
    head = (f'<div class="ph"><div class="l"><p class="seclabel strong">{n}-DAY {esc(sr["list_ko"])} RANK</p></div>'
            f'<div class="r"><p class="seclabel">단위: 순위 (역축)</p>' + ('<span class="lchip pos">NEW PEAK</span>' if peak else "") + "</div></div>")
    return f'<div class="sparkp">{head}{svg}</div>'


def pick_html(p, rep):
    pills, more = badges_html(p.get("badges", []), limit=4)
    sub = " · ".join(x for x in [p.get("sub") or ""] + more if x)
    streak = f"{p['streak']}일 연속 선정" if p["streak"] > 1 else "오늘의 선정 게임"
    links = " ".join(f'<a href="{H.escape(u, quote=True)}" target="_blank" rel="noopener">{esc(t)} ↗</a>' for t, u in p["links"])
    sr = (rep.get("series") or {}).get("pick") or {}
    return (f'<article class="panel pick"><div class="kick"><span class="lchip pos">{esc(streak)}</span>'
            + (f'<span class="seclabel">{esc(sr.get("list_ko", ""))} · {rep["round"]}회차</span>' if sr else "") + "</div>"
            + f'<h2 class="hl">{headline_html(p)}</h2>'
            + hero_html(p["name"], p["url"], rep, p, hero_overlays(p))
            + f'<p class="pk-sub">' + (f"<span>{esc(sub)}</span>" if sub else "") + pills + "</p>"
            + chips_html(pick_chips(p)) + spark_panel_html(rep)
            + f'<p class="pk-links">{links}</p></article>')


def headline_li(text, rep):
    info = headline_info(text)
    th = thumb_html(info["name"], info["url"], rep) if info["url"] else ""
    meta = [strip_links(x) for x in info["rest"]]
    big = ""
    if info["hero"]:
        big = (f'<div class="big"><span class="delta {info["dirn"]}">{esc(info["hero"])}</span>'
               + (f'<small>{esc(info["cap"])}</small>' if info["cap"] else "") + "</div>")
    name = (f'<a href="{H.escape(info["url"], quote=True)}" target="_blank" rel="noopener">{esc(info["name"])}</a>' if info["url"] else esc(info["name"]))
    return (f'<li class="{"" if th else "nothumb"}">{th}<div><div class="h1">{name}</div>'
            + (f'<div class="h2">{"".join(f"<span>{esc(x)}</span>" for x in meta if x)}</div>' if meta else "") + f"</div>{big}</li>")


def side_html(rep):
    hl = rep.get("headline") or []
    body = '<ul class="hl">' + "".join(headline_li(x, rep) for x in hl) + "</ul>" if hl else '<p class="empty">없음</p>'
    notes = rep.get("notes") or []
    nh = '<ul class="notes">' + "".join(f"<li>{md_links(x)}</li>" for x in notes) + "</ul>" if notes else '<p class="empty">없음</p>'
    return (f'<aside class="panel side"><div><p class="seclabel" style="margin-bottom:var(--sp-md)">BIG MOVERS · 큰 폭 변화</p>{body}</div>'
            f'<div><p class="seclabel" style="margin-bottom:var(--sp-sm)">NOTES · 특이사항</p>{nh}</div></aside>')


# ---------- 범프 차트 섹션 ----------

def bump_pick(rep):
    """범프 차트에서 강조할 이름과 보조 이름. (highlight, secondary[], 강조 설명)
    강조 = 오늘의 선정 게임(Top 안에 있으면) → 창 안에서 가장 크게 오른 게임 → 오늘 1위. 보조 = 가장 크게 내린 게임, 오늘 1위."""
    sr = rep.get("series") or {}
    bump = sr.get("bump") or {}
    names = list((bump.get("series") or {}).keys())
    if not names:
        return None, [], ""
    ser = bump["series"]

    def climb(name):
        vals = [v for v in ser[name] if v is not None]
        return (vals[0] - vals[-1]) if len(vals) >= 2 else 0

    def today(name):
        return ser[name][-1] if ser[name][-1] is not None else 999
    first = min(names, key=today)
    p = rep.get("pick")
    if p and p["name"] in ser:
        hi, why = p["name"], "오늘의 선정 게임"
    else:
        best = max(names, key=climb)
        if climb(best) > 0:
            hi, why = best, "이 중 가장 크게 오른 게임"
        else:
            hi, why = first, "오늘 1위"
    sec = []
    worst = min(names, key=climb)
    if worst != hi and climb(worst) < 0:
        sec.append(worst)
    if first != hi and first not in sec:
        sec.append(first)
    return hi, sec[:3], why


def movers_html(rep, cls="movers"):
    sr = rep.get("series") or {}
    out = []
    for key, arrow, c, word in (("biggest_up", "▲", "up", "가장 크게 오른"), ("biggest_down", "▼", "down", "가장 크게 내린")):
        m = sr.get(key)
        if m:
            name, a, b, d = m
            out.append(f'<span><span class="delta {c}">{arrow} {"+" if d > 0 else ""}{d}</span><span class="nm">{esc(name)}</span>'
                       f'<b class="num">{a}→{b}위</b><span class="seclabel">{word} 게임</span></span>')
        else:
            out.append(f'<span><span class="delta">{arrow} —</span><span class="seclabel">{word} 게임 없음</span></span>')
    return f'<p class="{cls}">{"".join(out)}</p>'


def bump_section_html(rep):
    sr = rep.get("series") or {}
    bump = sr.get("bump") or {}
    if not bump.get("series"):
        return ""
    hi, sec, why = bump_pick(rep)
    svg = charts.bump_chart(bump["series"], bump["days"], highlight=hi, secondary=sec, width=1112, height=440, scale="web",
                            n=bump.get("n", 10), label_chars=22, title=f"{bump['list_ko']} Top {bump.get('n', 10)} 순위 이동")
    n_days = bump.get("n_days") or len(bump.get("days") or [])
    basis = (f"{bump['list_ko']} 오늘 Top {bump.get('n', 10)} 게임의 {n_days}일 순위. "
             + ("7일치가 아직 안 쌓여 있는 만큼만 그렸습니다. " if n_days < 7 else "")
             + f"초록 굵은 선 = {why}, 흰 선 = 1위와 가장 크게 내린 게임, 맨 아래 줄 = {bump.get('n', 10)}위 밖.")
    return (f'<section id="s00"><h2><span class="no">7-DAY</span>이번 주 순위 이동 · {esc(bump["list_ko"])} {bump.get("n", 10)}</h2>'
            f'<p class="sbasis">{esc(basis)}</p><div class="panel" style="padding:var(--sp-lg)"><div class="chartbox">{svg}</div>{movers_html(rep)}</div></section>')


# ---------- 03 소재·장르 막대 ----------

def tag_rows(t):
    """태그 표 → [(태그, 개수, 배율|None, [(예시 이름, 주소)], 연속 회차)]."""
    rows = []
    for r in t["rows"]:
        name, cnt, base, mult, ex, st = (r + [""] * 6)[:6]
        m = RX_CNT.match(cnt)
        n = int(m.group(1)) if m else 0
        mv = float(mult.rstrip("×")) if mult.rstrip("×").replace(".", "", 1).isdigit() else None
        stn = int(st.replace("회차", "")) if st.replace("회차", "").isdigit() else 0
        rows.append((name, n, mv, LINK.findall(ex), stn))
    return rows


def lift_html(t, rep, rows_n=8):
    rows = tag_rows(t)
    if not rows:
        return f'<div class="panel lift"><h4>{esc(t.get("title") or t["cols"][0])}</h4><p class="empty">해당 없음</p></div>'
    svg = charts.bar_lift([(n, c, m) for n, c, m, _, _ in rows], width=560, height=max(40 * min(len(rows), rows_n), 120), scale="web",
                          max_rows=rows_n, label_chars=16, title=f"{t['cols'][0]}별 상승 게임 수와 배율")
    ex = "".join(f'<li><b>{esc(n)}</b><span class="pills">{"".join(thumb_html(tt, u, rep, cls="th xs") for tt, u in e[:3])}</span>'
                 + (f'<small>{st}회차 연속</small>' if st >= 2 else "") + "</li>" for n, _, _, e, st in rows[:rows_n] if e)
    return (f'<div class="panel lift"><h4>{esc(t.get("title") or t["cols"][0])} · TOP {min(len(rows), rows_n)}</h4>'
            f'<p class="legend"><i></i>막대 = 상승 묶음 안 게임 수 · 점 = 전체 모집단 대비 배율 · <i class="hot"></i>1.5× 이상 = 지금 특히 뜨는 것</p>'
            f'<div class="chartbox">{svg}</div>' + (f'<ul class="tg-ex">{ex}</ul>' if ex else "") + "</div>")


# ---------- 게임 카드(01·02·04 블록) ----------

def game_card(it, rep):
    hero, cap, dirn, rest = key_metric(it.get("line", ""))
    pills, more = badges_html(it.get("badges", []))
    meta = rest + more
    kpi = f'<div class="kpi"><span class="delta {dirn}">{esc(hero)}</span><small>{esc(cap)}</small></div>' if hero else ""
    return (f'<article class="g">{thumb_html(it["name"], it.get("url"), rep, it)}<div class="gb">'
            f'<div class="gh"><a class="nm" href="{H.escape(it.get("url") or "#", quote=True)}" target="_blank" rel="noopener">{esc(it["name"])}</a>{kpi}</div>'
            + pills
            + (f'<div class="sub">{esc(it["sub"])}</div>' if it.get("sub") else "")
            + (f'<div class="meta">{dots_html(meta)}</div>' if meta else "")
            + "</div></article>")


def block_html(b, rep):
    body = "".join(game_card(it, rep) for it in b["items"]) if b["items"] else '<p class="empty">해당 없음</p>'
    return f'<div class="panel block"><h4>{esc(b["title"])}</h4>{body}</div>'


# ---------- 페이지 ----------

def section_html(s, rep):
    body = []
    if s.get("text"):
        body.append(f'<p class="stext">{md_links(s["text"])}</p>')
    if s.get("blocks"):
        body.append('<div class="blocks">' + "".join(block_html(b, rep) for b in s["blocks"]) + "</div>")
    if s.get("list") is not None:
        body.append('<ul class="bul">' + "".join(f"<li>{md_links(x)}</li>" for x in s["list"]) + "</ul>" if s["list"] else '<p class="empty">없음</p>')
    lifts = [t for t in (s.get("tables") or []) if is_tag_table(t)]
    if lifts:
        body.append('<div class="lifts">' + "".join(lift_html(t, rep) for t in lifts) + "</div>")
    for t in s.get("tables") or []:
        if is_tag_table(t):
            continue
        elif s["no"] == "06":
            body.append(f'<details class="dt"><summary>{esc(t["title"])}</summary>{detail_table_html(t, rep)}</details>')
        else:
            body.append((f'<h4 class="tt">{esc(t["title"])}</h4>' if t.get("title") else "") + table_html(t))
    if not body:
        body.append('<p class="empty">이번 회차에는 해당 항목이 없습니다.</p>')
    return (f'<section id="s{s["no"]}"><h2><span class="no">{s["no"]}</span>{esc(s["title"])}</h2>'
            + (f'<p class="sbasis">{md_links(s["basis"])}</p>' if s.get("basis") else "") + "".join(body) + "</section>")


PLATFORM_TAG = {"steam": "Indie Trending · Steam", "itch": "Indie Trending · itch.io"}
PLATFORM_NAV = (("steam", "Steam"), ("itch", "itch.io"))


def to_html(rep):
    p = rep.get("pick")
    pick = pick_html(p, rep) if p else '<div class="panel side"><p class="empty">오늘은 선정 게임이 없습니다.</p></div>'
    status = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in rep["status"] if v not in (None, "", "—"))
    basis = "".join(f"<li>{esc(x)}</li>" for x in split_dots(rep["basis_line"]))
    toc = "".join(f'<a href="#s{s["no"]}"><b>{s["no"]}</b>{esc(s["title"])}</a>' for s in rep["sections"])
    secs = "".join(section_html(s, rep) for s in rep["sections"])
    title = f"{rep['platform_ko']} 트렌딩 · {rep['date']}"
    platform = rep["platform"]
    nav = "".join(f'<a class="{"on" if k == platform else ""}" href="../{k}/{rep["date"]}.html">{n}</a>' for k, n in PLATFORM_NAV)
    return f"""<!doctype html>
<html lang="ko" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
{ui.font_links()}
<style>{daily_css(platform)}</style></head>
<body class="{esc(platform)}"><div class="wrap">
<div class="appbar"><div style="display:flex;align-items:center;gap:var(--sp-lg);height:100%"><span class="brand">Indie Trending</span><nav>{nav}</nav></div><span class="when">{esc(date_ko(rep['date']))} · {rep['round']}회차</span></div>
<header class="rh"><div class="hrow"><div class="l"><span class="ptag">{esc(PLATFORM_TAG.get(platform, platform))}</span><span class="seclabel">Daily Report</span></div>
<div class="r"><span class="when">{esc(rep['date'])}</span><span class="lchip ghost">Edition #{rep['round']:02d}</span></div></div>
<h1>{esc(rep['platform_ko'])} 트렌딩 · {date_ko(rep['date'])}</h1>
<ul class="basis">{basis}</ul><dl class="status">{status}</dl></header>
<nav class="toc">{toc}</nav>
<div class="top">{pick}{side_html(rep)}</div>
{bump_section_html(rep)}
{secs}
<footer class="pf">{esc(rep['collect_line'])} · 생성 {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>모든 판매·매출 숫자는 추정치이며 게임 간 비교 용도입니다.</footer>
</div></body></html>"""


# ====================================================================
# Discord 임베드·이미지 카드용 (notify.py, cards.py). to_md / to_html 은 건드리지 않습니다.
# ====================================================================

STEAM_HEADER = "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"


def strip_links(s):
    """'[이름](주소)' → '이름'. 이미지 카드처럼 링크가 의미 없는 곳에 씁니다."""
    return LINK.sub(r"\1", s or "")


def thumb_url(url, rep, it=None):
    """Discord 임베드에 넣을 이미지 주소 하나. itch 는 분석기가 넘긴 thumb, Steam 은 header.jpg."""
    if it and it.get("thumb"):
        return it["thumb"]
    t = (rep.get("thumbs") or {}).get(url) or {}
    if t.get("src"):
        return t["src"]
    m = STEAM_APP.search(url or "")
    return STEAM_HEADER.format(appid=m.group(1)) if m else ""


def pick_tiles(p):
    """선정 게임 line → [(라벨, 값, 비고)] 핵심 수치 타일. pick_html 과 같은 규칙."""
    hero, cap, _, rest = key_metric(p.get("line", ""))
    tiles = []
    if hero:
        lab, _, note = cap.partition(" · ")
        tiles.append((lab, hero, note))
    for seg in rest:
        lab, val, note = seg_tile(seg)
        if lab:
            tiles.append((lab, val, "변화 없음" if note == "0" else note))
    return tiles


RX_LABELED = re.compile(r"^(.+?) ([+−]\d[\d,.]*%?)(?: \((.+?)\))?$")


def headline_info(text):
    """큰 폭 변화 한 줄 → dict(name, url, hero, cap, dirn, rest). 첫 조각의 링크를 떼고 나머지를 key_metric 으로 읽습니다."""
    segs = split_dots(text)
    first, rest = (segs[0] if segs else ""), segs[1:]
    m = LINK.search(first)
    if m:
        name, url = m.group(1), m.group(2)
        metric = (first[:m.start()] + first[m.end():]).strip()
    else:
        name, url, metric = first, "", ""
    hero, cap, dirn, rest2 = key_metric(" · ".join([metric] + rest) if metric else " · ".join(rest))
    if not hero and metric:
        m = RX_LABELED.match(metric)
        if m:
            hero, cap, dirn, rest2 = m.group(2), m.group(1) + (f" ({m.group(3)})" if m.group(3) else ""), direction(m.group(2)), rest
    if not metric and not hero:
        rest2 = rest
    return {"name": name, "url": url, "hero": hero, "cap": cap, "dirn": dirn, "rest": rest2}


def tag_top(rep, n=3):
    """03 섹션의 첫 태그 표에서 위 n 줄 → (섹션 제목, 열 이름, [(이름, 개수 문구, 전체 비율, 배율, [(예시 이름, 주소)])])."""
    for s in rep.get("sections") or []:
        for t in s.get("tables") or []:
            if is_tag_table(t) and t["rows"]:
                rows = [(r[0], r[1], r[2], r[3], LINK.findall(r[4] if len(r) > 4 else "")) for r in t["rows"][:n]]
                return s["title"], t["cols"][0], rows
    return None


# ---------- 옛 카드 CSS (라이트, 개인·미디어 렌더러가 아직 가져다 씀. 일간 카드는 아래 DAILY_CARD_CSS) ----------

CARD_CSS = """
*{box-sizing:border-box}
html,body{margin:0;width:1080px;height:1350px;overflow:hidden}
body{background:#F3F4F7;color:#14161C;font-family:"IBM Plex Sans KR","Apple SD Gothic Neo","Noto Sans CJK KR","Noto Sans KR","Malgun Gothic",sans-serif;
font-size:32px;line-height:1.45;-webkit-font-smoothing:antialiased;word-break:keep-all;overflow-wrap:anywhere}
.card{width:1080px;height:1350px;padding:70px 72px 52px;display:flex;flex-direction:column;position:relative;background:linear-gradient(180deg,#FFFFFF 0%,#F4F5F9 100%)}
.card::before{content:"";position:absolute;left:0;top:0;right:0;height:18px;background:#33409E}
.top{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px}
.eyebrow{font-size:26px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:#33409E}
.page{font-size:26px;color:#8891A0;font-variant-numeric:tabular-nums}
h1{font-size:62px;line-height:1.15;margin:0;font-weight:700;letter-spacing:-.015em}
.date{font-size:34px;color:#4E5768;margin:6px 0 0}
.body{flex:1;min-height:0;display:flex;flex-direction:column;margin-top:34px}
.lbl{font-size:26px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#4E5768;margin:0 0 16px}
.foot{margin-top:auto;padding-top:22px;border-top:2px solid #DDE1E8;font-size:24px;color:#8891A0;display:flex;justify-content:space-between;gap:24px}
.foot span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.up{color:#146C43}.down{color:#B3261E}
.empty{color:#8891A0;font-size:34px;margin:40px 0}
.th{display:block;border-radius:16px;background-color:hsl(var(--h,220) 48% 74%);background-size:cover;background-position:center;background-repeat:no-repeat;flex:none;aspect-ratio:616/353;width:800px;box-shadow:0 10px 30px rgba(20,22,28,.14)}
.hero{display:flex;justify-content:center}
body.itch .th{aspect-ratio:315/250;width:500px}
.body>*{flex:none}
.th.sm{width:300px;border-radius:12px;box-shadow:0 4px 14px rgba(20,22,28,.12)}body.itch .th.sm{width:190px}
.th.xs{width:190px;border-radius:10px;box-shadow:none}body.itch .th.xs{width:140px}
/* 표지 */
.name{font-size:56px;line-height:1.2;font-weight:700;margin:30px 0 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sub{font-size:30px;color:#4E5768;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pills{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}
.badge{font-size:26px;font-weight:500;line-height:1.5;padding:4px 18px;border:2px solid #BFC6D1;border-radius:999px;color:#4E5768;white-space:nowrap}
.badge.new{color:#146C43;border-color:transparent;background:#E3F3E9}.badge.excl{color:#B3261E;border-color:transparent;background:#FBEAE8}
.badge.disc{color:#7F5A00;border-color:transparent;background:#FBF1DC}.badge.acc{color:#33409E;border-color:transparent;background:#EBEDF9}
.tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;margin-top:30px}
.tile{background:#FFFFFF;border:2px solid #DDE1E8;border-radius:16px;padding:20px 24px 18px;min-width:0;margin:0}
.tile dt{font-size:26px;color:#4E5768;margin:0 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile dd{margin:0;font-size:58px;font-weight:700;line-height:1.1;font-variant-numeric:tabular-nums;letter-spacing:-.02em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile dd small{display:block;font-size:26px;font-weight:500;color:#4E5768;margin-top:6px;letter-spacing:0}
/* 큰 폭 변화 */
.row{display:grid;grid-template-columns:auto minmax(0,1fr);gap:30px;align-items:center;padding:30px 0;border-top:2px solid #DDE1E8}
.row:first-child{border-top:0;padding-top:10px}
.rb{min-width:0;display:flex;flex-direction:column;gap:6px}
.rh{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}
.nm{font-size:42px;font-weight:700;line-height:1.25;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.kpi{font-size:64px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums;letter-spacing:-.02em;white-space:nowrap;flex:none;padding-top:4px}
.cap{font-size:30px;color:#4E5768;line-height:1.35}
.meta{font-size:28px;color:#8891A0;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* 특이사항 */
.note{padding:28px 0;border-top:2px solid #DDE1E8;display:grid;grid-template-columns:auto minmax(0,1fr);gap:22px}
.note:first-child{border-top:0;padding-top:6px}
.note .dot{width:18px;height:18px;border-radius:50%;background:#33409E;margin-top:16px}
.n1{font-size:34px;font-weight:600;line-height:1.4}
.n2{font-size:28px;color:#4E5768;line-height:1.45;margin-top:6px}
/* 태그 Top 3 */
.tag{display:grid;grid-template-columns:64px minmax(0,1fr) auto;gap:0 22px;align-items:center;padding:30px 0;border-top:2px solid #DDE1E8}
.tag:first-child{border-top:0;padding-top:6px}
.tag .rk{font-size:44px;font-weight:700;color:#BFC6D1;font-variant-numeric:tabular-nums}
.tag .tn{font-size:44px;font-weight:700;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tag .ts{font-size:28px;color:#4E5768;margin-top:4px}
.tag .mult{font-size:64px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.02em;color:#4E5768}
.tag .mult.hot{color:#146C43}
.tag .ex{grid-column:2/4;display:flex;gap:14px;margin-top:18px}
"""



# ---------- 일간 이미지 카드 (1080×1350, 'Terminal Editorial' 시안 screen.png 기준, 값은 tokens.json) ----------
# 4장: 표지(메타 줄 · 초록 칩 라벨 · 대문자 헤드라인 2줄 · 캡슐 16:9 + 오버레이 칩 · 스탯 칩 3 · 7일 스파크라인 패널)
#      → 범프 차트 → 소재·장르 막대 → 큰 폭 변화. 반지름 0, 그림자 없음, 1px 선, 모노 라벨.
DAILY_CARD_CSS = """
.kick{display:flex;align-items:center;gap:var(--sp-sm);flex-wrap:wrap}
.hl{margin:0;font:var(--t-headline-xl-w) var(--t-headline-xl) var(--font-display);letter-spacing:var(--t-headline-xl-ls);text-transform:uppercase;color:var(--ink);font-synthesis:none;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.hl .hi{color:var(--primary-light)}
.hl .ul{color:var(--rise);text-decoration:underline;text-decoration-color:var(--rise-line);text-decoration-thickness:4px;text-underline-offset:6px}
.hl .dn{color:var(--fall);text-decoration:underline;text-decoration-color:var(--fall-line);text-decoration-thickness:4px;text-underline-offset:6px}
.hero{position:relative;overflow:hidden;border:var(--bw) solid var(--line-strong);background:var(--bg);width:100%;height:var(--cover-max-h);display:block}
.hero .bgl{position:absolute;inset:-10%;background-size:cover;background-position:center;filter:blur(24px) brightness(.6);transform:scale(1.15)}
.hero .img{position:absolute;inset:0;background-size:contain;background-position:center;background-repeat:no-repeat}
body.steam .hero .img{background-size:cover}
.hero .ov{position:absolute;display:flex;gap:var(--sp-sm);flex-wrap:wrap;max-width:calc(100% - 32px)}
.hero .ov.tl{top:16px;left:16px}.hero .ov.br{bottom:16px;right:16px;justify-content:flex-end}
.hero .ov .lchip{background:rgba(13,17,23,.9)}
.hero .ov .lchip.score{text-transform:none;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);gap:var(--sp-sm);padding:6px 12px}
.hero .ov .lchip.score::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--rise)}
.hero .ov .lchip.score b{color:var(--rise)}
.sparkp{background:var(--surface);border:var(--bw) solid var(--line);padding:var(--sp-lg) 24px;display:flex;flex-direction:column;gap:var(--sp-md)}
.sparkp .ph{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-md);padding-bottom:var(--sp-md);border-bottom:var(--bw) solid var(--line)}
.sparkp .ph .l{display:flex;align-items:center;gap:var(--sp-sm)}
.sparkp .ph .l::before{content:"↗";color:var(--rise);font-weight:700}
.sparkp .ph .r{display:flex;align-items:center;gap:var(--sp-md)}
.sparkp .ph .seclabel.strong{color:var(--ink)}
/* 범프·막대 패널 */
.chartp{background:var(--surface);border:var(--bw) solid var(--line);padding:24px;display:flex;flex-direction:column;gap:var(--sp-md);flex:1 1 auto;min-height:0}
.chartp .ph{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-md);padding-bottom:var(--sp-md);border-bottom:var(--bw) solid var(--line)}
.chartp .ph .seclabel.strong{color:var(--ink)}
.chartp .body{flex:1 1 auto;min-height:0;display:flex;align-items:center}
.movers{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-md);margin:0}
.movers>span{display:flex;flex-direction:column;gap:var(--sp-xs);background:var(--bg);border:var(--bw) solid var(--line);padding:var(--sp-md) var(--sp-lg);min-width:0}
.movers .seclabel{order:-1}
.movers .nm{font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display);letter-spacing:var(--t-headline-md-ls);color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.movers b.num{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2)}
.movers .delta{align-self:flex-start;font:700 var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls)}
.lines{margin:0;display:flex;flex-direction:column;gap:var(--sp-xs);font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2)}
.lines p{margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lines b{color:var(--ink);font-weight:600}
.lines i{display:inline-block;width:12px;height:8px;vertical-align:middle;margin-right:6px;background:var(--line-strong)}
.lines i.hot{background:var(--rise)}
/* 큰 폭 변화 */
.rows{display:flex;flex-direction:column;background:var(--surface);border:var(--bw) solid var(--line);flex:1 1 auto;justify-content:space-evenly}
.row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:32px;align-items:center;padding:32px;border-top:var(--bw) solid var(--line)}
.row:first-child{border-top:0}
.row .th{display:block;border:var(--bw) solid var(--line-strong);background-color:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;width:280px;aspect-ratio:616/353}
body.itch .row .th{width:190px;aspect-ratio:315/250}
.row .nm{margin:0;font:var(--t-headline-lg-w) var(--t-headline-lg) var(--font-display);letter-spacing:var(--t-headline-lg-ls);text-transform:uppercase;color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.row .cap{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2);margin:var(--sp-sm) 0 0;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.row .big{display:flex;flex-direction:column;align-items:flex-end;gap:var(--sp-sm)}
.row .big .delta{font:var(--t-data-xl-w) var(--t-data-xl) var(--font-mono);letter-spacing:var(--t-data-xl-ls);padding:var(--sp-sm) var(--sp-md)}
.row .big small{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);text-align:right;max-width:18ch}
.empty{color:var(--ink-3);font:var(--t-body-lg-w) var(--t-body-lg) var(--font-body);margin:auto 0}
"""


def card_inner_width():
    T = ui.tokens()
    return T["카드"]["폭"] - 2 * T["간격"]["카드_여백"]


def card_page(platform, tag, kind, when, edition, body, i, n, link=None, fallback_see="", extra_css="", title=""):
    """모든 리포트가 공유하는 카드 틀. platform 은 tokens 의 색 키(steam·itch·media·personal), tag 는 상단 라벨("Indie Trending · Weekly"),
    kind 는 그 옆 회색 라벨("Daily Report"), when 은 오른쪽 날짜 문구, edition 은 회차 숫자(없으면 None).
    푸터: 링크가 있으면 "■ 자세히 보기 → indie-trending <주소>", 없으면 fallback_see. 오른쪽 "i / n"."""
    see = (f'<span class="see">자세히 보기 → indie-trending <span>{esc(link.split("://", 1)[-1])}</span></span>' if link
           else f'<span class="see">{esc(fallback_see or tag)}</span>')
    ed = f'<span class="sep">|</span><span class="lchip ghost">Edition #{edition:02d}</span>' if edition is not None else ""
    return f"""<!doctype html>
<html lang="ko" data-theme="dark"><head><meta charset="utf-8"><title>{esc(title or tag)} {i}/{n}</title>
{ui.font_links()}
<style>{ui.card_head_css(platform)}{DAILY_CARD_CSS}{extra_css}</style></head>
<body class="{esc(platform)}"><div class="cardframe">
<div class="cardhead"><div class="l"><span class="ptag">{esc(tag)}</span><span class="seclabel">{esc(kind)}</span></div>
<div class="r"><span class="when">{esc(when)}</span>{ed}</div></div>
{body}
<div class="cardfoot">{see}<span class="pg">{i} / {n}</span></div>
</div></body></html>"""


def _card_page(rep, body, i, n, link=None):
    return card_page(rep["platform"], PLATFORM_TAG.get(rep["platform"], rep["platform"]), "Daily Report",
                     f"{date_ko(rep['date'])} · {rep['round']}회차", rep["round"], body, i, n, link,
                     fallback_see=f"{rep['platform_ko']} 트렌딩 · {date_ko(rep['date'])}", title=f"{rep['platform_ko']} {rep['date']}")


def _title_block(kick, kick_sub, title):
    return (f'<div class="cardtitle"><div class="kick"><span class="lchip pos">{esc(kick)}</span>'
            + (f'<span class="seclabel">{esc(kick_sub)}</span>' if kick_sub else "") + f'</div><h2>{title}</h2></div>')


def _cover_card(rep):
    p = rep.get("pick")
    w = card_inner_width()
    if not p:
        hl = rep.get("headline") or []
        first = strip_links(split_dots(hl[0])[0]) if hl else ""
        return _title_block("NO PICK", "", "오늘은 선정 게임이 없습니다") + (f'<div class="lines"><p>큰 폭 변화 · <b>{esc(first)}</b></p></div>' if first else "") + '<div class="grow"></div>'
    sr = (rep.get("series") or {}).get("pick") or {}
    dirn = headline.direction(headline_parts(p))
    kick = "BREAKOUT" if dirn == "up" else "PICK OF THE DAY"
    kick_sub = (f"{p['streak']}일 연속 선정" if p.get("streak", 1) > 1 else "오늘의 선정 게임") + (f" · {sr['list_ko']}" if sr else "")
    return (f'<div class="cardtitle"><div class="kick"><span class="lchip pos">{kick}</span><span class="seclabel">{esc(kick_sub)}</span></div>'
            f'<h1 class="hl">{headline_html(p, link=False)}</h1></div>'
            + hero_html(p["name"], p["url"], rep, p, hero_overlays(p))
            + chips_html(pick_chips(p)) + spark_panel_html(rep, scale="card", width=w - 48, height=168, uid="cover"))


def _bump_card(rep):
    sr = rep.get("series") or {}
    bump = sr.get("bump") or {}
    if not bump.get("series"):
        return None
    hi, sec, why = bump_pick(rep)
    w = card_inner_width() - 48
    svg = charts.bump_chart(bump["series"], bump["days"], highlight=hi, secondary=sec, width=w, height=720, scale="card",
                            n=bump.get("n", 10), label_chars=22, title=f"{bump['list_ko']} Top {bump.get('n', 10)}")
    n_days = bump.get("n_days") or len(bump.get("days") or [])
    return (_title_block("RANK TRAJECTORY", f"{bump['list_ko']} Top {bump.get('n', 10)} · {n_days}일치", "이번 주 순위 이동")
            + f'<div class="chartp"><div class="ph"><p class="seclabel strong">{n_days}-DAY {esc(bump["list_ko"])} TOP {bump.get("n", 10)}</p>'
            f'<p class="seclabel">초록 = {esc(why)} · 흰 선 = 1위 · 가장 크게 내린 게임 · 맨 아래 줄 = {bump.get("n", 10)}위 밖</p></div>'
            f'<div class="body">{svg}</div></div>' + movers_html(rep))


def _tags_card(rep):
    tables = [t for s in rep.get("sections") or [] for t in (s.get("tables") or []) if is_tag_table(t) and t["rows"]]
    if not tables:
        return None
    w = card_inner_width() - 48
    main = tables[0]
    rows = tag_rows(main)
    extra = tables[1:]
    n_rows = 8 if not extra else 6
    h = min(760, 100 * min(len(rows), n_rows))
    svg = charts.bar_lift([(n, c, m) for n, c, m, _, _ in rows], width=w, height=h, scale="card", max_rows=n_rows, label_chars=22,
                          title=f"{main['cols'][0]}별 상승 게임 수")
    hot = [(n, e) for n, c, m, e, _ in rows[:n_rows] if m is not None and m >= 1.5]
    lines = ['<p><i></i>막대 = 상승 묶음 안 게임 수 · ■ 점 = 전체 모집단 대비 배율 · <i class="hot"></i>1.5× 이상 = 지금 특히 뜨는 것</p>']
    if hot:
        n, e = hot[0]
        lines.append(f'<p><b>{esc(n)}</b> 예시 · {esc(" · ".join(t for t, _ in e[:3]))}</p>')
    for t in extra[:2]:
        rr = tag_rows(t)[:3]
        lines.append(f'<p><b>{esc(t.get("title") or t["cols"][0])}</b> · ' + esc(" · ".join(f"{n} {c}개 {('%.1f' % m).rstrip('0').rstrip('.') + '×' if m is not None else ''}" for n, c, m, _, _ in rr)) + "</p>")
    return (_title_block("TAG LIFT", f"{main['cols'][0]} Top {min(len(rows), n_rows)} · 상승 묶음 기준", "소재·장르 뜨는 것")
            + f'<div class="chartp"><div class="ph"><p class="seclabel strong">{esc(main["cols"][0])} × 상승 게임 수 · 배율</p><p class="seclabel">전체 모집단 대비</p></div>'
            f'<div class="body">{svg}</div></div><div class="lines">{"".join(lines[:3])}</div>')


def _changes_card(rep):
    rows = []
    for h in (rep.get("headline") or [])[:3]:
        info = headline_info(h)
        big = (f'<div class="big"><span class="delta {info["dirn"]}">{esc(info["hero"])}</span>'
               + (f'<small>{esc(info["cap"])}</small>' if info["cap"] else "") + "</div>") if info["hero"] else ""
        meta = " · ".join(strip_links(x) for x in info["rest"])
        th = thumb_html(info["name"], info["url"], rep, cls="th", big=True) if info["url"] else ""
        rows.append(f'<div class="row">{th}<div><h3 class="nm">{esc(info["name"])}</h3>' + (f'<p class="cap">{esc(meta)}</p>' if meta else "") + f"</div>{big}</div>")
    body = f'<div class="rows">{"".join(rows)}</div>' if rows else '<p class="empty">이번 회차에는 큰 폭 변화가 없습니다.</p>'
    return _title_block("BIG MOVERS", f"오늘 가장 크게 움직인 게임 {len(rows)}", "큰 폭 변화") + body


def to_cards(rep, link=None):
    """리포트 dict → [(파일명, html)]. 1080×1350 다크 카드 4장(표지 · 범프 차트 · 소재·장르 · 큰 폭 변화).
    시계열(rep["series"])이 없는 옛 리포트는 범프 카드를 건너뜁니다. 파일명은 <date>-N.png (notify.card_paths 규칙)."""
    pages = [_cover_card(rep), _bump_card(rep), _tags_card(rep), _changes_card(rep)]
    pages = [b for b in pages if b]
    n = len(pages)
    return [(f"{rep['date']}-{i}.png", _card_page(rep, body, i, n, link)) for i, body in enumerate(pages, 1)]
