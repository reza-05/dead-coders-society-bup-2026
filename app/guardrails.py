import logging
from typing import Any, Dict, List, Optional

from app.models import BatteryData, DirectiveInterpretation, DirectiveType

logger = logging.getLogger("gridwise.guardrails")

VALID_DIRECTIVE_TYPES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
}


def sanitize_hours(raw_hours: Any) -> List[int]:
    """
    Ensures hours array contains unique integers 0..23 in ascending order.
    """
    if not isinstance(raw_hours, list):
        return []
    valid = set()
    for h in raw_hours:
        try:
            h_int = int(h)
            if 0 <= h_int <= 23:
                valid.add(h_int)
        except (ValueError, TypeError):
            continue
    return sorted(list(valid))


def validate_and_repair_directive(
    raw_dict: Dict[str, Any],
    expected_index: int,
    note_text: str,
    battery: BatteryData
) -> DirectiveInterpretation:
    """
    Deterministically validates, sanitizes, and repairs a raw directive interpretation.
    Enforces the rules specified in Section 04 and Section 08 of the Problem Statement.
    """
    directive_type = raw_dict.get("directive_type", "no_op")
    if directive_type not in VALID_DIRECTIVE_TYPES:
        logger.warning(f"Unsupported directive_type '{directive_type}' received. Falling back to no_op.")
        directive_type = "no_op"

    raw_explanation = raw_dict.get("explanation")
    explanation = str(raw_explanation) if raw_explanation else f"Interpretation for note {expected_index}"

    if directive_type == "no_op":
        return DirectiveInterpretation(
            note_index=expected_index,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation=explanation
        )

    raw_adj = raw_dict.get("structured_adjustment")
    if not isinstance(raw_adj, dict):
        logger.warning(f"Missing structured_adjustment for {directive_type}. Falling back to no_op.")
        return DirectiveInterpretation(
            note_index=expected_index,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="Invalid adjustment format, defaulting to no_op"
        )

    hours = sanitize_hours(raw_adj.get("hours"))

    if directive_type == "solar_reduction":
        raw_factor = raw_adj.get("factor", 1.0)
        try:
            factor = float(raw_factor)
            factor = max(0.0, min(1.0, factor))
        except (ValueError, TypeError):
            factor = 1.0

        return DirectiveInterpretation(
            note_index=expected_index,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": hours, "factor": round(factor, 4)},
            explanation=explanation
        )

    elif directive_type == "minimum_battery_reserve":
        raw_min = raw_adj.get("minimum_energy_kwh", battery.minimum_energy_kwh)
        try:
            min_energy = float(raw_min)
            # If specified as a ratio/fraction (e.g. 0.5 for 50%), convert to kWh
            if 0.0 < min_energy <= 1.0 and battery.capacity_kwh > 1.0:
                min_energy = min_energy * battery.capacity_kwh
            min_energy = max(0.0, min(battery.capacity_kwh, min_energy))
        except (ValueError, TypeError):
            min_energy = battery.minimum_energy_kwh

        return DirectiveInterpretation(
            note_index=expected_index,
            applies=True,
            directive_type="minimum_battery_reserve",
            structured_adjustment={"hours": hours, "minimum_energy_kwh": round(min_energy, 4)},
            explanation=explanation
        )

    elif directive_type == "no_charge_window":
        return DirectiveInterpretation(
            note_index=expected_index,
            applies=True,
            directive_type="no_charge_window",
            structured_adjustment={"hours": hours},
            explanation=explanation
        )

    elif directive_type == "no_discharge_window":
        return DirectiveInterpretation(
            note_index=expected_index,
            applies=True,
            directive_type="no_discharge_window",
            structured_adjustment={"hours": hours},
            explanation=explanation
        )

    elif directive_type == "max_grid_window":
        raw_grid = raw_adj.get("max_grid_kwh", 0.0)
        try:
            max_grid = max(0.0, float(raw_grid))
        except (ValueError, TypeError):
            max_grid = 0.0

        return DirectiveInterpretation(
            note_index=expected_index,
            applies=True,
            directive_type="max_grid_window",
            structured_adjustment={"hours": hours, "max_grid_kwh": round(max_grid, 4)},
            explanation=explanation
        )

    # Safe catch-all fallback
    return DirectiveInterpretation(
        note_index=expected_index,
        applies=False,
        directive_type="no_op",
        structured_adjustment=None,
        explanation="Safe fallback to no_op"
    )


def guardrail_directives(
    raw_directives: List[Dict[str, Any]],
    operator_notes: List[str],
    battery: BatteryData
) -> List[DirectiveInterpretation]:
    """
    Enforces exact 0..N-1 ordering and coverage for every operator note.
    """
    result: List[DirectiveInterpretation] = []
    by_index = {item.get("note_index"): item for item in raw_directives if isinstance(item, dict) and "note_index" in item}

    for idx, note in enumerate(operator_notes):
        candidate = by_index.get(idx)
        if candidate is None and idx < len(raw_directives) and isinstance(raw_directives[idx], dict):
            candidate = raw_directives[idx]

        if candidate is None:
            candidate = {
                "note_index": idx,
                "directive_type": "no_op",
                "applies": False,
                "structured_adjustment": None,
                "explanation": "No valid LLM output found for this note."
            }

        sanitized = validate_and_repair_directive(candidate, idx, note, battery)
        result.append(sanitized)

    return result
