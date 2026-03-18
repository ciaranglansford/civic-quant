from __future__ import annotations

from ..themes.contracts import TransmissionPattern


TRANSMISSION_PATTERN_LIBRARY: tuple[TransmissionPattern, ...] = (
    "input_cost_pass_through",
    "supply_tightening",
    "capacity_curtailment",
    "trade_flow_rerouting",
    "substitution_effect",
    "margin_compression_expansion",
    "geographic_bottleneck",
)


def list_transmission_patterns() -> tuple[TransmissionPattern, ...]:
    return TRANSMISSION_PATTERN_LIBRARY
