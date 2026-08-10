"""Tests de perfiles de remitente (ui/senders.py): fallback archivo + seed de defaults."""

from __future__ import annotations

import senders


def _force_files(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.setattr(senders, "SENDERS_DIR", tmp_path / "senders")


def test_list_seeds_defaults_when_empty(monkeypatch, tmp_path):
    _force_files(monkeypatch, tmp_path)
    lst = senders.list_senders()
    slugs = {s["slug"] for s in lst}
    assert {"cesar-ceo", "fernando-cro", "rodrigo-bdr"} <= slugs   # sembró los 3 del contexto
    assert all(s.get("voice") for s in lst)                        # cada uno con su voz


def test_save_and_load_and_delete(monkeypatch, tmp_path):
    _force_files(monkeypatch, tmp_path)
    senders.list_senders()  # siembra
    slug = senders.save_sender({"name": "Ana SDR", "role": "SDR", "voice": "directa y cálida",
                                "examples": ["Hola {name}, vi que..."]})
    assert slug == "ana-sdr"
    loaded = senders.load_sender(slug)
    assert loaded["voice"] == "directa y cálida" and loaded["examples"]
    assert senders.delete_sender(slug) is True
    assert senders.load_sender(slug) is None


def test_save_updates_same_slug(monkeypatch, tmp_path):
    _force_files(monkeypatch, tmp_path)
    senders.save_sender({"name": "Ana", "voice": "v1"})
    senders.save_sender({"name": "Ana", "voice": "v2"})
    anas = [s for s in senders.list_senders() if s["slug"] == "ana"]
    assert len(anas) == 1 and anas[0]["voice"] == "v2"
