"""design/tokens.json → CSS 변수 블록과 공통 컴포넌트 CSS (다크 전용, 'Terminal Editorial Intelligence' 시안).

값은 전부 tokens.json 에서만 옵니다. 이 모듈에는 색·글꼴·크기 리터럴을 두지 않습니다.

쓰는 법:
    from market import ui
    head = ui.font_links()                      # Google Fonts <link>
    css  = ui.css_vars("steam")                 # :root 변수 (다크 하나. scale/mode 인자는 호환용)
    css += ui.components_css()                  # .chip .delta .rank .ptag .seclabel .badge .panel .t-* …
    css  = ui.card_head_css("itch")             # 카드 PNG: 변수 + 카드 틀 + 컴포넌트
    T    = ui.tokens()                          # 원본 dict
    ui.color("dark", "상승") → "#00E676"

CSS 변수(컴포넌트·차트·다른 렌더러가 참조):
    --bg --surface --surface-2 --line --line-strong --ink --ink-2 --ink-3
    --rise --rise-soft --rise-line --fall --fall-soft --fall-line --warn --warn-soft --primary-light
    --accent --accent-soft (플랫폼별)  --c-steam --c-itch --c-media --c-personal (+ -soft)
    --font-display --font-body --font-mono
    --t-headline-xl … --t-badge-num (크기/행간), --t-…-w (굵기), --t-…-ls (자간)
    --fs-label --fs-sub --fs-body --fs-strong --fs-chip --fs-title --fs-headline --fs-axis --fs-chart
    --sp --sp-xs --sp-sm --sp-md --sp-lg --sp-xl --gutter --margin --r-sm --r-md --r-lg --r-pill --bw --shadow
옛 이름(--ground --muted --faint --serif --sans --mono --ph-s --ph-l --ph-ink)은 별칭.
"""
import json
from functools import lru_cache
from pathlib import Path

TOKENS_PATH = Path(__file__).resolve().parent.parent / "design" / "tokens.json"

PLATFORMS = ("steam", "itch", "media", "personal")
COLOR_VARS = [("바탕", "bg"), ("표면", "surface"), ("표면_2", "surface-2"), ("선", "line"), ("선_진함", "line-strong"),
              ("글자_1", "ink"), ("글자_2", "ink-2"), ("글자_3", "ink-3"),
              ("상승", "rise"), ("상승_연함", "rise-soft"), ("상승_선", "rise-line"),
              ("하락", "fall"), ("하락_연함", "fall-soft"), ("하락_선", "fall-line"),
              ("경고", "warn"), ("경고_연함", "warn-soft"), ("강조_밝음", "primary-light"), ("그림자", "shadow")]
SIZE_VARS = [("라벨", "fs-label"), ("보조", "fs-sub"), ("본문", "fs-body"), ("강조", "fs-strong"), ("칩_숫자", "fs-chip"),
             ("제목", "fs-title"), ("헤드라인", "fs-headline"), ("축", "fs-axis"), ("차트_라벨", "fs-chart")]
FONT_VAR = {"제목": "var(--font-display)", "본문": "var(--font-body)", "숫자": "var(--font-mono)"}


@lru_cache(maxsize=1)
def tokens():
    return json.loads(TOKENS_PATH.read_text())


def color(mode, key):
    """key: tokens.json 색 키 ('상승', 'steam', '글자_2' …). mode 는 호환용(다크 하나뿐)."""
    return tokens()["색"]["다크"][key]


def font_stack(role):
    f = tokens()["글꼴"][role]
    names = f["후보"] + f["fallback"]
    return ", ".join(n if n.startswith(("-", "ui-")) or " " not in n else f'"{n}"' for n in names)


def font_links():
    """HTML <head> 에 넣을 웹폰트 <link>. 없어도 fallback 스택으로 깨지지 않습니다."""
    out = ['<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>']
    out += [f'<link rel="stylesheet" href="{u}">' for u in tokens()["글꼴"]["웹폰트_링크"]]
    return "".join(out)


