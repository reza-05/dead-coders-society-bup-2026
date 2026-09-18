import pytest
from app.models import EnergyRequest, BatteryData, HourData, DirectiveInterpretation
from app.llm_interpreter import LLMInterpreter
from app.optimizer import solve_energy_schedule, apply_directives_to_constraints


def make_dummy_hours(demand=200.0, solar=50.0, tariff=10.0):
    return [
        HourData(hour=h, demand_kwh=demand, solar_kwh=(solar if 8 <= h <= 17 else 0.0), tariff_bdt_per_kwh=tariff)
        for h in range(24)
    ]


def make_dummy_battery():
    return BatteryData(
        capacity_kwh=500.0,
        initial_energy_kwh=200.0,
        minimum_energy_kwh=50.0,
        max_charge_kwh_per_hour=100.0,
        max_discharge_kwh_per_hour=100.0
    )


# ---------------------------------------------------------------------------
# 1. All Distractor Notes (All "no_op")
# ---------------------------------------------------------------------------
def test_all_distractor_notes():
    interpreter = LLMInterpreter()
    battery = make_dummy_battery()
    notes = [
        "The cafeteria menu changed to biryani today.",
        "Staff meeting postponed to tomorrow afternoon.",
        "Cleaners are sweeping the hallway."
    ]
    results = interpreter.interpret(notes, battery)

    assert len(results) == 3
    for idx, r in enumerate(results):
        assert r.note_index == idx
        assert r.applies is False
        assert r.directive_type == "no_op"
        assert r.structured_adjustment is None


# ---------------------------------------------------------------------------
# 2. Night-time Solar Reduction (Night solar is 0)
# ---------------------------------------------------------------------------
def test_nighttime_solar_reduction():
    interpreter = LLMInterpreter()
    battery = make_dummy_battery()
    notes = [
        "From 8 PM to 10 PM, solar panel maintenance will drop solar output to 50%."
    ]
    results = interpreter.interpret(notes, battery)
    assert len(results) == 1
    r = results[0]
    assert r.applies is True
    assert r.directive_type == "solar_reduction"
    assert r.structured_adjustment["hours"] == [20, 21]
    assert abs(r.structured_adjustment["factor"] - 0.5) < 0.05

    # Run optimizer with this directive
    hours = make_dummy_hours()
    req = EnergyRequest(scenario_id="EDGE-NIGHT-SOLAR", operator_notes=notes, hours=hours, battery=battery)
    hourly_plan, total_grid, total_cost, peak_grid, summary = solve_energy_schedule(req, results)
    
    # Solar used at night should be 0, system must not crash
    assert hourly_plan[20].solar_used_kwh == 0.0
    assert hourly_plan[21].solar_used_kwh == 0.0


# ---------------------------------------------------------------------------
# 3. End-Hour Exclusion Trap: "from 1 PM to 3 PM" -> [13, 14]
# ---------------------------------------------------------------------------
def test_end_hour_exclusion_trap():
    interpreter = LLMInterpreter()
    battery = make_dummy_battery()
    notes = [
        "Do not charge the battery from 1 PM to 3 PM."
    ]
    results = interpreter.interpret(notes, battery)
    r = results[0]
    assert r.structured_adjustment["hours"] == [13, 14]
    # Check strictly unique and ascending
    hrs = r.structured_adjustment["hours"]
    assert hrs == sorted(list(set(hrs)))


# ---------------------------------------------------------------------------
# 4. Forced Battery Neutrality at High Cost (Hour 23 expensive)
# ---------------------------------------------------------------------------
def test_forced_battery_neutrality_expensive_final_hour():
    # Make hour 23 tariff 100x more expensive (1000 BDT)
    hours = []
    for h in range(24):
        tariff = 1000.0 if h == 23 else 5.0
        # Demand low during day, high at night
        hours.append(HourData(hour=h, demand_kwh=100.0, solar_kwh=0.0, tariff_bdt_per_kwh=tariff))
    
    # Force battery to discharge early by making hour 0-22 cheap and battery drained
    battery = make_dummy_battery()
    req = EnergyRequest(scenario_id="EDGE-EOD-NEUTRALITY", operator_notes=["Notice"], hours=hours, battery=battery)
    
    # Pass no_op directive
    dirs = [DirectiveInterpretation(note_index=0, applies=False, directive_type="no_op", structured_adjustment=None, explanation="dummy")]
    hourly_plan, total_grid, total_cost, peak_grid, summary = solve_energy_schedule(req, dirs)
    
    # Final battery energy MUST equal initial energy (200.0) despite huge tariff
    assert abs(hourly_plan[23].battery_energy_after_kwh - 200.0) < 0.01


