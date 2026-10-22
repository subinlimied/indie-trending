#!/usr/bin/env python3
"""주간 리포트: 태그별 성공률 표(Steam) + 캡슐 아트 보드(Steam·itch) → HTML · PNG · Discord.

사용:
  python3 weekly.py --date 2026-10-22 --dry-run   # 전송 없이 data/weekly/, reports/weekly/ 산출물만
  python3 weekly.py --date 2026-10-22 --no-send   # 산출물만 (Actions 에서 커밋 전 단계)
  python3 weekly.py --date 2026-10-22 --send-only # 만들어 둔 산출물로 Discord 전송만
  DISCORD_WEBHOOK_URL=... python3 weekly.py       # 오늘(KST) 기준 전부
--date 는 주의 마지막 날이고, 보드는 그날까지 7일치 일간 리포트를 씁니다.
태그 수집(10~15분)은 data/weekly/<date>-tags.json 이 있으면 건너뜁니다(--force 로 재수집).
"""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from cards import find_chrome, screenshot  # noqa: E402
from market import render_weekly, weekly  # noqa: E402
from market.render import date_ko  # noqa: E402
from notify import LIM_DESC, LIM_TOTAL, check_limits, clip, embed_len, post  # noqa: E402

KST = timezone(timedelta(hours=9))
COLOR = 0x33409E


def log(msg):
    print(f"{datetime.now(KST).strftime('%H:%M:%S')} {msg}", flush=True)


