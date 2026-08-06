import tomllib
from pathlib import Path


def test_core_has_no_paid_provider_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = " ".join(config["project"]["dependencies"]).lower()
    assert "openai" not in dependencies
    assert "anthropic" not in dependencies
    assert "google" not in dependencies


def test_runtime_does_not_import_gold_aware_package() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "agentic_text2sql"
    imports = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))
    assert "import agentic_text2sql_eval" not in imports
    assert "from agentic_text2sql_eval" not in imports
