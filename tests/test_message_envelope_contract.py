from pathlib import Path
import json
import importlib.util
from types import ModuleType

import pytest


def _load_validator_module() -> ModuleType:
    module_path = Path("services/shared/contracts/message_envelope.py")
    spec = importlib.util.spec_from_file_location("message_envelope", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_message_envelope_schema_exists() -> None:
    assert Path("config/contracts/message_envelope.schema.json").exists()


def test_message_envelope_schema_has_required_fields() -> None:
    payload = json.loads(
        Path("config/contracts/message_envelope.schema.json").read_text(encoding="utf-8")
    )
    required = set(payload["required"])
    assert "trace_id" in required
    assert "decision_id" in required
    assert "mode" in required
    assert "idempotency_key" in required
    assert "event_type" in required
    assert "emitted_at" in required
    assert "payload" in required


def test_message_envelope_validator_accepts_valid_envelope() -> None:
    module = _load_validator_module()
    envelope = {
        "trace_id": "74b14924-e94d-4db4-8fd9-7e5d53f0f787",
        "decision_id": "59c1c8ec-fde1-4950-919f-6d4dc7ca9124",
        "mode": "MOCK",
        "idempotency_key": "execution.intent.mock:74b14924-e94d-4db4-8fd9-7e5d53f0f787",
        "event_type": "execution.intent.created",
        "emitted_at": "2026-02-14T12:10:00Z",
        "payload": {"symbol": "BTC/USDT", "action": "BUY"},
    }

    module.validate_envelope(envelope)


def test_message_envelope_validator_rejects_missing_idempotency_key() -> None:
    module = _load_validator_module()
    envelope = {
        "trace_id": "74b14924-e94d-4db4-8fd9-7e5d53f0f787",
        "decision_id": "59c1c8ec-fde1-4950-919f-6d4dc7ca9124",
        "mode": "REAL",
        "event_type": "execution.intent.created",
        "emitted_at": "2026-02-14T12:10:00Z",
        "payload": {"symbol": "BTC/USDT", "action": "SELL"},
    }

    with pytest.raises(module.EnvelopeValidationError):
        module.validate_envelope(envelope)


def test_message_envelope_validator_rejects_unknown_mode() -> None:
    module = _load_validator_module()
    envelope = {
        "trace_id": "74b14924-e94d-4db4-8fd9-7e5d53f0f787",
        "decision_id": "59c1c8ec-fde1-4950-919f-6d4dc7ca9124",
        "mode": "PAPER",
        "idempotency_key": "execution.intent.real:74b14924-e94d-4db4-8fd9-7e5d53f0f787",
        "event_type": "execution.intent.created",
        "emitted_at": "2026-02-14T12:10:00Z",
        "payload": {"symbol": "BTC/USDT", "action": "SELL"},
    }

    with pytest.raises(module.EnvelopeValidationError):
        module.validate_envelope(envelope)
