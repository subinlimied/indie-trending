"""design/tokens.json → CSS 변수 블록과 공통 컴포넌트 CSS.

값은 전부 tokens.json 에서만 옵니다. 이 모듈에는 색·글꼴·크기 리터럴을 두지 않습니다.

쓰는 법:
    from market import ui
    head  = ui.font_links()                       # <link> 태그들 (Google Fonts + Pretendard CDN)
    css   = ui.css_vars("steam", scale="web")     # :root 변수 (라이트 기본 + 다크 미디어쿼리 + data-theme)
    css   = ui.css_vars("itch", scale="card", mode="dark")   # 카드: 다크 고정
    css  += ui.components_css()                   # .chip .rank .ptag .seclabel .cardframe …
    T     = ui.tokens()                           # 원본 dict
    ui.color("dark", "상승") → "#3DD68C"

CSS 변수 이름(컴포넌트·차트·다른 렌더러가 참조):
    --bg --surface --surface-2 --line --line-strong --ink --ink-2 --ink-3
    --rise --rise-soft --fall --fall-soft --warn --warn-soft
    --accent --accent-soft (플랫폼별)  --c-steam --c-itch --c-media --c-personal (+ -soft)
    --font-display --font-body --font-mono
    --fs-label --fs-sub --fs-body --fs-strong --fs-chip --fs-title --fs-headline --fs-axis --fs-chart
    --sp (그리드) --gutter --r-sm --r-md --r-lg --r-pill --bw --bw-2 --shadow
옛 이름(--ground --muted --faint --serif --sans --mono --ph-s --ph-l --ph-ink)은 별칭으로 같이 내보내
주간·미디어 렌더러가 지금 CSS 그대로 토큰 색을 받습니다.
"""
import json
from functools import lru_cache
from pathlib import Path

TOKENS_PATH = Path(__file__).resolve().parent.parent / "design" / "tokens.json"

PLATFORMS = ("steam", "itch", "media", "personal")
MODE_KEY = {"light": "라이트", "dark": "다크"}
# 토큰 키 → CSS 변수 (색)
COLOR_VARS = [("바탕", "bg"), ("표면", "surface"), ("표면_2", "surface-2"), ("선", "line"), ("선_진함", "line-strong"),
              ("글자_1", "ink"), ("글자_2", "ink-2"), ("글자_3", "ink-3"),
              ("상승", "rise"), ("상승_연함", "rise-soft"), ("하락", "fall"), ("하락_연함", "fall-soft"),
              ("경고", "warn"), ("경고_연함", "warn-soft"), ("그림자", "shadow")]
SIZE_VARS = [("라벨", "fs-label"), ("보조", "fs-sub"), ("본문", "fs-body"), ("강조", "fs-strong"), ("칩_숫자", "fs-chip"),
             ("제목", "fs-title"), ("헤드라인", "fs-headline"), ("축", "fs-axis"), ("차트_라벨", "fs-chart")]


@lru_cache(maxsize=1)
def tokens():
    return json.loads(TOKENS_PATH.read_text())


def color(mode, key):
    """mode: 'light' | 'dark', key: tokens.json 색 키 ('상승', 'steam', '글자_2' …)."""
    return tokens()["색"][MODE_KEY[mode]][key]


def font_stack(role):
    """role: '제목' | '본문' | '숫자' → CSS font-family 값."""
    f = tokens()["글꼴"][role]
    names = f["후보"] + f["fallback"]
    return ", ".join(n if n.startswith(("-", "ui-")) or " " not in n else f'"{n}"' for n in names)


def font_links():
    """HTML <head> 에 넣을 웹폰트 <link> 태그. 없어도 fallback 스택으로 깨지지 않습니다."""
    links = tokens()["글꼴"]["웹폰트_링크"]
    out = ['<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>']
    out += [f'<link rel="stylesheet" href="{u}">' for u in links]
    return "".join(out)


def _color_block(mode, platform):
    c = tokens()["색"][MODE_KEY[mode]]
    lines = [f"--{v}:{c[k]}" for k, v in COLOR_VARS]
    for p in PLATFORMS:
        lines += [f"--c-{p}:{c[p]}", f"--c-{p}-soft:{c[p + '_연함']}"]
    if platform in PLATFORMS:
        lines += [f"--accent:{c[platform]}", f"--accent-soft:{c[platform + '_연함']}"]
    else:
        lines += [f"--accent:{c['steam']}", f"--accent-soft:{c['steam_연함']}"]
    # 썸네일 폴백 색 블록(이름 해시 HSL)의 채도·명도와 머리글자 잉크. 다크는 어둡게, 라이트는 파스텔.
    if mode == "dark":
        lines += ["--ph-s:36%", "--ph-l:30%", "--ph-ink:rgba(255,255,255,.7)", "color-scheme:dark"]
    else:
        lines += ["--ph-s:48%", "--ph-l:74%", "--ph-ink:rgba(0,0,0,.55)", "color-scheme:light"]
    return ";".join(lines)


