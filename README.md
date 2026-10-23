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
DISCORD_WEBHOOK_URL_PERSONAL=... python3 personal.py --date 2026-10-21   # 개인 리포트 (profile.json 기준 "내 범위") → 비공개 채널
```

- `--date` 를 빼면 오늘(KST)입니다. `--only steam|itch` 로 한 플랫폼만 돌릴 수 있습니다.
- 같은 날짜 스냅샷이 있으면 수집을 건너뜁니다. 다시 받으려면 `collect.py --force`.
- 수집은 한 번에 하나만 돌리세요. 같은 IP에서 겹치면 Steam 리뷰 API가 429를 냅니다.
- 회차 1은 비교 대상이 없어 "회차 1 · 비교 없음"으로 나오고, 급상승 판정은 회차 2부터, 연속 판정(승격)은 회차 3부터 들어갑니다.

## 개인 리포트 (내 범위)

공용 리포트와 별도로, `profile.json` 에 적은 "내가 만들 수 있는 범위"로 같은 날 레코드를 다시 걸러 비공개 채널로 보냅니다. 분석을 다시 하지 않고 `reports/<platform>/<date>.json` 과 스냅샷의 태그·플레이 시간만 읽습니다.

```bash
python3 personal.py --date 2026-10-22 --dry-run    # 보내지 않고 임베드 JSON 출력 (산출물은 만듦)
python3 personal.py --date 2026-10-22 --no-send    # 생성만: reports/personal/<date>.json .md, cards/<date>.png
DISCORD_WEBHOOK_URL_PERSONAL=... python3 personal.py --date 2026-10-22 --send-only   # 만들어 둔 것을 전송만
python3 personal.py --weekly                       # 월요일 섹션 강제 (평소엔 KST 월요일에 자동)
```

**profile.json** (손으로 고치는 파일, 각 키의 `_설명` 참고)

| 키 | 뜻 |
|---|---|
| `dimensions` | 허용 차원. 태그에 2D/3D 가 있고 목록에 없으면 제외. 태그가 없으면 통과(미상) |
| `engines` | 내 엔진. itch 의 Made with 가 밝혀져 있고 목록에 없으면 제외. Steam 은 엔진 정보가 없어 통과. 비우면 끔 |
| `exclude_tags` | 하나라도 있으면 제외. 기본은 미연시(Dating Sim · Otome · Romance)와, 겹치는 일이 많은 Visual Novel |
| `prefer_tags` | 필터가 아니라 가산점(태그당 +2, 최대 +6) |
| `max_price_usd` | 정가 상한. 무료·NYOP 통과 |
| `max_playtime_hours` | 평균 플레이 시간 상한. itch 는 페이지의 평균 세션(A few minutes · About an hour · A few hours · Days or more)을 시간으로 환산. Steam 은 SteamSpy average_forever 를 쓰지만 현재 수집기가 저장하지 않아 당분간 "판단 보류"(통과) |
| `exclude_multiplayer` | Multiplayer · MMO · Co-op 중심 게임 제외. Singleplayer 태그가 같이 있으면 허용 |
| `watchlist` | `steam` 에 appid, `itch` 에 게임 id(스냅샷 `games` 키)를 문자열로. 매일 변화를 따로 보여 줌 |
| `min_reviews_for_signal` | 리뷰(평점) 수가 이 값 이상일 때만 증가율을 점수에 넣음 |

**규칙**
- 내 범위 = 공용 본문 포함 조건(정가 $30 · 대형 퍼블리셔 · 3년 · 리뷰 5만)을 넘고, 위 profile 조건을 **모두** 통과한 게임. 못 넘은 이유는 배지("Multiplayer", "정가 $29.99", "엔진 Godot", "태그 Dating Sim", "플레이 48시간" …)로 남습니다.
- 내 범위 급상승 Top 3 는 공용 선정 점수식(순위 상승폭 + 증가율 + 증가 수 + 신작·할인 없음·데모 가산점)에 선호 태그 가산점만 더해 다시 매깁니다. 공용 선정 게임·큰 폭 변화와 같은 게임이면 "공용 선정과 동일" · "공용 큰 폭 변화와 동일" 을 붙이고, 1위가 다르면 왜 다른지 한 줄을 적습니다.
- 공용 선정·큰 폭 변화 게임이 내 범위 조건에 걸리면 "내 범위 밖으로 밀린 공용 게임"에 이유와 함께 적습니다.
- 제작 관점 메모는 오늘 내 범위 1위(Steam 우선)의 차원 · 태그 · 가격 · 플레이 시간 · 데모 · 퍼블리싱 사실만 한 줄로 잇습니다. 기간 추정은 하지 않습니다.
- Steam · itch 모두 공용 선정·Top 3 와 완전히 같으면 짧은 한 줄 임베드만 보냅니다.
- KST 월요일(또는 `--weekly`)에는 지난 7일 `reports/personal/*.json` 으로 "가장 자주 오른 태그 조합 Top 3" 와 "출시 90일 이내 내 범위 신작 중 리뷰가 가장 빨리 쌓인 3개(일 평균)" 를 더합니다. 7일치가 안 되면 있는 만큼 계산하고 "n일치" 를 적습니다.
- 전송: 임베드 2~4개(Steam Top 3 · itch Top 3 · 메모·watchlist · 주간) + 카드 PNG 1장(`reports/personal/cards/<date>.png`, Chrome 없으면 건너뜀). 웹훅은 GitHub Secret `DISCORD_WEBHOOK_URL_PERSONAL`.
- 워크플로에서는 커밋 전에 `--no-send` 로 만들고(그래야 그날 커밋에 들어감), 공용 전송 뒤에 `--send-only` 로 보냅니다.

## 주간 리포트 (월요일 10:00 KST)

공용 채널에 보내는 주간 분석입니다. "무엇을 만들지"를 정할 때 보는 두 가지를 한 메시지로 보냅니다. 규칙은 [rules.md §11](rules.md)에 있습니다.

1. **태그별 성공률 표 (Steam)** — 최근 1년에 출시된 Indie 태그 게임을 `config.json` 의 `weekly.tags`(장르·메커닉 태그 40개)별로 세고, 리뷰 500+ (≈ 1만 장) · 100+ · 10 미만 비율, 중앙값, 대표 성공작 3개를 표로 만듭니다. 성공률이 높고 출시 수가 적은 태그가 "틈 후보"입니다.
2. **캡슐 아트 보드 (Steam + itch.io)** — 최근 7일 일간 리포트에 오른 게임(선정 게임 · 큰 폭 변화 · 급상승 Top 3)의 스토어 이미지를 1080×1350 격자 카드로 모읍니다. 스토어 캡슐 디자인 참고용입니다.

```bash
python3 weekly.py --date 2026-10-22 --dry-run     # 전송 없이 산출물 + 임베드 JSON (태그 수집 10~15분, 요청 1,000회 이하)
python3 weekly.py --date 2026-10-22 --no-send     # 산출물만 (Actions 에서 커밋 전 단계)
DISCORD_WEBHOOK_URL=... python3 weekly.py --date 2026-10-22 --send-only   # 만들어 둔 산출물로 전송만
```

- `--date` 는 주의 마지막 날이고, 보드는 그날까지 7일치 `reports/<platform>/<date>.json` 을 씁니다.
- 태그 데이터 `data/weekly/<date>-tags.json` 이 있으면 수집을 건너뜁니다(`--force` 로 재수집). `data/weekly/images.json` 은 Steam header · itch og:image 주소 캐시입니다.
- 산출물: `reports/weekly/<date>.html` (표 전체 + 보드), `reports/weekly/<date>.json` (전송용 요약), `reports/weekly/cards/<date>-board-steam.png`, `-itch.png` (게임이 많으면 `-2.png`).
- [.github/workflows/weekly.yml](.github/workflows/weekly.yml) 이 매주 월요일 10:00 KST(01:00 UTC)에 수집 → 커밋·push → Discord 전송을 합니다. 일간과 같은 concurrency 그룹(`daily`)이라 겹치면 순서대로 돕니다.

## 미디어·밈 트렌드 리포트 (매일 09:30 KST · 개인 채널 전용)

게임 리포트와 같은 뼈대(스냅샷 누적 → 전날 대비 → 임베드 카드 + 카드 PNG → Discord)로 틱톡·밈·검색 트렌드를 매일 받습니다. **개인 채널 전용**이라 공용 웹훅(`DISCORD_WEBHOOK_URL`)으로는 보내지 않습니다.

```bash
python3 media.py collect --date 2026-10-22            # 스냅샷 → data/media/<date>.json (소스별 정상/실패 상태 포함, --force 로 재수집)
python3 media.py report  --date 2026-10-22            # reports/media/<date>.json .md .html (+ state.json 연속 일수)
python3 media.py cards   --date 2026-10-22            # 카드 PNG 2장 → reports/media/cards/<date>-N.png (Chrome 없으면 건너뜀)
python3 media.py send    --date 2026-10-22 --dry-run  # 전송 없이 임베드 JSON 출력
DISCORD_WEBHOOK_URL_MEDIA=... python3 media.py send --date 2026-10-22   # 전송 (없으면 DISCORD_WEBHOOK_URL_PERSONAL, 둘 다 없으면 건너뜀)
```

| 소스 | 쓰는 값 | 비고 |
|---|---|---|
| Know Your Meme 뉴스피드 RSS | 최근 48시간 기사 제목·링크·요약·이미지, 제목의 플랫폼 단서(TikTok · Twitter/X · Reddit · YouTube · Instagram · Twitch) | 제목·요약은 영어 원문 그대로 |
| Google 트렌드 일간 RSS (KR · US) | 검색어·대략 검색량·관련 뉴스 1개 | 어제도 있었으면 "n일 연속" |
| 위키백과 조회수 상위 (en · ko) | 전날 상위 40개에서 대문·특수·프로젝트·파일·분류 문서를 뺀 20개 | 어제도 있었으면 "n일 연속" |
| Reddit top (t=day) RSS | r/memes · r/gaming · r/IndieGaming · r/gamedev · r/tiktokcringe 상위 8개 | 403·429 면 그 서브레딧만 실패 처리 |
| Imgflip 인기 템플릿 100개 | 이름·순위 | 전날 대비 ▲▼ · 신규 진입 · 이탈 |

- **오늘의 트렌드 한 건** = KYM 에서 플랫폼 단서가 TikTok 인 최신 기사, 없으면 KYM 최신 기사. 연속 선정 일수는 `reports/media/state.json` 에 쌓입니다.
- **게임 ↔ 밈 교차** = 검색·위키·Reddit 제목을 그날 `data/steam/` · `data/itch/` 스냅샷의 게임 이름과 대조(소문자 · 3글자 이상 · 부분 일치는 단어 경계, 이름이 2단어 이상이거나 8자 이상일 때만).
- HTML 섹션: 01 오늘의 밈·숏폼 트렌드(KYM) · 02 검색 급상승 KR/US · 03 세상의 관심사(위키 en/ko) · 04 커뮤니티 베스트(Reddit) · 05 밈 템플릿 순위 변동 · 06 게임 ↔ 밈 교차 · 07 수집 상태. 상세 링크는 `reports/media/<date>.html`.
- 카드 PNG: 표지(오늘의 트렌드 + 플랫폼 집계 + 검색 급상승 Top 5 KR/US) · 2장(밈 템플릿 변동 Top 5 + 게임 교차).
- `config.json` 의 `media` 키: `reddit_subs` · `kym_hours` · `wiki_top` · `trends_top` · `imgflip_top`.
- [.github/workflows/media.yml](.github/workflows/media.yml) 이 매일 09:30 KST(00:30 UTC, 게임 리포트 뒤)에 수집 → 리포트 → 카드 → 커밋·push → 전송을 합니다. 전송 단계에는 `DISCORD_WEBHOOK_URL_MEDIA` 와 `DISCORD_WEBHOOK_URL_PERSONAL` 만 넘깁니다(전용 채널을 쓰려면 `DISCORD_WEBHOOK_URL_MEDIA` secret 을 등록).

## GitHub Actions 자동 실행

[.github/workflows/daily.yml](.github/workflows/daily.yml) 이 매일 09:05 KST(00:05 UTC)에 수집 → 리포트 → 카드 이미지 → 개인 리포트 생성 → 커밋·push → Discord 전송 → 개인 리포트 전송을 합니다.
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
- [ ] GitHub 저장소 Secrets 에 `DISCORD_WEBHOOK_URL` 등록 (개인 리포트용 `DISCORD_WEBHOOK_URL_PERSONAL` 도 같은 방법)
- [ ] Settings → Actions → General → Workflow permissions 를 "Read and write permissions" 로
- [ ] Actions 탭에서 `daily indie trending` 을 **Run workflow** 로 한 번 수동 실행해 Discord에 도착하는지 확인
- [ ] 운영하면서 `config.json` 의 `big_publishers` 에 대형 퍼블리셔 이름을 채우기 (본문 제외 조건)

## 폴더

```
collect.py / report.py / cards.py / notify.py   진입점
weekly.py                          주간 리포트 진입점 (market/weekly.py 분석, market/render_weekly.py HTML·보드 카드)
media.py                           미디어·밈 리포트 진입점 (market/media_sources.py 수집, media_analyze.py 분석, render_media.py 임베드·HTML·카드)
personal.py                        개인 리포트 진입점 (profile.json → market/personal.py 분석, market/render_personal.py 임베드·카드)
market/steam.py, itch.py            수집기
market/analyze_steam.py, analyze_itch.py   판정·섹션 구성
market/render.py                    Discord 본문(markdown), HTML, 이미지 카드 HTML(to_cards)
market/common.py, http.py           공통 (스냅샷 로드, 회차 상태, 재시도 HTTP)
config.json                         report_base_url(상세 보고서 링크), 목록 크기, Steam 합성 지역(regions), 본문 포함 조건, 대형 퍼블리셔 목록
data/<platform>/<date>.json         일간 스냅샷 (지우지 않음), data/cache/ 는 Steam 메타 캐시
reports/<platform>/<date>.*         리포트, cards/<date>-N.png 는 카드 뉴스, state.json 은 연속 선정 회차 기록
data/weekly/, reports/weekly/      주간 태그 데이터 · 주간 HTML · 보드 PNG
data/media/, reports/media/        미디어·밈 스냅샷(소스별 상태 포함) · 리포트(.json .md .html) · cards/<date>-N.png · state.json
reports/personal/<date>.*           개인 리포트(.json .md), cards/<date>.png 는 내 범위 Top 3 카드 1장
profile.json                        개인 리포트의 "내 범위" 조건 (차원 · 엔진 · 제외 태그 · 가격 · 플레이 시간 · 멀티 제외 · watchlist)
```
