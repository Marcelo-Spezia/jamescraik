# ICP Engine

Motor que representa cualquier ICP (Ideal Customer Profile), lo versiona, y
califica cuentas/contactos contra él con un **fit-score explicable**. POC de la
vertical de Lead Generation (Making Sense).

## Qué hace
- **ICP versionable** (YAML, semver + changelog) — el cliente ideal es dato, no código.
- **Scoring híbrido y explicable**: reglas determinísticas + criterios difusos que
  evalúa un LLM (Claude), cada score con su "por qué".
- **Agnóstico a herramientas**: data/LLM/CRM detrás de adapters. Hoy: Apollo (ingestion/
  enrichment) y Claude (JudgeModel).
- **Armado de listas**: ICP → Apollo (descubrir + enriquecer) → scoring → leads rankeados.
- **UI** (Streamlit): editar el ICP sin tocar YAML + armar listas desde el navegador.

## Estructura
- `src/icp_engine/` — el motor (canonical, registry, scoring, feedback, adapters).
- `icp/` — los ICP versionables (YAML).
- `ui/` — la app Streamlit (`app.py`) + lógica (`icp_io.py`, `leadgen.py`).
- `examples/` — demos de consola.
- `docs/icp-engine-spec.md` — el spec técnico (contrato).

## Correr local
```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,ui]"
pytest -q                 # tests
streamlit run ui/app.py   # la UI
```
Credenciales en `.env` (ver `.env.example`). Nunca se commitea.

## Desplegar (sin instalar nada)
Ver [DEPLOY.md](DEPLOY.md) — Streamlit Community Cloud.
