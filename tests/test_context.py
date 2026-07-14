"""Tests de la base de contexto de Making Sense (persistencia + inyección)."""

from __future__ import annotations

import json

import chat_builder
import context as ms_context
import qualify


# --- persistencia ---
def test_save_and_load_context(tmp_path, monkeypatch):
    monkeypatch.setattr(ms_context, "CONTEXT_FILE", tmp_path / "context" / "ms.md")
    assert ms_context.has_saved_context() is False
    ms_context.save_context("# MS\nDesarrollo de software.")
    assert ms_context.has_saved_context() is True
    assert "Desarrollo de software" in ms_context.load_context()


def test_load_seeds_from_source(tmp_path, monkeypatch):
    monkeypatch.setattr(ms_context, "CONTEXT_FILE", tmp_path / "ms.md")  # no existe
    seed = tmp_path / "seed.md"
    seed.write_text("contexto semilla", encoding="utf-8")
    monkeypatch.setattr(ms_context, "SEED_SOURCE", seed)
    assert ms_context.load_context() == "contexto semilla"


# --- inyección en los prompts ---
class _Block:
    def __init__(self, t):
        self.type, self.text = "text", t


class _Resp:
    def __init__(self, t):
        self.content = [_Block(t)]


class _FakeClient:
    def __init__(self, t):
        self._t = t
        self.calls = []

    class _M:
        def __init__(self, o):
            self.o = o

        def create(self, **kw):
            self.o.calls.append(kw)
            return _Resp(self.o._t)

    @property
    def messages(self):
        return _FakeClient._M(self)


def test_chat_reply_injects_context():
    client = _FakeClient("ok")
    chat_builder.chat_reply([{"role": "user", "content": "hola"}], client,
                            context="Making Sense hace X y gana en fintech.")
    assert "Making Sense hace X y gana en fintech." in client.calls[0]["system"]


def test_qualify_injects_context():
    client = _FakeClient(json.dumps({"tier": "A", "reason": "ok"}))
    qualify.qualify_lead({"name": "X"}, "rúbrica", "vp", client,
                         context="Casos de éxito en seguros.")
    assert "Casos de éxito en seguros." in client.calls[0]["system"]


def test_context_optional_backcompat():
    # sin context, los prompts siguen funcionando (no rompe firmas anteriores)
    client = _FakeClient("ok")
    chat_builder.chat_reply([{"role": "user", "content": "hola"}], client)
    assert client.calls
