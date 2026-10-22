"""리포트 dict → Discord 본문(markdown) 과 HTML.

HTML 은 Discord 첨부로 열리는 정적 파일이라 스크립트 없이 CSS 만 씁니다.
게임 이미지: Steam 은 url 의 appid 로 캡슐 주소를 만들고, itch 는 분석기가 넘긴 "thumb" 를 씁니다.
"""
import html as H
import re
from datetime import datetime
from urllib.parse import quote

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

# 레이아웃: 본문 1160px 한 열. 상단은 선정 게임 큰 카드 + 변화 요약 두 열, 휴대폰에서는 한 열.
CSS = """
:root{--ground:#F3F4F7;--surface:#FFFFFF;--surface-2:#F7F8FA;--ink:#14161C;--muted:#4E5768;--faint:#8891A0;--line:#DDE1E8;--line-strong:#BFC6D1;
--accent:#2F3C99;--accent-soft:#EBEDF9;--rise:#11693F;--rise-soft:#E3F3E9;--fall:#B4261D;--fall-soft:#FBEAE8;--warn:#7F5A00;--warn-soft:#FBF1DC;
--ph-s:48%;--ph-l:74%;--ph-ink:rgba(0,0,0,.55);--shadow:0 1px 2px rgba(20,22,28,.06),0 6px 20px rgba(20,22,28,.05);
--serif:"Gowun Batang","Nanum Myeongjo",Georgia,serif;--sans:"IBM Plex Sans KR",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0F1217;--surface:#171B23;--surface-2:#1D222B;--ink:#E8EBF1;--muted:#A6AEBC;--faint:#737C8D;--line:#2A303B;--line-strong:#3B4350;
--accent:#9AA6F5;--accent-soft:#202652;--rise:#63D692;--rise-soft:#13301F;--fall:#F7928A;--fall-soft:#331A17;--warn:#E2BB55;--warn-soft:#2E2510;
--ph-s:36%;--ph-l:36%;--ph-ink:rgba(255,255,255,.7);--shadow:none;color-scheme:dark}}
:root[data-theme="dark"]{--ground:#0F1217;--surface:#171B23;--surface-2:#1D222B;--ink:#E8EBF1;--muted:#A6AEBC;--faint:#737C8D;--line:#2A303B;--line-strong:#3B4350;
--accent:#9AA6F5;--accent-soft:#202652;--rise:#63D692;--rise-soft:#13301F;--fall:#F7928A;--fall-soft:#331A17;--warn:#E2BB55;--warn-soft:#2E2510;
--ph-s:36%;--ph-l:36%;--ph-ink:rgba(255,255,255,.7);--shadow:none;color-scheme:dark}
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


# ---------- 게임 카드 ----------

def game_card(it, rep):
    hero, cap, dirn, rest = key_metric(it.get("line", ""))
    pills, more = badges_html(it.get("badges", []))
    meta = rest + more
    kpi = f'<div class="kpi {dirn}"><b>{esc(hero)}</b><small>{esc(cap)}</small></div>' if hero else ""
    return (f'<article class="g">{thumb_html(it["name"], it.get("url"), rep, it)}<div class="gb">'
            f'<div class="gh"><a class="nm" href="{H.escape(it.get("url") or "#", quote=True)}" target="_blank" rel="noopener">{esc(it["name"])}</a>{kpi}</div>'
            + pills
            + (f'<div class="sub">{esc(it["sub"])}</div>' if it.get("sub") else "")
            + (f'<div class="meta">{dots_html(meta)}</div>' if meta else "")
            + "</div></article>")


def block_html(b, rep):
    body = "".join(game_card(it, rep) for it in b["items"]) if b["items"] else '<p class="empty">해당 없음</p>'
    return f'<div class="card block"><h4>{esc(b["title"])}</h4>{body}</div>'


# ---------- 상단 ----------

def pick_html(p, rep):
    hero, cap, dirn, rest = key_metric(p["line"])
    tiles = []
    if hero:
        tiles.append((cap, hero, ""))
    for seg in rest:
        lab, val, note = seg_tile(seg)
        if lab:
            tiles.append((lab, val, note))
    extra = [seg for seg in rest if not seg_tile(seg)[0]]
    tiles_html = "".join(f'<dl class="tile"><dt title="{H.escape(l, quote=True)}">{esc(l)}</dt><dd class="{direction(v)}">{esc(v)}' + (f"<small>{esc(n)}</small>" if n else "") + "</dd></dl>"
                         for l, v, n in tiles[:4])
    pills, more = badges_html(p.get("badges", []))
    sub = " · ".join(x for x in [p.get("sub") or ""] + more + extra if x)
    streak = f" · {p['streak']}일 연속 ({p['since']}~)" if p["streak"] > 1 else ""
    links = " ".join(f'<a href="{H.escape(u, quote=True)}" target="_blank" rel="noopener">{esc(t)} ↗</a>' for t, u in p["links"])
    return (f'<article class="card pick"><div class="pk-img">{thumb_html(p["name"], p["url"], rep, p, big=True)}</div><div class="pk-body">'
            f'<p class="lbl">오늘의 선정 게임{esc(streak)}</p>'
            f'<h2 class="pk-name"><a href="{H.escape(p["url"], quote=True)}" target="_blank" rel="noopener">{esc(p["name"])}</a></h2>'
            + (f'<p class="pk-sub">{esc(sub)}</p>' if sub else "") + pills
            + (f'<div class="tiles">{tiles_html}</div>' if tiles_html else "")
            + f'<p class="pk-links">{links}</p></div></article>')


def headline_li(text, rep):
    segs = split_dots(text)
    first, rest = segs[0], segs[1:]
    m = LINK.search(first)
    th = ""
    if m:
        srcs, _ = thumb_srcs(m.group(2), rep)
        if srcs:
            th = thumb_html(m.group(1), m.group(2), rep, cls="th")
    return (f'<li class="{"" if th else "nothumb"}">{th}<div><div class="h1">{md_links(first)}</div>'
            + (f'<div class="h2">{dots_html(rest)}</div>' if rest else "") + "</div></li>")


def side_html(rep):
    def lst(items):
        if not items:
            return '<p class="empty">없음</p>'
        return '<ul class="hl">' + "".join(headline_li(x, rep) for x in items) + "</ul>"
    return (f'<aside class="card side"><div><p class="lbl">큰 폭 변화</p>{lst(rep["headline"])}</div>'
            f'<div><p class="lbl">특이사항</p>{lst(rep["notes"])}</div></aside>')


# ---------- 03 태그 표 ----------

RX_CNT = re.compile(r"^(\d+)개 \((\d+)%\)$")


def is_tag_table(t):
    return t["cols"][1:4] == ["상승 묶음", "전체 비율", "배율"]


def tag_table_html(t, rep):
    rows = []
    for r in t["rows"]:
        name, cnt, base, mult, ex, st = (r + [""] * 6)[:6]
        m = RX_CNT.match(cnt)
        n, share = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        bs = int(base.rstrip("%")) if base.rstrip("%").isdigit() else 0
        mv = float(mult.rstrip("×")) if mult.rstrip("×").replace(".", "", 1).isdigit() else None
        stn = int(st.replace("회차", "")) if st.replace("회차", "").isdigit() else 0
        rows.append((name, n, share, bs, mult, mv, LINK.findall(ex), stn))
    if not rows:
        return '<p class="empty">해당 없음</p>'
    show_st = any(r[7] >= 2 for r in rows)
    mx = max(max(r[2], r[3]) for r in rows) or 1
    st_cls = " st" if show_st else ""
    out = [f'<p class="legend"><span><i></i>상승 묶음 안의 비율</span><span><i class="b"></i>전체 모집단 비율</span></p>',
           f'<div class="tg-head{st_cls}"><span>{esc(t["cols"][0])}</span><span>비율</span><span style="text-align:right">배율</span><span>예시</span>' + ("<span style='text-align:right'>연속</span>" if show_st else "") + "</div>"]
    for name, n, share, bs, mult, mv, ex, stn in rows:
        hot = " hot" if mv is not None and mv >= 1.5 else ""
        exh = "".join(thumb_html(tt, u, rep) for tt, u in ex[:3])
        out.append(f'<div class="tg{st_cls}"><div class="tg-name">{esc(name)}</div>'
                   f'<div class="tg-bars"><div class="bar a"><i style="--w:{share / mx * 100:.0f}%"></i><span>{n}개 · {share}%</span></div>'
                   f'<div class="bar b"><i style="--w:{bs / mx * 100:.0f}%"></i><span>전체 {bs}%</span></div></div>'
                   f'<div class="tg-mult{hot}">{esc(mult)}</div><div class="tg-ex">{exh}</div>'
                   + (f'<div class="tg-st">{stn}회차 연속</div>' if show_st else "") + "</div>")
    return "".join(out)


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


# ---------- 페이지 ----------

def section_html(s, rep):
    body = []
    if s.get("text"):
        body.append(f'<p class="stext">{md_links(s["text"])}</p>')
    if s.get("blocks"):
        body.append('<div class="blocks">' + "".join(block_html(b, rep) for b in s["blocks"]) + "</div>")
    if s.get("list") is not None:
        body.append('<ul class="bul">' + "".join(f"<li>{md_links(x)}</li>" for x in s["list"]) + "</ul>" if s["list"] else '<p class="empty">없음</p>')
    for t in s.get("tables") or []:
        if is_tag_table(t):
            body.append((f'<h4 class="tt">{esc(t["title"])}</h4>' if t.get("title") else "") + tag_table_html(t, rep))
        elif s["no"] == "06":
            body.append(f'<details class="dt"><summary>{esc(t["title"])}</summary>{detail_table_html(t, rep)}</details>')
        else:
            body.append((f'<h4 class="tt">{esc(t["title"])}</h4>' if t.get("title") else "") + table_html(t))
    if not body:
        body.append('<p class="empty">이번 회차에는 해당 항목이 없습니다.</p>')
    return (f'<section id="s{s["no"]}"><h2><span class="no">{s["no"]}</span>{esc(s["title"])}</h2>'
            + (f'<p class="sbasis">{md_links(s["basis"])}</p>' if s.get("basis") else "") + "".join(body) + "</section>")


def to_html(rep):
    p = rep.get("pick")
    pick = pick_html(p, rep) if p else '<div class="card side"><p class="empty">오늘은 선정 게임이 없습니다.</p></div>'
    status = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in rep["status"] if v not in (None, "", "—"))
    basis = "".join(f"<li>{esc(x)}</li>" for x in split_dots(rep["basis_line"]))
    toc = "".join(f'<a href="#s{s["no"]}"><b>{s["no"]}</b>{esc(s["title"])}</a>' for s in rep["sections"])
    secs = "".join(section_html(s, rep) for s in rep["sections"])
    title = f"{rep['platform_ko']} 트렌딩 · {rep['date']}"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>{CSS}</style></head>
<body class="{esc(rep['platform'])}"><div class="wrap">
<header><p class="eyebrow">일간 리포트 · {rep['round']}회차</p><h1>{esc(rep['platform_ko'])} 트렌딩 · {date_ko(rep['date'])}</h1>
<ul class="basis">{basis}</ul><dl class="status">{status}</dl></header>
<nav class="toc">{toc}</nav>
<div class="top">{pick}{side_html(rep)}</div>
{secs}
<footer>{esc(rep['collect_line'])} · 생성 {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>모든 판매·매출 숫자는 추정치이며 게임 간 비교 용도입니다.</footer>
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


# ---------- 이미지 카드 (1080×1350, 라이트 단일 테마) ----------

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


def _card(body, rep, i, n, title, eyebrow=None, date=True):
    foot = f"{rep['platform_ko']} 트렌딩 · {date_ko(rep['date'])} · {rep['round']}회차"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>{CARD_CSS}</style></head>
<body class="{esc(rep['platform'])}"><div class="card">
<div class="top"><span class="eyebrow">{esc(eyebrow or f"{rep['platform_ko']} 트렌딩")}</span><span class="page">{i} / {n}</span></div>
<h1>{esc(title)}</h1>{f'<p class="date">{esc(date_ko(rep["date"]))}</p>' if date else ""}
<div class="body">{body}</div>
<div class="foot"><span>{esc(foot)}</span><span>indie-trending</span></div>
</div></body></html>"""


