# Troubleshooting

- In WSL, use the configured `OLLAMA_BASE_URL`; do not assume `127.0.0.1` reaches Windows Ollama.
- If `uv` hardlinking warns on `/mnt/d`, use `UV_LINK_MODE=copy` or place the cache on the same FS.
- Run `uv run text2sql doctor --json` for non-secret path/model diagnostics.

