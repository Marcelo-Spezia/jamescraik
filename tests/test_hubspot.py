"""Tests del adapter de HubSpot (ui/hubspot.py)."""

from __future__ import annotations

import hubspot


def test_stub_when_no_token(monkeypatch):
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)
    src = hubspot.get_source()
    assert isinstance(src, hubspot.StubHubSpotSource)
    assert src.configured is False
    assert src.conversions() == {"by_linkedin": {}, "by_email": {}}


def test_real_source_when_token(monkeypatch):
    monkeypatch.setenv("HUBSPOT_TOKEN", "tok")
    src = hubspot.get_source()
    assert isinstance(src, hubspot.HubSpotSource)
    assert src.configured is True


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Cliente httpx falso: devuelve páginas fijas y registra los bodies enviados."""

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append(json)
        return _FakeResp(self._pages[len(self.calls) - 1])


def test_conversions_indexes_by_linkedin_and_email():
    page = {"results": [
        {"properties": {"hs_linkedin_url": "https://www.linkedin.com/in/Maxi/",
                        "email": "Maxi@Acme.com",
                        "engagements_last_meeting_booked": "2026-06-09T20:00:00Z"}},
        {"properties": {"exp_contact_profile_url": "https://www.linkedin.com/in/dave/",
                        "num_associated_deals": "2"}},
    ]}
    src = hubspot.HubSpotSource(token="t", client=_FakeClient([page]))
    conv = src.conversions()
    # LinkedIn URL normalizada igual que en leads_store; email en minúsculas.
    assert conv["by_linkedin"]["linkedin.com/in/maxi"] == {"meeting": True, "deals": 0}
    assert conv["by_email"]["maxi@acme.com"]["meeting"] is True
    assert conv["by_linkedin"]["linkedin.com/in/dave"] == {"meeting": False, "deals": 2}


def test_conversions_paginates():
    p1 = {"results": [{"properties": {"hs_linkedin_url": "https://linkedin.com/in/a",
                                      "num_associated_deals": "1"}}],
          "paging": {"next": {"after": "CURSOR"}}}
    p2 = {"results": [{"properties": {"hs_linkedin_url": "https://linkedin.com/in/b",
                                      "engagements_last_meeting_booked": "x"}}]}
    client = _FakeClient([p1, p2])
    conv = hubspot.HubSpotSource(token="t", client=client).conversions()
    assert set(conv["by_linkedin"]) == {"linkedin.com/in/a", "linkedin.com/in/b"}
    assert client.calls[1]["after"] == "CURSOR"  # la 2da página usa el cursor


def test_merge_combines_duplicate_identifier():
    page = {"results": [
        {"properties": {"hs_linkedin_url": "in/x", "num_associated_deals": "1"}},
        {"properties": {"hs_linkedin_url": "in/x",
                        "engagements_last_meeting_booked": "y", "num_associated_deals": "3"}},
    ]}
    conv = hubspot.HubSpotSource(token="t", client=_FakeClient([page])).conversions()
    assert conv["by_linkedin"]["in/x"] == {"meeting": True, "deals": 3}  # OR reunión, max deals