def _color_block(platform):
    c = tokens()["색"]["다크"]
    lines = [f"--{v}:{c[k]}" for k, v in COLOR_VARS]
    for p in PLATFORMS:
        lines += [f"--c-{p}:{c[p]}", f"--c-{p}-soft:{c[p + '_연함']}"]
    p = platform if platform in PLATFORMS else "steam"
    lines += [f"--accent:{c[p]}", f"--accent-soft:{c[p + '_연함']}"]
    # 썸네일 폴백 색 블록(이름 해시 HSL)의 채도·명도와 머리글자 잉크
    lines += ["--ph-s:30%", "--ph-l:26%", "--ph-ink:rgba(255,255,255,.7)", "color-scheme:dark"]
    return ";".join(lines)


def _static_block(scale):
    T = tokens()
    s = T["글자_크기"]["카드" if scale == "card" else "웹"]
    g, r, b = T["간격"], T["모서리"], T["선_두께"]
    lines = [f"--font-display:{font_stack('제목')}", f"--font-body:{font_stack('본문')}", f"--font-mono:{font_stack('숫자')}",
             f"--display-weight:{T['글꼴']['제목']['굵기']}", f"--display-tracking:{T['글꼴']['제목']['자간']}"]
    for name, t in T["타이포"].items():
        if name.startswith("_"):
            continue
        lines += [f"--t-{name}:{t['크기']}px/{t['행간']}px", f"--t-{name}-w:{t['굵기']}", f"--t-{name}-ls:{t['자간']}"]
    lines += [f"--{v}:{s[k]}px" for k, v in SIZE_VARS]
    lines += [f"--sp:{g['그리드']}px", f"--sp-xs:{g['xs']}px", f"--sp-sm:{g['sm']}px", f"--sp-md:{g['md']}px", f"--sp-lg:{g['lg']}px", f"--sp-xl:{g['xl']}px",
              f"--gutter:{g['카드_여백'] if scale == 'card' else g['웹_거터']}px", f"--margin:{g['웹_마진']}px",
              f"--card-gap:{g['카드_요소_간격']}px", f"--section-gap:{g['웹_섹션_간격']}px", f"--content-max:{g['본문_최대폭']}px",
              f"--r-sm:{r['작음']}px", f"--r-md:{r['보통']}px", f"--r-lg:{r['큼']}px", f"--r-pill:{r['알약']}px",
              f"--bw:{b['가는']}px", f"--bw-2:{b['보통']}px", f"--chart-line:{b['차트_선']}px", f"--chart-line-hi:{b['차트_강조_선']}px"]
    lines += ["--ground:var(--bg)", "--muted:var(--ink-2)", "--faint:var(--ink-3)",
              "--serif:var(--font-display)", "--sans:var(--font-body)", "--mono:var(--font-mono)",
              "--rise-soft-solid:var(--rise-soft)", "--fall-soft-solid:var(--fall-soft)"]
    return ";".join(lines)


def css_vars(platform="steam", scale="web", mode="dark"):
    """:root 변수 블록. 시안이 다크 전용이라 mode 와 무관하게 다크 한 벌만 냅니다(인자는 호환용)."""
    return f":root{{{_static_block(scale)};{_color_block(platform)}}}\n"


def _typo_classes():
    out = []
    for name, t in tokens()["타이포"].items():
        if name.startswith("_"):
            continue
        extra = ";text-transform:uppercase" if name == "label-caps" else ""
        out.append(f".t-{name}{{font:var(--t-{name}-w) var(--t-{name}) {FONT_VAR[t['글꼴']]};letter-spacing:var(--t-{name}-ls){extra}}}")
    return "\n".join(out)


