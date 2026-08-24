from __future__ import annotations

import pytest
from battle_engine.rules import BYTEFRAY_RULESET_ID
from battle_engine.ruleset_policy import BYTEFRAY_RULESET_V2_ID

from app.services.ruleset_options import (
    DESIGNER_RULESET_OPTIONS,
    best_designer_ruleset,
    ruleset_supports_runtime_kinds,
    validate_designer_ruleset,
)


def test_product_options_are_permanent_ids_in_preference_order() -> None:
    assert [option.ruleset_id for option in DESIGNER_RULESET_OPTIONS] == [
        BYTEFRAY_RULESET_V2_ID,
        BYTEFRAY_RULESET_ID,
    ]
    assert all("alpha" not in option.ruleset_id for option in DESIGNER_RULESET_OPTIONS)


def test_python_composition_prefers_v2_and_vm_composition_prefers_v1() -> None:
    assert best_designer_ruleset({"python"}) == BYTEFRAY_RULESET_V2_ID
    assert best_designer_ruleset({"vm"}) == BYTEFRAY_RULESET_ID
    assert ruleset_supports_runtime_kinds(BYTEFRAY_RULESET_V2_ID, {"python"})
    assert not ruleset_supports_runtime_kinds(BYTEFRAY_RULESET_V2_ID, {"vm"})


def test_programmatic_v2_vm_launch_is_rejected_before_spawn() -> None:
    with pytest.raises(ValueError, match="Use Ruleset v1 for VM/blob matches"):
        validate_designer_ruleset(BYTEFRAY_RULESET_V2_ID, {"vm"})

    validate_designer_ruleset(BYTEFRAY_RULESET_V2_ID, {"python"})
    validate_designer_ruleset(BYTEFRAY_RULESET_ID, {"vm"})
