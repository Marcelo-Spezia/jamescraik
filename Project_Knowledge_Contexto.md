# Contexto del Project — Lead Gen Solution (Making Sense)
_Fuente de verdad de la iniciativa. Última actualización: 18 de junio de 2026._

> Subí este archivo a la **base de conocimiento** del Project. Resume las decisiones de la sesión de estrategia. Acompañalo del documento completo (`Estrategia_LeadGen_MakingSense.docx`) y del resumen visual (`Resumen_Ejecutivo_LeadGen.html`).

---

## 1. Resumen
La vertical de Lead Generation de Making Sense desarrolla una **herramienta interna** que permita trabajar de forma ágil en el proceso end-to-end de outbound. La solución es una **capa de orquestación con agentes de IA** que automatiza el trabajo repetitivo, conectando —sin atarse— el stack que el equipo ya usa. El primer foco es la raíz del problema de calidad: **targeting/ICP**, vía un POC llamado **ICP Engine**.

## 2. Equipo y restricciones
- **Líder / dueño de la iniciativa:** Marchel Spezia.
- **SME (demand gen):** Nicolás.
- **Build:** Claude + herramientas de vibe coding. **Sin equipo técnico dedicado.**
- **Implicación:** construir de forma agéntica y ligera; validar con automatizaciones antes de invertir en desarrollo pesado.

## 3. Usuarios
- **Primarios:** SDRs/BDRs y Marketing / Demand generation.
- **Stakeholder:** líder de la vertical (visibilidad de pipeline y de qué funciona).

### Proto-personas y Jobs-to-be-Done
- **Sofía — SDR/BDR:** "Cuando recibo una lista de cuentas objetivo, quiero lanzar secuencias multicanal personalizadas rápido, para agendar reuniones sin perder horas en setup manual."
- **Nicolás — Demand gen / SME:** "Cuando una campaña genera leads, quiero que se enriquezcan, califiquen y enruten solos, para que los buenos lleguen al SDR con contexto y nada se pierda."
- **Marchel — Líder (stakeholder):** "Quiero visibilidad del pipeline y de qué funciona, para decidir dónde invertir y escalar el output del equipo."

## 4. Problema (problem statement)
El equipo no logra escalar el volumen de outbound sin degradar la calidad de los leads. La calidad rompe principalmente en **targeting/ICP**: al crecer el volumen, las listas se llenan de contactos fuera del cliente ideal y sales reporta que los leads no encajan. La causa raíz es un proceso **fragmentado y manual** repartido entre HubSpot, Apollo, Clay y Expandi, sin un ICP riguroso aplicado de forma consistente ni automatización del armado/enriquecimiento de listas.

**How Might We:** ¿Cómo podríamos definir, aplicar y mantener vivo un ICP riguroso —que pueda evolucionar en el tiempo— y automatizar la construcción y enriquecimiento de listas de calidad, para escalar el volumen de outbound sin sacrificar la calidad del lead?

**Validación:** feedback cualitativo de sales (leads no encajan). Acción pendiente: capturar baseline del % de leads "fit ICP".

## 5. North star y objetivos
- **North star:** más reuniones calificadas sin sumar headcount.
- Escalar volumen manteniendo/ subiendo el % de leads "fit ICP".
- Más output por persona (agentes hacen lo repetitivo).
- Proceso medible y repetible con visibilidad de pipeline.

## 6. Scope end-to-end
1. **ICP & targeting** (+ enrichment de datos) — _foco inicial_
2. Outreach & secuencias multicanal (email, LinkedIn)
3. Calificación & handoff a sales
4. Medición & optimización del funnel

## 7. Solución — oportunidades
- **O1 · ICP poco riguroso / inconsistente** → ICP vivo, codificado y versionable (multi-ICP) con scoring; biblioteca de señales (firmográficas, tecnográficas, intent); reglas de fit automáticas.
- **O2 · Armado y enrichment manual** → agente que toma el ICP y arma/enriquece listas desde fuentes vigentes (ej. Apollo/Clay); de-dup y validación contra el CRM (ej. HubSpot); entrega lista para secuenciar.
- **O3 · Calificación/handoff sin contexto** → scoring pre-handoff; resumen de contexto por lead; loop de feedback (sales marca fit/no-fit → refina el ICP).

### POC: ICP Engine
Definir el ICP riguroso —artefacto vivo y versionable, capaz de incorporar nuevos ICPs— y construir una automatización (vibe coding) que arme y enriquezca una lista aplicándolo, con loop de feedback de sales. Mínimo, medible (ICP-fit rate), ataca la raíz, agnóstico al stack.

## 8. Roadmap (Value/Effort)
| Horizonte | Epic | Value/Effort | Foco |
|---|---|---|---|
| Ahora (0–6 sem) · POC | E1 · ICP Definition Engine | Alto / Bajo | ICP riguroso, versionable y multi-ICP + baseline de fit-rate |
| Siguiente (6–12 sem) | E2 · Automated List Builder & Enrichment | Alto / Medio | Armado + enrichment desde fuentes vigentes, validado contra CRM |
| Luego (3–6 meses) | E3 · Smart Qualification & Handoff | Alto / Medio | Scoring + contexto + loop de feedback |
| Luego (3–6 meses) | E4 · Outreach Orchestration | Alto / Medio-Alto | Secuencias y personalización multicanal |
| Transversal | E5 · Dashboard de medición | Medio / Bajo-Medio | Conversión por etapa; medir el north star |

## 9. Principios de diseño
1. **Agnóstico a herramientas** — orquestar el stack vigente sin lock-in.
2. **ICP vivo y versionable** — incorpora nuevos ICPs con el uso.
3. **Ágil y ligero** — incrementos validables; automatización antes que build pesado.

## 10. Stack actual (referencia, no compromiso)
HubSpot (CRM), Apollo, Clay (enrichment/data), Expandi (LinkedIn outreach), secuenciador de email, Claude (creación de mensajes).

## 11. Próximos pasos
1. Correr la skill `icp-architect` para producir el ICP real codificado, versionable.
2. Capturar el baseline de ICP-fit rate con feedback de sales.
3. Diseñar y construir la automatización del ICP Engine con vibe coding.
4. Medir mejora del fit-rate y decidir avance a E2.
