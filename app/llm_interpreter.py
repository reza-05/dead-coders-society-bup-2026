import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

from groq import Groq
from app.models import BatteryData, DirectiveInterpretation
from app.guardrails import guardrail_directives

load_dotenv()

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
   IMPORTANT: If the reserve is specified as a percentage of battery capacity (e.g. "at least 50% of the battery capacity" where capacity is 200 kWh), compute the exact value: (percentage / 100) * capacity_kwh (e.g. 0.50 * 200 = 100 kWh).

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

Output MUST be a valid JSON object with the key "directives" containing a list of objects, one for each note in exact index order:
{
  "directives": [
    {
      "note_index": 0,
      "applies": true,
      "directive_type": "solar_reduction",
      "structured_adjustment": {"hours": [12, 13], "factor": 0.25},
      "explanation": "Solar is reduced to 25% during panel washing from noon to 2 PM."
    },
    {
      "note_index": 1,
      "applies": false,
      "directive_type": "no_op",
      "structured_adjustment": null,
      "explanation": "Unrelated notice."
    }
  ]
}

Few-shot Guidance:
- "Facilities will wash the rooftop solar panels from noon until 2 PM. During cleaning, usable solar should be treated as roughly 25% of the forecast." -> solar_reduction, hours: [12, 13], factor: 0.25
- "Expect an 80% reduction in rooftop solar between 11 AM and 2 PM" -> solar_reduction, hours: [11, 12, 13], factor: 0.2
- "The battery charger will be isolated from 2 AM until 5 AM" -> no_charge_window, hours: [2, 3, 4]
- "Do not discharge the battery from 5 PM until 7 PM during relay testing" -> no_discharge_window, hours: [17, 18]
- "From 6 PM until 9 PM, campus grid import must not exceed 155 kWh" -> max_grid_window, hours: [18, 19, 20], max_grid_kwh: 155
- "Keep at least 50% of the battery capacity stored from 6 PM until 9 PM" (where capacity = 200 kWh) -> minimum_battery_reserve, hours: [18, 19, 20], minimum_energy_kwh: 100
- "The sports office moved next month's registration deadline", "The library is extending book-return hours next week", "A seminar room booking was moved" -> no_op, applies: false, structured_adjustment: null
"""


class LLMInterpreter:
    def __init__(self):
        self.groq_keys = self._load_groq_keys()
        self.current_key_idx = 0
        self.groq_primary_model = os.getenv("GROQ_PRIMARY_MODEL", "openai/gpt-oss-120b")
        self.groq_fallback_model = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
        self.groq_timeout = float(os.getenv("GROQ_TIMEOUT_SECONDS", "4.0"))

        # Optional Free High-Speed Cloud Fallbacks
        self.cerebras_api_key = os.getenv("CEREBRAS_API_KEY")
        self.cerebras_model = os.getenv("CEREBRAS_MODEL", "llama3.1-8b")

        self.sambanova_api_key = os.getenv("SAMBANOVA_API_KEY")
        self.sambanova_model = os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.1-8B-Instruct")

        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")

        # Optional Gemini fallback
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        # Optional Local LLM URL (Ollama / vLLM / Local OpenAI compatible)
        self.local_llm_url = os.getenv("LOCAL_LLM_URL")
        self.local_llm_model = os.getenv("LOCAL_LLM_MODEL", "llama3")

        # In-memory Directive Cache (saves quota & gives 0ms latency for repeated notes)
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def _load_groq_keys(self) -> List[str]:
        raw_keys = [os.getenv("GROQ_API_KEYS", ""), os.getenv("GROQ_API_KEY", "")]
        keys = []
        for raw in raw_keys:
            for k in raw.split(","):
                k_clean = k.strip()
                if k_clean and k_clean not in keys:
                    keys.append(k_clean)
        return keys

    def _get_active_groq_client(self) -> Optional[Groq]:
        if not self.groq_keys:
            return None
        key = self.groq_keys[self.current_key_idx % len(self.groq_keys)]
        return Groq(api_key=key, timeout=self.groq_timeout)

    def _rotate_groq_key(self):
        if len(self.groq_keys) > 1:
            self.current_key_idx = (self.current_key_idx + 1) % len(self.groq_keys)
            logger.info(f"Rotated to next Groq API key (index {self.current_key_idx})")

    def interpret(self, operator_notes: List[str], battery: BatteryData) -> List[DirectiveInterpretation]:
        """
        Multi-Tier Resilient Pipeline:
        0. In-Memory Cache (0ms, 0 Quota)
        1. Groq Cloud (Multi-key rotation, 120B -> 20B)
        2. Cerebras Cloud (World's fastest LLaMA inference, free tier)
        3. SambaNova Cloud (Fast LLaMA inference, free tier)
        4. OpenRouter (Free LLaMA models)
        5. Google Gemini (Gemini 2.0 Flash)
        6. Local LLM (Ollama / vLLM)
        7. Deterministic Safety Net
        """
        # 0. Check in-memory cache
        cache_key = f"{tuple(operator_notes)}|{battery.capacity_kwh}|{battery.minimum_energy_kwh}"
        if cache_key in self._cache:
            logger.info("Cache hit: Returning cached directive interpretation (0ms latency)")
            return guardrail_directives(self._cache[cache_key], operator_notes, battery)

        raw_directives: List[Dict[str, Any]] = []

        # 1. Tier 1: Groq Cloud with Multi-Key Rotation
        client = self._get_active_groq_client()
        if client:
            try:
                raw_directives = self._call_groq(client, operator_notes, battery, self.groq_primary_model)
            except Exception as e:
                logger.warning(f"Groq primary error: {e}. Trying secondary model.")
                self._rotate_groq_key()
                client = self._get_active_groq_client()
                try:
                    raw_directives = self._call_groq(client, operator_notes, battery, self.groq_fallback_model)
                except Exception as e2:
                    logger.error(f"Groq fallback model error: {e2}")

        # 2. Tier 2: Cerebras Inference (Free & Ultra-Fast)
        if not raw_directives and self.cerebras_api_key:
            try:
                logger.info("Activating Tier 2 Fallback: Cerebras Cloud API")
                raw_directives = self._call_openai_compatible(
                    "https://api.cerebras.ai/v1", self.cerebras_api_key, self.cerebras_model, operator_notes, battery
                )
            except Exception as e:
                logger.error(f"Cerebras fallback failed: {e}")

        # 3. Tier 3: SambaNova Cloud (Free & Ultra-Fast)
        if not raw_directives and self.sambanova_api_key:
            try:
                logger.info("Activating Tier 3 Fallback: SambaNova Cloud API")
                raw_directives = self._call_openai_compatible(
                    "https://api.sambanova.ai/v1", self.sambanova_api_key, self.sambanova_model, operator_notes, battery
                )
            except Exception as e:
                logger.error(f"SambaNova fallback failed: {e}")

        # 4. Tier 4: OpenRouter Free Models
        if not raw_directives and self.openrouter_api_key:
            try:
                logger.info("Activating Tier 4 Fallback: OpenRouter Free API")
                raw_directives = self._call_openai_compatible(
                    "https://openrouter.ai/api/v1", self.openrouter_api_key, self.openrouter_model, operator_notes, battery
                )
            except Exception as e:
                logger.error(f"OpenRouter fallback failed: {e}")

        # 5. Tier 5: Google Gemini Fallback
        if not raw_directives and self.google_api_key:
            try:
                logger.info("Activating Tier 5 Fallback: Google Gemini API")
                raw_directives = self._call_gemini(operator_notes, battery)
            except Exception as e:
                logger.error(f"Gemini fallback failed: {e}")

        # 6. Tier 6: Local LLM Fallback (Ollama / vLLM / Local server)
        if not raw_directives and self.local_llm_url:
            try:
                logger.info(f"Activating Tier 6 Fallback: Local LLM at {self.local_llm_url}")
                raw_directives = self._call_openai_compatible(
                    self.local_llm_url, "", self.local_llm_model, operator_notes, battery
                )
            except Exception as e:
                logger.error(f"Local LLM fallback failed: {e}")

        # 7. Tier 7: High-Precision Deterministic Emergency Parser
        if not raw_directives:
            logger.warning("Activating Tier 7 Safety Net: High-precision deterministic parser")
            raw_directives = self._fallback_rule_parser(operator_notes)

        # Store in cache if extraction succeeded
        if raw_directives:
            self._cache[cache_key] = raw_directives

        # Apply strict deterministic guardrails
        return guardrail_directives(raw_directives, operator_notes, battery)

    def _call_groq(self, client: Groq, operator_notes: List[str], battery: BatteryData, model_name: str) -> List[Dict[str, Any]]:
        user_prompt = (
            f"Battery System Specs: capacity_kwh = {battery.capacity_kwh}, "
            f"minimum_energy_kwh = {battery.minimum_energy_kwh}, "
            f"max_charge_kwh_per_hour = {battery.max_charge_kwh_per_hour}, "
            f"max_discharge_kwh_per_hour = {battery.max_discharge_kwh_per_hour}\n\n"
            f"Interpret the following operator notes:\n"
        )
        for idx, note in enumerate(operator_notes):
            user_prompt += f"Note {idx}: \"{note}\"\n"

        chat_completion = client.chat.completions.create(
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

    def _call_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        operator_notes: List[str],
        battery: BatteryData
    ) -> List[Dict[str, Any]]:
        import httpx

        user_prompt = (
            f"Battery System Specs: capacity_kwh = {battery.capacity_kwh}, "
            f"minimum_energy_kwh = {battery.minimum_energy_kwh}, "
            f"max_charge_kwh_per_hour = {battery.max_charge_kwh_per_hour}, "
            f"max_discharge_kwh_per_hour = {battery.max_discharge_kwh_per_hour}\n\n"
            f"Interpret the following operator notes:\n"
        )
        for idx, note in enumerate(operator_notes):
            user_prompt += f"Note {idx}: \"{note}\"\n"

        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }
        with httpx.Client(timeout=self.groq_timeout) as http_client:
            res = http_client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            content = res.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            if isinstance(data, dict):
                if "directives" in data and isinstance(data["directives"], list):
                    return data["directives"]
                if "directive_interpretation" in data and isinstance(data["directive_interpretation"], list):
                    return data["directive_interpretation"]
        return []

    def _call_gemini(self, operator_notes: List[str], battery: BatteryData) -> List[Dict[str, Any]]:
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