def _cover_body(rep):
    p = rep.get("pick")
    if not p:
        hl = rep.get("headline") or []
        first = strip_links(split_dots(hl[0])[0]) if hl else ""
        return '<p class="lbl">오늘의 선정 게임</p><p class="empty">오늘은 선정 게임이 없습니다.</p>' + (f'<p class="lbl">큰 폭 변화</p><p class="sub">{esc(first)}</p>' if first else "")
    streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
    tiles = pick_tiles(p)[:3]
    tiles_html = "".join(f'<dl class="tile"><dt>{esc(l)}</dt><dd class="{direction(v)}">{esc(v)}' + (f"<small>{esc(n)}</small>" if n else "") + "</dd></dl>" for l, v, n in tiles)
    pills = "".join(f'<span class="badge {badge_cls(b)}">{esc(b)}</span>' for b in (p.get("badges") or [])[:4])
    return (f'<p class="lbl">오늘의 선정 게임{esc(streak)}</p><div class="hero">{thumb_html(p["name"], p["url"], rep, p, big=True)}</div>'
            f'<h2 class="name">{esc(p["name"])}</h2>' + (f'<p class="sub">{esc(p["sub"])}</p>' if p.get("sub") else "")
            + (f'<div class="pills">{pills}</div>' if pills else "") + (f'<div class="tiles">{tiles_html}</div>' if tiles_html else ""))


