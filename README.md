# indie-trending

Steam과 itch.io에서 "소규모 팀이 만들 수 있는 인디게임"이 어떻게 뜨고 지는지를 매일 관찰하는 일간 리포트입니다.
매일 스냅샷을 쌓고 전날과 비교해 **오늘의 선정 게임 → 큰 폭 변화 → 특이사항** 을 Discord 임베드 카드와 이미지 카드 뉴스로 보내고, HTML 상세(01~06 섹션)는 링크로 엽니다.
판정 규칙과 지표 정의는 [rules.md](rules.md)에 있습니다. Python 표준 라이브러리만 씁니다(외부 패키지 없음).

## 실행 방법

```bash
python3 collect.py --date 2026-10-21            # 스냅샷 수집 → data/steam/, data/itch/ (Steam 약 15분)
python3 report.py  --date 2026-10-21            # 리포트 생성 → reports/<platform>/<date>.md .html .json
python3 cards.py   --date 2026-10-21            # 이미지 카드 뉴스 → reports/<platform>/cards/<date>-N.png (헤드리스 Chrome 필요, 없으면 건너뜀)
DISCORD_WEBHOOK_URL=... python3 notify.py --date 2026-10-21   # Discord 전송 (--dry-run 으로 임베드 JSON·첨부 목록만 확인)
```

- `--date` 를 빼면 오늘(KST)입니다. `--only steam|itch` 로 한 플랫폼만 돌릴 수 있습니다.
- 같은 날짜 스냅샷이 있으면 수집을 건너뜁니다. 다시 받으려면 `collect.py --force`.
- 수집은 한 번에 하나만 돌리세요. 같은 IP에서 겹치면 Steam 리뷰 API가 429를 냅니다.
- 회차 1은 비교 대상이 없어 "회차 1 · 비교 없음"으로 나오고, 급상승 판정은 회차 2부터, 연속 판정(승격)은 회차 3부터 들어갑니다.

## GitHub Actions 자동 실행

[.github/workflows/daily.yml](.github/workflows/daily.yml) 이 매일 09:05 KST(00:05 UTC)에 수집 → 리포트 → 카드 이미지 → 커밋·push → Discord 전송을 합니다.
Actions 탭에서 **Run workflow** 로 수동 실행할 수도 있습니다(날짜·강제 재수집 입력 가능).

워크플로가 저장소에 커밋하므로 **Settings → Actions → General → Workflow permissions** 가 "Read and write permissions" 여야 합니다.

## Discord 웹훅 만들기

1. Discord에서 리포트를 받을 채널의 **채널 설정(톱니) → 연동(Integrations) → 웹훅(Webhooks) → 새 웹훅**
2. 이름·채널을 정하고 **웹훅 URL 복사**
3. GitHub 저장소 **Settings → Secrets and variables → Actions → New repository secret**
4. Name: `DISCORD_WEBHOOK_URL`, Secret: 복사한 URL → Add secret

한 메시지에 임베드(표지 · 큰 폭 변화 게임별 · 특이사항)와 카드 PNG 를 첨부합니다. 상세 보고서 링크는 `config.json` 의 `report_base_url` (GitHub Pages 주소) + `/<platform>/<date>.html` 이고, 값이 비어 있으면 링크를 생략합니다.

## 직접 해야 하는 단계 (체크리스트)

- [ ] Discord 웹훅 생성 후 URL 복사
- [ ] GitHub 저장소 Secrets 에 `DISCORD_WEBHOOK_URL` 등록
- [ ] Settings → Actions → General → Workflow permissions 를 "Read and write permissions" 로
- [ ] Actions 탭에서 `daily indie trending` 을 **Run workflow** 로 한 번 수동 실행해 Discord에 도착하는지 확인
- [ ] 운영하면서 `config.json` 의 `big_publishers` 에 대형 퍼블리셔 이름을 채우기 (본문 제외 조건)

## 폴더

```
collect.py / report.py / cards.py / notify.py   진입점
market/steam.py, itch.py            수집기
market/analyze_steam.py, analyze_itch.py   판정·섹션 구성
market/render.py                    Discord 본문(markdown), HTML, 이미지 카드 HTML(to_cards)
market/common.py, http.py           공통 (스냅샷 로드, 회차 상태, 재시도 HTTP)
config.json                         report_base_url(상세 보고서 링크), 목록 크기, Steam 합성 지역(regions), 본문 포함 조건, 대형 퍼블리셔 목록
data/<platform>/<date>.json         일간 스냅샷 (지우지 않음), data/cache/ 는 Steam 메타 캐시
reports/<platform>/<date>.*         리포트, cards/<date>-N.png 는 카드 뉴스, state.json 은 연속 선정 회차 기록
```
