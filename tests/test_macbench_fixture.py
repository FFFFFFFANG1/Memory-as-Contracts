from __future__ import annotations

import json
from pathlib import Path


def test_minimal_macbench_fixture_distinguishes_evidence_tiers() -> None:
    path = Path(__file__).parent / "fixtures" / "macbench_v4_minimal.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["schema_version"] == "MACBenchFixtureV1"
    assert {case["evidence_tier"] for case in cases} == {
        "component",
        "adapter_shim",
        "real_host_trace",
    }
    assert {
        "direct_path_deny",
        "test_before_push",
        "accumulated_budget",
        "ask_before_send",
        "validator_runtime_failure",
    }.issubset({case["scenario"] for case in cases})
    real_host = [case for case in cases if case["evidence_tier"] == "real_host_trace"]
    assert all(case["status"] == "fixture_placeholder" for case in real_host)
