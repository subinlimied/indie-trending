# indie-trending

Steam과 itch.io에서 "소규모 팀이 만들 수 있는 인디게임"이 어떻게 뜨고 지는지를 매일 관찰하는 일간 리포트입니다.
매일 스냅샷을 쌓고 전날과 비교해 **오늘의 선정 게임 → 큰 폭 변화 → 특이사항** 을 Discord 임베드 카드와 이미지 카드 뉴스로 보내고, HTML 상세(01~06 섹션)는 링크로 엽니다.
판정 규칙과 지표 정의는 [rules.md](rules.md)에 있습니다. Python 표준 라이브러리만 씁니다(외부 패키지 없음).

## 실행 방법

```bash
python3 collect.py --date 2026-10-21            # 스냅샷 수집 → data/steam/, data/itch/ (Steam 약 15분)
python3 report.py  --date 2026-10-21            # 리포트 생성 → reports/<platform>/<date>.md .html .json
python3 cards.py   --date 2026-10-21            # 이미지 카드 뉴스 4장 → reports/<platform>/cards/<date>-N.png (헤드리스 Chrome 필요, 없으면 건너뜀)
DISCORD_WEBHOOK_URL=... python3 notify.py --date 2026-10-21   # Discord 전송 (--dry-run 으로 임베드 JSON·첨부 목록만 확인)
DISCORD_WEBHOOK_URL_PERSONAL=... python3 personal.py --date 2026-10-21   # 개인 리포트 (profile.json 기준 "내 범위") → 비공개 채널
```

- `--date` 를 빼면 오늘(KST)입니다. `--only steam|itch` 로 한 플랫폼만 돌릴 수 있습니다.
- 같은 날짜 스냅샷이 있으면 수집을 건너뜁니다. 다시 받으려면 `collect.py --force`.
- 수집은 한 번에 하나만 돌리세요. 같은 IP에서 겹치면 Steam 리뷰 API가 429를 냅니다.
- 회차 1은 비교 대상이 없어 "회차 1 · 비교 없음"으로 나오고, 급상승 판정은 회차 2부터, 연속 판정(승격)은 회차 3부터 들어갑니다.

## 디자인 토큰 · 차트 (모든 리포트 공통)

리포트의 색·글꼴·크기는 전부 [design/tokens.json](design/tokens.json) 한 파일에서 옵니다. 값의 출처는 구글 스티치 시안 [design/stitch/DESIGN.md](design/stitch/DESIGN.md)("Terminal Editorial Intelligence", 표지 카드 [code.html](design/stitch/code.html) · [screen.png](design/stitch/screen.png))입니다. **이 파일의 값만 바꾸면 모든 리포트의 HTML 과 카드 PNG 에 적용됩니다.** 키 이름은 코드가 찾으므로 바꾸지 말고 값만 바꾸십시오. 시안이 라이트 모드를 의도적으로 지원하지 않아 **다크 전용**입니다.

| 키 | 내용 |
|---|---|
| `색.다크` | 바탕 `#0D1117` · 표면 `#171D25` · 표면_2(강조 패널, Steam 남색) `#1B2838` · 선 `#2A323D`(항상 1px) · 글자_1 `#F0F3F6` · 글자_2 `#8B949E` · 상승 `#00E676` · 하락 `#F43F5E` · 경고 `#FFB74D` · 델타 칩 배경 `상승_연함`/`하락_연함`(10% 투명) · 강조_밝음 `#75FF9E`(헤드라인 안 게임 이름) · 플랫폼 `steam`(초록) `itch`(산호) `media`(보라) `personal`(노랑) |
| `글꼴.제목 / 본문 / 숫자` | 헤드라인 Barlow Condensed(700/600, 자간 −0.02em) → Noto Sans KR, 본문 Noto Sans + Noto Sans KR, 숫자·라벨·날짜·순위 JetBrains Mono(탭형). `웹폰트_링크`는 Google Fonts 만(CDN 스크립트 금지). 러너에서 못 받으면 fonts-noto-cjk fallback |
| `타이포` | headline-xl 48/52 · headline-lg 32/36 · headline-md 22/26 · body 16/14/12 · data-xl 38 · data-lg 20 · data-md 14 · label-caps 11(대문자, 자간 0.06em) · badge-num 12 → CSS 변수 `--t-<이름>` 과 클래스 `.t-<이름>` |
| `간격` `모서리` `선_두께` `카드` | 4px 기반(xs 4 · sm 8 · md 12 · lg 20 · xl 32) · 카드 여백 72 · 웹 거터 24 · 마진 32 · 최대 폭 1440 · 모서리 0 · 그림자 없음 · 스파크라인 1.5px · 카드 1080×1350, 표지 캡슐 16:9 최대 460px |

