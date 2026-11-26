import json
import datetime as dt
from unittest import mock

import pytest

import fetch_and_build_context as fc


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


# ── 스코어링 ────────────────────────────────────
def test_score_is_monotonic_in_freq_and_growth():
    assert fc.score_item(0.9, 0.0) > fc.score_item(0.1, 0.0)
    assert fc.score_item(0.5, 0.8) > fc.score_item(0.5, -0.5)


def test_score_is_bounded_even_for_huge_inputs():
    # 예전 버그: YouTube 개수(50)가 그대로 들어가 점수가 23.195로 고정됨
    assert fc.score_item(50, 100, 1.0, 1.15) == fc.score_item(1.0, 1.0, 1.0, 1.15)
    assert fc.score_item(1.0, 1.0, 1.0, 1.0) == 1.0


def test_pct_change_handles_zero_and_clips():
    assert fc.pct_change(10, 0) == 1.0
    assert fc.pct_change(0, 0) == 0.0
    assert fc.pct_change(1000, 1) == 3.0
    assert fc.pct_change(5, 10) == -0.5


def test_normalize_is_per_source_and_ignores_fallback():
    signals = [
        fc.make_signal("a", "youtube", 1_000_000, 0, 0.85),
        fc.make_signal("b", "youtube", 1_000, 0, 0.85),
        fc.make_signal("c", "x", 50, 0, 0.8),
        fc.fallback_signal("d", "x", "test"),
    ]
    norm = {s["keyword"]: s["freq_norm"] for s in fc.normalize_freqs(signals)}
    assert norm["a"] == 1.0
    assert norm["c"] == 1.0  # 소스 안에서 최댓값이면 1 — 소스 간 단위 차이 제거
    assert 0 < norm["b"] < 1
    assert norm["d"] == 0.0


# ── 랭킹 ───────────────────────────────────────
def _sample_signals():
    return [
        fc.make_signal("AI tutorial", "youtube", 5000, 0.5, 0.85),
        fc.make_signal("SEO", "x", 8000, 0.1, 0.8),
        fc.make_signal("SEO", "trends", 60, 0.2, 0.7),
        fc.make_signal("Claude", "trends", 40, 0.9, 0.7),
        fc.fallback_signal("AEO", "trends", "test"),
    ]


def test_rank_merges_duplicate_keywords_across_sources():
    ranked = fc.rank_by_mode(_sample_signals())
    seo = [k for k in ranked["blog"] if k["keyword"] == "SEO"]
    assert len(seo) == 1
    assert seo[0]["sources"] == ["trends", "x"]


def test_fallback_keywords_rank_below_real_and_are_flagged():
    ranked = fc.rank_by_mode(_sample_signals())
    for mode, items in ranked.items():
        assert items[-1]["keyword"] == "AEO", mode
        assert items[-1]["is_fallback"] is True


def test_modes_are_differentiated_by_source_preference():
    signals = [
        fc.make_signal("video-kw", "youtube", 100, 0.3, 0.8),
        fc.make_signal("sns-kw", "x", 100, 0.3, 0.8),
    ]
    ranked = fc.rank_by_mode(signals)
    assert ranked["video"][0]["keyword"] == "video-kw"
    assert ranked["sns"][0]["keyword"] == "sns-kw"


def test_top_n_limit():
    signals = [fc.make_signal(f"k{i}", "trends", i + 1, 0, 0.7) for i in range(12)]
    assert all(len(v) == 3 for v in fc.rank_by_mode(signals, top_n=3).values())


# ── 수집기 ─────────────────────────────────────
def test_trend_from_series_uses_recent_vs_previous_half():
    s = fc.trend_from_series("kw", [10, 10, 20, 20])
    assert s["freq"] == 20
    assert s["growth"] == 1.0
    assert not s["is_fallback"]