def _changes_body(rep):
    rows = []
    for h in (rep.get("headline") or [])[:3]:
        info = headline_info(h)
        kpi = f'<div class="kpi {info["dirn"]}">{esc(info["hero"])}</div>' if info["hero"] else ""
        cap = info["cap"] if info["hero"] else ""
        meta = " · ".join(strip_links(x) for x in info["rest"])
        th = thumb_html(info["name"], info["url"], rep, cls="th sm", big=True) if info["url"] else ""
        rows.append(f'<div class="row">{th}<div class="rb"><div class="rh"><div class="nm">{esc(info["name"])}</div>{kpi}</div>'
                    + (f'<div class="cap">{esc(cap)}</div>' if cap else "") + (f'<div class="meta">{esc(meta)}</div>' if meta else "") + "</div></div>")
    return "".join(rows) if rows else '<p class="empty">이번 회차에는 큰 폭 변화가 없습니다.</p>'


def _notes_body(rep, limit=5):
    notes = rep.get("notes") or []
    out = []
    for n in notes[:limit]:
        segs = split_dots(strip_links(n))
        head, rest = segs[0], segs[1:]
        if ": " in head and len(head) > 40:
            label, first = head.split(": ", 1)
            head, rest = label, [first] + rest
        out.append(f'<div class="note"><span class="dot"></span><div><div class="n1">{esc(head)}</div>' + (f'<div class="n2">{esc(" · ".join(rest))}</div>' if rest else "") + "</div></div>")
    if len(notes) > limit:
        out.append(f'<div class="note"><span class="dot"></span><div><div class="n2">외 {len(notes) - limit}건 · 상세 보고서 참고</div></div></div>')
    body = "".join(out) if out else '<p class="empty">이번 회차에는 특이사항이 없습니다.</p>'
    return body + f'<div class="note" style="margin-top:auto;border-top:0"><span class="dot" style="background:#BFC6D1"></span><div><div class="n2" style="margin:0">{esc(rep.get("collect_line", ""))}</div></div></div>'