# ---------------------------------------------------------------------------
# 5. Hourly Rate Limit Clash (Demand exceeds max discharge)
# ---------------------------------------------------------------------------
def test_hourly_rate_limits():
    hours = make_dummy_hours(demand=500.0, solar=0.0, tariff=50.0)
    battery = make_dummy_battery() # max_discharge is 100
    req = EnergyRequest(scenario_id="EDGE-RATE-LIMIT", operator_notes=["Notice"], hours=hours, battery=battery)
    dirs = [DirectiveInterpretation(note_index=0, applies=False, directive_type="no_op", structured_adjustment=None, explanation="dummy")]
    
    hourly_plan, total_grid, total_cost, peak_grid, summary = solve_energy_schedule(req, dirs)
    for p in hourly_plan:
        if p.battery_action == "discharge":
            assert p.battery_kwh <= battery.max_discharge_kwh_per_hour + 1e-4
        elif p.battery_action == "charge":
            assert p.battery_kwh <= battery.max_charge_kwh_per_hour + 1e-4


# ---------------------------------------------------------------------------
# 6. Multiple Overlapping Constraints
# ---------------------------------------------------------------------------
def test_multiple_overlapping_constraints():
    battery = make_dummy_battery()
    hours = make_dummy_hours()
    
    # Note 1: no_charge from 12 PM to 3 PM [12, 13, 14]
    # Note 2: minimum reserve 150 kWh from 2 PM to 5 PM [14, 15, 16]
    # Hour 14 is overlapping!
    d1 = DirectiveInterpretation(
        note_index=0, applies=True, directive_type="no_charge_window",
        structured_adjustment={"hours": [12, 13, 14]}, explanation="no charge"
    )
    d2 = DirectiveInterpretation(
        note_index=1, applies=True, directive_type="minimum_battery_reserve",
        structured_adjustment={"hours": [14, 15, 16], "minimum_energy_kwh": 150.0}, explanation="reserve"
    )
    
    req = EnergyRequest(scenario_id="EDGE-OVERLAP", operator_notes=["note1", "note2"], hours=hours, battery=battery)
    hourly_plan, total_grid, total_cost, peak_grid, summary = solve_energy_schedule(req, [d1, d2])
    
    # At hour 14:
    # 1) Charge must be 0 (cannot charge)
    assert hourly_plan[14].battery_action != "charge" or hourly_plan[14].battery_kwh == 0.0
    # 2) Battery energy after must be >= 150.0
    assert hourly_plan[14].battery_energy_after_kwh >= 150.0 - 0.01


# ---------------------------------------------------------------------------
# 7. Precision & Float Tolerance
# ---------------------------------------------------------------------------
def test_precision_float_tolerance():
    hours = make_dummy_hours()
    battery = make_dummy_battery()
    req = EnergyRequest(scenario_id="EDGE-PRECISION", operator_notes=["Note"], hours=hours, battery=battery)
    dirs = [DirectiveInterpretation(note_index=0, applies=False, directive_type="no_op", structured_adjustment=None, explanation="dummy")]
    
    hourly_plan, total_grid, total_cost, peak_grid, summary = solve_energy_schedule(req, dirs)
    
    recomputed_grid = sum(p.grid_kwh for p in hourly_plan)
    recomputed_cost = sum(p.grid_kwh * hours[p.hour].tariff_bdt_per_kwh for p in hourly_plan)
    recomputed_peak = max(p.grid_kwh for p in hourly_plan)
    
    assert abs(total_grid - recomputed_grid) < 0.01
    assert abs(total_cost - recomputed_cost) < 0.01
    assert abs(peak_grid - recomputed_peak) < 0.01
