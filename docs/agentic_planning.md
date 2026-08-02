# Agentic planning

## What makes this agentic, and what would not

The word usually points at a model that chooses its own tools and loops until it decides
it is finished. That is not what is here, and the omission is the design.

A retail site decision does not fail because nobody could compute a weighted score. It
fails earlier, in the part that is genuinely hard: working out what the decision actually
is. What format is this store. Who is it for. Does growth matter more than current
purchasing power. Is the municipality the market, or is the market a drive-time polygon
that happens to straddle three municipalities. Which of the things you just asked for can
this data even speak to.

That is the work the agent does. It reads an objective in an executive's words, says what
it inferred, asks about what it could not infer and that would change the answer, and
proposes a plan. Then it stops and waits.

So the claim this system makes is narrow and, I think, more defensible than the usual one:

> The agent does not decide which location is best. It collaborates with the user to
> define the decision, constructs a governed analytical plan, identifies what is missing,
> orchestrates approved analytical services, and explains the resulting evidence.

An agent that also decided what the numbers were would be easier to build and impossible
to trust, because the second capability can always paper over failures in the first.

## Why the agent manages the process and not the facts

Two failure modes matter for this product, and they are not equally bad.

If the planner misreads "prioritize growth" and proposes the wrong weights, a human sees
the proposal, sees the weights, and fixes them. The error is visible, cheap, and lands in
front of the person best placed to catch it.

If the planner invents a plausible median household income, nothing catches it. It looks
exactly like a real one. It flows into a score, into a ranking, into a narrative, and out
to a real-estate committee.

The whole architecture follows from taking that asymmetry seriously. The agent is given
broad latitude over the reversible, inspectable decisions and no latitude at all over the
irreversible, invisible ones.

## Authority boundaries

**The planner may:** extract a retailer profile from prose; resolve strategic priorities;
propose category weights; propose metric ids drawn from the approved registry; identify
missing information; generate clarifying questions; explain why a category or metric is
relevant; identify unsupported requirements; and recommend whether the analysis is ready
to run.

**The planner may not:** emit an Atlas datapoint identifier; emit a factual value; invent
a metric or a geography; perform scoring; claim a metric predicts store performance;
produce a recommendation about which region wins; override a refusal or a validation
failure; or call the Atlas client.

These are not conventions. The planner returns a typed schema, and every field of it is
revalidated before it can influence anything:

| Field | Revalidation |
| --- | --- |
| `selected_metric_ids` | Must exist in `MetricRegistry`; anything else is dropped and recorded |
| `candidate_geographies` | Resolved through the licensed-region allowlist; unmatched names are dropped |
| `category_weights` | Each in `[0, 1]`, sum positive, renormalized to 1, adjustment disclosed |
| Prose fields | Scanned for Atlas datapoint patterns and for factual figures; a match rejects the field |
| Unknown fields | Rejected by the schema |

A rejected field is not silently discarded. It lands on `PlannerProvenance.rejected_fields`
with the offending value and the reason, appears in the trace, and is rendered in the plan
review panel. A guardrail you cannot observe firing is a guardrail you cannot trust.

## The plan lifecycle

```
DRAFT ──> NEEDS_CLARIFICATION ──> READY_FOR_REVIEW ──> APPROVED ──> EXECUTED
  │                │                     │                              │
  │                └─────────────────────┤                              │
  │                                      v                              v
  └──────────────────────────────────> REJECTED                    SUPERSEDED
```

`AnalysisPlanProposal` is frozen, versioned, and carries its own approval record. Two
properties gate everything:

- **`can_approve`** — validation passed, no unanswered required question, and the status
  is one a human may act on. This is what enables the approve button.
- **`can_execute`** — status is `APPROVED`, *and* an approval record exists, *and*
  validation passed, *and* no required question is open. This is the only thing
  `AnalysisPipeline.run_approved` consults before constructing a request.

The two are deliberately separate. Forging `status = APPROVED` without an approval record
does not produce an executable plan, and there is a test that does exactly that.