def _static_block(scale):
    T = tokens()
    s = T["글자_크기"]["카드" if scale == "card" else "웹"]
    g, r, b = T["간격"], T["모서리"], T["선_두께"]
    lines = [f"--font-display:{font_stack('제목')}", f"--font-body:{font_stack('본문')}", f"--font-mono:{font_stack('숫자')}",
             f"--display-weight:{T['글꼴']['제목']['굵기']}", f"--display-tracking:{T['글꼴']['제목']['자간']}"]
    lines += [f"--{v}:{s[k]}px" for k, v in SIZE_VARS]
    lines += [f"--sp:{g['그리드']}px", f"--gutter:{g['카드_여백'] if scale == 'card' else g['웹_거터']}px",
              f"--section-gap:{g['웹_섹션_간격']}px", f"--content-max:{g['본문_최대폭']}px",
              f"--r-sm:{r['작음']}px", f"--r-md:{r['보통']}px", f"--r-lg:{r['큼']}px", f"--r-pill:{r['알약']}px",
              f"--bw:{b['가는']}px", f"--bw-2:{b['보통']}px", f"--chart-line:{b['차트_선']}px", f"--chart-line-hi:{b['차트_강조_선']}px"]
    # 옛 이름 별칭
    lines += ["--ground:var(--bg)", "--muted:var(--ink-2)", "--faint:var(--ink-3)",
              "--serif:var(--font-display)", "--sans:var(--font-body)", "--mono:var(--font-mono)"]
    return ";".join(lines)


def css_vars(platform="steam", scale="web", mode="both"):
    """:root 변수 블록.
    mode='both'  : 라이트 기본 + 다크(prefers-color-scheme, data-theme) — 웹용
    mode='dark'  : 다크 고정 — 카드 PNG 용
    mode='light' : 라이트 고정
    """
    static = _static_block(scale)
    if mode == "dark":
        return f":root{{{static};{_color_block('dark', platform)}}}\n"
    if mode == "light":
        return f":root{{{static};{_color_block('light', platform)}}}\n"
    dark = _color_block("dark", platform)
    return (f":root{{{static};{_color_block('light', platform)}}}\n"
            f"@media (prefers-color-scheme:dark){{:root:not([data-theme=\"light\"]){{{dark}}}}}\n"
            f":root[data-theme=\"dark\"]{{{dark}}}\n")


# ---------- 공통 컴포넌트 ----------
# 모든 크기는 --fs-* / --sp 변수로만 정합니다. 카드와 웹이 같은 CSS 를 쓰고 변수 값만 다릅니다.
COMPONENTS_CSS = """
/* 스탯 칩: 라벨 위 · 큰 숫자 · 화살표 델타. 상자 없이 간격으로만 나눕니다. */
.chip{display:flex;flex-direction:column;gap:calc(var(--sp)*.5);min-width:0;margin:0}
.chip .lbl{font-size:var(--fs-label);line-height:1.3;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0;font-weight:500}
.chip .val{font-family:var(--font-mono);font-size:var(--fs-chip);font-weight:700;line-height:1.05;letter-spacing:-.03em;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0}
.chip .val small{font-size:.5em;font-weight:500;color:var(--ink-2);letter-spacing:0;margin-left:.15em}
.chip .delta{font-family:var(--font-mono);font-size:var(--fs-sub);font-weight:500;line-height:1.3;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0;font-variant-numeric:tabular-nums}
.chip .delta.up{color:var(--rise)}.chip .delta.down{color:var(--fall)}
.chips{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:calc(var(--sp)*3)}
/* 순위 배지 */
.rank{display:inline-flex;align-items:center;justify-content:center;min-width:2.2em;height:2.2em;padding:0 .5em;border-radius:var(--r-sm);background:var(--surface-2);color:var(--ink);font-family:var(--font-mono);font-size:var(--fs-sub);font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
.rank.top{background:var(--accent);color:var(--bg)}
/* 플랫폼 태그 · 섹션 번호 라벨 · 배지 */
.ptag{display:inline-flex;align-items:center;gap:.4em;font-family:var(--font-mono);font-size:var(--fs-label);font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);white-space:nowrap}
.ptag::before{content:"";width:.6em;height:.6em;border-radius:50%;background:var(--accent);flex:none}
.seclabel{font-family:var(--font-mono);font-size:var(--fs-label);font-weight:500;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3);margin:0}
.seclabel b{color:var(--accent);font-weight:700;margin-right:.8em}
.badge{display:inline-block;font-size:var(--fs-label);font-weight:500;line-height:1.6;padding:.1em .7em;border:var(--bw) solid var(--line-strong);border-radius:var(--r-pill);color:var(--ink-2);white-space:nowrap}
.badge.new{color:var(--rise);border-color:transparent;background:var(--rise-soft)}
.badge.excl{color:var(--fall);border-color:transparent;background:var(--fall-soft)}
.badge.disc{color:var(--warn);border-color:transparent;background:var(--warn-soft)}
.badge.acc{color:var(--accent);border-color:transparent;background:var(--accent-soft)}
.pills{display:inline-flex;flex-wrap:wrap;gap:calc(var(--sp)*.5);vertical-align:middle}
/* 방향 색 */
.up{color:var(--rise)}.down{color:var(--fall)}
.num{font-variant-numeric:tabular-nums}
/* 제목 서체 */
.display{font-family:var(--font-display);font-weight:var(--display-weight);letter-spacing:var(--display-tracking);font-synthesis:none;text-wrap:balance;line-height:1.05}
/* 차트 공통 */
.chart{display:block;width:100%;height:auto;max-width:100%}
.chart text{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
.chart .tx{font-family:var(--font-body)}
"""

