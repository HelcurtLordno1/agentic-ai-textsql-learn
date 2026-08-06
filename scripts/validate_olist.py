"""Thin wrapper for the canonical Olist CLI validation command."""

from agentic_text2sql.interfaces.cli.app import app

if __name__ == "__main__":
    app(["data", "validate", "olist"])
