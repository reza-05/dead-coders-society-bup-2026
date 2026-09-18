import math
from typing import List, Tuple, Dict, Any
import numpy as np
from scipy.optimize import linprog

from app.models import EnergyRequest, DirectiveInterpretation, HourlyPlan


def apply_directives_to_constraints(
    request: EnergyRequest,
    directives: List[DirectiveInterpretation]
) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """
    Applies extracted operator directives to deterministic parameter bounds.
    Returns:
      (effective_solar, effective_min_reserve, effective_max_charge, effective_max_discharge, effective_max_grid)
    """
    effective_solar = [h.solar_kwh for h in request.hours]
    effective_min_reserve = [request.battery.minimum_energy_kwh for _ in range(24)]
    effective_max_charge = [request.battery.max_charge_kwh_per_hour for _ in range(24)]
    effective_max_discharge = [request.battery.max_discharge_kwh_per_hour for _ in range(24)]
    effective_max_grid = [float("inf") for _ in range(24)]

    for d in directives:
        if not d.applies or not d.structured_adjustment:
            continue

        adj = d.structured_adjustment
        hours = adj.get("hours", [])

        if d.directive_type == "solar_reduction":
            factor = float(adj.get("factor", 1.0))
            for h in hours:
                if 0 <= h < 24:
                    effective_solar[h] = effective_solar[h] * factor

        elif d.directive_type == "minimum_battery_reserve":
            min_energy = float(adj.get("minimum_energy_kwh", request.battery.minimum_energy_kwh))
            for h in hours:
                if 0 <= h < 24:
                    effective_min_reserve[h] = max(effective_min_reserve[h], min_energy)

        elif d.directive_type == "no_charge_window":
            for h in hours:
                if 0 <= h < 24:
                    effective_max_charge[h] = 0.0

        elif d.directive_type == "no_discharge_window":
            for h in hours:
                if 0 <= h < 24:
                    effective_max_discharge[h] = 0.0

        elif d.directive_type == "max_grid_window":
            max_grid = float(adj.get("max_grid_kwh", float("inf")))
            for h in hours:
                if 0 <= h < 24:
                    effective_max_grid[h] = min(effective_max_grid[h], max_grid)

    return (
        effective_solar,
        effective_min_reserve,
        effective_max_charge,
        effective_max_discharge,
        effective_max_grid,
    )