# 카드 틀(1080×1350, 다크 고정). body 의 .cardframe 하나가 카드 전체입니다.
CARD_FRAME_CSS = """
*{box-sizing:border-box}
html,body{margin:0;width:var(--card-w);height:var(--card-h);overflow:hidden}
body{background:var(--bg);color:var(--ink);font-family:var(--font-body);font-size:var(--fs-body);line-height:1.4;-webkit-font-smoothing:antialiased;word-break:keep-all;overflow-wrap:anywhere}
.cardframe{width:var(--card-w);height:var(--card-h);padding:var(--gutter);display:flex;flex-direction:column;gap:calc(var(--sp)*3);position:relative;background:var(--bg)}
.cardframe>*{flex:none;min-width:0}
.cardframe .grow{flex:1 1 auto;min-height:0}
.cardhead{display:flex;justify-content:space-between;align-items:baseline;gap:calc(var(--sp)*2)}
.cardhead .when{font-family:var(--font-mono);font-size:var(--fs-label);letter-spacing:.08em;color:var(--ink-3);white-space:nowrap}
.cardfoot{margin-top:auto;display:flex;justify-content:space-between;align-items:baseline;gap:calc(var(--sp)*3);padding-top:calc(var(--sp)*2);border-top:var(--bw) solid var(--line);font-family:var(--font-mono);font-size:var(--fs-label);color:var(--ink-3);letter-spacing:.04em}
.cardfoot span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cardfoot .pg{flex:none;color:var(--ink-2)}
.cardtitle{margin:0;font-size:var(--fs-title);color:var(--ink)}
.cardtitle small{display:block;font-family:var(--font-mono);font-size:var(--fs-label);font-weight:500;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-3);margin-bottom:calc(var(--sp)*1)}
.headline{margin:0;font-size:var(--fs-headline);color:var(--ink);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.headline .dim{color:var(--ink-2);font-weight:600}
"""


def components_css():
    return COMPONENTS_CSS


def card_frame_css():
    T = tokens()["카드"]
    return f":root{{--card-w:{T['폭']}px;--card-h:{T['높이']}px;--cover-ratio:{T['표지_이미지_비율']}}}\n" + CARD_FRAME_CSS


def card_head_css(platform, with_components=True):
    """카드 HTML <style> 전체: 다크 고정 변수 + 틀 + 컴포넌트."""
    return css_vars(platform, scale="card", mode="dark") + card_frame_css() + (components_css() if with_components else "")


def chart_theme(scale="web"):
    """charts.py 가 쓰는 값: 글자 크기(px)와 선 두께. 색은 CSS 변수 이름으로 넘겨 라이트·다크 양쪽에서 읽히게 합니다."""
    T = tokens()
    s = T["글자_크기"]["카드" if scale == "card" else "웹"]
    b = T["선_두께"]
    return {"fs_axis": s["축"], "fs_label": s["차트_라벨"], "fs_sub": s["보조"], "fs_strong": s["강조"],
            "line": b["차트_선"], "line_hi": b["차트_강조_선"], "dot": b["차트_점"],
            "font_mono": "var(--font-mono)", "font_body": "var(--font-body)",
            "ink": "var(--ink)", "ink2": "var(--ink-2)", "ink3": "var(--ink-3)", "line_c": "var(--line)", "line_strong": "var(--line-strong)",
            "surface": "var(--bg)", "accent": "var(--accent)", "accent_soft": "var(--accent-soft)",
            "rise": "var(--rise)", "fall": "var(--fall)", "warn": "var(--warn)"}
