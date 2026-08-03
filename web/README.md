# Web client

Next.js map-first workspace for Retail Location Intelligence.

**Architecture rule:** this package renders server projections. It must not reimplement
scoring, clustering, simulation generation, or analog distance math.

| Area | Role |
| --- | --- |
| `src/lib/api.ts` / `types.ts` | Typed client + wire contracts |
| `src/lib/session.tsx` | Opaque session id; OpenAI key in tab memory only |
| `src/lib/selection.tsx` | Map / tray / panel selection (UI state, not workflow) |
| `src/components/map/` | MapLibre canvas, resizable shell, intelligence panel |
| `src/components/stages/` | Describe → clarify → review → executed / refused |
| `src/components/panels/` | Recommendation, archetypes, simulation, analogs, evidence, … |
| `src/test/` | Generated fixtures + fetch harness |

Parent docs: [`../README.md`](../README.md), [`../docs/architecture.md`](../docs/architecture.md).