def test_x_counts_compares_last_24h_with_previous_24h(monkeypatch):
    monkeypatch.setattr(fc, "X_BEARER", "dummy")
    buckets = [{"start": f"2026-01-01T{h:02d}", "tweet_count": 1} for h in range(24)]
    buckets += [{"start": f"2026-01-02T{h:02d}", "tweet_count": 3} for h in range(24)]
    with mock.patch.object(fc, "safe_request", return_value=FakeResponse({"data": buckets})):
        s = fc.fetch_x_counts("SEO")
    assert s["freq"] == 72
    assert s["growth"] == 2.0
    assert not s["is_fallback"]


def test_x_without_token_is_fallback(monkeypatch):
    monkeypatch.setattr(fc, "X_BEARER", None)
    s = fc.fetch_x_counts("SEO")
    assert s["is_fallback"] and s["freq"] == 0


def test_youtube_uses_total_results_not_item_count(monkeypatch):
    monkeypatch.setattr(fc, "YOUTUBE_API_KEY", "dummy")
    responses = [
        FakeResponse({"pageInfo": {"totalResults": 1200}, "items": [{}]}),
        FakeResponse({"pageInfo": {"totalResults": 800}, "items": [{}]}),
    ]
    now = dt.datetime(2026, 11, 26, tzinfo=dt.timezone.utc)
    with mock.patch.object(fc, "safe_request", side_effect=responses) as req:
        s = fc.fetch_youtube_search_count("AI tutorial", now=now)
    assert s["freq"] == 1200
    assert s["growth"] == pytest.approx(0.5)
    first_params = req.call_args_list[0].kwargs["params"]
    assert first_params["publishedAfter"] == "2026-11-25T00:00:00Z"
    second_params = req.call_args_list[1].kwargs["params"]
    assert second_params["publishedBefore"] == "2026-11-25T00:00:00Z"


def test_youtube_request_failure_is_fallback(monkeypatch):
    monkeypatch.setattr(fc, "YOUTUBE_API_KEY", "dummy")
    with mock.patch.object(fc, "safe_request", return_value=None):
        s = fc.fetch_youtube_search_count("AI tutorial")
    assert s["is_fallback"]


def test_google_trends_failure_is_fallback():
    fake_module = mock.MagicMock()
    fake_module.TrendReq.return_value.build_payload.side_effect = RuntimeError("429")
    with mock.patch.dict("sys.modules", {"pytrends": mock.MagicMock(), "pytrends.request": fake_module}):
        out = fc.fetch_google_trends(["a", "b"])
    assert [s["is_fallback"] for s in out] == [True, True]


# ── 출력 ───────────────────────────────────────
def test_markdown_shows_quality_and_fallback_marks():
    ctx = fc.build_context(_sample_signals(), [{"title": "t", "url": "https://e.x"}], "2026-01-01T00:00:00Z")
    md = fc.render_markdown(ctx)
    assert "데이터 품질: 실데이터 4/5" in md
    assert "대체 데이터" in md
    assert "[t](https://e.x)" in md


def test_write_outputs_skips_when_only_timestamp_changes(tmp_path):
    ctx1 = fc.build_context(_sample_signals(), [], "2026-01-01T00:00:00Z")
    assert fc.write_outputs(ctx1, str(tmp_path)) is True

    ctx2 = fc.build_context(_sample_signals(), [], "2026-01-02T00:00:00Z")
    assert fc.write_outputs(ctx2, str(tmp_path)) is False
    saved = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert saved["updated_at"] == "2026-01-01T00:00:00Z"

    ctx3 = fc.build_context(_sample_signals()[:2], [], "2026-01-03T00:00:00Z")
    assert fc.write_outputs(ctx3, str(tmp_path)) is True


def test_env_int_tolerates_inline_comment(monkeypatch):
    monkeypatch.setenv("MAX_KEYWORDS_PER_MODE", "7     # 모드별 최대 키워드 수")
    assert fc._env_int("MAX_KEYWORDS_PER_MODE", 5) == 7
    monkeypatch.setenv("MAX_KEYWORDS_PER_MODE", "abc")
    assert fc._env_int("MAX_KEYWORDS_PER_MODE", 5) == 5
