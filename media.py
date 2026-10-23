#!/usr/bin/env python3
"""미디어·밈 트렌드 일간 리포트 진입점 (수집 → 분석·렌더 → 카드 → Discord).

사용:
  python3 media.py collect --date 2026-10-22 [--force] [--only wiki,reddit]   # data/media/<date>.json (소스별 상태 포함)
  python3 media.py report  --date 2026-10-22             # reports/media/<date>.json .md .html (+ state.json)
  python3 media.py cards   --date 2026-10-22             # reports/media/cards/<date>-N.png (Chrome 없으면 건너뜀)
  python3 media.py send    --date 2026-10-22 [--dry-run] # Discord 임베드 + 카드 PNG 전송

개인 채널 전용: 웹훅은 DISCORD_WEBHOOK_URL_MEDIA → DISCORD_WEBHOOK_URL_PERSONAL 순서로 찾고, 둘 다 없으면
경고만 내고 보내지 않습니다. 공용 DISCORD_WEBHOOK_URL 은 쓰지 않습니다.
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
from notify import (LIM_DESC, LIM_FIELD, LIM_FIELD_NAME, LIM_FOOTER, LIM_TITLE, LIM_TOTAL, MAX_FILES,  # noqa: E402
                    check_limits, clip, embed_len, post)
from market import media_analyze, media_sources, render_media  # noqa: E402

KST = timezone(timedelta(hours=9))
DATA = ROOT / "data" / "media"
REPORTS = ROOT / "reports" / "media"
LIMITS = {"title": LIM_TITLE, "desc": LIM_DESC, "field_name": LIM_FIELD_NAME, "field": LIM_FIELD, "footer": LIM_FOOTER, "total": LIM_TOTAL}
WEBHOOK_ENVS = ("DISCORD_WEBHOOK_URL_MEDIA", "DISCORD_WEBHOOK_URL_PERSONAL")


def log(msg):
    print(f"{datetime.now(KST).strftime('%H:%M:%S')} {msg}", flush=True)


def load_cfg():
    cfg = json.loads((ROOT / "config.json").read_text())
    media = cfg.get("media") or {}
    media.setdefault("reddit_subs", ["memes", "gaming", "IndieGaming", "gamedev", "tiktokcringe"])
    media.setdefault("kym_hours", 48)
    media.setdefault("wiki_top", 20)
    media.setdefault("trends_top", 10)
    media.setdefault("imgflip_top", 30)
    return cfg, media


def report_url(cfg, date):
    base = (cfg.get("report_base_url") or "").rstrip("/")
    return f"{base}/media/{date}.html" if base else ""


def card_paths(date):
    return sorted((REPORTS / "cards").glob(f"{date}-*.png"))


# ---------- 서브커맨드 ----------

SOURCE_GROUPS = ("kym", "trends", "wiki", "reddit", "imgflip")


def cmd_collect(args):
    _, media = load_cfg()
    out = DATA / f"{args.date}.json"
    only = {x.strip() for x in (args.only or "").split(",") if x.strip()}
    bad = only - set(SOURCE_GROUPS)
    if bad:
        sys.exit(f"[media] --only 에 모르는 소스: {', '.join(sorted(bad))} (가능: {', '.join(SOURCE_GROUPS)})")
    base = json.loads(out.read_text()) if out.exists() else None
    if base and not args.force and not only:
        log(f"[media] {out.name} 이미 있음, 건너뜀 (--force 로 재수집, --only kym,wiki 로 일부만)")
        return
    snap = media_sources.collect(media, args.date, log, only=only or None, base=base if only else None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    ok = sum(1 for s in snap["sources"].values() if s["status"] == "ok")
    log(f"[media] 저장 {out.relative_to(ROOT)} · 소스 {ok}/{len(snap['sources'])} 정상")


def cmd_report(args):
    cfg, media = load_cfg()
    if not (DATA / f"{args.date}.json").exists():
        sys.exit(f"[media] data/media/{args.date}.json 없음 — 먼저 collect 를 실행하세요")
    rep = media_analyze.analyze(media, args.date, ROOT / "data", ROOT / "reports")
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{args.date}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    (REPORTS / f"{args.date}.md").write_text(render_media.to_md(rep))
    (REPORTS / f"{args.date}.html").write_text(render_media.to_html(rep))
    p = rep.get("pick")
    log(f"[media] reports/media/{args.date}.json · .md · .html 생성 ({rep['round']}회차" + (f" · 오늘의 트렌드: {p['title']}" if p else "") + f" · 교차 {len(rep['cross'])}건)")


def cmd_cards(args):
    src = REPORTS / f"{args.date}.json"
    if not src.exists():
        sys.exit(f"[media] {src} 없음 — 먼저 report 를 실행하세요")
    chrome = find_chrome()
    if not chrome:
        print("경고: Chrome 을 찾지 못해 카드를 건너뜁니다 (CHROME_BIN 환경변수로 지정할 수 있습니다).")
        return
    rep = json.loads(src.read_text())
    out_dir = REPORTS / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{args.date}-*.png"):
        old.unlink()
    made = []
    with tempfile.TemporaryDirectory(prefix="media-cards-") as tmp:
        html_dir = Path(args.html_dir) if args.html_dir else Path(tmp) / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        for fname, html in render_media.to_cards(rep):
            html_path = html_dir / f"media-{Path(fname).stem}.html"
            html_path.write_text(html)
            out_png = out_dir / fname
            try:
                screenshot(chrome, html_path, out_png, Path(tmp) / "profile")
                made.append(out_png)
            except Exception as e:  # noqa: BLE001  한 장이 실패해도 나머지는 계속
                print(f"[media] 경고: {fname} 실패 — {e}")
    log(f"[media] 카드 {len(made)}장: " + ", ".join(str(p.relative_to(ROOT)) for p in made))


def pick_webhook():
    for name in WEBHOOK_ENVS:
        v = (os.environ.get(name) or "").strip()
        if v:
            return name, v
    return None, None


def cmd_send(args):
    cfg, _ = load_cfg()
    src = REPORTS / f"{args.date}.json"
    if not src.exists():
        sys.exit(f"[media] {src} 없음 — 먼저 report 를 실행하세요")
    rep = json.loads(src.read_text())
    link = report_url(cfg, args.date)
    embeds = render_media.build_embeds(rep, link, clip, LIMITS)
    p = rep.get("pick")
    content = f"**{render_media.TITLE} · {render_media.date_ko(rep['date'])} · {rep['round']}회차**"
    if p:
        content += f" · 오늘의 트렌드: {p['title']}"
    payload = {"content": clip(content, 2000), "embeds": embeds, "allowed_mentions": {"parse": []}}
    files = card_paths(args.date)[:MAX_FILES]
    bad = check_limits(embeds)
    if bad:
        sys.exit("[media] Discord 글자 수 제한 초과: " + ", ".join(bad))
    total = sum(embed_len(e) for e in embeds)
    if args.dry_run:
        print(f"----- [media] 임베드 {len(embeds)}개 · 합 {total}/{LIM_TOTAL}자 · 첨부 {len(files)}개")
        print(json.dumps(payload, ensure_ascii=False, indent=1))
        for fp in files:
            print(f"  첨부 {fp.relative_to(ROOT)} ({fp.stat().st_size // 1024} KB)")
        if not files:
            print("  첨부 없음 (media.py cards 를 먼저 실행하면 이미지 카드가 붙습니다)")
        return
    name, webhook = pick_webhook()
    if not webhook:
        print(f"경고: {' / '.join(WEBHOOK_ENVS)} 가 모두 비어 있어 전송을 건너뜁니다 (개인 채널 전용).")
        return
    status = post(webhook, payload, files)
    log(f"[media] 전송 {status} ({name}) · 임베드 {len(embeds)}개 {total}자 · 첨부 {len(files)}개")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    today = datetime.now(KST).strftime("%Y-%m-%d")
    for name, fn in (("collect", cmd_collect), ("report", cmd_report), ("cards", cmd_cards), ("send", cmd_send)):
        sp = sub.add_parser(name)
        sp.add_argument("--date", default=today)
        sp.set_defaults(fn=fn)
        if name == "collect":
            sp.add_argument("--force", action="store_true", help="같은 날짜 스냅샷이 있어도 다시 수집")
            sp.add_argument("--only", help="일부 소스만 다시 받아 기존 스냅샷에 합침 (쉼표 구분: kym,trends,wiki,reddit,imgflip)")
        if name == "cards":
            sp.add_argument("--html-dir", help="카드 HTML 을 임시 폴더 대신 여기에 남깁니다(디자인 확인용)")
        if name == "send":
            sp.add_argument("--dry-run", action="store_true", help="보내지 않고 임베드 JSON 과 첨부 목록만 출력")
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
