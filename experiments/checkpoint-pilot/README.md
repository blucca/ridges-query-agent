# Local-only checkpoint pilot

A separate experimental agent for source inspection → exact-text production
editing → verification. It advertises only `apply_changes` during the editing
phase and uses the OpenAI-standard forced function choice for that phase.
Phase-specific final reminders and tool-name/error metadata make protocol
failures visible without copying edit arguments into the new log fields.

## Transport and qualification

The measured transport was a **local OpenAI-compatible relay**.
**Qwen3.8-Max is the alias supplied by that relay**; model identification here
is scoped to that alias. Production OpenRouter/ZDR and forced function-choice
qualification is separate; the current Max production route is stopped at
that gate. The root `agent.py` and its production/ZDR candidate remain unchanged.

This publication copy requires private endpoint, credential, and budget
configuration through the existing environment interface. It carries no
embedded relay address, credential path, or measured monetary default.
The request/phase protocol matches the corrected local pilot; publication
changes make configuration explicit and replace offline pricing fixtures
with arbitrary synthetic values.

## Separate result records

| Record | Observed result | Evidence scope |
|---|---|---|
| Initial shared pilot: 12 HTTP attempts | Failed gate; GORM returned an empty patch with three editing-phase tool errors | Historical failure retained |
| NetBox fresh re-verification | The original patch was unchanged; restoring the official configuration file to mode `0644` and running the fresh official verifier passed **10/10** | Public NetBox sample, separate re-verification without model calls |
| Independent GORM protocol-corrected pilot: 6 model calls | **631-byte** production patch, zero tool errors; PostgreSQL **16.15** oracle passed **4/4** | Public [GORM issue #6798](https://github.com/go-gorm/gorm/issues/6798), independent regression fixture |

These rows are distinct execution and re-verification records. The initial
gate retains its failed status. Evidence covers the named public sample and
four-case fixture; official scoring, leaderboard results, and production
OpenRouter/ZDR qualification require separate evaluations.

The GORM oracle covers composite DISTINCT tuples, a filtered composite query,
ordinary count, and single-column DISTINCT count. [gorm-repair-public.json](gorm-repair-public.json) contains only
public fixture identity, SQL, expected/observed counts, and acceptance fields.
The existing [fixture](../../eval/gorm-distinct-count/) supplies its baseline
and reproduction instructions.

## Offline request check

```sh
python -B experiments/checkpoint-pilot/check.py
```

Run from the repository root. Every HTTP response in this check is mocked;
all pricing and usage fixtures are arbitrary **synthetic/offline** values.
It checks phase-specific tools, forced editing choice, unforced non-editing
requests, accounting-field preservation, and the call/output configuration.
The offline check is request-construction evidence; repair capability is
measured by the separate records above.

