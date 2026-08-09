"""Create the deterministic, gold-blind-at-runtime Spider mini-100 ID manifest."""

from pathlib import Path

from agentic_text2sql_eval.spider_adapter import create_manifest

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    dev = ROOT / "data/raw/spider/spider_data/dev.json"
    mini = create_manifest(dev)
    mini_output = ROOT / "evals/configs/spider-mini-100.json"
    mini_output.write_text(mini.model_dump_json(indent=2) + "\n", encoding="utf-8")
    holdout = create_manifest(
        dev, excluded_indices=frozenset(case.dev_index for case in mini.cases)
    )
    holdout_output = ROOT / "evals/configs/spider-holdout-100.json"
    holdout_output.write_text(holdout.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {mini_output} and {holdout_output}")


if __name__ == "__main__":
    main()
