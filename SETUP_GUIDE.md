# 🚀 외부 데이터 연동 시스템 설정 가이드

GitHub Actions를 활용한 자동화된 트렌드 데이터 수집 시스템 구축 가이드입니다.

## 📋 목차
1. [사전 준비](#사전-준비)
2. [API 키 발급](#api-키-발급)
3. [GitHub 설정](#github-설정)
4. [로컬 테스트](#로컬-테스트)
5. [자동화 확인](#자동화-확인)
6. [문제해결](#문제해결)

---

## 🛠️ 사전 준비

### 필요한 계정
- GitHub 계정 (리포지토리 생성용)
- X (Twitter) Developer 계정
- Google Cloud Platform 계정 (YouTube API용)

### 시스템 요구사항
- Python 3.11+ 
- Git

---

## 🔑 API 키 발급

### 1. X (Twitter) API Bearer Token

1. **X Developer Portal 접속**: https://developer.twitter.com/en/portal/dashboard
2. **앱 생성**:
   - "Create App" 클릭
   - 앱 이름: `Context-Collector-[랜덤문자]`
   - 앱 설명: "Automated trend data collection for content optimization"
3. **Bearer Token 복사**: 
   - App settings → Keys and tokens → Bearer Token
   - 🚨 **중요**: 토큰을 안전한 곳에 저장

### 2. YouTube Data API v3 Key

1. **Google Cloud Console 접속**: https://console.developers.google.com/
2. **프로젝트 생성**:
   - "새 프로젝트" 클릭
   - 프로젝트 이름: `context-system-[날짜]`
3. **YouTube Data API v3 활성화**:
   - "API 및 서비스" → "라이브러리"
   - "YouTube Data API v3" 검색 후 사용 설정
4. **API 키 생성**:
   - "API 및 서비스" → "사용자 인증 정보"
   - "사용자 인증 정보 만들기" → "API 키"
   - 🚨 **중요**: API 키를 안전한 곳에 저장

---

## 🔧 GitHub 설정

### 1. 리포지토리 생성

```bash
# 새 리포지토리 생성 후
git clone https://github.com/[username]/[repository-name].git
cd [repository-name]

# 생성된 파일들을 리포지토리에 복사
```

### 2. GitHub Secrets 설정

1. **리포지토리 설정 페이지 접속**: 
   - `https://github.com/[username]/[repository]/settings/secrets/actions`

2. **Secrets 추가** ("New repository secret" 클릭):

| Secret 이름 | 값 | 설명 |
|-------------|----|----|
| `X_BEARER` | `Bearer aaaa...` | X API Bearer Token |
| `YOUTUBE_API_KEY` | `AIzaSy...` | YouTube Data API Key |

### 3. 워크플로우 권한 설정

1. **Actions 설정**: `Settings` → `Actions` → `General`
2. **Workflow permissions**: "Read and write permissions" 선택
3. **Save** 클릭

---

## 🧪 로컬 테스트

### 1. 환경 설정

```bash
# 가상환경 생성 (옵션)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어서 실제 API 키 입력
```

### 2. 테스트 실행

```bash
# 스크립트 실행
python fetch_and_build_context.py

# 성공 시 생성되는 파일들
ls context/
# latest.json  latest.md
```

### 3. 결과 확인

```bash
# 생성된 Markdown 파일 확인
cat context/latest.md
```

---

## ⚙️ 자동화 확인

### 1. GitHub Actions 수동 실행

1. **Actions 탭 이동**: `https://github.com/[username]/[repository]/actions`
2. **"Update Dynamic Context" 워크플로우 클릭**
3. **"Run workflow" 버튼 클릭**
4. **실행 결과 확인**

### 2. 스케줄 확인

- **매일 06:00 KST** (UTC 21:00)
- **매일 13:00 KST** (UTC 04:00)

### 3. 자동 커밋 확인

성공적으로 실행되면 다음과 같은 커밋이 자동 생성됩니다:
```
🤖 Update dynamic context 2025-01-08T21:00:15Z
```

---

## 🎯 사용 방법

### Dynamic Context Block 활용

1. **최신 컨텍스트 확인**:
   ```bash
   cat context/latest.md
   ```

2. **시스템 프롬프트에 추가**:
   - `context/latest.md` 내용을 복사
   - 시스템 프롬프트 최상단에 붙여넣기

3. **업데이트 시각 확인**:
   - 파일 최상단의 `Updated: [timestamp]` 확인

---

## 🔧 문제해결

### API 관련 문제

**문제**: `401 Unauthorized` 에러
```bash
# 해결방법
1. API 키가 올바른지 확인
2. GitHub Secrets에 정확히 입력했는지 확인
3. API 키에 적절한 권한이 있는지 확인
```

**문제**: `429 Too Many Requests` 에러
```bash
# 해결방법
1. API 호출 빈도 줄이기 (스케줄 간격 늘리기)
2. API 키 할당량 확인
3. 백오프 전략 적용 (코드에 이미 포함)
```

### GitHub Actions 문제

**문제**: 워크플로우가 실행되지 않음
```bash
# 해결방법
1. .github/workflows/context.yml 파일 위치 확인
2. YAML 문법 오류 확인
3. 리포지토리 Actions 권한 확인
```

**문제**: 커밋이 자동으로 되지 않음
```bash
# 해결방법
1. Workflow permissions 설정 확인
2. 변경사항이 실제로 있는지 확인
3. Git 설정 확인
```

### 로컬 실행 문제

**문제**: `ModuleNotFoundError`
```bash
# 해결방법
pip install -r requirements.txt
```

**문제**: 환경변수를 찾을 수 없음
```bash
# 해결방법
1. .env 파일이 올바른 위치에 있는지 확인
2. 환경변수 이름이 정확한지 확인
3. python-dotenv가 설치되어 있는지 확인
```

---

## 📈 고도화 옵션

### 1. 추가 데이터 소스
- Reddit API
- 네이버 트렌드 
- 구글 뉴스 RSS
- Stack Overflow API

### 2. 스코어링 알고리즘 개선
- 머신러닝 기반 중요도 예측
- 시계열 트렌드 분석
- 사용자 참여도 가중치

### 3. 캐싱 및 성능 최적화
- Redis 캐싱
- 비동기 API 호출
- 병렬 처리

---

## 📞 지원

문제가 발생하면 다음을 확인해 주세요:

1. **로그 확인**: GitHub Actions → 해당 워크플로우 → 로그 상세 보기
2. **API 상태**: 각 API 서비스 상태 페이지 확인
3. **할당량 확인**: API 사용량이 제한에 걸리지 않았는지 확인

---

> ✨ **팁**: 시스템이 안정적으로 동작하기 시작하면, 수집되는 데이터를 분석해서 더 정교한 키워드 선별 로직을 구현할 수 있습니다!