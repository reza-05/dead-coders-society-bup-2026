import json
from pathlib import Path
import pytest
from app.models import EnergyRequest
from app.llm_interpreter import LLMInterpreter
from app.optimizer import solve_energy_schedule

SAMPLE_PATH = Path(__file__).parent / "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"


def load_sample_cases():
    if not SAMPLE_PATH.exists():
        return []
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


@pytest.fixture(scope="module")
def interpreter():
    return LLMInterpreter()


@pytest.mark.parametrize("case_data", load_sample_cases(), ids=lambda c: c["id"])
def test_each_official_case(case_data, interpreter):
    req_data = case_data["input"]
    expected_output = case_data["expected_output"]
    expected_dirs = expected_output["directive_interpretation"]
    expected_cost = expected_output["total_cost_bdt"]

    req = EnergyRequest(**req_data)

    # 1. Interpret
    dirs = interpreter.interpret(req.operator_notes, req.battery)

    # 2. Check directives
    assert len(dirs) == len(expected_dirs)
    for exp_d, act_d in zip(expected_dirs, dirs):
        assert act_d.note_index == exp_d["note_index"]
        assert act_d.directive_type == exp_d["directive_type"]
        assert act_d.applies == exp_d["applies"]

        if exp_d["applies"]:
            exp_adj = exp_d["structured_adjustment"]
            act_adj = act_d.structured_adjustment
            assert act_adj is not None
            assert act_adj.get("hours") == exp_adj.get("hours")
            for num_key in ["factor", "minimum_energy_kwh", "max_grid_kwh"]:
                if num_key in exp_adj:
                    assert abs(float(act_adj[num_key]) - float(exp_adj[num_key])) < 0.05

    # 3. Optimize
    hourly_plan, total_grid, total_cost, peak_grid, summary = solve_energy_schedule(req, dirs)

    # 4. Check cost within 0.05 tolerance of expected
    assert abs(total_cost - expected_cost) < 0.05, f"Cost mismatch: {total_cost} vs expected {expected_cost}"
