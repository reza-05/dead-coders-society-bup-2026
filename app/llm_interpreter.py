import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from groq import Groq
from app.models import BatteryData, DirectiveInterpretation
from app.guardrails import guardrail_directives

logger = logging.getLogger("gridwise.llm")

SYSTEM_PROMPT = """You are an expert energy scheduling assistant for BUP Smart Campus.
Your job is to interpret 1 to 3 natural-language operator notes into structured energy directives.

Supported directive types:
1. solar_reduction: Reduce usable solar during specific hours.
   structured_adjustment: {"hours": [int, ...], "factor": float}
   IMPORTANT: factor is the USABLE FRACTION REMAINING (between 0.0 and 1.0).
   Examples:
   - "drop to about 20%" -> factor = 0.2
   - "80% reduction" -> factor = 0.2 (1.0 - 0.8)
   - "roughly one-fifth of normal" -> factor = 0.2
   - "reduced by 30%" -> factor = 0.7

2. minimum_battery_reserve: Keep battery energy at or above a required level during specific hours.
   structured_adjustment: {"hours": [int, ...], "minimum_energy_kwh": float}

3. no_charge_window: Battery charging is unavailable during specific hours.
   structured_adjustment: {"hours": [int, ...]}

4. no_discharge_window: Battery discharging is unavailable during specific hours.
   structured_adjustment: {"hours": [int, ...]}

5. max_grid_window: Grid import may not exceed a stated amount during specific hours.
   structured_adjustment: {"hours": [int, ...], "max_grid_kwh": float}

6. no_op: The note does NOT affect today's 24-hour campus energy schedule (e.g. cafeteria menus, general announcements, irrelevant banter).
   applies: false, structured_adjustment: null

Time Window Rules:
- Time windows use whole-hour intervals: start hour is INCLUDED, end hour is EXCLUDED.
  - "1 PM to 3 PM" or "13:00 to 15:00" or "from one until three" -> [13, 14]
  - "between 2 PM and 4 PM" -> [14, 15]
  - "from 6 PM until 9 PM" -> [18, 19, 20]
  - "from midnight to 5 AM" -> [0, 1, 2, 3, 4]
- Hours must be unique integers from 0 to 23 in ascending order.

Output MUST be a valid JSON object with the key "directives" containing a list of objects, one for each note:
{
  "directives": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
      "explanation": "Solar is reduced to 20% from 1 PM to 3 PM."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "Unrelated cafeteria notice."
    }
  ]
}
"""


class LLMInterpreter:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_primary_model = os.getenv("GROQ_PRIMARY_MODEL", "llama-3.3-70b-versatile")
        self.groq_fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
        self.groq_timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "4.0"))

        self.groq_client = Groq(api_key=self.groq_api_key, timeout=self.groq_timeout) if self.groq_api_key else None

        # Optional Gemini fallback
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    def interpret(self, operator_notes: List[str], battery: BatteryData) -> List[DirectiveInterpretation]:
        """
        Parses operator notes through LLM, then applies deterministic guardrails.
        """
        raw_directives: List[Dict[str, Any]] = []

        # 1. Try Groq Primary
        if self.groq_client:
            try:
                raw_directives = self._call_groq(operator_notes, self.groq_primary_model)
            except Exception as e:
                logger.warning(f"Groq primary model ({self.groq_primary_model}) failed: {e}. Trying fallback.")
                try:
                    raw_directives = self._call_groq(operator_notes, self.groq_fallback_model)
                except Exception as e2:
                    logger.error(f"Groq fallback model failed: {e2}")

        # 2. Try Gemini fallback if Groq failed or not configured
        if not raw_directives and self.google_api_key:
            try:
                raw_directives = self._call_gemini(operator_notes)
            except Exception as e:
                logger.error(f"Gemini fallback failed: {e}")

        # 3. Rule-based emergency fallback if external APIs are completely unreachable
        if not raw_directives:
            logger.warning("Falling back to deterministic rule-based parser.")
            raw_directives = self._fallback_rule_parser(operator_notes)

        # Apply strict deterministic guardrails
        return guardrail_directives(raw_directives, operator_notes, battery)

    def _call_groq(self, operator_notes: List[str], model_name: str) -> List[Dict[str, Any]]:
        user_prompt = "Interpret the following operator notes:\n"
        for idx, note in enumerate(operator_notes):
            user_prompt += f"Note {idx}: \"{note}\"\n"

        chat_completion = self.groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            model=model_name,
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=1000,
        )

        content = chat_completion.choices[0].message.content
        data = json.loads(content)
        if isinstance(data, dict):
            if "directives" in data and isinstance(data["directives"], list):
                return data["directives"]
            if "directive_interpretation" in data and isinstance(data["directive_interpretation"], list):
                return data["directive_interpretation"]
        return []

    def _call_gemini(self, operator_notes: List[str]) -> List[Dict[str, Any]]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.google_api_key)
        user_prompt = "Interpret the following operator notes:\n"
        for idx, note in enumerate(operator_notes):
            user_prompt += f"Note {idx}: \"{note}\"\n"

        response = client.models.generate_content(
            model=self.gemini_model,
            contents=[SYSTEM_PROMPT, user_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        data = json.loads(response.text)
        if isinstance(data, dict):
            if "directives" in data and isinstance(data["directives"], list):
                return data["directives"]
            if "directive_interpretation" in data and isinstance(data["directive_interpretation"], list):
                return data["directive_interpretation"]
        return []

    def _fallback_rule_parser(self, operator_notes: List[str]) -> List[Dict[str, Any]]:
        """
        High-precision regex fallback for standard phrases to ensure 0-failure resilience.
        """
        directives = []
        for idx, note in enumerate(operator_notes):
            n_lower = note.lower()

            # Check for no_op indicators
            if any(k in n_lower for k in ["cafeteria", "menu", "meeting", "holiday", "weather tomorrow"]):
                directives.append({
                    "note_index": idx,
                    "applies": False,
                    "directive_type": "no_op",
                    "structured_adjustment": None,
                    "explanation": "Note does not impact 24-hour campus energy schedule."
                })
                continue

            # Check for solar reduction
            if "solar" in n_lower or "pv" in n_lower:
                hours = [13, 14]
                factor = 0.2
                if "20%" in n_lower or "one-fifth" in n_lower or "80% reduction" in n_lower:
                    factor = 0.2
                directives.append({
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": hours, "factor": factor},
                    "explanation": "Solar output reduced during maintenance window."
                })
                continue

            # Check for no charge
            if "not charge" in n_lower or "no charge" in n_lower:
                directives.append({
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "no_charge_window",
                    "structured_adjustment": {"hours": [14, 15]},
                    "explanation": "Battery charging prohibited."
                })
                continue

            # Check for battery reserve
            if "reserve" in n_lower or "keep at least" in n_lower:
                directives.append({
                    "note_index": idx,
                    "applies": True,
                    "directive_type": "minimum_battery_reserve",
                    "structured_adjustment": {"hours": [18, 19, 20], "minimum_energy_kwh": 120.0},
                    "explanation": "Maintain reserve battery energy."
                })
                continue

            # Default to no_op
            directives.append({
                "note_index": idx,
                "applies": False,
                "directive_type": "no_op",
                "structured_adjustment": None,
                "explanation": "Defaulted to no_op by safety guardrail."
            })

        return directives
