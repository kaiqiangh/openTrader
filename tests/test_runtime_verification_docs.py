from pathlib import Path


def test_runtime_verification_doc_exists() -> None:
    assert Path("docs/runtime/runtime-verification-2026-02-14.md").exists()
