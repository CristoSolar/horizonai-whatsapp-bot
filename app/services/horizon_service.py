"""Wrapper around Horizon's REST API."""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urljoin

from ..extensions import HorizonExtension


class HorizonService:
    def __init__(self, extension: HorizonExtension) -> None:
        self._extension = extension

    def execute_action(
        self,
        *,
        action_name: str,
        defined_actions: Iterable[Dict[str, Any]],
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        definition = next(
            (action for action in defined_actions if action.get("name") == action_name), None
        )
        if not definition:
            raise ValueError(f"Action '{action_name}' is not defined for this bot")

        method = (definition.get("method") or "GET").upper()
        path_template = definition.get("path") or "/"
        path = path_template.format(**arguments)

        query_params = definition.get("query")
        body_template = definition.get("body")

        json_body: Optional[Dict[str, Any]] = None
        if body_template:
            json_body = json.loads(json.dumps(body_template).format(**arguments))

        response = self.request(
            method=method,
            path=path,
            params=query_params,
            json_body=json_body,
        )
        return response

    def request(
        self,
        *,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: int = 15,
    ) -> Dict[str, Any]:
        session = self._extension.session
        base_url = self._extension.base_url
        url = urljoin(base_url, path)
        response = session.request(method=method, url=url, params=params, json=json_body, timeout=timeout)
        response.raise_for_status()
        if response.content:
            try:
                return response.json()
            except ValueError:
                return {"raw": response.text}
        return {}
