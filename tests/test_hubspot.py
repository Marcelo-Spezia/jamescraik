"""Test del seam de HubSpot (ui/hubspot.py)."""

from __future__ import annotations

import hubspot


def test_stub_returns_none(monkeypatch):
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)
    src = hubspot.get_source()
    assert isinstance(src, hubspot.StubHubSpotSource)
    assert src.metrics("camp-1") is None
