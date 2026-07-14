# Handoff a Claude Code — ICP Engine

## Cómo arrancar (pasos)
1. Creá una carpeta nueva para el repo del ICP Engine.
2. Copiá adentro: `CLAUDE.md`, `docs/icp-engine-spec.md`, `docs/icp.example.yaml` (de este Project).
3. Abrí Claude Code en esa carpeta.
4. Pegá el prompt de abajo como primer mensaje.

---

## Prompt de arranque (copiar/pegar)

```
Vamos a construir el ICP Engine, un POC de un motor de calificación de leads.

Antes de escribir código, leé en este orden:
1. CLAUDE.md (instrucciones y principios del repo)
2. docs/icp-engine-spec.md (el spec técnico completo — es el contrato)
3. docs/icp.example.yaml (el schema del ICP materializado)

Contexto: el motor representa cualquier ICP (en YAML, versionable), y califica
una cuenta + un contacto contra una versión de ese ICP, devolviendo un fit-score
explicable (score 0-100 + tier A/B/C/D + knockouts + el "por qué"). El scoring es
híbrido: reglas determinísticas con pesos + un paso LLM para criterios difusos.

Principios que no se negocian (están en CLAUDE.md): agnóstico a herramientas
(todo proveedor detrás de un adapter), ICP vivo y versionable (nunca hardcodear
criterios), y scoring explicable por construcción.

Quiero que primero me propongas:
- el stack que vas a usar y por qué (Python es buen fit, pero decidí vos),
- la estructura de carpetas (tomá como base la sugerida en el spec §15),
- el orden de implementación (empezando por canonical + registry + scoring con
  fixtures, SIN adapters reales todavía).

No escribas código hasta que validemos eso. Cuando lo aprobemos, arrancá por el
modelo canónico (§4) y el registry (§5, §8), con tests.

Definition of done: §14 del spec.
```

---

## Notas
- El **ICP v1 real todavía no está definido** (es contenido, no motor). El motor se prueba con los fixtures / el `icp.example.yaml`. Cuando quieras, volvemos acá y lo definimos con la skill `icp-architect` para guardarlo como el primer archivo de `icp/`.
- El spec es un documento vivo: si durante el build aparece la necesidad de un campo o regla nueva, se actualiza `docs/icp-engine-spec.md` primero y después el código.
- Si Claude Code propone desviarse de los principios (ej. llamar a un proveedor directo desde el scoring), frenalo: eso rompe el "agnóstico" y el "versionable".
