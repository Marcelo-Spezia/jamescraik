"""JudgeModel real respaldado por Claude (Anthropic) — §6.3, §12.

Implementa la interfaz `JudgeModel` evaluando cada criterio difuso con un
modelo de Claude detrás de la interfaz. El motor de scoring NUNCA importa este
módulo ni el SDK: solo conoce `JudgeModel` (principio agnóstico a herramientas).

Configurable por entorno (el spec no fija proveedor/modelo):
  - ANTHROPIC_API_KEY   credencial (la resuelve el SDK).
  - ICP_JUDGE_MODEL     id del modelo (default: claude-opus-4-8).

Salida estructurada (JSON Schema) garantiza `{score_0_1, rationale}`; el
score se interpreta luego en [0,1] (el pipeline ya lo clampa). Regla §6.3:
si no hay datos suficientes → score 0 + rationale, nunca inventar.
"""

from __future__ import annotations

import json
import os
from typing import Any

from icp_engine.adapters.base import FuzzyResult, JudgeModel

DEFAULT_MODEL = "claude-opus-4-8"

_SYSTEM_PROMPT = (
    "Sos un evaluador de criterios difusos para calificar empresas/contactos "
    "contra un Ideal Customer Profile (ICP). Recibís UN criterio (una pregunta) "
    "y los datos disponibles de la entidad.\n\n"
    "Devolvés SIEMPRE un JSON con dos campos:\n"
    "  - score_0_1: número entre 0.0 y 1.0 = grado en que la entidad cumple el "
    "criterio (1.0 = lo cumple claramente, 0.0 = no lo cumple o no hay evidencia).\n"
    "  - rationale: una frase breve justificando el score, citando la evidencia.\n\n"
    "Reglas (no negociables):\n"
    "  - Basate SOLO en los datos provistos. No inventes hechos.\n"
    "  - Si no hay datos suficientes para juzgar → score_0_1 = 0.0 y aclaralo en "
    "el rationale ('datos insuficientes').\n"
    "  - Sé consistente y calibrado: usá el rango intermedio cuando la evidencia "
    "sea parcial."
)

# JSON Schema para forzar salida estructurada (sin restricciones numéricas, que
# structured outputs no soporta; el rango [0,1] lo clampa el pipeline).
_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "score_0_1": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["score_0_1", "rationale"],
    "additionalProperties": False,
}


class AnthropicJudgeModel(JudgeModel):
    """JudgeModel que delega cada criterio difuso a Claude.

    Args:
        model: id del modelo. Default: env ICP_JUDGE_MODEL o ``claude-opus-4-8``.
        client: cliente AsyncAnthropic ya construido (inyectable para tests).
        max_tokens: tope de tokens de salida (la respuesta es chica).
        cache: si True, cachea por (prompt, datos) en memoria (§6.3: determinismo).
    """

    def __init__(
        self,
        model: str | None = None,
        client: Any | None = None,
        max_tokens: int = 1024,
        cache: bool = True,
    ) -> None:
        self.model = model or os.getenv("ICP_JUDGE_MODEL", DEFAULT_MODEL)
        self.max_tokens = max_tokens
        self._cache: dict[tuple[str, str], FuzzyResult] | None = {} if cache else None

        if client is not None:
            self._client = client
        else:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:  # pragma: no cover - depende del extra
                raise ImportError(
                    "El adapter AnthropicJudgeModel requiere el SDK de Anthropic. "
                    'Instalá el extra: pip install -e ".[anthropic]"'
                ) from exc
            self._client = AsyncAnthropic()

    async def evaluate(
        self,
        criterion_prompt: str,
        entity_data: dict[str, Any],
    ) -> FuzzyResult:
        entity_json = json.dumps(entity_data, ensure_ascii=False, sort_keys=True, default=str)

        if self._cache is not None:
            key = (criterion_prompt, entity_json)
            if key in self._cache:
                return self._cache[key]

        user_content = (
            f"Criterio a evaluar:\n{criterion_prompt}\n\n"
            f"Datos de la entidad (JSON):\n{entity_json}"
        )

        # Sin temperature (Opus 4.8 la rechaza); salida estructurada por schema.
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
            output_config={"format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA}},
        )

        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        result = FuzzyResult(
            score_0_1=float(data["score_0_1"]),
            rationale=str(data.get("rationale", "")),
        )

        if self._cache is not None:
            self._cache[(criterion_prompt, entity_json)] = result
        return result


def build_judge_from_env() -> JudgeModel:
    """Construye el JudgeModel real a partir del entorno (factory para demos/CLI)."""
    return AnthropicJudgeModel()