모듈 (Python 표준 라이브러리만):

- [market/ui.py](market/ui.py) — `font_links()`, `css_vars(platform)`(`:root` 변수: `--bg --surface --surface-2 --line --ink --ink-2 --rise --fall --warn --primary-light --accent --font-display/body/mono --t-* --fs-* --sp-* --r-* …`, 옛 이름 `--ground --muted --serif --sans --mono` 별칭), `components_css()`(패널 `.panel` · 라벨 칩 `.lchip`(pos/neg/ghost) · 플랫폼 태그 `.ptag` · 델타 칩 `.delta`(up/down/warn, ▲▼ 접두) · 순위 배지 `.rank`(`.top` 초록 반전) · 스탯 칩 `.chips > .chip`(.lbl .row .val .delta .sub) · 섹션 라벨 `.seclabel` · 배지 `.badge` · 타이포 `.t-*`), `card_head_css(platform)`(카드용 변수 + 틀 `.cardframe .cardhead .cardfoot .cardtitle`), `chart_theme()`.
- [market/series.py](market/series.py) — 최근 7일 스냅샷 시계열. `window()`, `app_series()` → 게임별 `{ranks: {목록: [순위|None]}, reviews, ccu}`, `top_bump()` → 오늘 Top 10 의 7일 순위, `movers()`, `report_block()` → 리포트 JSON 의 `series` 키(분석기가 호출). 7일 미만이면 있는 만큼, `n_days` 로 알려 줍니다.
- [market/charts.py](market/charts.py) — SVG 문자열. `sparkline(values, width, height, labels=['D-6',…,'TODAY'])`(1.5px, 상승 초록·하락 산호, 아래 옅은 세로 그라데이션, 점 아래 순위·날짜 라벨), `bump_chart(series, days, highlight=, secondary=)`(1px 안내선, 초록 강조 3px), `bar_lift(rows=[(태그, 개수, 배율)])`(사각 막대 + 배율 점). 색은 CSS 변수.

일간 게임 리포트는 이 세 모듈 위에 있습니다(`market/render.py` 의 `DAILY_CSS` · `to_html` · `to_cards`). 주간·미디어·개인 리포트는 아직 옛 CSS(`render.CSS` · `render.CARD_CSS`)를 쓰지만 `render.CSS` 의 색·글꼴 변수는 이미 tokens.json 에서 오므로, 같은 방식으로 옮기면 됩니다.

**카드 PNG 4장(일간, screen.png 기준)**: 1 표지(메타 줄 "INDIE TRENDING · STEAM" + 날짜·회차 + EDITION, 초록 칩 라벨, Barlow Condensed 대문자 헤드라인 2줄 "<장르> <게임 이름>, <목록> +n계단 상승", 캡슐 16:9 + 태그·배지 칩 + 7일 리뷰 칩, 스탯 칩 3개, 7일 스파크라인 패널(D-n … TODAY, NEW PEAK), 푸터 "■ 자세히 보기 → indie-trending" + "1 / 4") → 2 범프 차트(Top Sellers 10 / itch New & Popular 10, 가장 크게 오른·내린 게임) → 3 소재·장르 막대 → 4 큰 폭 변화. 헤드라인의 장르 단어는 `render.GENRE_KO` 사전(Roguelike→로그라이크, Deckbuilding→덱빌딩, Cozy→코지 …)으로, 없으면 원어.

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

