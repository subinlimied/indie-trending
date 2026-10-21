#!/usr/bin/env python3
"""Discord 웹훅으로 리포트 본문과 HTML 파일을 보냅니다.

사용:
  DISCORD_WEBHOOK_URL=... python3 notify.py --date 2026-10-20 [--only steam|itch]
본문은 reports/<platform>/<date>.md, 첨부는 reports/<platform>/<date>.html 입니다.
"""
import argparse
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from market.http import _CTX  # noqa: E402

KST = timezone(timedelta(hours=9))
LIMIT = 1900  # Discord 메시지 2000자 제한, 여유분


def post(webhook, content, file_path=None):
    boundary = uuid.uuid4().hex
    parts = []
    # flags 4 = SUPPRESS_EMBEDS: 링크마다 미리보기가 붙어 본문이 길어지는 것을 막습니다.
    payload = {"content": content, "allowed_mentions": {"parse": []}, "flags": 4}
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
        f"Content-Type: application/json\r\n\r\n{json.dumps(payload, ensure_ascii=False)}\r\n".encode()
    )
    if file_path:
        data = Path(file_path).read_bytes()
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[0]\"; filename=\"{Path(file_path).name}\"\r\n"
            f"Content-Type: text/html\r\n\r\n".encode() + data + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(webhook + "?wait=true", data=body, method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "indie-trending-report/1.0",
    })
    with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
        return r.status


def chunks(text, limit=LIMIT):
    """빈 줄 경계에서 나눕니다. 한 덩어리가 너무 길면 줄 단위로 더 나눕니다."""
    out, cur = [], ""
    for para in text.split("\n\n"):
        cand = (cur + "\n\n" + para) if cur else para
        if len(cand) <= limit:
            cur = cand
            continue
        if cur:
            out.append(cur)
        cur = ""
        for line in para.split("\n"):
            cand = (cur + "\n" + line) if cur else line
            if len(cand) > limit:
                out.append(cur)
                cur = line
            else:
                cur = cand
    if cur:
        out.append(cur)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--only", choices=["steam", "itch"])
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 본문만 출력")
    args = ap.parse_args()

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook and not args.dry_run:
        sys.exit("DISCORD_WEBHOOK_URL 환경변수가 없습니다.")

    for platform in ("steam", "itch"):
        if args.only and args.only != platform:
            continue
        md = ROOT / "reports" / platform / f"{args.date}.md"
        html_path = ROOT / "reports" / platform / f"{args.date}.html"
        if not md.exists():
            print(f"[{platform}] {md} 없음, 건너뜀")
            continue
        pieces = chunks(md.read_text())
        for i, piece in enumerate(pieces):
            attach = html_path if (i == len(pieces) - 1 and html_path.exists()) else None
            if args.dry_run:
                print(f"----- [{platform}] {i + 1}/{len(pieces)} ({len(piece)}자){' + ' + attach.name if attach else ''}\n{piece}")
            else:
                status = post(webhook, piece, attach)
                print(f"[{platform}] {i + 1}/{len(pieces)} 전송 {status}")


if __name__ == "__main__":
    main()
