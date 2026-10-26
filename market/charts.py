"""외부 라이브러리 없이 SVG 문자열을 만드는 차트 세 가지 ('Terminal Editorial' 시안: 1px 선, 모노 라벨, 초록 강조, 반지름 0).

색은 CSS 변수(--rise, --accent, --ink …)로 넣어 ui.css_vars 가 채웁니다.
글자 크기·선 두께는 design/tokens.json 에서 읽습니다(scale 인자, 카드와 웹이 같은 값).

    from market import charts
    charts.sparkline([30, 22, None, 15, 12], width=936, height=170, labels=["D-4","D-3","D-2","D-1","TODAY"])
    charts.bump_chart({"A": [3,2,1,1,1,1,1], ...}, days=["10-20",...], highlight="A", secondary=["B"], width=936, height=700)
    charts.bar_lift([("Simulation", 13, 1.4), ...], width=936, height=600)
"""
import html as H

from . import ui


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[: max(1, n - 1)].rstrip() + "…"


def _segments(values):
    segs, cur = [], []
    for i, v in enumerate(values):
        if v is None:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append((i, v))
    if cur:
        segs.append(cur)
    return segs


# ---------- 스파크라인 ----------

def sparkline(values, width=700, height=170, scale="web", invert=True, highlight_last=True, labels=None, color=None, title="",
              point_labels=True, unit="위", uid="sp"):
    """values: 숫자 또는 None(왼쪽이 과거). invert=True 면 작은 값(1위)이 위.
    1.5px 선, 점은 표면색 속 + 선 테두리, 마지막 점은 채움. 선 아래는 옅은 세로 그라데이션만.
    상승(마지막이 처음보다 좋음)은 초록, 하락은 산호. labels(['D-6', …, 'TODAY'])를 주면 점 아래에 값과 날짜 라벨을 두 줄로 적습니다.
    None 은 선을 끊고 라벨은 '—'."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    n = len(values)
    nums = [v for v in values if v is not None]
    pad_x = t["dot"] * 3
    lab_h = (fl * 1.2 + fs * 1.4 + 10) if (labels and point_labels) else 0
    pad_top = t["dot"] * 3
    pad_bot = t["dot"] * 3 + lab_h
    out = [f'<svg class="chart spark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not nums or n == 0:
        out.append(f'<text x="{width / 2}" y="{height / 2}" dy=".35em" text-anchor="middle" class="tx" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    first, last = nums[0], nums[-1]
    improving = (last < first) if invert else (last > first)
    col = color or (t["rise"] if improving or last == first else t["fall"])
    lo, hi = min(nums), max(nums)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    plot_h = height - pad_top - pad_bot
    step = (width - pad_x * 2) / max(n - 1, 1)

    def X(i):
        return pad_x + i * step

    def Y(v):
        r = (v - lo) / (hi - lo)
        return pad_top + (r if invert else 1 - r) * plot_h

    base = pad_top + plot_h
    for y in (pad_top, pad_top + plot_h / 2, base):
        out.append(f'<line x1="{pad_x}" x2="{width - pad_x}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    gid = f"g-{uid}"
    out.append(f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" style="stop-color:{col};stop-opacity:.22"/><stop offset="90%" style="stop-color:{col};stop-opacity:0"/></linearGradient></defs>')
    for seg in _segments(values):
        if len(seg) > 1:
            pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg)
            area = f"M{X(seg[0][0]):.1f},{base:.1f} L" + " L".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg) + f" L{X(seg[-1][0]):.1f},{base:.1f} Z"
            out.append(f'<path d="{area}" style="fill:url(#{gid})"/>')
            out.append(f'<polyline points="{pts}" style="fill:none;stroke:{col};stroke-width:{t["line"]};stroke-linejoin:round;stroke-linecap:round"/>')
        for i, v in seg:
            out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{t["dot"]}" style="fill:{t["surface"]};stroke:{col};stroke-width:1.5"/>')
    last_i = max((i for i, v in enumerate(values) if v is not None), default=None)
    if highlight_last and last_i is not None:
        v = values[last_i]
        out.append(f'<circle cx="{X(last_i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * 2}" style="fill:{col};opacity:.25"/>'
                   f'<circle cx="{X(last_i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * 1.3}" style="fill:{col};stroke:{t["bg"]};stroke-width:1.5"/>')
    if labels and point_labels and len(labels) == n:
        y1 = base + 10 + fl
        y2 = y1 + fs * 1.4
        out.append(f'<line x1="{pad_x}" x2="{width - pad_x}" y1="{base + 6:.1f}" y2="{base + 6:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
        for i, lab in enumerate(labels):
            v = values[i]
            is_last = i == last_i
            anchor = "start" if i == 0 and n > 1 else "end" if i == n - 1 and n > 1 else "middle"
            vcol = col if is_last else t["ink"]
            out.append(f'<text x="{X(i):.1f}" y="{y1:.1f}" text-anchor="{anchor}" style="font-size:{fl}px;font-weight:700;fill:{vcol if v is not None else t["ink3"]}">{_f(v) + unit if v is not None else "—"}</text>')
            out.append(f'<text x="{X(i):.1f}" y="{y2:.1f}" text-anchor="{anchor}" style="font-size:{fs}px;font-weight:{700 if is_last else 500};letter-spacing:.06em;fill:{col if is_last else t["ink2"]}">{H.escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- 범프 차트 ----------

def bump_chart(series, days, highlight=None, secondary=(), width=936, height=700, scale="web", n=10, label_chars=18, title=""):
    """series: {이름: [순위|None] × len(days)}. 1~n 행 + 'n+' 행. 1px 안내선, 모노 축 라벨.
    highlight 는 초록 3px, secondary 는 글자_1 색 1.5px, 나머지는 선 색. 오른쪽 끝 이름 라벨(겹치면 밀어 냄)."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    hi = set([highlight] if isinstance(highlight, str) else (highlight or []))
    sec = set(secondary or []) - hi
    cols = len(days)
    label_w = int(label_chars * fl * 0.58) + fs
    pad_l = fs * 3.6
    pad_t = fs * 2.6
    pad_b = fs * 1.2
    rows = n + 1
    plot_w = width - pad_l - label_w - t["dot"] * 2
    plot_h = height - pad_t - pad_b
    row_h = plot_h / rows
    col_w = plot_w / max(cols - 1, 1)

    def X(i):
        return pad_l + i * col_w

    def Y(r):
        return pad_t + (min(r, n + 1) - .5) * row_h

    out = [f'<svg class="chart bump" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    for r in range(1, rows + 1):
        y = Y(r)
        out.append(f'<line x1="{pad_l}" x2="{pad_l + plot_w:.1f}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
        lab = f"{r:02d}" if r <= n else f"{n}+"
        out.append(f'<text x="{pad_l - fs * .8:.1f}" y="{y:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs}px;letter-spacing:.06em;fill:{t["ink2"]}">{lab}</text>')
    for i, d in enumerate(days):
        last = i == cols - 1
        out.append(f'<text x="{X(i):.1f}" y="{pad_t - fs * 1.1:.1f}" text-anchor="middle" style="font-size:{fs}px;font-weight:{700 if last else 500};letter-spacing:.06em;fill:{t["ink"] if last else t["ink2"]}">{H.escape(d)}</text>')
        out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{pad_t}" y2="{pad_t + plot_h:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    order = sorted(series.items(), key=lambda kv: (2 if kv[0] in hi else 1 if kv[0] in sec else 0))
    for name, vals in order:
        vals = list(vals)[:cols] + [None] * max(0, cols - len(vals))
        if name in hi:
            col, w, dot = t["rise"], t["line_hi"], t["dot"] * 1.3
        elif name in sec:
            col, w, dot = t["ink"], t["line"], t["dot"]
        else:
            col, w, dot = t["line_strong"], t["line"], t["dot"] * .8
        for seg in _segments(vals):
            if len(seg) > 1:
                pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg)
                out.append(f'<polyline points="{pts}" style="fill:none;stroke:{col};stroke-width:{w};stroke-linejoin:round;stroke-linecap:round"/>')
            for i, v in seg:
                out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{dot}" style="fill:{t["bg"]};stroke:{col};stroke-width:1.5"/>')
    labels = []
    for name, vals in series.items():
        vals = list(vals)[:cols]
        last = next((v for v in reversed(vals) if v is not None), None)
        if last is not None:
            labels.append([Y(last), name, last])
    labels.sort()
    min_gap = fl * 1.25
    for k in range(1, len(labels)):
        if labels[k][0] - labels[k - 1][0] < min_gap:
            labels[k][0] = labels[k - 1][0] + min_gap
    if labels and labels[-1][0] > pad_t + plot_h:
        shift = labels[-1][0] - (pad_t + plot_h)
        for lb in labels:
            lb[0] -= shift
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1][0] - labels[k][0] < min_gap:
                labels[k][0] = labels[k + 1][0] - min_gap
    lx = pad_l + plot_w + t["dot"] * 2 + fs * .6
    for y, name, last in labels:
        if name in hi:
            style = f"font-size:{fl}px;font-weight:700;fill:{t['rise']}"
        elif name in sec:
            style = f"font-size:{fl}px;font-weight:600;fill:{t['ink']}"
        else:
            style = f"font-size:{fl}px;fill:{t['ink2']}"
        out.append(f'<text class="tx" x="{lx:.1f}" y="{y:.1f}" dy=".35em" style="{style}"><title>{H.escape(name)} · {last}위</title>{H.escape(_trunc(name, label_chars))}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- 소재·장르 막대 ----------

def bar_lift(rows, width=936, height=600, scale="web", hot=1.5, max_rows=8, label_chars=16, title=""):
    """rows: [(태그, 개수, 배율|None)]. 사각 가로 막대(개수) + 오른쪽 고정 열에 배율 점·숫자. 배율 >= hot 는 초록, 나머지는 선 색."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    rows = list(rows)[:max_rows]
    out = [f'<svg class="chart lift" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not rows:
        out.append(f'<text x="{width / 2}" y="{height / 2}" class="tx" text-anchor="middle" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    label_w = int(label_chars * fl * .58)
    mult_w = fl * 5
    pad_l = label_w + fl
    row_h = height / len(rows)
    bar_h = min(fl * 1.6, row_h * .5)
    plot_w = width - pad_l - mult_w - t["dot"] * 3
    mx = max((c for _, c, _ in rows), default=1) or 1
    for k, (tag, cnt, mult) in enumerate(rows):
        cy = (k + .5) * row_h
        is_hot = mult is not None and mult >= hot
        col = t["rise"] if is_hot else t["line_strong"]
        w = max(plot_w * cnt / mx, 2)
        y0 = cy - bar_h / 2
        out.append(f'<rect x="{pad_l:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{bar_h:.1f}" style="fill:{col}"><title>{H.escape(tag)} · {cnt}개 · {_f(mult) if mult is not None else "—"}×</title></rect>')
        out.append(f'<text class="tx" x="{pad_l - fl * .8:.1f}" y="{cy:.1f}" dy=".35em" text-anchor="end" style="font-size:{fl}px;font-weight:{700 if is_hot else 500};fill:{t["ink"] if is_hot else t["ink2"]}">{H.escape(_trunc(tag, label_chars))}</text>')
        if w > fs * 3.5:
            out.append(f'<text x="{pad_l + w - fs * .7:.1f}" y="{cy:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs + 1}px;font-weight:700;fill:{t["bg"] if is_hot else t["ink"]}">{cnt}</text>')
        else:
            out.append(f'<text x="{pad_l + w + fs * .6:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fs + 1}px;font-weight:700;fill:{t["ink"]}">{cnt}</text>')
        mx_x = width - mult_w + t["dot"] * 1.5
        if mult is not None:
            out.append(f'<rect x="{mx_x - t["dot"]:.1f}" y="{cy - t["dot"]:.1f}" width="{t["dot"] * 2}" height="{t["dot"] * 2}" style="fill:{t["rise"] if is_hot else t["ink2"]}"/>')
            out.append(f'<text x="{mx_x + t["dot"] * 2.6:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fl}px;font-weight:{700 if is_hot else 500};letter-spacing:-.02em;fill:{t["rise"] if is_hot else t["ink2"]}">{_f(mult)}×</text>')
        else:
            out.append(f'<text x="{mx_x + t["dot"] * 2.6:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fl}px;fill:{t["ink3"]}">—</text>')
        if k:
            out.append(f'<line x1="{pad_l:.1f}" x2="{width}" y1="{k * row_h:.1f}" y2="{k * row_h:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    out.append(f'<line x1="{pad_l:.1f}" x2="{pad_l:.1f}" y1="0" y2="{height}" style="stroke:{t["line_strong"]};stroke-width:1"/>')
    out.append("</svg>")
    return "".join(out)
