# ICP Engine

Motor que representa **cualquier** ICP, lo versiona, y califica cuentas/contactos contra él con un fit-score explicable. POC de la vertical de Lead Generation (Making Sense).

## Fuente de verdad
- `docs/icp-engine-spec.md` — spec técnico completo. **Es el contrato.** Si algo del código necesita un campo nuevo, primero se actualiza el spec.
- `docs/icp.example.yaml` — template del artefacto ICP (lo versionable).

## Principios (no negociables)
1. **Agnóstico a herramientas.** Toda fuente externa (data, enrichment, CRM, output, LLM) vive detrás de una interfaz adapter. El motor opera solo sobre el modelo canónico. Nunca importar SDKs de proveedores dentro de `scoring/`.
2. **ICP vivo y versionable.** El ICP es dato (YAML), externo al motor, con semver + changelog. El motor nunca hardcodea criterios. Multi-ICP nativo.
3. **Ágil y ligero.** Scoring explicable por construcción (cada score trae su "por qué"). Determinístico donde se puede; LLM solo para criterios difusos.

## Alcance del POC
Dentro: ICP Registry + Scoring Engine + Feedback loop + fit-rate. Tajada fina de ingestion/enrichment con fixtures.
Fuera: list builder a escala (E2), qualification/handoff (E3), outreach (E4), dashboard (E5), UI de edición del ICP.

## Orden de construcción sugerido
1. `canonical/` — modelos Account / Contact / Signal (§4 del spec).
2. `registry/` — carga + validación de ICP YAML (§5, §8). Rechazar ICP inválido.
3. `scoring/` — pipeline de 5 pasos (§6) con **fixtures**, sin adapters reales.
4. `feedback/` — contrato §10 + ICP-fit rate §11.
5. `adapters/` — recién acá implementaciones reales (§12), una por proveedor.

## Definition of done
Ver §14 del spec. Clave: dado `(Account, Contact, ICP@version)` devolver un `ScoreResult` completo y explicable, con knockouts/disqualifiers forzando tier D, fuzzy detrás de `JudgeModel` configurable, y scores asociados a su versión de ICP.

## Reglas de build
- `JudgeModel` (LLM) detrás de interfaz desde el día uno; configurable por env; nunca un proveedor hardcodeado en el pipeline.
- Tests del scoring con ICPs sintéticos: knockout, disqualifier, match parcial, intent boost, límites de tier.
- Empezar con datos mock (fixtures) y probar el motor end-to-end antes de tocar cualquier herramienta del stack.
- Stack a elección. Python es buen fit (data/YAML/validación/LLM), pero no es requisito.
