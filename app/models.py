from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class HourData(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour of the day (0-23)")
    demand_kwh: float = Field(..., ge=0.0, description="Campus demand in kWh")
    solar_kwh: float = Field(..., ge=0.0, description="Base solar generation in kWh")
    tariff_bdt_per_kwh: float = Field(..., ge=0.0, description="Grid tariff in BDT/kWh")


class BatteryData(BaseModel):
    capacity_kwh: float = Field(..., gt=0.0, description="Maximum energy battery can store")
    initial_energy_kwh: float = Field(..., ge=0.0, description="Energy at the start of hour 0")
    minimum_energy_kwh: float = Field(..., ge=0.0, description="Base minimum reserve level")
    max_charge_kwh_per_hour: float = Field(..., ge=0.0, description="Maximum charge rate in one hour")
    max_discharge_kwh_per_hour: float = Field(..., ge=0.0, description="Maximum discharge rate in one hour")

    @model_validator(mode="after")
    def validate_battery_limits(self):
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError("initial_energy_kwh cannot be below minimum_energy_kwh")
        return self


class EnergyRequest(BaseModel):
    scenario_id: str = Field(..., min_length=1, description="Unique scenario identifier")
    operator_notes: List[str] = Field(..., min_length=1, max_length=3, description="1-3 natural language notes")
    hours: List[HourData] = Field(..., min_length=24, max_length=24, description="Hourly data for 24 hours")
    battery: BatteryData = Field(..., description="Battery configuration")

    @field_validator("hours")
    def validate_exact_24_hours(cls, v: List[HourData]) -> List[HourData]:
        if len(v) != 24:
            raise ValueError("hours array must contain exactly 24 entries")
        seen_hours = [item.hour for item in v]
        if sorted(seen_hours) != list(range(24)):
            raise ValueError("hours array must contain unique hours from 0 through 23 in sequence")
        return v


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op"
]

BatteryActionType = Literal["charge", "discharge", "idle"]


class DirectiveInterpretation(BaseModel):
    note_index: int = Field(..., ge=0, description="Zero-based index of corresponding operator note")
    applies: bool = Field(..., description="True for non-no_op, false only for no_op")
    directive_type: DirectiveType = Field(..., description="One of the supported directive types")
    structured_adjustment: Optional[Dict[str, Any]] = Field(
        None,
        description="Structured adjustment object, or null only for no_op"
    )
    explanation: str = Field(..., description="Short explanation of the interpretation")

    @model_validator(mode="after")
    def validate_applies_logic(self):
        if self.directive_type == "no_op":
            if self.applies is not False:
                raise ValueError("applies must be false for no_op directive")
            if self.structured_adjustment is not None:
                raise ValueError("structured_adjustment must be null for no_op directive")
        else:
            if self.applies is not True:
                raise ValueError("applies must be true for non-no_op directive")
            if self.structured_adjustment is None:
                raise ValueError("structured_adjustment cannot be null for non-no_op directive")
        return self


class HourlyPlan(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="Hour index (0-23)")
    grid_kwh: float = Field(..., ge=0.0, description="Grid energy purchased in this hour")
    solar_used_kwh: float = Field(..., ge=0.0, description="Solar energy used in this hour")
    battery_action: BatteryActionType = Field(..., description="charge, discharge, or idle")
    battery_kwh: float = Field(..., ge=0.0, description="Magnitude of battery action, 0 if idle")
    battery_energy_after_kwh: float = Field(..., ge=0.0, description="Battery energy state after this hour")


class EnergyResponse(BaseModel):
    scenario_id: str = Field(..., description="Echoed scenario_id")
    directive_interpretation: List[DirectiveInterpretation] = Field(..., description="One entry per note in index order")
    hourly_plan: List[HourlyPlan] = Field(..., min_length=24, max_length=24, description="Hourly schedule for 24 hours")
    total_grid_kwh: float = Field(..., ge=0.0, description="Sum of grid_kwh across all 24 hours")
    total_cost_bdt: float = Field(..., ge=0.0, description="Total grid electricity cost in BDT")
    peak_grid_kwh: float = Field(..., ge=0.0, description="Maximum hourly grid_kwh")
    plan_summary: str = Field(..., description="Short human-readable summary of the strategy")


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
