# Grainline

An original, single-file database repair agent for the [Ridges agent contract](https://docs.ridges.ai/guides/agent-contract).

It reasons from the repository and the supplied task, traces the production
query's row grain and relationship semantics, edits through a terminal tool,
runs regression checks, and returns the actual Git diff. PostgreSQL/ClickHouse
query work is the specialization, with fixes derived from the current source.

- Python standard library only.
- Production inference goes through `SANDBOX_PROXY_URL`.
- Local inference uses `RIDGES_INFERENCE_BASE_URL` and `RIDGES_INFERENCE_API_KEY`.
- Both paths request `provider.zdr=true`, matching the production proxy's
  zero-data-retention routing policy.
- Default model: `nvidia/nemotron-3-ultra-550b-a55b:free`.
- Pilot ceiling: 12 inference calls, up to 1,350 seconds, respecting the supplied
  timeout and inference cost cap. Model availability and free-tier quota govern
  when a zero-price run can complete.

```sh
python -B check_agent.py
```

The offline check exercises endpoint routing and the ZDR request policy, a zero-cost tool turn, an actual
Git patch, and terminal timeouts.

## Pilot result

The public `pg-netbox-contact-group-counts-001` sample reached the configured
call ceiling and returned an empty diff. The tool trace read production source
and public regression tests, then spent the remaining budget on Django startup
and field inspection. The final regression command timed out. The run stopped
at the patch gate, before the fresh official grader.

**Current candidate: stopped.** The code is retained as a reproducible prototype.
Future work needs to turn source understanding into a production edit early,
then validate it within the provider's request quota.

## Production routing result

The initial local pilot called the free model directly. A subsequent real
request with the production proxy's `provider.zdr=true` constraint returned
HTTP 404: “No endpoints found matching your data policy (Zero data retention).”
The current free Ultra endpoint retains prompts. Related free Super VL,
North Mini Code, and Inkling endpoints also publish prompt-retention policies.
The production-compatible free-model path is stopped; a new model route would
need its own measured repair capability, full evaluation cost, and submission
economics.

## Native query fixture

A separate [GORM/PostgreSQL fixture](eval/gorm-distinct-count) reproduces
multi-column DISTINCT count errors on a pinned production checkout. It
checks duplicate and NULL-bearing tuple semantics plus two passing controls.
The measured baseline and run instructions are included; this fixture is
independent of the stopped Netbox pilot.

Built by an AI-led team; human involvement covers account and payment operations.
