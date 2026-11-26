# Project: Dynamic Context System

트렌드 데이터를 수집 → 정제/스코어링 → 구조화해 `context/latest.md`(프롬프트 주입용 Dynamic Context Block)와 `context/latest.json`을 만든다. GitHub Actions가 하루 2회(06:00, 13:00 KST) 실행한다.

## Tech Stack
- Python 3.11 (CI 기준), 단일 스크립트 `fetch_and_build_context.py`
- requests, feedparser, pytrends(+pandas<3), python-dotenv
- 테스트: pytest (`tests/`)

## Commands
- 의존성: `pip install -r requirements-dev.txt`
- 테스트: `python -m pytest -q`
- 실행(로컬): `python fetch_and_build_context.py` (`.env`에 키가 없으면 대체 데이터로 동작)

## 데이터 규칙 (깨지면 안 되는 것)
- 실데이터와 대체 데이터는 항상 구분한다. 수집기가 실패하면 `fallback_signal()`을 반환하고 `is_fallback=True`, `fallback_reason`을 채운다. 가짜 수치를 실데이터처럼 내보내지 않는다.
- 빈도는 소스마다 단위가 다르다(YouTube totalResults ≫ X 트윗 수 ≫ Trends 0~100). 반드시 `normalize_freqs()`로 소스 안에서 정규화한 뒤 점수에 넣는다.
- 성장률은 `pct_change(최근 구간, 직전 구간)`으로 계산하고 [-1, 3]으로 제한한다.
- 같은 키워드는 모드별로 병합한다(`rank_by_mode`). 실데이터 소스가 여럿이면 보너스.
- 타임스탬프 외에 바뀐 내용이 없으면 `write_outputs()`가 파일을 쓰지 않는다. 이 동작이 불필요한 봇 커밋을 막는다.
- `latest.json` 스키마는 기존 키(`updated_at`, `version`, `modes[].top_keywords[].keyword/score`)를 유지한 채 필드를 추가만 한다. 스키마를 깨는 변경은 `CONTEXT_VERSION`을 올린다.

## Boundaries
- `context/latest.*`는 봇이 관리한다. 사람이나 에이전트가 직접 수정·커밋하지 않는다.
- API 키를 코드, 로그, 커밋에 남기지 않는다. 로그에는 URL의 쿼리스트링(키 포함 가능)을 찍지 않는다.
- pytrends `TrendReq`에 `retries`를 넘기지 않는다(urllib3 2.x와 충돌).
- 수집기나 스코어링 로직을 바꾸면 실패하는 테스트를 먼저 추가한다.
- 외부 API 동작은 기억이 아니라 공식 문서로 확인한다(X API v2 counts, YouTube Data API v3 search, pytrends).

## Skills
- `.claude/skills/`: agent-skills에서 가져온 5개 스킬 (출처·버전은 `.claude/skills/README.md`).
- 전체 세트와 `/spec` `/plan` `/build` `/test` `/review` `/ship`: `/plugin install agent-skills@addy-agent-skills`.
