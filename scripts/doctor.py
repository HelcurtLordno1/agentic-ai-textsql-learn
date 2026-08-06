"""Compatibility wrapper for the canonical CLI doctor command."""

from agentic_text2sql.interfaces.cli.app import app

if __name__ == "__main__":
    app(["doctor"])