# 모든 크기는 변수로만. 반지름 0, 그림자 없음, 선은 1px.
COMPONENTS_CSS = """
.mono{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
.num{font-variant-numeric:tabular-nums}
.up{color:var(--rise)}.down{color:var(--fall)}
.display{font-family:var(--font-display);font-weight:var(--display-weight);letter-spacing:var(--display-tracking);font-synthesis:none;text-wrap:balance;line-height:1.08}
/* 패널: 표면 + 1px 선 */
.panel{background:var(--surface);border:var(--bw) solid var(--line);border-radius:var(--r-md)}
/* 라벨(caps 모노) */
.seclabel{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);margin:0}
.seclabel b{color:var(--accent);font-weight:700;margin-right:.8em}
/* 라벨 칩: 사각, 표면 + 1px 선 */
.lchip{display:inline-flex;align-items:center;gap:var(--sp-sm);font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink);background:var(--surface);border:var(--bw) solid var(--line);padding:var(--sp-xs) calc(var(--sp-sm) + 2px);white-space:nowrap}
.lchip.pos{color:var(--rise);background:var(--rise-soft);border-color:var(--rise-line)}
.lchip.neg{color:var(--fall);background:var(--fall-soft);border-color:var(--fall-line)}
.lchip.ghost{background:var(--bg);color:var(--ink-2)}
.lchip.solid{background:var(--rise);color:var(--bg);border-color:var(--rise)}
/* 플랫폼 태그: 표면 바탕 + 1px 선 + 초록 점 + 11px 대문자 모노 */
.ptag{display:inline-flex;align-items:center;gap:var(--sp-sm);font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink);background:var(--surface);border:var(--bw) solid var(--line);padding:var(--sp-xs) calc(var(--sp-sm) + 2px);white-space:nowrap}
.ptag::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--accent);flex:none}
.ptag.muted{color:var(--ink-2)}.ptag.muted::before{display:none}
/* 델타 칩: 사각, ▲/▼ 접두 */
.delta{display:inline-flex;align-items:center;gap:var(--sp-xs);font:var(--t-badge-num-w) var(--t-badge-num) var(--font-mono);letter-spacing:var(--t-badge-num-ls);padding:var(--sp-xs) var(--sp-sm);border:var(--bw) solid var(--line);background:var(--bg);color:var(--ink-2);white-space:nowrap;font-variant-numeric:tabular-nums}
.delta.up{color:var(--rise);background:var(--rise-soft);border-color:var(--rise-line)}
.delta.down{color:var(--fall);background:var(--fall-soft);border-color:var(--fall-line)}
.delta.warn{color:var(--warn);background:var(--warn-soft);border-color:var(--line)}
/* 순위 배지: 모노, 표면 + 1px 선, Top 3 는 초록 반전 */
.rank{display:inline-flex;align-items:center;justify-content:center;min-width:2.4em;height:2em;padding:0 .5em;background:var(--surface);border:var(--bw) solid var(--line);color:var(--ink);font:var(--t-badge-num-w) var(--t-badge-num) var(--font-mono);letter-spacing:var(--t-badge-num-ls);font-variant-numeric:tabular-nums}
.rank.top{background:var(--rise);border-color:var(--rise);color:var(--bg)}
/* 스탯 칩: 패널 안에 라벨 caps · 큰 모노 숫자 + 단위 · 델타 칩 · 회색 보조 줄 */
.chips{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:calc(var(--sp-md) + 2px)}
.chip{background:var(--surface);border:var(--bw) solid var(--line);padding:var(--sp-lg);display:flex;flex-direction:column;gap:0;min-width:0;margin:0}
.chip .lbl{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0}
.chip .row{display:flex;align-items:baseline;justify-content:space-between;gap:var(--sp-sm);margin:var(--sp-md) 0 var(--sp-xs)}
.chip .val{font-family:var(--font-mono);font-size:var(--fs-chip);font-weight:700;line-height:1;letter-spacing:-.03em;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:0;font-variant-numeric:tabular-nums}
.chip .val small{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2);margin-left:2px}
.chip .sub{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:var(--sp-xs) 0 0}
/* 배지(기존 이름 유지): 사각 */
.badge{display:inline-block;font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;padding:var(--sp-xs) var(--sp-sm);border:var(--bw) solid var(--line);background:var(--surface);color:var(--ink-2);white-space:nowrap}
.badge.new{color:var(--rise);background:var(--rise-soft);border-color:var(--rise-line)}
.badge.excl{color:var(--fall);background:var(--fall-soft);border-color:var(--fall-line)}
.badge.disc{color:var(--warn);background:var(--warn-soft)}
.badge.acc{color:var(--primary-light)}
.pills{display:inline-flex;flex-wrap:wrap;gap:var(--sp-xs);vertical-align:middle}
/* 차트 공통 */
.chart{display:block;width:100%;height:auto;max-width:100%}
.chart text{font-family:var(--font-mono);font-variant-numeric:tabular-nums}
.chart .tx{font-family:var(--font-body)}
"""

