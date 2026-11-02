"""Grainline: an original, bounded database-repair agent for the Ridges contract."""

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from decimal import Decimal
from pathlib import Path


MODEL = os.environ.get("RIDGES_MODEL", "qwen3.8-max")
MAX_CALLS = int(os.environ.get("RIDGES_MAX_CALLS", "6"))
SYSTEM = """You repair database-backed application code in the current repository.
Work from the problem statement and inspected source; discover paths at runtime.
Before editing, establish the result's row grain, the relationship traversal,
and the caller's exact contract. Trace the production query and relevant schema.
Use at most three inspection calls, batching several narrow source reads per
terminal request. Read the exact target function, its imports, the relevant
base/relationship definition, and a nearby implementation where useful. Read
matching definitions around their line numbers rather than arbitrary file heads.
Prefer source inspection of installed dependencies to starting the application
just to discover inherited fields. Runtime tests come after a production edit.
After inspection, a separate exact-text editing tool replaces terminal access.
Use only witnessed old text and a fix supported by the inspected relationships;
if decisive source evidence is missing, describe the gap and stop.
Check join multiplicity, distinctness, hierarchy boundaries, null/empty groups,
ties, ordering, and composability where relevant. Keep work in the production
path and within the task's change scope. Preserve unrelated code and imports.
Use terminal only for inspection and post-edit regression checks.
Use apply_changes for production edits after inspection.
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
        "description": "Run a shell command in the application repository to inspect source and run post-edit checks. Production edits use apply_changes.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}]
EDIT_TOOL = {
    "type": "function", "function": {
        "name": "apply_changes",
        "description": "Apply production edits using exact, unique old source text. Each old string must match once.",
        "parameters": {
            "type": "object", "properties": {
                "changes": {"type": "array", "items": {
                    "type": "object", "properties": {
                        "path": {"type": "string"}, "old": {"type": "string"},
                        "new": {"type": "string"},
                    }, "required": ["path", "old", "new"], "additionalProperties": False,
                }},
            }, "required": ["changes"], "additionalProperties": False,
        },
    },
}


def _endpoint():
    # This experimental transport requires explicit local relay configuration.
    return os.environ["RIDGES_INFERENCE_BASE_URL"].rstrip("/") + "/chat/completions"


def _chat(messages, timeout, phase):
    # Local relay measurement uses its standard OpenAI/Qwen fields. The published
    # Ridges production transport retains its original ZDR contract separately.
    credential_path = Path(os.environ["RIDGES_CRED_PATH"]) if os.getenv("RIDGES_CRED_PATH") else None
    current = json.loads(credential_path.read_text()) if credential_path and credential_path.exists() else None
    request_model = current["model"] if current else MODEL
    request_key = current["key"] if current else os.environ["RIDGES_INFERENCE_API_KEY"]
    input_price = str(current["pricing"]["input_usd_per_million"]) if current else os.environ["RIDGES_INPUT_USD_PER_M"]
    output_price = str(current["pricing"]["output_usd_per_million"]) if current else os.environ["RIDGES_OUTPUT_USD_PER_M"]
    url = current["endpoint"].rstrip("/")+"/v1/chat/completions" if current else _endpoint()
    payload = {
        "model": request_model, "messages": messages,
        "tools": [EDIT_TOOL] if phase == "edit" else TOOLS + ([EDIT_TOOL] if phase == "verify" else []),
        "max_tokens": 6144, "temperature": 0, "enable_thinking": False,
    }
    if phase == "edit":
        payload["tool_choice"] = {"type": "function", "function": {"name": "apply_changes"}}
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + request_key,
                 "Content-Type": "application/json"},
    )
    _log("inference_attempt", phase=phase, model=MODEL)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)
    usage = data.get("usage", {})
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not isinstance(prompt, int) or not isinstance(completion, int):
        raise ValueError("Relay usage is required for this quota-limited measurement")
    # The supplied key's quota uses the user's relay rates, including any
    # underlying-provider markup. Preserve a provider-reported cost separately.
    if "cost" in usage:
        usage["reported_provider_cost"] = usage["cost"]
    cost = (Decimal(prompt) * Decimal(input_price)
            + Decimal(completion) * Decimal(output_price)) / 1000000
    usage["cost"] = float(cost)
    usage["cost_source"] = "quoted_full_input_rate_upper_bound"
    data["usage"] = usage
    return data


def _apply_changes(changes, repo):
    # Validate all exact matches before writing; a mismatched source span is
    # evidence to inspect again, not a fuzzy replacement of unrelated code.
    if not isinstance(changes, list) or not 1 <= len(changes) <= 8:
        raise ValueError("Provide one to eight exact production changes.")
    files = {}
    for change in changes:
        path = (repo / change["path"]).resolve()
        path.relative_to(repo.resolve())
        old, new = change["old"], change["new"]
        if not isinstance(old, str) or not isinstance(new, str) or not old:
            raise ValueError("old/new must be strings; old must contain witnessed source.")
        source = files.get(path) if path in files else path.read_text()
        if source.count(old) != 1:
            raise ValueError(f"Old text must match once: {change['path']}")
        files[path] = source.replace(old, new, 1)
    for path, source in files.items():
        path.write_text(source)
    return {"returncode": 0, "stdout": "Applied " + ", ".join(str(p.relative_to(repo)) for p in files)}


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
    max_cost = float(os.environ["RIDGES_MAX_COST_USD"])
    spent = 0.0
    calls = 0
    # Sample images ship without .git. Stage the supplied working tree as the
    # baseline; git diff then describes exactly the agent's changes, without a commit.
    prepared = _terminal("git rev-parse --git-dir >/dev/null 2>&1 || git init -q; git add -A", repo, 60)
    if prepared["returncode"]:
        _log("baseline_failed", returncode=prepared["returncode"])
        return ""
    context = _terminal("pwd; ls -a | head -45", repo, 15)
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": input["problem_statement"]
         + "\n\nInitial repository context:\n" + json.dumps(context)},
    ]
    # Six calls test a distinct source -> edit checkpoint -> verification
    # mechanism within this pilot's quota. Complex repositories can need a
    # larger inspection budget; broaden it only after measured completion.
    editing_started = False
    for turn in range(MAX_CALLS):
        remaining = deadline - time.monotonic()
        if remaining < 40 or spent > max_cost:
            break
        patch_now = _terminal("git diff --stat", repo, 10)["stdout"]
        phase = "verify" if patch_now else ("edit" if turn >= 3 else "retrieve")
        allowed_tools = ["apply_changes"] if phase == "edit" else (["terminal", "apply_changes"] if phase == "verify" else ["terminal"])
        if phase == "edit" and not editing_started:
            messages.append({"role": "user", "content":
                "Source inspection is complete. Make the smallest grounded production change now "
                "using apply_changes with exact old/new text. Use the inspected relationship and caller "
                "contract. If decisive evidence is missing, explain the missing span and stop. "
                "Application startup diagnostics are reserved for verification after the edit."})
            editing_started = True
        if turn == MAX_CALLS - 1:
            if phase == "edit":
                final_instruction = "One model call remains. Make the smallest grounded production change now using apply_changes with exact old/new text. If decisive evidence is missing, explain the gap and stop."
            elif phase == "verify":
                final_instruction = "One model call remains. Review and verify the actual production diff, or revise from the check result."
            else:
                final_instruction = "One model call remains. Use terminal to inspect the decisive production source. If decisive evidence is missing, explain the gap and stop."
            messages.append({"role": "user", "content": final_instruction})
        try:
            response = _chat(messages, min(180, remaining - 20), phase)
            usage = response.get("usage", {})
            cost = usage.get("cost")
            if cost is not None:
                spent += float(cost)
            calls += 1
            choice = response["choices"][0]
            message = choice["message"]
            _log("inference", call=calls, phase=phase, model=response.get("model"),
                 usage=usage, cost_total=spent, finish_reason=choice.get("finish_reason"),
                 tool_names=[call.get("function", {}).get("name") for call in message.get("tool_calls", [])])
        except Exception as error:
            _log("inference_stopped", error_type=type(error).__name__,
                 detail=(error.read().decode(errors="replace")[:1500]
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
            function_name = None
            try:
                function = call["function"]
                function_name = function["name"]
                arguments = json.loads(function["arguments"])
                if function_name == "apply_changes" and phase in {"edit", "verify"}:
                    result = _apply_changes(arguments["changes"], repo)
                    _log("edit", call=calls, phase=phase, result=result)
                elif function_name == "terminal" and phase != "edit":
                    command = arguments["command"]
                    if not isinstance(command, str):
                        raise ValueError("command must be a string")
                    result = _terminal(command, repo, max(1, min(120, remaining - 20)))
                    # The failed pilot lacked persisted stderr; retain a bounded
                    # source/check receipt so its next decision uses real errors.
                    _log("terminal", call=calls, phase=phase, command=command[:600],
                         returncode=result["returncode"], stdout=result["stdout"][:2000],
                         stderr=result["stderr"][:2000])
                else:
                    reason = "Tool unavailable in this phase" if function_name in {"terminal", "apply_changes"} else "Unknown tool name"
                    raise ValueError(f"{reason}: {function_name}; allowed tools: {allowed_tools}")
            except (KeyError, TypeError, ValueError, OSError) as error:
                result = {"returncode": 1, "stderr": str(error)}
                _log("tool_error", call=calls, phase=phase, tool_name=function_name,
                     allowed_tools=allowed_tools, error_type=type(error).__name__, result=result)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)})
    # Include genuinely new source files in the returned diff as well.
    _terminal("git add -N .; git diff --check", repo, 15)
    patch = _terminal("git diff --no-ext-diff --binary", repo, 15, output_limit=2_000_000)
    _log("finished", calls=calls, cost_total=spent, patch_chars=len(patch["stdout"]))
    return patch["stdout"]
