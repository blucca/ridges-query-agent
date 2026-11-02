#!/usr/bin/env python3
"""SYNTHETIC/OFFLINE protocol checks only; capability evaluation is separate."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def main():
    requests = []
    logs = io.StringIO()
    response = {
        "model": "synthetic-offline-model",
        "choices": [{"finish_reason": "stop", "message": {"content": "synthetic"}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 11, "cost": 0.75},
    }

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://synthetic.invalid/v1/chat/completions"
        assert timeout == 12
        requests.append(json.loads(request.data))
        return io.BytesIO(json.dumps(response).encode())

    with tempfile.TemporaryDirectory(prefix="synthetic-offline-", dir=HERE) as scratch:
        env = {
            "RIDGES_CRED_PATH": str(Path(scratch) / "absent.json"),
            "RIDGES_INFERENCE_BASE_URL": "https://synthetic.invalid/v1",
            "RIDGES_INFERENCE_API_KEY": "synthetic-offline-key",
            # Arbitrary synthetic rates and usage; measured pricing stays private.
            "RIDGES_INPUT_USD_PER_M": "1",
            "RIDGES_OUTPUT_USD_PER_M": "2",
        }
        with patch.dict(os.environ, env, clear=True):
            spec = importlib.util.spec_from_file_location("protocol_v3_offline", HERE / "agent.py")
            agent = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(agent)
            assert agent.MAX_CALLS == 6
            with patch.object(agent.urllib.request, "urlopen", side_effect=fake_urlopen) as mocked:
                with contextlib.redirect_stderr(logs):
                    for phase in ("retrieve", "edit", "verify"):
                        result = agent._chat([{"role": "user", "content": "synthetic/offline"}], 12, phase)
                        usage = result["usage"]
                        assert usage["cost"] == 0.000029
                        assert usage["reported_provider_cost"] == 0.75
                        assert usage["cost_source"] == "quoted_full_input_rate_upper_bound"
                        assert usage["prompt_tokens"] == 7
                        assert usage["completion_tokens"] == 11
            assert mocked.call_count == 3

    retrieve, edit, verify = requests
    assert "tool_choice" not in retrieve
    assert "tool_choice" not in verify
    assert edit["tool_choice"] == {"type": "function", "function": {"name": "apply_changes"}}
    assert [t["function"]["name"] for t in retrieve["tools"]] == ["terminal"]
    assert [t["function"]["name"] for t in edit["tools"]] == ["apply_changes"]
    assert [t["function"]["name"] for t in verify["tools"]] == ["terminal", "apply_changes"]
    for request in requests:
        assert request["max_tokens"] == 6144
        assert request["temperature"] == 0
        assert request["enable_thinking"] is False
    assert "synthetic-offline-key" not in logs.getvalue()
    print(json.dumps({
        "mode": "synthetic/offline",
        "status": "pass",
        "mock_urlopen_calls": 3,
        "real_model_api_calls": 0,
        "capability_gate_evidence": 0,
        "checks": ["phase_tools", "edit_tool_choice", "nonedit_no_tool_choice",
                   "synthetic_rates_and_provider_cost", "six_call_default", "6144_token_cap"],
    }, indent=2))


if __name__ == "__main__":
    main()
