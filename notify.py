#!/usr/bin/env python3
"""Discord 웹훅으로 리포트를 임베드 카드 + 이미지 카드 뉴스로 보냅니다.

사용:
  DISCORD_WEBHOOK_URL=... python3 notify.py --date 2026-10-20 [--only steam|itch]
  python3 notify.py --dry-run --date 2026-10-20     # 보내지 않고 임베드 JSON 과 첨부 목록만 출력
본문은 reports/<platform>/<date>.json (report.py 가 저장한 리포트 dict), 첨부는 reports/<platform>/cards/<date>-N.png (cards.py).
상세 보고서 링크는 config.json 의 "report_base_url" + /<platform>/<date>.html 이고, 값이 비어 있으면 생략합니다.
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
from cards import card_paths  # noqa: E402
from market import render  # noqa: E402
from market.http import _CTX  # noqa: E402

KST = timezone(timedelta(hours=9))

COLOR = {"up": 0x146C43, "down": 0xB3261E, "": 0x33409E}
# Discord 임베드 글자 수 제한
LIM_TITLE, LIM_DESC, LIM_FIELD_NAME, LIM_FIELD, LIM_FOOTER, LIM_TOTAL = 256, 4096, 256, 1024, 2048, 6000
MAX_EMBEDS, MAX_FILES = 10, 10


def clip(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: max(0, n - 1)].rstrip() + "…"


def embed_len(e):
    n = len(e.get("title", "")) + len(e.get("description", "")) + len((e.get("footer") or {}).get("text", ""))
    return n + sum(len(f["name"]) + len(f["value"]) for f in e.get("fields", []))


def report_url(cfg, platform, date):
    base = (cfg.get("report_base_url") or "").rstrip("/")
    return f"{base}/{platform}/{date}.html" if base else ""


def build_embeds(rep, link):
    """리포트 dict → [표지, 큰 폭 변화 ×≤3, 특이사항(+링크·수집 상태)]."""
    embeds = []
    title = f"{rep['platform_ko']} 트렌딩 · {render.date_ko(rep['date'])} · {rep['round']}회차"
    cover = {"title": clip(title, LIM_TITLE), "color": COLOR[""]}
    if link:
        cover["url"] = link
    p = rep.get("pick")
    if p:
        streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
        lines = [f"**오늘의 선정 게임 → [{p['name']}]({p['url']})**{streak}"]
        if p.get("sub"):
            lines.append(p["sub"])
        if p.get("badges"):
            lines.append(" · ".join(p["badges"][:4]))
        if p.get("links"):
            lines.append(" · ".join(f"[{t}]({u})" for t, u in p["links"]))
        cover["description"] = clip("\n".join(lines), LIM_DESC)
        cover["fields"] = [{"name": clip(l, LIM_FIELD_NAME), "value": clip(f"**{v}**" + (f"\n{n}" if n else ""), LIM_FIELD), "inline": True}
                           for l, v, n in render.pick_tiles(p)[:3]]
        img = render.thumb_url(p["url"], rep, p)
        if img:
            cover["image"] = {"url": img}
    else:
        cover["description"] = "오늘은 선정 게임이 없습니다."
    if not rep.get("headline"):
        cover["description"] += "\n\n큰 폭 변화: 없음"
    embeds.append(cover)

    for h in (rep.get("headline") or [])[:3]:
        info = render.headline_info(h)
        e = {"title": clip(f"{info['name']} · {info['hero']}" if info["hero"] else info["name"], LIM_TITLE), "color": COLOR[info["dirn"]]}
        if info["url"]:
            e["url"] = info["url"]
            img = render.thumb_url(info["url"], rep)
            if img:
                e["thumbnail"] = {"url": img}
        desc = " · ".join(([info["cap"]] if info["hero"] and info["cap"] else []) + info["rest"])
        if desc:
            e["description"] = clip(desc, LIM_DESC)
        embeds.append(e)

    notes = rep.get("notes") or []
    body = "\n".join(f"• {n}" for n in notes) if notes else "• 없음"
    if link:
        body += f"\n\n**[📄 상세 보고서 열기]({link})**"
    embeds.append({"title": "특이사항", "color": COLOR[""], "description": clip(body, LIM_DESC),
                   "footer": {"text": clip(rep.get("collect_line", ""), LIM_FOOTER)}})

    # 전체 합 6000자: 넘치면 뒤쪽 임베드의 description 부터 줄입니다.
    excess = sum(embed_len(e) for e in embeds) - LIM_TOTAL
    for e in reversed(embeds):
        if excess <= 0:
            break
        d = e.get("description", "")
        if len(d) > 80:
            cut = min(len(d) - 80, excess)
            e["description"] = clip(d, len(d) - cut)
            excess -= cut
    return embeds[:MAX_EMBEDS]


def build_payload(rep, link):
    p = rep.get("pick")
    content = f"**{rep['platform_ko']} 트렌딩 · {render.date_ko(rep['date'])} · {rep['round']}회차**"
    if p:
        content += f" · 오늘의 선정 게임: {p['name']}"
    return {"content": clip(content, 2000), "embeds": build_embeds(rep, link), "allowed_mentions": {"parse": []}}


def post(webhook, payload, files):
    boundary = uuid.uuid4().hex
    parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"payload_json\"\r\n"
             f"Content-Type: application/json\r\n\r\n{json.dumps(payload, ensure_ascii=False)}\r\n".encode()]
    for i, fp in enumerate(files):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files[{i}]\"; filename=\"{fp.name}\"\r\n"
                     f"Content-Type: image/png\r\n\r\n".encode() + fp.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(webhook + "?wait=true", data=b"".join(parts), method="POST", headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "indie-trending-report/1.0",
    })
    with urllib.request.urlopen(req, timeout=60, context=_CTX) as r:
        return r.status


def check_limits(embeds):
    """제한을 넘는 항목을 [문구] 로 돌려줍니다 (정상이면 빈 목록)."""
    bad = []
    for i, e in enumerate(embeds, 1):
        if len(e.get("title", "")) > LIM_TITLE:
            bad.append(f"임베드 {i} title {len(e['title'])}자")
        if len(e.get("description", "")) > LIM_DESC:
            bad.append(f"임베드 {i} description {len(e['description'])}자")
        for f in e.get("fields", []):
            if len(f["name"]) > LIM_FIELD_NAME or len(f["value"]) > LIM_FIELD:
                bad.append(f"임베드 {i} field '{f['name']}' {len(f['value'])}자")
    total = sum(embed_len(e) for e in embeds)
    if total > LIM_TOTAL:
        bad.append(f"전체 {total}자")
    if len(embeds) > MAX_EMBEDS:
        bad.append(f"임베드 {len(embeds)}개")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(KST).strftime("%Y-%m-%d"))
    ap.add_argument("--only", choices=["steam", "itch"])
    ap.add_argument("--dry-run", action="store_true", help="보내지 않고 임베드 JSON 과 첨부 목록만 출력")
    args = ap.parse_args()

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook and not args.dry_run:
        sys.exit("DISCORD_WEBHOOK_URL 환경변수가 없습니다.")
    cfg = json.loads((ROOT / "config.json").read_text())

    for platform in ("steam", "itch"):
        if args.only and args.only != platform:
            continue
        src = ROOT / "reports" / platform / f"{args.date}.json"
        if not src.exists():
            print(f"[{platform}] {src} 없음, 건너뜀")
            continue
        rep = json.loads(src.read_text())
        payload = build_payload(rep, report_url(cfg, platform, args.date))
        files = card_paths(platform, args.date)[:MAX_FILES]
        bad = check_limits(payload["embeds"])
        if bad:
            sys.exit(f"[{platform}] Discord 글자 수 제한 초과: " + ", ".join(bad))
        total = sum(embed_len(e) for e in payload["embeds"])
        if args.dry_run:
            print(f"----- [{platform}] 임베드 {len(payload['embeds'])}개 · 합 {total}/{LIM_TOTAL}자 · 첨부 {len(files)}개")
            print(json.dumps(payload, ensure_ascii=False, indent=1))
            for fp in files:
                print(f"  첨부 {fp.relative_to(ROOT)} ({fp.stat().st_size // 1024} KB)")
            if not files:
                print("  첨부 없음 (cards.py 를 먼저 실행하면 이미지 카드가 붙습니다)")
        else:
            status = post(webhook, payload, files)
            print(f"[{platform}] 전송 {status} · 임베드 {len(payload['embeds'])}개 {total}자 · 첨부 {len(files)}개")


if __name__ == "__main__":
    main()