def _tags_body(rep):
    top = tag_top(rep)
    if not top:
        return ""
    _, col, rows = top
    out = [f'<p class="lbl">{esc(col)} Top 3 · 상승 묶음 안 비율 · 배율 = 전체 대비</p>']
    for i, (name, cnt, base, mult, ex) in enumerate(rows, 1):
        mv = float(mult.rstrip("×")) if mult.rstrip("×").replace(".", "", 1).isdigit() else None
        hot = " hot" if mv is not None and mv >= 1.5 else ""
        exh = "".join(thumb_html(t, u, rep, cls="th xs", big=True) for t, u in ex[:3])
        out.append(f'<div class="tag"><div class="rk">{i}</div><div><div class="tn">{esc(name)}</div><div class="ts">상승 묶음 {esc(cnt)} · 전체 {esc(base)}</div></div>'
                   f'<div class="mult{hot}">{esc(mult)}</div>' + (f'<div class="ex">{exh}</div>' if exh else "") + "</div>")
    return "".join(out)


def to_cards(rep):
    """리포트 dict → [(파일명, html)]. 세로형 1080×1350 카드 3~4장(표지 · 큰 폭 변화 · 특이사항 · 태그 Top 3)."""
    eyebrow = f"일간 리포트 · {rep['round']}회차"
    pages = [(f"{rep['platform_ko']} 트렌딩", _cover_body(rep), eyebrow, True),
             ("큰 폭 변화", _changes_body(rep), None, False),
             ("특이사항", _notes_body(rep), None, False)]
    top = tag_top(rep)
    if top:
        pages.append((top[0], _tags_body(rep), None, False))
    n = len(pages)
    return [(f"{rep['date']}-{i}.png", _card(body, rep, i, n, title, eyebrow=eb, date=dt))
            for i, (title, body, eb, dt) in enumerate(pages, 1)]