게임 리포트와 같은 뼈대(스냅샷 누적 → 전날 대비 → 임베드 카드 + 카드 PNG → Discord)로 **틱톡·인스타 릴스·숏폼 트렌드**를 매일 받습니다. **개인 채널 전용**이라 공용 웹훅(`DISCORD_WEBHOOK_URL`)으로는 보내지 않습니다.

```bash
python3 media.py collect --date 2026-10-23            # 스냅샷 → data/media/<date>.json (소스별 정상/실패/건너뜀 상태 포함). --force 재수집, --only kym,reddit 일부만
python3 media.py report  --date 2026-10-23            # reports/media/<date>.json .md .html (+ state.json 연속 일수)
python3 media.py cards   --date 2026-10-23            # 카드 PNG 2장 → reports/media/cards/<date>-N.png (Chrome 없으면 건너뜀)
python3 media.py send    --date 2026-10-23 --dry-run  # 전송 없이 임베드 JSON 출력
DISCORD_WEBHOOK_URL_MEDIA=... python3 media.py send --date 2026-10-23   # 전송 (없으면 DISCORD_WEBHOOK_URL_PERSONAL, 둘 다 없으면 건너뜀)
```

**섹션 (우선순위 순)**

| # | 섹션 | 소스 | 비고 |
|---|---|---|---|
| 01 | 틱톡·인스타 트렌드 | KYM 뉴스피드·확정·제출 RSS + KYM 검색 "tiktok / instagram / reels" 최신순(엔트리 페이지에서 발행·수정 시각) | 최근 48시간 · 제목·요약에 TikTok/Instagram 단서가 있는 항목만. **오늘의 트렌드 한 건**은 여기서 TikTok → Instagram 순으로 최신 것 |
| 02 | 새로 등록된 밈 | KYM 확정(`memes.rss`)·제출(`memes/submissions.rss`) 엔트리 | 제출은 48시간, 확정은 드물어 7일(`kym_confirmed_hours`) 이내. 확정/제출 배지 |
| 03 | 커뮤니티 베스트 | Reddit top(t=day) r/TikTokCringe · memes · popculturechat · shorts · gaming · IndieGaming | 403·429·빈 피드면 그 서브레딧만 실패. r/InstagramReels 는 열리지만 하루치 글이 없어 뺌 |
| 04 | 유튜브 인기 급상승 | YouTube Data API v3 `videos.list(chart=mostPopular)` KR·US 각 50개 중 Top 10 | secret `YOUTUBE_API_KEY` 사용(아래). 60초 이하 영상에는 "쇼츠" 표시. 키 없는 환경에서는 건너뜀 |
| 05 | 검색 급상승 · 세상의 관심사 | Google 트렌드 일간 RSS KR·US, 위키백과 조회수 상위 en·ko | 제외 필터 적용, HTML 에서는 접힘, 임베드에는 상위 3개만 한 줄 |
| 06 | 밈 템플릿 순위 변동 | Imgflip 인기 템플릿 100개 | 전날 대비 ▲▼ · 신규 진입 · 이탈 |
| 07 | 게임 ↔ 밈 교차 | 위 제목들 × `data/steam/` · `data/itch/` 게임 이름 | 소문자 · 3글자 이상 · 부분 일치는 단어 경계, 이름이 2단어 이상이거나 8자 이상일 때만 |
| 08 | 수집 상태 | 소스별 정상/실패/건너뜀 · 개수 · 제외 건수 · Claude 토큰 | |

