from pathlib import Path

from agentic_text2sql.doctor import CheckStatus, run_doctor
from agentic_text2sql.settings import Settings


class FakeProvider:
    def version(self) -> str:
        return "test-version"

    def list_models(self) -> list[dict[str, str]]:
        return [{"name": "qwen3:14b-q4_K_M"}]


def test_doctor_passes_with_fake_local_provider(tmp_path: Path) -> None:
    settings = Settings(PROJECT_ROOT=tmp_path, TEXT2SQL_DATA_DIR=tmp_path / "data")
    report = run_doctor(settings, provider=FakeProvider())  # type: ignore[arg-type]
    by_name = {check.name: check for check in report.checks}
    assert report.passed
    assert by_name["ollama"].status is CheckStatus.PASS
    assert by_name["model"].status is CheckStatus.PASS
    assert "free_gib=" in by_name["disk"].detail
