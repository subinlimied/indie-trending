#!/usr/bin/env python3
"""개인 리포트: 공용 리포트를 profile.json(내가 만들 수 있는 범위)으로 다시 걸러 비공개 Discord 채널로 보냅니다.

사용:
  python3 personal.py --date 2026-10-22 --dry-run     # 보내지 않고 임베드 JSON 만 출력 (산출물은 만듦)
  python3 personal.py --date 2026-10-22 --no-send     # 생성만 (reports/personal/<date>.json .md, cards/<date>.png)
  DISCORD_WEBHOOK_URL_PERSONAL=... python3 personal.py --date 2026-10-22 --send-only   # 만들어 둔 것을 전송만
  python3 personal.py --weekly                        # 월요일 섹션 강제 (평소엔 KST 월요일에 자동)
입력: reports/<platform>/<date>.json (공용 리포트) + data/<platform>/ 스냅샷(태그·플레이 시간). 분석을 다시 하지 않습니다.
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cards import find_chrome, screenshot  # noqa: E402
from market import analyze_itch, analyze_steam, personal, render_personal  # noqa: E402
from market.common import load_snaps, to_date  # noqa: E402
from notify import check_limits, embed_len, post  # noqa: E402

KST = timezone(timedelta(hours=9))
OUT = ROOT / "reports" / "personal"


def load_platform(platform, cfg, date):
    """공용 리포트 dict + 정규화한 게임 목록. 둘 중 하나라도 없으면 None."""
    rep_path = ROOT / "reports" / platform / f"{date}.json"
    if not rep_path.exists() or not (ROOT / "data" / platform / f"{date}.json").exists():
        return None, None
    rep = json.loads(rep_path.read_text())
    snaps = load_snaps(ROOT / "data", platform, date)
    if platform == "steam":
        recs = analyze_steam.build_records(cfg["steam"], date, snaps)[0]
        apps = snaps[-1][1]["apps"]
        games = [personal.norm_steam(r, apps.get(r["appid"]) or {}) for r in recs.values()]
    else:
        recs = analyze_itch.build_records(cfg["itch"], date, snaps)[0]
        gs = snaps[-1][1]["games"]
        games = [personal.norm_itch(r, gs.get(r["id"]) or {}) for r in recs.values()]
    return rep, games


def past_results(date, days=7):
    """오늘 이전 days 일 안의 개인 리포트 JSON (오늘 제외)."""
    out = []
    today = to_date(date)
    for p in sorted(OUT.glob("*.json")):
        try:
            d = to_date(p.stem)
        except ValueError:
            continue
        if 0 < (today - d).days < days:
            out.append(json.loads(p.read_text()))
    return out


def build(date, want_weekly):
    cfg = json.loads((ROOT / "config.json").read_text())
    prof = json.loads((ROOT / "profile.json").read_text())
    plats, games_by = {}, {}
    for p in ("steam", "itch"):
        rep, games = load_platform(p, cfg, date)
        if rep is None:
            print(f"[{p}] reports/{p}/{date}.json 또는 스냅샷 없음, 건너뜀")
            continue
        plats[p] = personal.analyze_platform(p, rep, games, prof)
        games_by[p] = games
    if not plats:
        sys.exit("공용 리포트가 하나도 없습니다. report.py 를 먼저 실행하십시오.")
    res = {"date": date, "profile": {k: v for k, v in prof.items() if not k.startswith("_")}, "platforms": plats,
           "same_as_public": all(pl["same_as_public"] for pl in plats.values()),
           "watchlist": personal.watchlist(prof, games_by), "memo": personal.memo(plats), "weekly": None}
    if want_weekly:
        res["weekly"] = personal.weekly(date, past_results(date) + [res])
    res["discord"] = render_personal.build_payload(res)
    return res


def make_card(res, date):
    out_png = OUT / "cards" / f"{date}.png"
    chrome = find_chrome()
    if not chrome:
        print("경고: Chrome 을 찾지 못해 카드를 건너뜁니다 (CHROME_BIN 환경변수로 지정할 수 있습니다).")
        return None
    out_png.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="indie-personal-") as tmp:
        html_path = Path(tmp) / "card.html"
        html_path.write_text(render_personal.to_card(res))
        try:
            screenshot(chrome, html_path, out_png, Path(tmp) / "profile")
        except Exception as e:  # 카드가 실패해도 전송은 계속
            print(f"경고: 카드 실패 — {e}")
            return None
    print(f"카드: {out_png.relative_to(ROOT)} ({out_png.stat().st_size // 1024} KB)")
    return out_png


def send(payload, files, dry_run):
    bad = check_limits(payload["embeds"])
    if bad:
        sys.exit("Discord 글자 수 제한 초과: " + ", ".join(bad))
    total = sum(embed_len(e) for e in payload["embeds"])
    if dry_run:
        print(f"----- 임베드 {len(payload['embeds'])}개 · 합 {total}/6000자 · 첨부 {len(files)}개")
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        for fp in files:
            print(f"  첨부 {fp.relative_to(ROOT)} ({fp.stat().st_size // 1024} KB)")
        return
    webhook = os.environ.get("DISCORD_WEBHOOK_URL_PERSONAL")
    if not webhook:
        sys.exit("DISCORD_WEBHOOK_URL_PERSONAL 환경변수가 없습니다.")
    status = post(webhook, payload, files)
    print(f"전송 {status} · 임베드 {len(payload['embeds'])}개 {total}자 · 첨부 {len(files)}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 임베드 JSON 출력")
    ap.add_argument("--no-send", action="store_true", help="산출물만 만들고 보내지 않음")
    ap.add_argument("--send-only", action="store_true", help="만들어 둔 reports/personal/<date>.json 을 전송만")
    ap.add_argument("--weekly", action="store_true", help="월요일 섹션을 강제로 추가")
    ap.add_argument("--no-card", action="store_true", help="카드 PNG 를 만들지 않음")
    args = ap.parse_args()
    json_path = OUT / f"{args.date}.json"

    if args.send_only:
        if not json_path.exists():
            sys.exit(f"{json_path} 가 없습니다. 먼저 --no-send 로 만드십시오.")
        res = json.loads(json_path.read_text())
        png = OUT / "cards" / f"{args.date}.png"
        send(res["discord"], [png] if png.exists() else [], args.dry_run)
        return

    want_weekly = args.weekly or to_date(args.date).weekday() == 0  # KST 날짜 기준 월요일
    res = build(args.date, want_weekly)
    OUT.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    (OUT / f"{args.date}.md").write_text(render_personal.to_md(res))
    print(f"reports/personal/{args.date}.json · .md 생성" + (" · 주간 섹션 포함" if want_weekly else "") + (" · 공용과 동일" if res["same_as_public"] else ""))
    png = None if args.no_card else make_card(res, args.date)
    if args.no_send:
        return
    send(res["discord"], [png] if png else [], args.dry_run)


if __name__ == "__main__":
    main()
