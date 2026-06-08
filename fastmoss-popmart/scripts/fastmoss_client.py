from __future__ import annotations

import copy
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_BASE_URL = "https://openapi.fastmoss.com"


class FastMossAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.payload = payload
        self.response = response


class FastMossClient:
    def __init__(
        self,
        client_secret: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: int = 60,
        sleep_seconds: float = 0.25,
        max_retries: int = 3,
    ) -> None:
        self.client_secret = client_secret or os.environ.get("FASTMOSS_CLIENT_SECRET")
        if not self.client_secret:
            raise FastMossAPIError(
                "Missing FASTMOSS_CLIENT_SECRET. Add it to .env or export it before running."
            )

        self.base_url = (base_url or os.environ.get("FASTMOSS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.sleep_seconds = sleep_seconds
        self.max_retries = max_retries

    def post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.client_secret}",
            "Content-Type": "application/json",
            "User-Agent": "popmart-fastmoss-daily-tracker/1.0",
        }

        last_error: Optional[FastMossAPIError] = None
        for attempt in range(self.max_retries):
            if attempt:
                time.sleep(min(8.0, (2 ** attempt) + self.sleep_seconds))

            request = urllib.request.Request(url, data=encoded, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                    status = response.status
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                status = exc.code
                parsed_error = _parse_json(body)
                error = FastMossAPIError(
                    f"FastMoss HTTP {status}: {parsed_error.get('msg') or parsed_error.get('message') or body[:200]}",
                    status=status,
                    code=parsed_error.get("code"),
                    payload=payload,
                    response=parsed_error,
                )
                if status in (429, 500, 502, 503, 504):
                    last_error = error
                    continue
                raise error
            except urllib.error.URLError as exc:
                last_error = FastMossAPIError(f"FastMoss request failed: {exc}", payload=payload)
                continue

            parsed = _parse_json(body)
            api_code = parsed.get("code")
            if api_code in (0, "0"):
                time.sleep(self.sleep_seconds)
                return parsed

            error = FastMossAPIError(
                str(parsed.get("msg") or parsed.get("message") or f"FastMoss API error code {api_code}"),
                status=status,
                code=api_code,
                payload=payload,
                response=parsed,
            )
            if api_code in (30003, "30003"):
                last_error = error
                continue
            raise error

        if last_error:
            raise last_error
        raise FastMossAPIError("FastMoss request failed after retries.", payload=payload)

    def paged_post(
        self,
        path: str,
        payload: Dict[str, Any],
        *,
        pagesize: int,
        max_pages: int,
    ) -> Iterable[Dict[str, Any]]:
        for page in range(1, max_pages + 1):
            page_payload = copy.deepcopy(payload)
            page_payload["page"] = page
            page_payload["pagesize"] = pagesize
            response = self.post(path, page_payload)
            data = response.get("data") or {}
            items = data.get("list") or []
            for item in items:
                yield item

            total = _safe_int(data.get("total"))
            has_more = data.get("has_more")
            if not items:
                break
            if has_more is False or has_more == 0:
                break
            if total and page * pagesize >= total:
                break


def _parse_json(body: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise FastMossAPIError(f"FastMoss returned non-JSON response: {body[:200]}") from exc
    if not isinstance(parsed, dict):
        raise FastMossAPIError(f"FastMoss returned unexpected response: {body[:200]}")
    return parsed


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0

