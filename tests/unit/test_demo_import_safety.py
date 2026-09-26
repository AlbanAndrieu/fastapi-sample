"""Import-safety contracts for demo feature-flag bootstrap."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "nabla" / "api" / "demo" / "demo.py"
LIFESPAN = ROOT / "nabla" / "lifespan.py"


def test_demo_feature_flags_are_not_initialized_at_module_import() -> None:
    source = DEMO.read_text(encoding="utf-8")
    tree = ast.parse(source)

    top_level_feature_flag_calls = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        function_name = ast.unparse(node.value.func)
        if function_name == "FeatureFlags" or function_name.startswith("FeatureFlags."):
            top_level_feature_flag_calls.append(function_name)

    assert top_level_feature_flag_calls == []
    assert 'print("Enabled Features:"' not in source
    assert "def initialize_demo_feature_flags()" in source


def test_demo_feature_flag_initialization_is_owned_by_lifespan() -> None:
    source = LIFESPAN.read_text(encoding="utf-8")

    assert "initialize_demo_feature_flags()" in source
