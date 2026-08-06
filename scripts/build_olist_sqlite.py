"""Thin wrapper for the canonical Olist CLI build command."""

from agentic_text2sql.interfaces.cli.app import app

if __name__ == "__main__":
    app(["data", "build", "olist"])
