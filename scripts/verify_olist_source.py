"""Verify an already-downloaded Olist archive and raw CSV set."""

from agentic_text2sql.data.olist import (
    default_olist_paths,
    extract_and_verify_source,
    load_source_manifest,
)


def main() -> None:
    paths = default_olist_paths()
    manifest = load_source_manifest(paths["manifest"])
    result = extract_and_verify_source(paths["archive"], paths["raw_dir"], manifest)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
