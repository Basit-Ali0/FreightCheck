# backend/tests/integration/test_gemini_live.py
"""Live Gemini smoke test for M3 DoD.

Excluded from default CI via `@pytest.mark.integration` and the `-m "not
integration"` filter. Run locally with:

    GEMINI_API_KEY=... uv run pytest tests/integration/test_gemini_live.py \\
        -m integration

Verifies that the wrapper's token accounting surfaces a non-zero usage count
when talking to the real Gemini API — catching the class of bug where
`usage_metadata` is read from the wrong attribute and silently reported as 0.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from freightcheck.agent import prompts
from freightcheck.services import gemini
from tests.support.live_integration_env import is_real_gemini_api_key_configured


class _Ping(BaseModel):
    status: str
    reason: str


@pytest.mark.integration
async def test_call_gemini_reports_nonzero_tokens() -> None:
    if not is_real_gemini_api_key_configured():
        pytest.skip(
            "GEMINI_API_KEY missing, placeholder, or too short for live Gemini; "
            "skipping live Gemini test (set a real key in the environment or backend/.env).",
        )

    parsed, tokens = await gemini.call_gemini(
        prompt_name="semantic_validator",
        prompt_template=prompts.SEMANTIC_VALIDATOR_PROMPT,
        template_vars={
            "field_name": "shipper",
            "doc_a": "bol",
            "value_a": "Acme Exports Ltd",
            "doc_b": "invoice",
            "value_b": "ACME EXPORTS PRIVATE LIMITED",
        },
        response_schema=_Ping,
    )
    assert parsed.status in {"match", "minor_mismatch", "critical_mismatch"}
    assert tokens > 0, "Gemini wrapper must report a non-zero token count"
