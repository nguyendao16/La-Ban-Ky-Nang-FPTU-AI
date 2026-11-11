"""Verified text Responses capabilities; do not infer support from name prefixes.

Sources: https://developers.openai.com/api/docs/models/{model}
and /api/docs/guides/latest-model?model=gpt-5.4, checked 2026-10-13.
Prices are USD per million tokens for standard processing (not an invoice).
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    context_window: int
    max_output_tokens: int
    reasoning_efforts: frozenset[str]
    temperature_without_reasoning: bool
    input_price: float
    cached_input_price: float
    output_price: float


REASONING_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh"})
MODEL_CAPABILITIES = {}
for aliases, capability in [
    (("gpt-4o-mini", "gpt-4o-mini-2024-07-18"), ModelCapabilities(128000, 16384, frozenset(), True, .15, .075, .6)),
    (("gpt-4.1", "gpt-4.1-2025-04-14"), ModelCapabilities(1047576, 32768, frozenset(), True, 2, .5, 8)),
    (("gpt-5.4", "gpt-5.4-2026-03-05"), ModelCapabilities(1050000, 128000, REASONING_EFFORTS, True, 2.5, .25, 15)),
    # Mini custom temperature is deliberately disabled until explicitly verified.
    (("gpt-5.4-mini", "gpt-5.4-mini-2026-03-17"), ModelCapabilities(400000, 128000, REASONING_EFFORTS, False, .75, .075, 4.5)),
]:
    for alias in aliases:
        MODEL_CAPABILITIES[alias] = capability
