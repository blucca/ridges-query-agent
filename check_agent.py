"""Small, offline contract check. Run: python -B check_agent.py"""
import json
import os
import tempfile
from pathlib import Path

import agent


temp_root = Path(__file__).resolve().parents[2] / "temp"
temp_root.mkdir(exist_ok=True)
original = dict(os.environ)
original_chat = agent._chat
try:
    os.environ["SANDBOX_PROXY_URL"] = "http://sandbox-proxy:80"
    assert agent._endpoint() == "http://sandbox-proxy:80/api/v1/chat/completions"
    os.environ.pop("SANDBOX_PROXY_URL")
    os.environ["RIDGES_INFERENCE_BASE_URL"] = "https://openrouter.ai/api/v1/"
    assert agent._endpoint() == "https://openrouter.ai/api/v1/chat/completions"
    with tempfile.TemporaryDirectory(prefix="grainline-check-", dir=temp_root) as directory:
        repo = Path(directory)
        (repo / "calc.py").write_text("def total(values):\n    return 0\n")
        os.environ["RIDGES_REPO_DIR"] = str(repo)
        os.environ["RIDGES_MAX_COST_USD"] = "0"
        responses = iter([
            {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
                {"id": "edit", "type": "function", "function": {"name": "terminal", "arguments": json.dumps({
                    "command": "python -c \"from pathlib import Path; Path('calc.py').write_text('def total(values):\\n    return sum(values)\\n')\""
                })}}
            ]}}], "usage": {"cost": 0}},
            {"choices": [{"message": {"role": "assistant", "content": "DONE"}}], "usage": {"cost": 0}},
        ])
        agent._chat = lambda messages, timeout: next(responses)
        patch = agent.agent_main({"problem_statement": "Implement a total of the supplied values."})
        assert "diff --git a/calc.py b/calc.py" in patch
        assert "+    return sum(values)" in patch
        assert agent._terminal("rm example", repo, 1)["returncode"] == 1
        assert agent._terminal("sleep 2", repo, 0.01)["returncode"] == 124
finally:
    agent._chat = original_chat
    os.environ.clear()
    os.environ.update(original)
print("PASS: endpoints, C0 tool loop, real diff, deletion rule, command timeout")
