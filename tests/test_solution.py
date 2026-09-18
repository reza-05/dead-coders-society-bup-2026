import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


def test_malformed_request_returns_400():
    response = client.post("/optimize-energy", json={"invalid": "data"})
    assert response.status_code == 400


def test_sample_scenario_7_4():
    # Build 24 hours sample data
    hours_data = []
    for h in range(24):
        # Realistic curve: solar midday, higher demand afternoon
        solar = 150.0 if 8 <= h <= 17 else 0.0
        demand = 180.0 if (0 <= h <= 6 or 22 <= h <= 23) else 250.0
        tariff = 12.0 if 17 <= h <= 22 else 7.0
        hours_data.append({
            "hour": h,
            "demand_kwh": demand,
            "solar_kwh": solar,
            "tariff_bdt_per_kwh": tariff
        })

    payload = {
        "scenario_id": "GRID-101",
        "operator_notes": [
            "Solar output will drop to about 20% from 1 PM to 3 PM.",
            "Do not charge the battery between 2 PM and 4 PM.",
            "The cafeteria menu changes tomorrow."
        ],
        "hours": hours_data,
        "battery": {
            "capacity_kwh": 500.0,
            "initial_energy_kwh": 200.0,
            "minimum_energy_kwh": 50.0,
            "max_charge_kwh_per_hour": 100.0,
            "max_discharge_kwh_per_hour": 100.0
        }
    }

    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 200, f"Error: {response.text}"
    data = response.json()

    # 1. Top level validation
    assert data["scenario_id"] == "GRID-101"
    assert "total_grid_kwh" in data
    assert "total_cost_bdt" in data
    assert "peak_grid_kwh" in data
    assert "plan_summary" in data

    # 2. Directive Interpretation validation
    directives = data["directive_interpretation"]
    assert len(directives) == 3
    assert directives[0]["note_index"] == 0
    assert directives[1]["note_index"] == 1
    assert directives[2]["note_index"] == 2

    # Verify Note 2 (cafeteria) is no_op
    assert directives[2]["applies"] is False
    assert directives[2]["directive_type"] == "no_op"
    assert directives[2]["structured_adjustment"] is None

    # Verify Note 0 & 1 apply
    assert directives[0]["applies"] is True
    assert directives[1]["applies"] is True

    # 3. Hourly Plan validation
    plan = data["hourly_plan"]
    assert len(plan) == 24

    initial_energy = 200.0
    current_energy = initial_energy

    calc_total_grid = 0.0
    calc_total_cost = 0.0
    calc_peak_grid = 0.0

    for h_idx, item in enumerate(plan):
        hour = item["hour"]
        assert hour == h_idx
        grid = item["grid_kwh"]
        solar_used = item["solar_used_kwh"]
        action = item["battery_action"]
        b_kwh = item["battery_kwh"]
        e_after = item["battery_energy_after_kwh"]

        # Action consistency
        assert action in ["charge", "discharge", "idle"]
        if action == "idle":
            assert abs(b_kwh) < 1e-4
            expected_energy = current_energy
            chg = 0.0
            dis = 0.0
        elif action == "charge":
            assert b_kwh > 0
            expected_energy = current_energy + b_kwh
            chg = b_kwh
            dis = 0.0
        else:
            assert b_kwh > 0
            expected_energy = current_energy - b_kwh
            chg = 0.0
            dis = b_kwh

        # Battery transition check
        assert abs(e_after - expected_energy) < 0.05, f"Hour {hour}: e_after={e_after} vs exp={expected_energy}"
        current_energy = e_after

        # Energy balance check: grid + solar_used + discharge = demand + charge
        req_demand = hours_data[hour]["demand_kwh"]
        lhs = grid + solar_used + dis
        rhs = req_demand + chg
        assert abs(lhs - rhs) < 0.05, f"Hour {hour}: Energy balance failed: {lhs} != {rhs}"

        calc_total_grid += grid
        calc_total_cost += grid * hours_data[hour]["tariff_bdt_per_kwh"]
        calc_peak_grid = max(calc_peak_grid, grid)

    # 4. End of day neutrality
    assert abs(plan[23]["battery_energy_after_kwh"] - initial_energy) < 0.05

    # 5. Totals agreement
    assert abs(data["total_grid_kwh"] - calc_total_grid) < 0.1
    assert abs(data["total_cost_bdt"] - calc_total_cost) < 0.1
    assert abs(data["peak_grid_kwh"] - calc_peak_grid) < 0.1
