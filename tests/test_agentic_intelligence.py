"""No-network unit tests for the first Jirow read-only investigation loop."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from grid_monitor.services import agentic_intelligence as agent


def test_disallows_unrecognized_tool_and_arbitrary_arguments():
    assert agent.execute_tool("run_sql", "{}") == {"error": "unsupported_tool"}
    assert agent.execute_tool("generation_history", '{"days":7,"query":"DROP TABLE"}') == {
        "error": "unsupported_tool"
    }
    assert agent.execute_tool("generation_history", '{"days":1000}')["error"] == "invalid_tool_arguments"


def test_history_uses_observations_and_preserves_coverage(monkeypatch):
    monkeypatch.setattr(agent, "utc_now", lambda: datetime(2026, 10, 29, tzinfo=timezone.utc))
    recorded = {}

    def fake_analysis(start, end):
        recorded["start"], recorded["end"] = start.isoformat(), end.isoformat()
        return {
            "window": {"start": start.isoformat(), "end_exclusive": end.isoformat()},
            "coverage": {"missing_days": 2},
            "statistics": {"peak_observed_generation_mw": 5100},
            "daily": [],
            "methodology": {"limitations": "Missing days are not outages.", "sources": []},
        }

    monkeypatch.setattr(agent, "generation_analysis", fake_analysis)
    result = agent.generation_history(7)
    assert recorded == {"start": "2026-10-23", "end": "2026-10-30"}
    assert result["coverage"]["missing_days"] == 2
    assert result["data_grade"] == "stored_source_observations"


def test_model_must_call_read_only_tool_and_does_not_store_response(monkeypatch):
    monkeypatch.setattr(agent, "generation_history", lambda days: {"days": days, "count": 2})
    call = SimpleNamespace(
        type="function_call", name="generation_history", arguments='{"days":7}', call_id="call_1"
    )
    first = SimpleNamespace(output=[call], output_text="")
    final = SimpleNamespace(output=[SimpleNamespace(type="message")],
                            output_text="Two stored observations were found; check coverage.")
    client = SimpleNamespace(responses=SimpleNamespace(create=Mock(side_effect=[first, final])))
    output = agent.investigate("Investigate national generation.", client=client, model="test-model")
    assert output["read_only"] is True
    assert output["tools_used"] == ["generation_history"]
    assert client.responses.create.call_count == 2
    first_args = client.responses.create.call_args_list[0].kwargs
    assert first_args["store"] is False
    assert first_args["parallel_tool_calls"] is False
    assert first_args["tool_choice"] == "required"
    second_args = client.responses.create.call_args_list[1].kwargs
    assert any(item.get("type") == "function_call_output" for item in second_args["input"]
               if isinstance(item, dict))


def test_rejects_questions_outside_bounds():
    client = object()
    with pytest.raises(ValueError):
        agent.investigate("short", client=client)
    with pytest.raises(ValueError):
        agent.investigate("x" * 601, client=client)


def test_missing_evidence_never_returns_unsupported_answer():
    response = SimpleNamespace(output=[SimpleNamespace(type="message")],
                               output_text="Everything is fine.")
    client = SimpleNamespace(responses=SimpleNamespace(create=Mock(return_value=response)))
    with pytest.raises(agent.AgentUnavailable):
        agent.investigate("Investigate generation changes.", client=client)
