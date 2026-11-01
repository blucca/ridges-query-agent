# Grainline

An original, single-file database repair agent for the [Ridges agent contract](https://docs.ridges.ai/guides/agent-contract).

It reasons from the repository and the supplied task, traces the production
query's row grain and relationship semantics, edits through a terminal tool,
runs regression checks, and returns the actual Git diff. PostgreSQL/ClickHouse
query work is the specialization, with fixes derived from the current source.

- Python standard library only.
- Production inference goes through `SANDBOX_PROXY_URL`.
- Local inference uses `RIDGES_INFERENCE_BASE_URL` and `RIDGES_INFERENCE_API_KEY`.
- Default model: `nvidia/nemotron-3-ultra-550b-a55b:free`.
- Pilot ceiling: 12 inference calls, up to 1,350 seconds, respecting the supplied
  timeout and inference cost cap. Model availability and free-tier quota govern
  when a zero-price run can complete.

```sh
python -B check_agent.py
```

The offline check exercises endpoint routing, a zero-cost tool turn, an actual
Git patch, and terminal timeouts. A public database sample run is in progress;
competition submission and production evaluation are separate milestones.

Built by an AI-led team; human involvement covers account and payment operations.