def solve_energy_schedule(
    request: EnergyRequest,
    directives: List[DirectiveInterpretation]
) -> Tuple[List[HourlyPlan], float, float, float, str]:
    """
    Formulates and solves the 24-hour cost minimization problem via SciPy HiGHS LP.
    Returns:
      (hourly_plan, total_grid_kwh, total_cost_bdt, peak_grid_kwh, plan_summary)
    """
    (
        effective_solar,
        effective_min_reserve,
        effective_max_charge,
        effective_max_discharge,
        effective_max_grid,
    ) = apply_directives_to_constraints(request, directives)

    # 120 variables: 24 of each (G, S, C, D, E)
    # Indices:
    # G_h = 0..23
    # S_h = 24..47
    # C_h = 48..71
    # D_h = 72..95
    # E_h = 96..119
    n_vars = 120

    # Objective: Minimize sum(G_h * tariff_h) + tiny penalty on C_h and D_h to prevent simultaneous charge/discharge
    c = np.zeros(n_vars)
    for h in range(24):
        c[h] = request.hours[h].tariff_bdt_per_kwh
        c[48 + h] = 1e-6  # tiny tie-breaker
        c[72 + h] = 1e-6  # tiny tie-breaker

    # Equality constraints (A_eq @ x == b_eq):
    # 1) Energy balance: G_h + S_h - C_h + D_h = demand_h (24 eq)
    # 2) Battery continuity:
    #    h=0: E_0 - C_0 + D_0 = initial_energy
    #    h>0: E_h - E_{h-1} - C_h + D_h = 0 (23 eq)
    # 3) End of day battery neutrality:
    #    E_23 = initial_energy (1 eq)
    n_eq = 24 + 24 + 1
    A_eq = np.zeros((n_eq, n_vars))
    b_eq = np.zeros(n_eq)

    # Energy balance
    for h in range(24):
        A_eq[h, h] = 1.0       # G_h
        A_eq[h, 24 + h] = 1.0  # S_h
        A_eq[h, 48 + h] = -1.0 # - C_h
        A_eq[h, 72 + h] = 1.0  # + D_h
        b_eq[h] = request.hours[h].demand_kwh

    # Battery continuity
    # h = 0
    row = 24
    A_eq[row, 96] = 1.0       # E_0
    A_eq[row, 48] = -1.0      # - C_0
    A_eq[row, 72] = 1.0       # + D_0
    b_eq[row] = request.battery.initial_energy_kwh

    # h = 1..23
    for h in range(1, 24):
        row = 24 + h
        A_eq[row, 96 + h] = 1.0      # E_h
        A_eq[row, 96 + h - 1] = -1.0 # - E_{h-1}
        A_eq[row, 48 + h] = -1.0     # - C_h
        A_eq[row, 72 + h] = 1.0      # + D_h
        b_eq[row] = 0.0

    # End of day neutrality: E_23 = initial_energy
    row = 48
    A_eq[row, 96 + 23] = 1.0
    b_eq[row] = request.battery.initial_energy_kwh

    # Bounds on variables
    bounds = []
    # G_h (0 .. effective_max_grid[h])
    for h in range(24):
        upper = None if math.isinf(effective_max_grid[h]) else effective_max_grid[h]
        bounds.append((0.0, upper))

    # S_h (0 .. effective_solar[h])
    for h in range(24):
        bounds.append((0.0, max(0.0, effective_solar[h])))

    # C_h (0 .. effective_max_charge[h])
    for h in range(24):
        bounds.append((0.0, max(0.0, effective_max_charge[h])))

    # D_h (0 .. effective_max_discharge[h])
    for h in range(24):
        bounds.append((0.0, max(0.0, effective_max_discharge[h])))

    # E_h (effective_min_reserve[h] .. capacity_kwh)
    for h in range(24):
        bounds.append((max(0.0, effective_min_reserve[h]), request.battery.capacity_kwh))

    res = linprog(
        c=c,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )

    if not res.success:
        raise RuntimeError(f"Optimizer failed to find a feasible schedule: {res.message}")

    x = res.x
    G = x[0:24]
    S = x[24:48]
    C = x[48:72]
    D = x[72:96]
    E = x[96:120]

    hourly_plan: List[HourlyPlan] = []
    current_energy = request.battery.initial_energy_kwh

    for h in range(24):
        g_val = max(0.0, float(G[h]))
        s_val = max(0.0, float(S[h]))
        c_val = max(0.0, float(C[h]))
        d_val = max(0.0, float(D[h]))

        # Net battery action to guarantee mutually exclusive action
        net_diff = c_val - d_val
        threshold = 1e-4

        if net_diff > threshold:
            action = "charge"
            action_kwh = net_diff
            new_energy = current_energy + action_kwh
        elif net_diff < -threshold:
            action = "discharge"
            action_kwh = -net_diff
            new_energy = current_energy - action_kwh
        else:
            action = "idle"
            action_kwh = 0.0
            new_energy = current_energy

        # Bound safety
        new_energy = max(0.0, min(request.battery.capacity_kwh, new_energy))
        current_energy = new_energy

        # Ensure exact energy balance for the hour:
        # grid + solar_used + discharge = demand + charge
        # => grid = demand + charge - solar_used - discharge
        # Adjust grid slightly for numerical stability if needed
        req_demand = request.hours[h].demand_kwh
        if action == "charge":
            g_val = max(0.0, req_demand + action_kwh - s_val)
        elif action == "discharge":
            g_val = max(0.0, req_demand - action_kwh - s_val)
        else:
            g_val = max(0.0, req_demand - s_val)

        # Enforce max_grid directive if present
        if not math.isinf(effective_max_grid[h]):
            g_val = min(g_val, effective_max_grid[h])

        plan_entry = HourlyPlan(
            hour=h,
            grid_kwh=round(g_val, 4),
            solar_used_kwh=round(s_val, 4),
            battery_action=action,
            battery_kwh=round(action_kwh, 4),
            battery_energy_after_kwh=round(new_energy, 4),
        )
        hourly_plan.append(plan_entry)

    # Re-calculate exact totals from hourly_plan to guarantee 100% agreement
    total_grid_kwh = round(sum(p.grid_kwh for p in hourly_plan), 4)
    total_cost_bdt = round(
        sum(p.grid_kwh * request.hours[p.hour].tariff_bdt_per_kwh for p in hourly_plan), 4
    )
    peak_grid_kwh = round(max(p.grid_kwh for p in hourly_plan), 4)

    plan_summary = (
        f"Optimized schedule for scenario {request.scenario_id}: "
        f"Total grid electricity purchased is {total_grid_kwh:.2f} kWh costing {total_cost_bdt:.2f} BDT "
        f"with a peak grid draw of {peak_grid_kwh:.2f} kWh. "
        f"Battery maintains end-of-day neutrality at {hourly_plan[-1].battery_energy_after_kwh:.2f} kWh."
    )

    return hourly_plan, total_grid_kwh, total_cost_bdt, peak_grid_kwh, plan_summary