Deterministic validation checks: at least two geographies resolve; every metric exists in
the registry; every metric supports the requested geography levels; weights are in range
and normalized; required clarifications are answered; unsupported requirements are
disclosed; assumptions are visible.

## Clarification behaviour

The bar is materiality, and it exists to stop the agent turning into an intake form.

A question is asked only when the answer could change metric selection, category weights,
geography interpretation, trade-area definition, or whether the analysis is supportable at
all. At most three per round. Each one stores the missing decision, why it matters, which
parts of the analysis it could change, whether it is required, and a safe default.

- **Optional and unanswered** proceeds on an explicitly disclosed assumption, which is
  shown on the review screen with its basis and how to overrule it.
- **Required and unanswered** blocks execution. `NEEDS_CLARIFICATION` has no edge to
  `APPROVED`.

Answers re-plan rather than patch. An answer about store format can change which metrics
belong in the analysis, so applying it as a field edit would leave the rest of the
proposal reflecting an assumption the user just overruled.

What the agent must never do is convert an unknown into an assumption silently. Every
field of `RetailStrategyProfile` is an `Attributed` value carrying one of four
provenances: user-supplied, planner-inferred, unknown, or unsupported. "Unknown" is a
first-class state, and the review panel prints it as one.

## Approval behaviour

Nothing reaches Atlas without a human. The approve control is disabled, not hidden, when
the plan is not approvable, because the reason is more useful than the absence.

A user may also edit before approving: weights, the metric set, the candidate regions.
Edits are not exempt from validation. Each is recorded as a `PlanEdit` with its before and
after, the edited plan is revalidated, and the trace distinguishes what the planner
proposed from what the human overrode.

## Revision behaviour

A chat surface attached to a live analysis is a control surface whether or not it was
designed as one. "Double the importance of household income" is an instruction.

So a revision request produces a proposal and stops:

1. The message is classified deterministically, behind the injection and forecast gates.
2. A `PlanRevisionProposal` is built: changed fields, before values, proposed values, the
   rationale, and a hedged statement of the analytical effect.
3. It is validated deterministically before it is offered.
4. The UI renders the exact before-and-after and waits.
5. On confirmation, `apply_revision` produces version *n+1* with `parent_plan_id` set.
6. The new version re-enters approval and runs.
7. The previous version is marked `SUPERSEDED`, and its result is retained.
8. `diff_plans` and `diff_results` produce the comparison; the model may narrate it, but
   it does not compute it.

The expected-effect text is directional and always ends by saying that only a rerun
settles it. Saying "this will make Winooski win" would be a prediction about a calculation
that has not run, which is precisely the thing the architecture exists to prevent.

Requests the analysis cannot express — "prioritize low rent" — produce a proposal with no
changed fields and an explicit `unsupported_parts` list, rather than a silent no-op or an
invented proxy.

## Failure and fallback behaviour

The product has no runtime dependency on a language model. The deterministic planner is
not a degraded mode; it is the reference implementation, and the LLM planner merges its
validated contributions onto a deterministic baseline rather than replacing it.

| Failure | Behaviour |
| --- | --- |
| No `OPENAI_API_KEY` | Deterministic planner runs. Clarification, approval, revision, and the assistant all work |
| Malformed JSON from the model | Fall back to the deterministic baseline, record the reason |
| Model raises or times out | Same |
| Model returns an unknown metric | Field rejected and recorded; the baseline's metric set stands |
| Model returns an Atlas identifier or a figure | Field rejected and recorded |
| Model returns invalid weights | Rejected, or renormalized with the adjustment disclosed |
| Objective is an injection attempt | Refused before any planner runs; recorded in the trace |
| Objective asks for a forecast | Refused with the company-specific inputs a real answer would need |
| Revised plan fails validation | Not run; returned to review with the failures shown |
| Evidence is insufficient after execution | The ranking is withheld. The agent explains the insufficiency and does not override it |

The last row is the one worth dwelling on. The sufficiency gate can withhold an answer
from a plan the user explicitly approved, and the agent has no route around it. An agent
that could talk its way past a deterministic gate would make every other guarantee in this
document decorative.
