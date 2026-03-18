from __future__ import annotations

from app.contexts.themes.registry import (
    get_theme_definition,
    list_lens_definitions,
    list_theme_definitions,
    validate_registry,
)


def test_theme_registry_contains_energy_to_agri_inputs():
    definitions = list_theme_definitions()
    keys = [definition.key for definition in definitions]
    assert "energy_to_agri_inputs" in keys

    theme = get_theme_definition("energy_to_agri_inputs")
    assert theme.title == "Energy to Agri Inputs"
    assert set(theme.supported_cadences) == {"daily", "weekly"}

    lens_keys = [lens.key for lens in list_lens_definitions("energy_to_agri_inputs")]
    assert set(lens_keys) == {"input_cost_pass_through", "capacity_curtailment"}


def test_theme_registry_validation_passes():
    validate_registry()
