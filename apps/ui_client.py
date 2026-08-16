"""Small typed-ish HTTP client used by Streamlit; it has no database access."""

from __future__ import annotations

import os
from typing import Any, cast

import httpx


class LocalAPIClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        resolved = base_url or os.environ.get("TEXT2SQL_API_URL") or "http://127.0.0.1:8000"
        self.base_url = resolved.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self.client.close()

    def health(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/health"))

    def models(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", "/models"))

    def catalogs(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/catalogs"))

    def ingest(self, dataset: str) -> dict[str, Any]:
        return cast(
            dict[str, Any], self._request("POST", "/catalogs/ingest", json={"dataset": dataset})
        )

    def submit(self, db_id: str, question: str, correction_enabled: bool) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/queries",
                json={
                    "db_id": db_id,
                    "question": question,
                    "correction_enabled": correction_enabled,
                },
            ),
        )

    def run(self, run_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", f"/queries/{run_id}"))

    def runs(self, search: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, str | bool] = {"include_result": False}
        if search:
            params["search"] = search
        return cast(list[dict[str, Any]], self._request("GET", "/queries", params=params))

    def events(self, run_id: str) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", f"/queries/{run_id}/trace"))

    def feedback(
        self, run_id: str, rating: str, categories: list[str], note: str | None
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self._request(
                "POST",
                "/feedback",
                json={
                    "run_id": run_id,
                    "rating": rating,
                    "categories": categories,
                    "note": note,
                },
            ),
        )

    def reports(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/reports"))

    def report(self, report_id: str) -> dict[str, Any]:
        return cast(dict[str, Any], self._request("GET", f"/reports/{report_id}"))
