# 🤖 Dynamic Context System

GitHub Actions를 활용한 자동화된 외부 데이터 연동 시스템

## 📖 개요

이 시스템은 **수집 → 정제/스코어링 → 요약/구조화 → 프롬프트 주입**의 4단계 파이프라인으로 구성된 자동화 트렌드 데이터 수집 도구입니다.

## ✨ 주요 기능

- 🕒 **자동화된 스케줄링**: GitHub Actions로 매일 2회 자동 실행
- 📊 **다중 데이터 소스**: X(Twitter) API, YouTube API, RSS 피드
- 🎯 **모드별 최적화**: SNS, Blog, Video, Education 등 7가지 모드
- 🔄 **Dynamic Context Block**: 시스템 프롬프트에 바로 적용 가능한 형태로 출력
- 🛡️ **안전한 API 관리**: GitHub Secrets를 통한 보안 관리

## 🏗️ 시스템 아키텍처

```
[GitHub Actions 스케줄러]
     ↓
[데이터 수집 모듈]
├── Google Trends
├── X API v2 
├── YouTube Data API v3
└── RSS 피드
     ↓
[정제·스코어링 엔진]
├── 중복/노이즈 제거
├── AEO 가중치 적용
└── 모드별 점수 계산
     ↓
[구조화 및 출력]
├── JSON 데이터
├── Markdown 형태
└── Dynamic Context Block
```

## 📁 파일 구조

```
dynamic-context-system/
├── .github/workflows/
│   └── context.yml              # GitHub Actions 워크플로우 (테스트 → 갱신)
├── context/                     # 생성된 컨텍스트 파일들
│   ├── latest.json             # JSON 형태 데이터
│   └── latest.md               # Markdown 형태 출력
├── fetch_and_build_context.py  # 메인 스크립트
├── tests/                       # pytest 테스트
├── .claude/                     # Claude Code 설정·스킬
├── CLAUDE.md                    # AI 에이전트 프로젝트 규칙
├── requirements.txt             # Python 의존성
├── requirements-dev.txt         # 개발·테스트 의존성
├── .env.example                # 환경변수 템플릿
├── SETUP_GUIDE.md              # 상세 설정 가이드
└── README.md                   # 이 파일
```

## 🚀 빠른 시작

### 1. API 키 발급
- **X API**: https://developer.twitter.com/en/portal/dashboard
- **YouTube API**: https://console.developers.google.com/

### 2. GitHub Secrets 설정
리포지토리 Settings → Secrets and variables → Actions에서 설정:
- `X_BEARER`: X API Bearer Token  
- `YOUTUBE_API_KEY`: YouTube Data API Key

### 3. 워크플로우 활성화
GitHub Actions 탭에서 "Update Dynamic Context" 워크플로우를 수동 실행

## 📊 출력 예시

### Dynamic Context Block (v2.0)
```markdown
<!-- Dynamic Context Block | Updated: 2026-11-26T21:00:15Z -->
<!-- Version: 2.0 -->

> 데이터 품질: 실데이터 9/11 (82%)
> - trends: 5건 실데이터
> - x: 1건 실데이터, 2건 대체(요청 실패)
> - youtube: 3건 실데이터

### [SNS] 최신 트렌드 키워드
- **SEO** (점수: 0.912 · 출처: trends, x)
- **AI automation** (점수: 0.874 · 출처: trends, x(대체))
- **Claude** (점수: 0.801 · 출처: trends)
```
> 위 수치는 형식 예시입니다. 실제 값은 실행할 때마다 달라집니다.

### 스코어링 방식 (v2.0)
| 단계 | 내용 |
|---|---|
| 빈도 | 소스 안에서 `log1p(freq)/log1p(max)`로 0~1 정규화 (소스 간 단위 차이 제거) |
| 성장률 | 최근 구간 vs 직전 구간 변화율, [-1, 3]으로 제한 |
| 점수 | `(빈도×0.4 + 성장률×0.4 + 신뢰도×0.2) × AEO 가중치 × 모드별 소스 선호도` |
| 병합 | 같은 키워드는 모드별로 합치고, 실데이터 소스가 여럿이면 +0.05씩 |
| 대체 데이터 | API 키 없음/요청 실패 시 중립값 + 점수 50% 감점, 출력에 `대체`로 표시 |
| 커밋 | 타임스탬프 외 내용이 같으면 파일을 쓰지 않아 봇 커밋이 생기지 않음 |

## ⚙️ 설정 옵션

### 스케줄 설정
- 매일 06:00 KST (UTC 21:00)
- 매일 13:00 KST (UTC 04:00)
- 수동 실행 가능

### AEO 가중치
- **Marketing**: 1.15 (CTR 강화)
- **Education**: 1.00 (신뢰성 균형)  
- **Academic**: 0.95 (설득 요소 최소화)

## 🔧 로컬 개발

```bash
# 저장소 클론
git clone https://github.com/[username]/dynamic-context-system.git
cd dynamic-context-system

# 의존성 설치 (테스트 포함)
pip install -r requirements-dev.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 실제 API 키 입력

# 테스트
python -m pytest -q

# 실행 (키가 없으면 대체 데이터로 동작하고 출력에 표시됨)
python fetch_and_build_context.py
```

## 🤖 AI 에이전트 작업 규칙

- 프로젝트 규칙: [`CLAUDE.md`](CLAUDE.md)
- 포함된 스킬 5종(addyosmani/agent-skills, MIT): [`.claude/skills/`](.claude/skills/README.md)
- 전체 스킬·커맨드 설치: Claude Code에서 `/plugin install agent-skills@addy-agent-skills`

## 📈 확장 가능성

- **추가 데이터 소스**: Reddit API, 네이버 트렌드, Google News
- **ML 기반 스코어링**: 머신러닝을 통한 중요도 예측
- **실시간 업데이트**: 웹소켓을 통한 실시간 컨텍스트 업데이트
- **다국어 지원**: 언어별 트렌드 분석

## 🛠️ 문제해결

자세한 문제해결 방법은 [SETUP_GUIDE.md](SETUP_GUIDE.md)를 참조하세요.

## 📝 라이선스

MIT License

---

**만든이**: Dynamic Context System  
**업데이트**: 2026-11-26  
**버전**: 2.0.0