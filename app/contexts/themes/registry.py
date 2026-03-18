from __future__ import annotations

from .contracts import LensDefinition, ThemeDefinition
from .definitions import THEME_DEFINITIONS


_THEME_BY_KEY: dict[str, ThemeDefinition] = {definition.key: definition for definition in THEME_DEFINITIONS}
_LENS_BY_KEY: dict[str, LensDefinition] = {
    lens.key: lens
    for definition in THEME_DEFINITIONS
    for lens in definition.lenses
}


def list_theme_definitions() -> tuple[ThemeDefinition, ...]:
    return tuple(sorted(THEME_DEFINITIONS, key=lambda d: d.key))


def get_theme_definition(theme_key: str) -> ThemeDefinition:
    definition = _THEME_BY_KEY.get(theme_key)
    if definition is None:
        raise ValueError(f"unknown theme_key: {theme_key}")
    return definition


def list_lens_definitions(theme_key: str) -> tuple[LensDefinition, ...]:
    definition = get_theme_definition(theme_key)
    return tuple(sorted(definition.lenses, key=lambda lens: lens.key))


def get_lens_definition(lens_key: str) -> LensDefinition:
    lens = _LENS_BY_KEY.get(lens_key)
    if lens is None:
        raise ValueError(f"unknown lens_key: {lens_key}")
    return lens


def validate_registry() -> None:
    if not _THEME_BY_KEY:
        raise ValueError("theme registry is empty")
    for definition in _THEME_BY_KEY.values():
        if not definition.supported_cadences:
            raise ValueError(f"theme has no supported cadences: {definition.key}")
        if not definition.lenses:
            raise ValueError(f"theme has no lenses: {definition.key}")
        lens_keys = {lens.key for lens in definition.lenses}
        if len(lens_keys) != len(definition.lenses):
            raise ValueError(f"theme has duplicate lens keys: {definition.key}")
