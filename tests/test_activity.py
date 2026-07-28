"""Tests del ActivitySource (ui/activity.py) — seam de la Fase 2."""

from __future__ import annotations

import activity


def test_stub_returns_none_without_provider(monkeypatch):
    monkeypatch.delenv("ICP_ACTIVITY_DEMO", raising=False)
    assert activity.StubActivitySource().fetch_activity("https://linkedin.com/in/x") is None


def test_stub_demo_sample_when_flag_set(monkeypatch):
    monkeypatch.setenv("ICP_ACTIVITY_DEMO", "1")
    got = activity.StubActivitySource().fetch_activity("https://linkedin.com/in/x")
    assert got and "[DEMO]" in got["summary"] and got["source"] == "demo"


def test_stub_demo_needs_a_linkedin_url(monkeypatch):
    monkeypatch.setenv("ICP_ACTIVITY_DEMO", "1")
    assert activity.StubActivitySource().fetch_activity("") is None


def test_get_source_defaults_to_stub(monkeypatch):
    monkeypatch.delenv("CLAY_WEBHOOK_URL", raising=False)
    assert isinstance(activity.get_source(), activity.StubActivitySource)


def test_get_source_uses_clay_when_url_set(monkeypatch):
    monkeypatch.setenv("CLAY_WEBHOOK_URL", "https://clay.example/hook/abc")
    src = activity.get_source()
    assert isinstance(src, activity.ClayActivitySource) and src.mode == "async"


def test_clay_request_posts_lead_and_linkedin():
    src = activity.ClayActivitySource(url="https://clay.example/hook/abc")
    sent = {}

    class _Resp:
        def raise_for_status(self): pass

    def fake_post(url, payload):
        sent["url"], sent["payload"] = url, payload
        return _Resp()

    ok = src.request_activity("lead-123", "https://linkedin.com/in/x", poster=fake_post)
    assert ok is True
    assert sent["url"] == "https://clay.example/hook/abc"
    assert sent["payload"] == {"lead_id": "lead-123", "linkedin_url": "https://linkedin.com/in/x"}


def test_clay_request_skips_without_linkedin():
    src = activity.ClayActivitySource(url="https://clay.example/hook/abc")
    assert src.request_activity("lead-123", "", poster=lambda u, j: None) is False