def week_dates(end):
    d1 = datetime.strptime(end, "%Y-%m-%d")
    return [(d1 - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]


def build_payload(summary, link):
    s = summary
    lines = [f"**성공률 상위 5 · 리뷰 {s['success_reviews']}+ 비율**"]
    for i, t in enumerate(s["top"], 1):
        lines.append(f"{i}. **{t['name']}** {t['p_success']:.1f}% · 1년 출시 {t['n']:,}개 · {s['mid_reviews']}+ {t['p_mid']:.1f}% · 중앙값 리뷰 {t['median']:,.0f}")
    lines.append("")
    lines.append("**틈 후보 3 · 성공률 높고 출시 적은 태그**")
    for i, t in enumerate(s["niche"], 1):
        lines.append(f"{i}. **{t['name']}** 틈 지수 {t['niche']:.1f} · 1년 출시 {t['n']:,}개 · {s['mid_reviews']}+ {t['p_mid']:.1f}% · {s['success_reviews']}+ {t['p_success']:.1f}%")
    if not s["top"]:
        lines.append("표본이 충분한 태그가 없습니다.")
    if link:
        lines += ["", f"**[📄 상세 보고서 열기 (표 전체 · 보드)]({link})**"]
    embeds = [{"title": clip(f"주간 분석 · {date_ko(s['dates'][0])} ~ {date_ko(s['dates'][-1])}", 256), "color": COLOR,
               "description": clip("\n".join(lines), LIM_DESC),
               "footer": {"text": clip(f"태그 {s['tag_count']}개 · 게임 {s['games_total']:,}개 · 최근 {s['window_days']}일 Indie 출시작 · 리뷰 {s['success_reviews']}+ ≈ 1만 장", 2048)}}]
    if link:
        embeds[0]["url"] = link
    files = []
    for platform, ko in (("steam", "Steam"), ("itch", "itch.io")):
        b = s["boards"].get(platform) or {}
        pngs = [ROOT / "reports" / "weekly" / "cards" / f for f in b.get("pngs") or []]
        pngs = [p for p in pngs if p.exists()]
        if not pngs:
            continue
        e = {"title": clip(f"캡슐 아트 보드 · {ko} · 이번 주 급상승 {b.get('count', 0)}개", 256), "color": COLOR,
             "description": "스토어 캡슐 디자인 참고용 · 일간 리포트 선정 게임 · 큰 폭 변화 · 급상승 Top 3 에 오른 게임",
             "image": {"url": f"attachment://{pngs[0].name}"}}
        if link:
            e["url"] = link + "#s2"
        embeds.append(e)
        files.extend(pngs)
    content = f"**주간 리포트 · {date_ko(s['dates'][0])} ~ {date_ko(s['dates'][-1])}** · 태그별 성공률 + 캡슐 아트 보드"
    return {"content": clip(content, 2000), "embeds": embeds, "allowed_mentions": {"parse": []}}, files[:10]


def make_boards(dates, out_dir, html_dir, profile, chrome, cache_path):
    """플랫폼별 보드 PNG. {platform: {"games": [...], "pngs": [파일명], "count": n}}"""
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    boards = {}
    for platform in ("steam", "itch"):
        games = weekly.board_games(platform, dates, ROOT / "reports")
        limit = render_weekly.PER_CARD[platform] * render_weekly.MAX_CARDS
        shown = games[:limit]
        log(f"[board/{platform}] 게임 {len(games)}개 (보드에 {len(shown)}개) · 이미지 받는 중")
        ok = weekly.attach_images(shown, platform, cache, log, dates=dates, data_dir=ROOT / "data")
        log(f"[board/{platform}] 이미지 {ok}/{len(shown)}개 성공")
        pngs = []
        for old in out_dir.glob(f"{dates[-1]}-board-{platform}*.png"):
            old.unlink()
        for fname, html in render_weekly.board_cards(shown, platform, dates):
            hp = html_dir / f"{Path(fname).stem}.html"
            hp.write_text(html)
            if not chrome:
                continue
            try:
                screenshot(chrome, hp, out_dir / fname, profile)
                pngs.append(fname)
            except Exception as e:  # noqa: BLE001
                log(f"[board/{platform}] 경고: {fname} 실패 — {e}")
        for g in shown:
            g.pop("data", None)  # data URI 는 JSON 에 남기지 않습니다
        boards[platform] = {"games": [{k: v for k, v in g.items() if k != "prio"} for g in games],
                            "pngs": pngs, "count": len(games)}
        log(f"[board/{platform}] 카드 {len(pngs)}장: " + ", ".join(pngs))
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=0))
    return boards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"), help="주의 마지막 날 (YYYY-MM-DD, 기본 오늘 KST)")
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 산출물 + 임베드 JSON 만")
    ap.add_argument("--no-send", action="store_true", help="산출물만 만들고 전송은 생략")
    ap.add_argument("--send-only", action="store_true", help="만들어 둔 reports/weekly/<date>.json 으로 전송만")
    ap.add_argument("--force", action="store_true", help="태그 데이터가 있어도 다시 수집")
    ap.add_argument("--html-dir", help="보드 카드 HTML 을 임시 폴더 대신 여기에 남깁니다(디자인 확인용)")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    dates = week_dates(args.date)
    data_dir = ROOT / "data" / "weekly"
    rep_dir = ROOT / "reports" / "weekly"
    cards_dir = rep_dir / "cards"
    for d in (data_dir, cards_dir):
        d.mkdir(parents=True, exist_ok=True)
    base = (cfg.get("report_base_url") or "").rstrip("/")
    link = f"{base}/weekly/{args.date}.html" if base else ""
    summary_path = rep_dir / f"{args.date}.json"

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook and not (args.dry_run or args.no_send):
        sys.exit("DISCORD_WEBHOOK_URL 환경변수가 없습니다 (--dry-run 또는 --no-send 로 전송 없이 돌릴 수 있습니다).")

    if not args.send_only:
        # A. 태그별 성공률
        tags_path = data_dir / f"{args.date}-tags.json"
        if tags_path.exists() and not args.force:
            log(f"[weekly] {tags_path.relative_to(ROOT)} 이미 있음, 태그 수집 건너뜀 (--force 로 재수집)")
            data = json.loads(tags_path.read_text())
        else:
            t0 = time.time()
            data = weekly.collect_tags(cfg, args.date, log)
            tags_path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            log(f"[weekly] 저장 {tags_path.relative_to(ROOT)} · 태그 {len(data['tags'])}개 · 요청 {data['requests']}회 · {time.time() - t0:.0f}초")
        top, niche = weekly.rank_tags(data)

        # B. 캡슐 아트 보드
        chrome = find_chrome()
        if not chrome:
            log("경고: Chrome 을 찾지 못해 보드 PNG 를 건너뜁니다 (CHROME_BIN 환경변수로 지정할 수 있습니다).")
        with tempfile.TemporaryDirectory(prefix="indie-weekly-") as tmp:
            html_dir = Path(args.html_dir) if args.html_dir else Path(tmp) / "html"
            html_dir.mkdir(parents=True, exist_ok=True)
            boards = make_boards(dates, cards_dir, html_dir, Path(tmp) / "profile", chrome, data_dir / "images.json")

        # C. HTML + 전송용 요약
        html_path = rep_dir / f"{args.date}.html"
        html_path.write_text(render_weekly.to_html(data, top, niche, boards, dates, cfg))
        summary = {"date": args.date, "dates": dates, "tag_count": len(data["tags"]), "games_total": data["games_total"],
                   "window_days": data["window_days"], "success_reviews": data["success_reviews"], "mid_reviews": data["mid_reviews"],
                   "top": [{k: t[k] for k in ("name", "n", "p_success", "p_mid", "median", "niche")} for t in top],
                   "niche": [{k: t[k] for k in ("name", "n", "p_success", "p_mid", "median", "niche")} for t in niche],
                   "boards": {p: {"pngs": b["pngs"], "count": b["count"],
                                  "games": [{k: g[k] for k in ("name", "url", "metric", "hits", "days", "image_url") if k in g} for g in b["games"]]}
                              for p, b in boards.items()}}
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1))
        log(f"[weekly] 저장 {html_path.relative_to(ROOT)}, {summary_path.relative_to(ROOT)}")
        if args.no_send:
            return
    else:
        if not summary_path.exists():
            sys.exit(f"{summary_path} 없음 — 먼저 --no-send 로 산출물을 만드세요.")
        summary = json.loads(summary_path.read_text())

    payload, files = build_payload(summary, link)
    bad = check_limits(payload["embeds"])
    if bad:
        sys.exit("[weekly] Discord 글자 수 제한 초과: " + ", ".join(bad))
    total = sum(embed_len(e) for e in payload["embeds"])
    if args.dry_run:
        print(f"----- [weekly] 임베드 {len(payload['embeds'])}개 · 합 {total}/{LIM_TOTAL}자 · 첨부 {len(files)}개")
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        for fp in files:
            print(f"  첨부 {fp.relative_to(ROOT)} ({fp.stat().st_size // 1024} KB)")
    else:
        status = post(webhook, payload, files)
        log(f"[weekly] 전송 {status} · 임베드 {len(payload['embeds'])}개 {total}자 · 첨부 {len(files)}개")


if __name__ == "__main__":
    main()
