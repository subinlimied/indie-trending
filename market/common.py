"""분석 공통: 스냅샷 로드, 회차 계산, 변화량, 연속 회차 상태."""
import json
from datetime import datetime
from pathlib import Path


def to_date(s):
    return datetime.strptime(s, "%Y-%m-%d")


def load_snaps(data_dir: Path, platform, date, days=35):
    """date 이전(포함) days 일 안의 스냅샷을 날짜 오름차순 [(date, snap)] 로."""
    out = []
    today = to_date(date)
    for p in sorted((data_dir / platform).glob("*.json")):
        try:
            d = to_date(p.stem)
        except ValueError:
            continue
        if 0 <= (today - d).days <= days:
            out.append((p.stem, json.loads(p.read_text())))
    return out


def round_no(data_dir: Path, platform, date):
    n = 0
    for p in (data_dir / platform).glob("*.json"):
        try:
            if to_date(p.stem) <= to_date(date):
                n += 1
        except ValueError:
            pass
    return n


def window_snap(snaps, date, days):
    """date 에서 days 일 이상 떨어진 것 중 가장 가까운 스냅샷. 없으면 가장 오래된 것(실제 일수와 함께)."""
    today = to_date(date)
    older = [(d, s) for d, s in snaps if (today - to_date(d)).days >= days]
    if older:
        d, s = older[-1]
        return d, s, (today - to_date(d)).days
    prior = [(d, s) for d, s in snaps if d != date]
    if prior:
        d, s = prior[0]
        return d, s, (today - to_date(d)).days
    return None, None, 0


def delta(cur, prev):
    if cur is None or prev is None:
        return None
    return cur - prev


def pct(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    return (cur - prev) / prev * 100


def streak_up(series):
    """series: 최신→과거 순 값 리스트. 최신부터 연속으로 직전보다 커진 회차 수."""
    n = 0
    for a, b in zip(series, series[1:]):
        if a is None or b is None or a <= b:
            break
        n += 1
    return n


class State:
    """연속 선정·태그 연속 같은 회차 누적 값을 reports/<platform>/state.json 에 보관."""

    def __init__(self, path: Path):
        self.path = path
        self.d = json.loads(path.read_text()) if path.exists() else {}

    def bump(self, key, name, date, prev_date=None):
        """같은 이름이 직전 회차(prev_date)에도 있었으면 +1, 아니면 1.
        같은 date 로 다시 실행하면 값을 유지합니다. 한 회차라도 빠졌으면 1부터 다시 셉니다."""
        cur = self.d.get(key) or {}
        if cur.get("name") == name and cur.get("date") == date:
            pass
        elif cur.get("name") == name and prev_date and cur.get("date") == prev_date:
            cur = {"name": name, "n": cur.get("n", 1) + 1, "date": date, "since": cur.get("since", date)}
        else:
            cur = {"name": name, "n": 1, "date": date, "since": date}
        self.d[key] = cur
        return cur["n"], cur["since"]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, ensure_ascii=False, indent=1))


def fmt_int(n):
    return "—" if n is None else f"{n:,}"


def fmt_signed(n, suffix=""):
    if n is None:
        return "—"
    return f"{'+' if n > 0 else ''}{n:,}{suffix}".replace("-", "−")


def fmt_pct(p):
    if p is None:
        return "—"
    return f"{'+' if p > 0 else ''}{p:.1f}%".replace("-", "−")


def fmt_usd(cents):
    if cents is None:
        return "—"
    if cents == 0:
        return "무료"
    return f"${cents / 100:,.2f}"


def fmt_money(v):
    if v is None:
        return "—"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.0f}k"
    return f"${v:.0f}"
