"""Create the pinned Gate P6 laptop-stratified Spider-200 manifest."""

from pathlib import Path

from agentic_text2sql_eval.spider_release import create_laptop_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    manifest = create_laptop_manifest(
        ROOT / "data/raw/spider/spider_data",
        ROOT / "evals/configs/spider-mini-100.json",
        ROOT / "evals/configs/spider-holdout-100.json",
    )
    output = ROOT / "evals/configs/spider-laptop-200.json"
    output.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"manifest={output} cases={manifest.case_count} "
        f"databases={manifest.database_count} profile={manifest.benchmark_profile}"
    )


if __name__ == "__main__":
    main()
