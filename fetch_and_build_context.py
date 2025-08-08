#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
외부 데이터 연동 시스템 - Dynamic Context Builder
GitHub Actions로 자동화되는 트렌드 데이터 수집 및 컨텍스트 생성
"""

import os
import json
import time
import datetime as dt
import requests
import feedparser
from urllib.parse import urlencode
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 환경변수
X_BEARER = os.getenv("X_BEARER")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# 유틸리티 함수
NOW = dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def score_item(freq=1, growth=0.0, trust=0.7, aeo_weight=1.0):
    """간단 가중합 점수 계산"""
    return round((freq * 0.4 + growth * 0.4 + trust * 0.2) * aeo_weight, 3)

def clean_text(text):
    """텍스트 정제"""
    return " ".join((text or "").split())[:300]

def safe_request(url, headers=None, params=None, timeout=30):
    """안전한 HTTP 요청"""
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return None

# 1) Google Trends 대체 스텁 (실제로는 pytrends 사용 권장)
def fetch_trends_stub(keywords):
    """트렌드 데이터 스텁 - 실제로는 pytrends 사용"""
    logger.info("Fetching Google Trends data (stub)")
    return [
        {"keyword": kw, "freq": 10, "growth": 0.25, "trust": 0.7, "src": "trends"} 
        for kw in keywords
    ]

# 2) X API v2 최근 트윗 카운트
def fetch_x_counts(query, hours=24):
    """X API v2를 통한 트윗 카운트 조회"""
    if not X_BEARER:
        logger.warning("X_BEARER token not found, using dummy data")
        return {"keyword": query, "freq": 5, "growth": 0.0, "trust": 0.8, "src": "x_dummy"}
    
    logger.info(f"Fetching X data for: {query}")
    url = "https://api.twitter.com/2/tweets/counts/recent"
    headers = {"Authorization": f"Bearer {X_BEARER}"}
    params = {"query": query, "granularity": "hour"}
    
    response = safe_request(url, headers=headers, params=params)
    if response:
        data = response.json()
        total = sum([b.get("tweet_count", 0) for b in data.get("data", [])])
        return {"keyword": query, "freq": total, "growth": 0.0, "trust": 0.8, "src": "x_counts"}
    
    # 실패 시 더미 데이터
    return {"keyword": query, "freq": 3, "growth": 0.0, "trust": 0.5, "src": "x_fallback"}

# 3) YouTube Data API v3 검색량 근사
def fetch_youtube_search_count(query):
    """YouTube API를 통한 검색 결과 카운트"""
    if not YOUTUBE_API_KEY:
        logger.warning("YOUTUBE_API_KEY not found, using dummy data")
        return {"keyword": query, "freq": 8, "growth": 0.0, "trust": 0.85, "src": "youtube_dummy"}
    
    logger.info(f"Fetching YouTube data for: {query}")
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "maxResults": 50,
        "key": YOUTUBE_API_KEY,
        "type": "video"
    }
    
    response = safe_request(url, params=params)
    if response:
        items = response.json().get("items", [])
        return {"keyword": query, "freq": len(items), "growth": 0.0, "trust": 0.85, "src": "youtube"}
    
    # 실패 시 더미 데이터
    return {"keyword": query, "freq": 5, "growth": 0.0, "trust": 0.6, "src": "youtube_fallback"}

# 4) RSS 뉴스 피드
def fetch_rss(url):
    """RSS 피드에서 뉴스 수집"""
    logger.info(f"Fetching RSS from: {url}")
    try:
        feed = feedparser.parse(url)
        out = []
        for entry in feed.entries[:20]:
            out.append({
                "title": clean_text(entry.get("title")),
                "url": entry.get("link"),
                "src": "rss"
            })
        return out
    except Exception as e:
        logger.error(f"RSS fetch failed: {e}")
        return []

# AEO 가중치 테이블
AEO_WEIGHTS = {
    "marketing": 1.15,  # CTR 강화
    "education": 1.00,  # 신뢰성 균형
    "academic": 0.95    # 설득 요소 최소화
}

# 모드별 가중치 매핑
MODE_WEIGHT = {
    "sns": "marketing",
    "sales": "marketing", 
    "blog": "marketing",
    "video": "marketing",
    "ebook": "education",
    "edu": "education",
    "public": "academic"
}

# 기본 키워드 풀
BASE_KEYWORDS = [
    "AI automation", "AEO", "SEO", "ChatGPT", "Claude", 
    "react", "python", "javascript", "productivity", "automation"
]

def build_context():
    """메인 컨텍스트 빌드 함수"""
    logger.info("Starting context build process")
    
    # 1) 데이터 수집
    trends = fetch_trends_stub(BASE_KEYWORDS[:5])
    
    x_queries = ["AI automation", "SEO", "productivity"]
    xdata = [fetch_x_counts(q) for q in x_queries]
    
    yt_queries = ["AI tutorial", "SEO guide", "productivity tips"]
    ydata = [fetch_youtube_search_count(q) for q in yt_queries]
    
    # RSS 소스들
    rss_sources = [
        "https://hnrss.org/frontpage",  # Hacker News
        "https://feeds.feedburner.com/TechCrunch"  # TechCrunch
    ]
    rss_data = []
    for rss_url in rss_sources:
        rss_data.extend(fetch_rss(rss_url))
    
    # 2) 정제 및 스코어링
    logger.info("Processing and scoring data")
    items = []
    all_raw_data = trends + xdata + ydata
    
    for raw in all_raw_data:
        for mode, aeo_tag in MODE_WEIGHT.items():
            weight = AEO_WEIGHTS[aeo_tag]
            items.append({
                "mode": mode,
                "keyword": raw["keyword"],
                "score": score_item(raw["freq"], raw["growth"], raw["trust"], weight),
                "source": raw["src"],
                "evidence": None
            })
    
    # 모드별 상위 키워드 선별
    by_mode = {}
    for item in items:
        by_mode.setdefault(item["mode"], []).append(item)
    
    top_by_mode = {
        mode: sorted(lst, key=lambda x: x["score"], reverse=True)[:5] 
        for mode, lst in by_mode.items()
    }
    
    # 3) 요약 및 구조화
    def generate_meta_description(mode):
        return f"{mode.upper()} 모드 최신 트렌드 반영. 핵심 키워드와 실행 가능한 전략으로 즉시 활용 가능합니다."
    
    def generate_headings(mode):
        return [
            f"# {mode.upper()} Mode: Latest Trends",
            "## 핵심 키워드",
            "## 실행 전략",
            "## FAQ"
        ]
    
    # 최종 컨텍스트 구성
    context = {
        "updated_at": NOW,
        "version": "1.0",
        "modes": []
    }
    
    for mode, keyword_list in top_by_mode.items():
        context["modes"].append({
            "mode": mode,
            "top_keywords": [
                {"keyword": item["keyword"], "score": item["score"]} 
                for item in keyword_list
            ],
            "meta_description": generate_meta_description(mode)[:158],
            "headings": generate_headings(mode),
            "faq": [
                {
                    "q": f"{mode} 모드에서 즉시 적용할 수 있는 3가지는?", 
                    "a": "핵심 키워드 반영, 명확한 가치제안, 구체적인 CTA 설정입니다."
                },
                {
                    "q": f"{mode} 모드에서 피해야 할 실수는?", 
                    "a": "키워드 남용, 검증되지 않은 정보 인용, 과도한 형식적 요소 사용입니다."
                }
            ]
        })
    
    logger.info(f"Context built successfully with {len(context['modes'])} modes")
    return context, rss_data[:10]  # 참고 소스 일부만 반환

def render_markdown(context, refs):
    """Markdown 형식으로 컨텍스트 렌더링"""
    lines = []
    lines.append(f"<!-- Dynamic Context Block | Updated: {context['updated_at']} -->")
    lines.append(f"<!-- Version: {context['version']} -->")
    lines.append("")
    
    for mode_data in context["modes"]:
        mode = mode_data["mode"]
        lines.append(f"### [{mode.upper()}] 최신 트렌드 키워드")
        
        for keyword_data in mode_data["top_keywords"]:
            lines.append(f"- **{keyword_data['keyword']}** (점수: {keyword_data['score']})")
        
        lines.append("")
        lines.append(f"**메타 설명**: {mode_data['meta_description']}")
        lines.append("")
        
        # 헤딩 구조
        for heading in mode_data["headings"]:
            lines.append(heading)
        
        lines.append("")
        lines.append("**자주 묻는 질문**")
        for faq in mode_data["faq"]:
            lines.append(f"- **Q**: {faq['q']}")
            lines.append(f"  **A**: {faq['a']}")
        
        lines.append("---")
        lines.append("")
    
    # 참고 소스
    if refs:
        lines.append("### 📰 최신 참고 소스")
        for ref in refs:
            if ref.get("title") and ref.get("url"):
                lines.append(f"- [{ref['title']}]({ref['url']})")
        lines.append("")
    
    lines.append(f"*마지막 업데이트: {context['updated_at']}*")
    
    return "\n".join(lines)

def main():
    """메인 실행 함수"""
    try:
        logger.info("=== Dynamic Context Builder Started ===")
        
        # 컨텍스트 빌드
        context, refs = build_context()
        
        # 디렉토리 생성
        os.makedirs("context", exist_ok=True)
        
        # JSON 파일 저장
        json_path = "context/latest.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(context, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON saved: {json_path}")
        
        # Markdown 파일 저장
        md_path = "context/latest.md"
        markdown_content = render_markdown(context, refs)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        logger.info(f"Markdown saved: {md_path}")
        
        logger.info("=== Dynamic Context Builder Completed Successfully ===")
        
    except Exception as e:
        logger.error(f"Context build failed: {e}")
        raise

if __name__ == "__main__":
    main()