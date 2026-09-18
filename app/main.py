import logging
import os
import time
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.models import EnergyRequest, EnergyResponse, HealthResponse
from app.llm_interpreter import LLMInterpreter
from app.optimizer import solve_energy_schedule

# Load environment variables
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gridwise.main")

app = FastAPI(
    title="GridWise LLM - BUP Smart Campus Energy Optimizer",
    version="1.0.0",
    description="LLM-Assisted Operator Directive Interpretation & 24-Hour Energy Scheduling"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize LLM interpreter
llm_interpreter = LLMInterpreter()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Returns HTTP 400 for malformed JSON or structurally invalid request as required by Section 6.1.
    """
    logger.warning(f"Malformed or structurally invalid request: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Malformed JSON or structurally invalid request", "errors": exc.errors()}
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Ensures safe 500 failure without exposing credentials, keys, or internal stack traces.
    """
    logger.error(f"Controlled server error: {exc}", exc_info=False)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Controlled internal server error"}
    )


@app.get("/", tags=["Root"])
def root():
    """
    Root landing response pointing to health probe and documentation.
    """
    return {
        "service": "GridWise LLM - BUP Smart Campus Energy Optimizer",
        "status": "online",
        "endpoints": {
            "health": "/health",
            "optimize_energy": "/optimize-energy",
            "documentation": "/docs"
        }
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """
    Readiness endpoint for judging harness. Returns status 'ok'.
    """
    return HealthResponse(status="ok")


@app.post("/optimize-energy", response_model=EnergyResponse, tags=["Optimization"])
def optimize_energy(payload: EnergyRequest):
    """
    Main endpoint: Accepts 24-hour campus energy scenario and operator notes.
    Interprets directives using LLM, applies deterministic guardrails, and solves
    the cost-minimization Linear Program.
    """
    start_time = time.monotonic()
    logger.info(f"Processing scenario: {payload.scenario_id} with {len(payload.operator_notes)} notes")

    try:
        # Step 1: Interpret operator notes through LLM + Guardrails
        directives = llm_interpreter.interpret(
            operator_notes=payload.operator_notes,
            battery=payload.battery
        )

        # Step 2: Solve 24-hour energy optimization schedule
        (
            hourly_plan,
            total_grid_kwh,
            total_cost_bdt,
            peak_grid_kwh,
            plan_summary
        ) = solve_energy_schedule(payload, directives)

        duration_ms = (time.monotonic() - start_time) * 1000
        logger.info(f"Scenario {payload.scenario_id} solved in {duration_ms:.1f}ms with cost {total_cost_bdt:.2f} BDT")

        return EnergyResponse(
            scenario_id=payload.scenario_id,
            directive_interpretation=directives,
            hourly_plan=hourly_plan,
            total_grid_kwh=total_grid_kwh,
            total_cost_bdt=total_cost_bdt,
            peak_grid_kwh=peak_grid_kwh,
            plan_summary=plan_summary
        )

    except Exception as e:
        logger.error(f"Error processing scenario {payload.scenario_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Controlled error during energy optimization pipeline"
        )
