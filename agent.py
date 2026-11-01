"""Grainline: an original, bounded database-repair agent for the Ridges contract."""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
MAX_CALLS = 12
SYSTEM = """You repair database-backed application code in the current repository.
Work from the problem statement and inspected source; discover paths at runtime.
Before editing, establish the result's row grain, the relationship traversal,
and the caller's exact contract. Trace the production query and relevant schema.
Check join multiplicity, distinctness, hierarchy boundaries, null/empty groups,
ties, ordering, and composability where relevant. Keep work in the production
path and within the task's change scope. Preserve unrelated code and imports.
Use the terminal tool to inspect, edit, and run the task's regression checks.
Keep terminal output bounded with sed/head or narrow searches. Use Python for
file deletion. Do not use rm. Do not inspect secrets or files outside the repo.
Do not change tests or inspect grader/solution files. Never recognize a task by
an identifier or substitute a stored patch. Compute the fix from current code.
After editing, review the actual diff and run available relevant checks. Make
the smallest complete change. Finish with DONE; the runner extracts git diff.
"""
TOOLS = [{
    "type": "function",
    "function": {
        "name": "terminal",
        "description": "Run a shell command in the application repository; inspect or edit source and run checks.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}]


def _endpoint():
    proxy = os.getenv("SANDBOX_PROXY_URL")
    base = proxy.rstrip("/") + "/api/v1" if proxy else os.getenv(
        "RIDGES_INFERENCE_BASE_URL", "https://openrouter.ai/api/v1"
    ).rstrip("/")
    return base + "/chat/completions"


def _chat(messages, timeout):
    key = os.getenv("OPENROUTER_API_KEY") or os.getenv("RIDGES_INFERENCE_API_KEY", "")
    payload = {
        "model": MODEL, "messages": messages, "tools": TOOLS,
        "provider": {"zdr": True},
        "max_tokens": 6144, "temperature": 0,
        "reasoning": {"effort": "medium", "exclude": True},
    }
    request = urllib.request.Request(
        _endpoint(), data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _terminal(command, repo, timeout, output_limit=20000):
    # This host's deletion rule also applies to model-generated tool commands.
    if re.search(r"(?:^|[\s;&|])rm(?:\s|$)", command):
        return {"returncode": 1, "stdout": "", "stderr": "Use Python for file deletion."}
    try:
        result = subprocess.run(
            command, shell=True, executable="/bin/bash", cwd=repo,
            capture_output=True, text=True, errors="replace", timeout=timeout,
        )
        return {"returncode": result.returncode, "stdout": result.stdout[:output_limit],
                "stderr": result.stderr[:output_limit]}
    except subprocess.TimeoutExpired as error:
        out = error.stdout or b""
        err = error.stderr or b""
        return {"returncode": 124,
                "stdout": (out.decode(errors="replace") if isinstance(out, bytes) else out)[:output_limit],
                "stderr": (err.decode(errors="replace") if isinstance(err, bytes) else err)[:output_limit]
                + "\nCommand timed out."}


def _log(event, **fields):
    print(json.dumps({"event": event, **fields}), file=sys.stderr, flush=True)


def agent_main(input: dict) -> str:
    repo = Path(os.getenv("RIDGES_REPO_DIR", "/repo" if Path("/repo").exists() else "/app"))
    deadline = time.monotonic() + min(float(os.getenv("AGENT_TIMEOUT", "900")), 1350)
    max_cost = float(os.getenv("RIDGES_MAX_COST_USD", "0.29"))
    spent = 0.0
    calls = 0
    # Sample images ship without .git. Stage the supplied working tree as the
    # baseline; git diff then describes exactly the agent's changes, without a commit.
    prepared = _terminal("git rev-parse --git-dir >/dev/null 2>&1 || git init -q; git add -A", repo, 60)
    if prepared["returncode"]:
        _log("baseline_failed", returncode=prepared["returncode"])
        return ""
    context = _terminal("pwd; ls -a | head -45; git status --short", repo, 15)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": input["problem_statement"]
         + "\n\nInitial repository context:\n" + json.dumps(context)},
    ]
    # Twelve calls are the deliberate C0 pilot ceiling. Broader evaluation can
    # change this constant after measuring per-task cost and completion rate.
    for turn in range(MAX_CALLS):
        remaining = deadline - time.monotonic()
        if remaining < 40 or spent > max_cost:
            break
        if turn == MAX_CALLS - 2:
            messages.append({"role": "user", "content":
                             "Two model calls remain. Finish the production edit, inspect diff, and run checks now."})
        try:
            response = _chat(messages, min(180, remaining - 20))
            usage = response.get("usage", {})
            cost = usage.get("cost")
            if cost is not None:
                spent += float(cost)
            calls += 1
            _log("inference", call=calls, model=response.get("model"),
                 usage=usage, cost_total=spent)
            message = response["choices"][0]["message"]
        except Exception as error:
            _log("inference_stopped", error_type=type(error).__name__,
                 detail=(error.read().decode(errors="replace")[:2000]
                         if isinstance(error, urllib.error.HTTPError) else str(error)[:700]))
            break
        assistant = {"role": "assistant", "content": message.get("content")}
        tool_calls = message.get("tool_calls", [])
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        messages.append(assistant)
        if not tool_calls:
            break
        for call in tool_calls:
            remaining = deadline - time.monotonic()
            try:
                function = call["function"]
                if function["name"] != "terminal":
                    raise ValueError("Unknown tool")
                command = json.loads(function["arguments"])["command"]
                if not isinstance(command, str):
                    raise ValueError("command must be a string")
                result = _terminal(command, repo, max(1, min(120, remaining - 20)))
                _log("terminal", call=calls, command=command[:600], returncode=result["returncode"])
            except (KeyError, TypeError, ValueError) as error:
                result = {"returncode": 1, "stderr": str(error)}
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
    # Include genuinely new source files in the returned diff as well.
    _terminal("git add -N .; git diff --check", repo, 15)
    patch = _terminal("git diff --no-ext-diff --binary", repo, 15, output_limit=2_000_000)
    _log("finished", calls=calls, cost_total=spent, patch_chars=len(patch["stdout"]))
    return patch["stdout"]
