from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
import sys


def _load_module(path: Path, *, module_name: str) -> ModuleType:
    spec = spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_workflow_normalizes_deepseek_model_for_direct_endpoint() -> None:
    module = _load_module(
        Path("scripts/mock_realtime_workflow_test.py"),
        module_name="mock_realtime_workflow_test_module",
    )
    normalized = module._normalize_litellm_model(  # type: ignore[attr-defined]
        base_url="https://api.deepseek.com",
        model="deepseek/deepseek-chat",
    )
    assert normalized == "deepseek-chat"

    unchanged = module._normalize_litellm_model(  # type: ignore[attr-defined]
        base_url="http://litellm:4000",
        model="deepseek/deepseek-chat",
    )
    assert unchanged == "deepseek/deepseek-chat"


def test_env_validator_flags_direct_deepseek_model_prefix_mismatch() -> None:
    module = _load_module(Path("scripts/validate_env.py"), module_name="validate_env_module")
    error = module._validate_litellm_model_binding(  # type: ignore[attr-defined]
        base_url="https://api.deepseek.com",
        model="deepseek/deepseek-chat",
    )
    assert error is not None
    assert "deepseek-chat" in error

    ok = module._validate_litellm_model_binding(  # type: ignore[attr-defined]
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )
    assert ok is None
