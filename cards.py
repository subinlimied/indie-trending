#!/usr/bin/env python3
"""리포트 → 이미지 카드 뉴스 (reports/<platform>/cards/<date>-N.png, 1080×1350).

사용:
  python3 cards.py --date 2026-10-22 [--only steam|itch] [--html-dir 폴더]
render.to_cards 가 만든 HTML 을 임시 파일로 쓰고 헤드리스 Chrome 으로 스크린샷을 찍습니다.
Chrome 은 CHROME_BIN → google-chrome → chromium-browser → chromium → macOS 앱 순서로 찾고,
없으면 경고만 내고 건너뜁니다(전송은 카드 없이 계속됩니다).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from market import render, ui  # noqa: E402

KST = timezone(timedelta(hours=9))
WIDTH, HEIGHT = ui.tokens()["카드"]["폭"], ui.tokens()["카드"]["높이"]  # design/tokens.json
MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def find_chrome():
    env = os.environ.get("CHROME_BIN")
    if env and (Path(env).exists() or shutil.which(env)):
        return env
    for name in ("google-chrome", "chromium-browser", "chromium"):
        p = shutil.which(name)
        if p:
            return p
    if Path(MAC_CHROME).exists():
        return MAC_CHROME
    return None


def screenshot(chrome, html_path, out_png, profile_dir):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
           "--force-device-scale-factor=1", f"--user-data-dir={profile_dir}", f"--window-size={WIDTH},{HEIGHT}",
           "--virtual-time-budget=5000", f"--screenshot={out_png}", Path(html_path).resolve().as_uri()]
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        cmd.insert(1, "--no-sandbox")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if r.returncode != 0 or not Path(out_png).exists():
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(f"Chrome 종료 코드 {r.returncode}: {' / '.join(tail)}")


def card_paths(platform, date):
    """notify.py 가 첨부할 카드 PNG 목록(번호순)."""
    d = ROOT / "reports" / platform / "cards"
    return sorted(d.glob(f"{date}-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]) if p.stem.rsplit("-", 1)[1].isdigit() else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--only", choices=["steam", "itch"])
    ap.add_argument("--html-dir", help="카드 HTML 을 임시 폴더 대신 여기에 남깁니다(디자인 확인용)")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text())
    base = (cfg.get("report_base_url") or "").rstrip("/")
    chrome = find_chrome()
    if not chrome:
        print("경고: Chrome 을 찾지 못해 카드를 건너뜁니다 (CHROME_BIN 환경변수로 지정할 수 있습니다).")
        return
    print(f"Chrome: {chrome}")

    with tempfile.TemporaryDirectory(prefix="indie-cards-") as tmp:
        html_dir = Path(args.html_dir) if args.html_dir else Path(tmp) / "html"
        html_dir.mkdir(parents=True, exist_ok=True)
        profile = Path(tmp) / "profile"
        for platform in ("steam", "itch"):
            if args.only and args.only != platform:
                continue
            src = ROOT / "reports" / platform / f"{args.date}.json"
            if not src.exists():
                print(f"[{platform}] {src} 없음, 건너뜀")
                continue
            rep = json.loads(src.read_text())
            out_dir = ROOT / "reports" / platform / "cards"
            out_dir.mkdir(parents=True, exist_ok=True)
            for old in out_dir.glob(f"{args.date}-*.png"):
                old.unlink()
            made = []
            link = f"{base}/{platform}/{args.date}.html" if base else None
            for fname, html in render.to_cards(rep, link):
                html_path = html_dir / f"{platform}-{Path(fname).stem}.html"
                html_path.write_text(html)
                out_png = out_dir / fname
                try:
                    screenshot(chrome, html_path, out_png, profile)
                    made.append(out_png)
                except Exception as e:  # 카드 한 장이 실패해도 나머지는 계속
                    print(f"[{platform}] 경고: {fname} 실패 — {e}")
            print(f"[{platform}] 카드 {len(made)}장: " + ", ".join(str(p.relative_to(ROOT)) for p in made))


if __name__ == "__main__":
    main()
