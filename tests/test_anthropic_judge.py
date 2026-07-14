"""Tests del AnthropicJudgeModel con un cliente mockeado (sin API real)."""

from __future__ import annotations

import asyncio
import json

from icp_engine.adapters.anthropic_judge import AnthropicJudgeModel
from icp_engine.adapters.base import FuzzyResult


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Response:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]


class _FakeMessages:
    """Registra las llamadas y devuelve un JSON configurable."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Response(json.dumps(self._payload))


class _FakeClient:
    def __init__(self, payload: dict) -> None:
        self.messages = _FakeMessages(payload)


def test_evaluate_parses_model_json():
    client = _FakeClient({"score_0_1": 0.83, "rationale": "Stack moderno detectado."})
    judge = AnthropicJudgeModel(model="claude-opus-4-8", client=client)

    result = asyncio.run(
        judge.evaluate("¿Es tech-enabled?", {"name": "Acme", "tech_stack": ["aws"]})
    )

    assert isinstance(result, FuzzyResult)
    assert result.score_0_1 == 0.83
    assert result.rationale == "Stack moderno detectado."
    # Pasa salida estructurada y no setea temperature (Opus 4.8 la rechaza).
    call = client.messages.calls[0]
    assert call["model"] == "claude-opus-4-8"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in call


def test_cache_avoids_second_call():
    client = _FakeClient({"score_0_1": 0.5, "rationale": "Parcial."})
    judge = AnthropicJudgeModel(client=client, cache=True)

    asyncio.run(judge.evaluate("p", {"a": 1}))
    asyncio.run(judge.evaluate("p", {"a": 1}))  # mismo (prompt, datos) → cache

    assert len(client.messages.calls) == 1


def test_plugs_into_scoring_pipeline():
    """El adapter funciona como JudgeModel dentro del motor (detrás de la interfaz)."""
    from pathlib import Path

    from icp_engine.canonical.enums import Industry, Seniority
    from icp_engine.canonical.models import Account, Contact
    from icp_engine.registry.loader import load_icp
    from icp_engine.scoring.pipeline import score

    icp_path = Path(__file__).parent / "fixtures" / "icps" / "valid_with_fuzzy.yaml"
    icp = load_icp(icp_path)

    client = _FakeClient({"score_0_1": 0.9, "rationale": "Madurez digital alta."})
    judge = AnthropicJudgeModel(client=client)

    account = Account(account_id="a1", name="Acme", industry=Industry.SOFTWARE,
                      region="NA", employee_count=500, source="test")
    contact = Contact(contact_id="c1", account_id="a1", full_name="X",
                      seniority=Seniority.VP, source="test")

    result = score(account, contact, icp, judge=judge)

    fuzzy = next(f for f in result.fuzzy if f.id == "digital_maturity")
    assert fuzzy.score_0_1 == 0.9
    assert fuzzy.rationale == "Madurez digital alta."
    assert client.messages.calls  # el motor invocó al judge