# 카드 틀(1080×1350). 맨 위 3px 초록 그라데이션 줄은 시안의 장식.
CARD_FRAME_CSS = """
*{box-sizing:border-box}
html,body{margin:0;width:var(--card-w);height:var(--card-h);overflow:hidden}
body{background:var(--bg);color:var(--ink);font-family:var(--font-body);font:var(--t-body-lg-w) var(--t-body-lg) var(--font-body);-webkit-font-smoothing:antialiased;word-break:keep-all;overflow-wrap:anywhere}
.cardframe{width:var(--card-w);height:var(--card-h);padding:var(--gutter);display:flex;flex-direction:column;gap:var(--card-gap);position:relative;background:var(--bg)}
.cardframe::before{content:"";position:absolute;left:0;top:0;width:100%;height:3px;background:linear-gradient(90deg,transparent,var(--rise),transparent);opacity:.8}
.cardframe>*{flex:none;min-width:0}
.cardframe .grow{flex:1 1 auto;min-height:0;display:flex;flex-direction:column}
.cardhead{display:flex;justify-content:space-between;align-items:center;gap:var(--sp-md);padding-bottom:var(--sp-md);border-bottom:var(--bw) solid var(--line)}
.cardhead .l,.cardhead .r{display:flex;align-items:center;gap:var(--sp-md);min-width:0}
.cardhead .when{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2);white-space:nowrap}
.cardhead .sep{color:var(--line)}
.cardfoot{margin-top:auto;display:flex;justify-content:space-between;align-items:center;gap:var(--sp-md);padding-top:var(--sp-lg);border-top:var(--bw) solid var(--line)}
.cardfoot .see{display:flex;align-items:center;gap:var(--sp-sm);font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink);min-width:0;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.cardfoot .see::before{content:"";width:8px;height:8px;background:var(--primary-light);flex:none}
.cardfoot .see span{color:var(--ink-2);font-weight:400}
.cardfoot .pg{font:700 var(--t-data-md) var(--font-mono);letter-spacing:.1em;color:var(--ink);background:var(--bg);border:var(--bw) solid var(--line);padding:var(--sp-xs) calc(var(--sp-sm) + 2px);flex:none}
.cardtitle{margin:0;display:flex;flex-direction:column;gap:var(--sp-sm)}
.cardtitle .kick{display:flex;align-items:center;gap:var(--sp-sm);flex-wrap:wrap}
.cardtitle h2{margin:0;font:var(--t-headline-xl-w) var(--t-headline-xl) var(--font-display);letter-spacing:var(--t-headline-xl-ls);text-transform:uppercase;color:var(--ink);font-synthesis:none}
.cardtitle h2 .hi{color:var(--primary-light)}
.cardtitle h2 .ul{color:var(--rise);text-decoration:underline;text-decoration-color:var(--rise-line);text-decoration-thickness:4px;text-underline-offset:6px}
"""


def components_css():
    return _typo_classes() + "\n" + COMPONENTS_CSS


def card_frame_css():
    T = tokens()["카드"]
    return f":root{{--card-w:{T['폭']}px;--card-h:{T['높이']}px;--cover-max-h:{T['표지_이미지_최대높이']}px}}\n" + CARD_FRAME_CSS


def card_head_css(platform, with_components=True):
    """카드 HTML <style> 전체: 변수 + 틀 + 컴포넌트."""
    return css_vars(platform, scale="card") + card_frame_css() + (components_css() if with_components else "")


def chart_theme(scale="web"):
    """charts.py 가 쓰는 값. 색은 CSS 변수 이름으로 넘깁니다."""
    T = tokens()
    s = T["글자_크기"]["카드" if scale == "card" else "웹"]
    b = T["선_두께"]
    return {"fs_axis": s["축"], "fs_label": s["차트_라벨"], "fs_sub": s["보조"], "fs_strong": s["강조"],
            "line": b["차트_선"], "line_hi": b["차트_강조_선"], "dot": b["차트_점"],
            "font_mono": "var(--font-mono)", "font_body": "var(--font-body)",
            "ink": "var(--ink)", "ink2": "var(--ink-2)", "ink3": "var(--ink-3)", "line_c": "var(--line)", "line_strong": "var(--line-strong)",
            "surface": "var(--surface)", "bg": "var(--bg)", "accent": "var(--accent)", "accent_soft": "var(--accent-soft)",
            "rise": "var(--rise)", "fall": "var(--fall)", "warn": "var(--warn)", "primary_light": "var(--primary-light)"}