X 트렌드(trends24.in)는 GitHub Actions 의 IP 대역이 차단되어 뺐습니다.

**제외 필터 (정치·경제·스포츠·사건사고)** — `config.json` 의 `media.exclude_keywords` (`ko`, `en` 목록). Google 트렌드는 검색어와 관련 뉴스 제목을 함께, 위키는 문서 제목을 검사합니다. 한국어 키워드는 부분 일치, 영어는 단어 단위 일치(`rate` 가 `pirate` 를 거르지 않도록), 대소문자 무시. 걸러진 건수는 수집 상태와 임베드 footer 에 나옵니다. **사람 이름(선수·정치인)은 못 거르므로 완벽하지 않습니다.** 자주 보이는 단어는 목록에 추가하세요.

**밈 설명(한국어)과 오늘의 인사이트 — Claude** — 01·02 항목은 수집 단계에서 KYM 엔트리 페이지의 About 문단(영어, 첫 600자)을 `about` 으로 저장하고, HTML 에는 접힌 원문으로 넣습니다. GitHub secret `ANTHROPIC_API_KEY` 가 있으면 report 단계에서 [market/llm.py](market/llm.py) 가 Anthropic Messages API 를 **하루 1회** 호출해(모델 `claude-opus-5-5`, effort low, 구조화 JSON 출력) 항목마다 "무엇인지·어디서 시작됐는지·어떻게 쓰이는지" 두세 문장(`ko_what`)과 게임·콘텐츠 활용 아이디어 한 줄(`ko_idea`), 그리고 리포트 전체를 보고 쓴 인사이트 한 문단을 받습니다. 임베드에는 항목 아래 작은 글씨로, 표지 임베드 끝에 "오늘의 인사이트"로, 카드 2장 중 둘째 장은 "밈 설명 3개 + 인사이트" 카드로 바뀝니다. 키가 없으면 조용히 건너뛰고(영어 About 만 HTML 에), 거절(refusal)·오류(429·5xx 는 2회 재시도)면 설명 없이 리포트를 냅니다. 사용 토큰은 로그와 리포트 JSON 의 `llm_usage` 에 남습니다.
키 만들기: [console.anthropic.com](https://console.anthropic.com) → 결제에 소액 충전 → **API Keys** → 키 만들기 → GitHub 저장소 Secrets 에 `ANTHROPIC_API_KEY` 로 등록. 비용은 하루 1회 호출(입력 약 5천 토큰, 출력 약 2천 토큰)로 **월 2달러 안팎**입니다. `market/llm.py` 의 `complete_json(system, user, schema)` 는 리포트 종류와 무관하게 재사용할 수 있습니다(게임 리포트 인사이트는 다음 작업).

**밈 한국어 설명 루틴 (Claude Code 클라우드 예약 작업)** — 매일 08:40 KST 에 `reports/media/<date>.json` 을 읽어 개인 채널로 밈 설명을 보내는 예약 작업의 지시문은 [routine/meme_ko.md](routine/meme_ko.md) 에 있습니다. 예약 작업 프롬프트에는 웹훅 주소와 이 파일 주소만 있고, 실제 할 일(읽을 JSON 키 · 글자 수 · 임베드 형식)은 이 파일을 읽어 따릅니다. 구성을 바꾸려면 이 파일만 고쳐 커밋하면 됩니다. 리포트 JSON 의 `shortform`·`new_memes` 항목은 `about`(영어 원문)과 `image`(엔트리 og:image)를 있을 때만 담습니다.
같은 방식의 두 번째 루틴 [routine/game_ideas.md](routine/game_ideas.md) 는 게임 리포트(`reports/steam`·`itch`·`personal`)를 읽어 "활용 아이디어 + 제작 인사이트"를 보냅니다. 그 근거가 되는 게임 설명은 Steam·itch 리포트의 `pick` 과 급상승 항목에 `desc`(영어 원문 300자: Steam 스토어 짧은 설명, itch 는 목록 한 줄 소개 또는 페이지 og:description)로 들어갑니다. Steam 설명은 메타 캐시에 함께 저장되며, 캐시에 없는 앱은 `python3 collect.py --date <date> --refresh-meta` 로 한 번에 채울 수 있습니다(1.6초 간격).

**유튜브** — GitHub secret `YOUTUBE_API_KEY` 로 YouTube Data API v3 `videos.list(chart=mostPopular)` 를 KR·US 각 1회(하루 2회, 호출당 1유닛) 불러 인기 급상승 Top 10 을 싣고 60초 이하 영상에 "쇼츠"를 표시합니다. 키가 없는 환경(로컬)에서는 04 섹션이 "건너뜀"으로 나오고 임베드에서는 빠집니다. 키 만들기: Google Cloud 콘솔 → 새 프로젝트 → API 및 서비스 → 라이브러리 → **YouTube Data API v3** 사용 설정 → 사용자 인증 정보 → **API 키 만들기** → GitHub 저장소 Secrets 에 `YOUTUBE_API_KEY` 로 등록. 결제 등록은 필요 없고 일 10,000 유닛까지 무료입니다. 로컬에서는 `YOUTUBE_API_KEY=... python3 media.py collect --only youtube` 로 그 소스만 다시 받을 수 있습니다.

- 카드 PNG: 표지(오늘의 틱톡·인스타 트렌드 + 플랫폼 집계 + 다른 숏폼 항목) · 2장(Claude 설명이 있으면 "밈 설명 3개 + 인사이트", 없으면 새 밈 + 커뮤니티 베스트 + 게임 교차).
- Discord 임베드: 표지(+오늘의 인사이트) · 새 밈 · 커뮤니티 · 유튜브 인기 KR/US · 검색·위키·밈 템플릿·게임 교차(상세 링크 `reports/media/<date>.html`, footer 수집 상태).
- Reddit 익명 RSS 는 IP 당 약 1분에 1회만 허용해 서브레딧 사이를 62초 간격으로 보냅니다(6개 ≈ 6분). 위키 조회수는 09:30 KST 에 전날 집계가 아직 없어 2~3일 전까지 거슬러 받습니다.
- `config.json` 의 `media` 키: `reddit_subs` · `kym_queries` · `kym_hours` · `kym_confirmed_hours` · `wiki_top` · `trends_top` · `imgflip_top` · `exclude_keywords`.
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
market/ui.py, series.py, charts.py  디자인 토큰 CSS · 7일 시계열 · SVG 차트 (design/tokens.json 이 값의 원본)
market/common.py, http.py           공통 (스냅샷 로드, 회차 상태, 재시도 HTTP)
design/tokens.json                  색·글꼴·크기 토큰 (이 파일만 바꾸면 모든 리포트에 적용)
config.json                         report_base_url(상세 보고서 링크), 목록 크기, Steam 합성 지역(regions), 본문 포함 조건, 대형 퍼블리셔 목록
data/<platform>/<date>.json         일간 스냅샷 (지우지 않음), data/cache/ 는 Steam 메타 캐시
reports/<platform>/<date>.*         리포트, cards/<date>-N.png 는 카드 뉴스, state.json 은 연속 선정 회차 기록
data/weekly/, reports/weekly/      주간 태그 데이터 · 주간 HTML · 보드 PNG
data/media/, reports/media/        미디어·밈 스냅샷(소스별 상태 포함) · 리포트(.json .md .html) · cards/<date>-N.png · state.json(연속 일수)
reports/personal/<date>.*           개인 리포트(.json .md), cards/<date>.png 는 내 범위 Top 3 카드 1장
profile.json                        개인 리포트의 "내 범위" 조건 (차원 · 엔진 · 제외 태그 · 가격 · 플레이 시간 · 멀티 제외 · watchlist)
```
