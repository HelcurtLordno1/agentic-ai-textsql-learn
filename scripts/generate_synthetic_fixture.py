"""Thin wrapper around the canonical deterministic fixture generator."""

from pathlib import Path

from datasets.synthetic_commerce.generator import build_database


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "data" / "samples" / "synthetic_commerce_tiny.sqlite"
    seed = root / "datasets" / "synthetic_commerce" / "seed.yaml"
    digest = build_database(output, seed)
    print(f"built={output} logical_sha256={digest}")


if __name__ == "__main__":
    main()
