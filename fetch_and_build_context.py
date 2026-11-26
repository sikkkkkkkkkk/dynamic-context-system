#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
외부 데이터 연동 시스템 - Dynamic Context Builder
GitHub Actions로 자동화되는 트렌드 데이터 수집 및 컨텍스트 생성

파이프라인: 수집 → 정제/스코어링 → 요약/구조화 → 프롬프트 주입(latest.md)

설계 원칙
- 실데이터와 대체(fallback) 데이터를 항상 구분한다 (is_fallback 플래그 + 출력 표시).
- 빈도(freq)는 소스마다 단위가 다르므로 소스 안에서 로그 정규화한 뒤 합산한다.
- 성장률(growth)은 '최근 구간 vs 직전 구간' 비교로 계산한다.
- 내용이 바뀌지 않았으면(타임스탬프 제외) 파일을 다시 쓰지 않는다 → 불필요한 커밋 방지.
"""

import os
import json
import math
import datetime as dt
import logging

import requests
import feedparser

try:  # 로컬 실행 시 .env 지원 (Actions에서는 Secrets 사용)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경변수
X_BEARER = os.getenv("X_BEARER")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

CONTEXT_VERSION = "2.0"
CONTEXT_DIR = "context"


def _env_int(name, default):
    """환경변수를 정수로 읽는다. '5  # 주석' 같은 값도 허용."""
    raw = (os.getenv(name) or "").split("#")[0].strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        logger.warning(f"{name}={raw!r} 는 정수가 아니어서 기본값 {default} 사용")
        return default


TOP_N = _env_int("MAX_KEYWORDS_PER_MODE", 5)


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────
def utc_now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def utc_iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(text):
    """텍스트 정제 (공백 정리 + 300자 제한)"""
    return " ".join((text or "").split())[:300]


def safe_request(url, headers=None, params=None, timeout=30):
    """안전한 HTTP 요청. 실패 시 None."""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        # URL에 API 키가 포함될 수 있으므로 예외 메시지 대신 유형과 상태만 기록
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.error(f"Request failed: {type(e).__name__} (status={status}) {url.split('?')[0]}")
        return None


def pct_change(recent, previous):
    """직전 구간 대비 변화율. [-1, 3] 범위로 제한."""
    if previous > 0:
        g = (recent - previous) / previous
    else:
        g = 1.0 if recent > 0 else 0.0
    return max(-1.0, min(g, 3.0))


def make_signal(keyword, src, freq, growth, trust, is_fallback=False, reason=None):
    return {
        "keyword": keyword,
        "src": src,
        "freq": float(freq),
        "growth": float(growth),
        "trust": float(trust),
        "is_fallback": bool(is_fallback),
        "fallback_reason": reason,
    }


def fallback_signal(keyword, src, reason):
    """대체 데이터: 순위를 오염시키지 않도록 중립값 + 낮은 신뢰도."""
    return make_signal(keyword, src, freq=0, growth=0.0, trust=0.3, is_fallback=True, reason=reason)


# ──────────────────────────────────────────────
# 1) 데이터 수집
# ──────────────────────────────────────────────
def trend_from_series(keyword, values):
    """Google Trends 관심도 시계열(0~100)을 신호로 변환: 후반부 평균 vs 전반부 평균."""
    if not values:
        return fallback_signal(keyword, "trends", "빈 시계열")
    half = len(values) // 2
    prev = values[:half] or values
    recent = values[half:]
    prev_mean = sum(prev) / len(prev)
    recent_mean = sum(recent) / len(recent)
    return make_signal(keyword, "trends", recent_mean, pct_change(recent_mean, prev_mean), trust=0.7)


def fetch_google_trends(keywords, timeframe="now 7-d", geo=""):
    """pytrends로 최근 7일 관심도 조회 (한 번에 최대 5개 키워드)."""
    keywords = list(keywords)[:5]
    try:
        from pytrends.request import TrendReq
    except ImportError:
        logger.warning("pytrends 미설치 → Google Trends 대체 데이터 사용")
        return [fallback_signal(kw, "trends", "pytrends 미설치") for kw in keywords]

    logger.info(f"Fetching Google Trends: {keywords}")
    try:
        # retries 인자는 urllib3 2.x와 호환되지 않으므로 사용하지 않는다
        client = TrendReq(hl="en-US", tz=0, timeout=(10, 25))
        client.build_payload(keywords, timeframe=timeframe, geo=geo)
        df = client.interest_over_time()
    except Exception as e:  # pytrends는 429 등 다양한 예외를 던진다
        logger.error(f"Google Trends 실패: {type(e).__name__}")
        return [fallback_signal(kw, "trends", f"요청 실패({type(e).__name__})") for kw in keywords]

    if df is None or getattr(df, "empty", True):
        return [fallback_signal(kw, "trends", "응답 없음") for kw in keywords]

    out = []
    for kw in keywords:
        if kw in df.columns:
            out.append(trend_from_series(kw, [float(v) for v in df[kw].tolist()]))
        else:
            out.append(fallback_signal(kw, "trends", "키워드 누락"))
    return out


def fetch_x_counts(query, hours=24):
    """X API v2 counts/recent: 최근 N시간 vs 직전 N시간 트윗 수."""
    if not X_BEARER:
        logger.warning("X_BEARER 없음 → X 대체 데이터 사용")
        return fallback_signal(query, "x", "X_BEARER 미설정")

    logger.info(f"Fetching X counts for: {query}")
    url = "https://api.twitter.com/2/tweets/counts/recent"
    headers = {"Authorization": f"Bearer {X_BEARER}"}
    params = {"query": f"{query} -is:retweet", "granularity": "hour"}

    response = safe_request(url, headers=headers, params=params)
    if not response:
        return fallback_signal(query, "x", "요청 실패")

    buckets = response.json().get("data", [])
    counts = [b.get("tweet_count", 0) for b in sorted(buckets, key=lambda b: b.get("start", ""))]
    if not counts:
        return fallback_signal(query, "x", "응답 데이터 없음")

    recent = sum(counts[-hours:])
    previous = sum(counts[-2 * hours:-hours])
    return make_signal(query, "x", recent, pct_change(recent, previous), trust=0.8)


def _youtube_total(query, published_after, published_before=None):
    params = {
        "part": "id",
        "q": query,
        "type": "video",
        "maxResults": 1,  # 개수가 아니라 pageInfo.totalResults만 사용
        "publishedAfter": utc_iso(published_after),
        "key": YOUTUBE_API_KEY,
    }
    if published_before:
        params["publishedBefore"] = utc_iso(published_before)
    response = safe_request("https://www.googleapis.com/youtube/v3/search", params=params)
    if not response:
        return None
    return response.json().get("pageInfo", {}).get("totalResults")


def fetch_youtube_search_count(query, hours=24, now=None):
    """YouTube Data API v3: 최근 N시간 업로드 수 vs 직전 N시간 (pageInfo.totalResults)."""
    if not YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY 없음 → YouTube 대체 데이터 사용")
        return fallback_signal(query, "youtube", "YOUTUBE_API_KEY 미설정")

    logger.info(f"Fetching YouTube counts for: {query}")
    now = now or utc_now()
    window = dt.timedelta(hours=hours)
    recent = _youtube_total(query, now - window)
    if recent is None:
        return fallback_signal(query, "youtube", "요청 실패")
    previous = _youtube_total(query, now - 2 * window, now - window)
    growth = pct_change(recent, previous) if previous is not None else 0.0
    return make_signal(query, "youtube", recent, growth, trust=0.85)


def fetch_rss(url, limit=20):
    """RSS 피드에서 뉴스 수집"""
    logger.info(f"Fetching RSS from: {url}")
    try:
        feed = feedparser.parse(url)
        return [
            {"title": clean_text(e.get("title")), "url": e.get("link"), "src": "rss"}
            for e in feed.entries[:limit]
        ]
    except Exception as e:
        logger.error(f"RSS fetch failed: {type(e).__name__}")
        return []


# ──────────────────────────────────────────────
# 2) 정제 및 스코어링
# ──────────────────────────────────────────────
# AEO 가중치 테이블
AEO_WEIGHTS = {
    "marketing": 1.15,  # CTR 강화
    "education": 1.00,  # 신뢰성 균형
    "academic": 0.95,   # 설득 요소 최소화
}

# 모드별 가중치 매핑
MODE_WEIGHT = {
    "sns": "marketing",
    "sales": "marketing",
    "blog": "marketing",
    "video": "marketing",
    "ebook": "education",
    "edu": "education",
    "public": "academic",
}

# 모드별 소스 선호도: 같은 키워드라도 모드에 맞는 소스의 신호를 우대
SOURCE_MODE_BOOST = {
    "sns": {"x": 1.25},
    "sales": {"trends": 1.1, "x": 1.1},
    "blog": {"trends": 1.2},
    "video": {"youtube": 1.3},
    "ebook": {"trends": 1.1},
    "edu": {"youtube": 1.15, "trends": 1.1},
    "public": {"trends": 1.2},
}

MULTI_SOURCE_BONUS = 0.05  # 실데이터 소스가 하나 늘 때마다 가산
FALLBACK_PENALTY = 0.5

# 기본 키워드 풀
BASE_KEYWORDS = [
    "AI automation", "AEO", "SEO", "ChatGPT", "Claude",
    "react", "python", "javascript", "productivity", "automation",
]
X_QUERIES = ["AI automation", "SEO", "productivity"]
YT_QUERIES = ["AI tutorial", "SEO guide", "productivity tips"]
RSS_SOURCES = [
    "https://hnrss.org/frontpage",              # Hacker News
    "https://feeds.feedburner.com/TechCrunch",  # TechCrunch
]


def score_item(freq_norm=0.0, growth=0.0, trust=0.7, aeo_weight=1.0):
    """가중합 점수. freq_norm∈[0,1], growth∈[-1,3]→[0,1]로 매핑."""
    g = (max(-1.0, min(growth, 1.0)) + 1.0) / 2.0
    f = max(0.0, min(freq_norm, 1.0))
    return round((f * 0.4 + g * 0.4 + trust * 0.2) * aeo_weight, 3)


def normalize_freqs(signals):
    """소스별 로그 정규화: log1p(freq)/log1p(max_freq). 대체 데이터는 0."""
    max_by_src = {}
    for s in signals:
        if not s["is_fallback"]:
            max_by_src[s["src"]] = max(max_by_src.get(s["src"], 0.0), s["freq"])
    out = []
    for s in signals:
        m = max_by_src.get(s["src"], 0.0)
        norm = 0.0 if s["is_fallback"] or m <= 0 else math.log1p(s["freq"]) / math.log1p(m)
        out.append({**s, "freq_norm": round(norm, 4)})
    return out


def rank_by_mode(signals, top_n=TOP_N):
    """모드별 점수 계산 → 키워드 단위 병합 → 상위 N개."""
    signals = normalize_freqs(signals)
    result = {}
    for mode, aeo_tag in MODE_WEIGHT.items():
        weight = AEO_WEIGHTS[aeo_tag]
        boosts = SOURCE_MODE_BOOST.get(mode, {})
        merged = {}
        for s in signals:
            score = score_item(s["freq_norm"], s["growth"], s["trust"], weight * boosts.get(s["src"], 1.0))
            if s["is_fallback"]:
                score = round(score * FALLBACK_PENALTY, 3)
            key = s["keyword"].strip().lower()
            entry = merged.setdefault(key, {"keyword": s["keyword"], "best": 0.0, "sources": [], "real": 0})
            entry["best"] = max(entry["best"], score)
            entry["sources"].append(s["src"] + ("(대체)" if s["is_fallback"] else ""))
            entry["real"] += 0 if s["is_fallback"] else 1

        ranked = []
        for e in merged.values():
            bonus = MULTI_SOURCE_BONUS * max(e["real"] - 1, 0)
            ranked.append({
                "keyword": e["keyword"],
                "score": round(e["best"] + bonus, 3),
                "sources": sorted(set(e["sources"])),
                "is_fallback": e["real"] == 0,
            })
        ranked.sort(key=lambda x: (-x["score"], x["keyword"].lower()))
        result[mode] = ranked[:top_n]
    return result


def summarize_quality(signals):
    """소스별 실데이터/대체 데이터 현황."""
    by_src = {}
    for s in signals:
        d = by_src.setdefault(s["src"], {"real": 0, "fallback": 0, "reasons": []})
        if s["is_fallback"]:
            d["fallback"] += 1
            if s["fallback_reason"] and s["fallback_reason"] not in d["reasons"]:
                d["reasons"].append(s["fallback_reason"])
        else:
            d["real"] += 1
    total = len(signals)
    real = sum(d["real"] for d in by_src.values())
    return {
        "real_signals": real,
        "total_signals": total,
        "real_ratio": round(real / total, 3) if total else 0.0,
        "sources": by_src,
    }


# ──────────────────────────────────────────────
# 3) 요약 및 구조화
# ──────────────────────────────────────────────
def build_context(signals, refs, updated_at):
    top_by_mode = rank_by_mode(signals)
    context = {
        "updated_at": updated_at,
        "version": CONTEXT_VERSION,
        "data_quality": summarize_quality(signals),
        "modes": [],
        "references": refs,
    }
    for mode, keyword_list in top_by_mode.items():
        context["modes"].append({
            "mode": mode,
            "top_keywords": keyword_list,
            "meta_description": f"{mode.upper()} 모드 최신 트렌드 반영. 핵심 키워드와 실행 가능한 전략으로 즉시 활용 가능합니다."[:158],
            "headings": [
                f"# {mode.upper()} Mode: Latest Trends",
                "## 핵심 키워드",
                "## 실행 전략",
                "## FAQ",
            ],
            "faq": [
                {"q": f"{mode} 모드에서 즉시 적용할 수 있는 3가지는?",
                 "a": "핵심 키워드 반영, 명확한 가치제안, 구체적인 CTA 설정입니다."},
                {"q": f"{mode} 모드에서 피해야 할 실수는?",
                 "a": "키워드 남용, 검증되지 않은 정보 인용, 과도한 형식적 요소 사용입니다."},
            ],
        })
    logger.info(f"Context built with {len(context['modes'])} modes")
    return context


def collect_signals():
    signals = []
    signals += fetch_google_trends(BASE_KEYWORDS[:5])
    signals += [fetch_x_counts(q) for q in X_QUERIES]
    signals += [fetch_youtube_search_count(q) for q in YT_QUERIES]
    refs = []
    for url in RSS_SOURCES:
        refs.extend(fetch_rss(url))
    refs = [r for r in refs if r.get("title") and r.get("url")][:10]
    return signals, refs


def render_markdown(context):
    """Markdown 형식으로 컨텍스트 렌더링 (프롬프트 주입용)"""
    q = context["data_quality"]
    lines = [
        f"<!-- Dynamic Context Block | Updated: {context['updated_at']} -->",
        f"<!-- Version: {context['version']} -->",
        "",
        f"> 데이터 품질: 실데이터 {q['real_signals']}/{q['total_signals']} "
        f"({q['real_ratio'] * 100:.0f}%)",
    ]
    for src, d in sorted(q["sources"].items()):
        status = f"{d['real']}건 실데이터" + (f", {d['fallback']}건 대체({', '.join(d['reasons'])})" if d["fallback"] else "")
        lines.append(f"> - {src}: {status}")
    if q["real_ratio"] < 0.5:
        lines.append("> ⚠️ 실데이터 비율이 낮습니다. 아래 순위는 참고용으로만 사용하세요.")
    lines.append("")

    for mode_data in context["modes"]:
        lines.append(f"### [{mode_data['mode'].upper()}] 최신 트렌드 키워드")
        for k in mode_data["top_keywords"]:
            tag = " · 대체 데이터" if k["is_fallback"] else ""
            lines.append(f"- **{k['keyword']}** (점수: {k['score']} · 출처: {', '.join(k['sources'])}{tag})")
        lines.append("")
        lines.append(f"**메타 설명**: {mode_data['meta_description']}")
        lines.append("")
        lines.extend(mode_data["headings"])
        lines.append("")
        lines.append("**자주 묻는 질문**")
        for faq in mode_data["faq"]:
            lines.append(f"- **Q**: {faq['q']}")
            lines.append(f"  **A**: {faq['a']}")
        lines.append("---")
        lines.append("")

    if context.get("references"):
        lines.append("### 📰 최신 참고 소스")
        for ref in context["references"]:
            lines.append(f"- [{ref['title']}]({ref['url']})")
        lines.append("")

    lines.append(f"*마지막 업데이트: {context['updated_at']}*")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# 4) 출력 (내용 변경 시에만)
# ──────────────────────────────────────────────
def _without_timestamp(ctx):
    return {k: v for k, v in ctx.items() if k != "updated_at"}


def content_changed(new_context, json_path):
    """타임스탬프를 제외한 내용이 기존 파일과 다른지."""
    try:
        with open(json_path, encoding="utf-8") as f:
            old = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return True
    return _without_timestamp(old) != _without_timestamp(new_context)


def write_outputs(context, out_dir=CONTEXT_DIR):
    """변경이 있을 때만 latest.json / latest.md 저장. 저장 여부 반환."""
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "latest.json")
    md_path = os.path.join(out_dir, "latest.md")

    if not content_changed(context, json_path):
        logger.info("내용 변경 없음 → 파일을 갱신하지 않습니다 (불필요한 커밋 방지)")
        return False

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(context))
    logger.info(f"Saved: {json_path}, {md_path}")
    return True


def main():
    logger.info("=== Dynamic Context Builder Started ===")
    signals, refs = collect_signals()
    context = build_context(signals, refs, utc_iso(utc_now()))
    q = context["data_quality"]
    logger.info(f"실데이터 {q['real_signals']}/{q['total_signals']}")
    write_outputs(context)
    logger.info("=== Dynamic Context Builder Completed ===")


if __name__ == "__main__":
    main()
