"""StateBook Atlas API client.

Owns authentication, timeouts, bounded retries, error translation, and raw-response
capture. It knows nothing about retail metrics or scoring; it returns Atlas payloads and
the :class:`RawCall` records that make every downstream number traceable.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Iterable

import httpx

from core.config import Settings, get_settings
from core.logging import get_logger, log_event, redact
from models.evidence import RawCall

logger = get_logger("api.client")

GETDATA_PATH = "/api/v1/getdata"

# Only these are worth a retry. A 4xx means the request itself is wrong, so retrying it
# just burns the caller's rate limit.
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class AtlasError(RuntimeError):
    """Base class for every Atlas failure surfaced to the orchestration layer."""

    def __init__(self, message: str, *, call: RawCall | None = None) -> None:
        super().__init__(message)
        self.call = call


class AtlasHTTPError(AtlasError):
    def __init__(self, message: str, *, status_code: int, call: RawCall | None = None) -> None:
        super().__init__(message, call=call)
        self.status_code = status_code


class AtlasTimeoutError(AtlasError):
    pass


class AtlasResponseError(AtlasError):
    """Atlas answered with HTTP 200 but the body carried an ``error`` object."""


class AtlasClient:
    """Thin, typed wrapper over the Atlas REST surface."""

    def __init__(
        self,
        settings: Settings | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        # Fail fast and loudly if no token is configured, before any network work.
        self._token = self._settings.require_token()
        self._client = httpx.Client(
            base_url=self._settings.atlas_base_url,
            timeout=httpx.Timeout(self._settings.timeout_seconds),
            transport=transport,
            headers={"User-Agent": "retail-location-intelligence/0.1"},
        )
        self.calls: list[RawCall] = []

    def __enter__(self) -> AtlasClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_data(
        self,
        datapoints: Iterable[str],
        geographies: Iterable[str],
        *,
        periods: list[str] | None = None,
        include_metadata: bool = True,
    ) -> tuple[dict[str, Any], RawCall]:
        """Fetch datapoints for one or more geographies.

        Returns the parsed body alongside the recorded call so callers can cite it.
        """
        datapoint_list = list(datapoints)
        geography_list = list(geographies)
        if not datapoint_list:
            raise ValueError("At least one datapoint is required")
        if not geography_list:
            raise ValueError("At least one geography is required")

        data: dict[str, Any] = {"datapoints": datapoint_list}
        if periods:
            data["scope"] = {"periods": periods}

        criteria: dict[str, Any] = (
            {"geography": geography_list[0]}
            if len(geography_list) == 1
            else {"geographies": geography_list}
        )

        body: dict[str, Any] = {"data": data, "criteria": criteria}
        if include_metadata:
            body["options"] = {"includeMetadata": True, "outputFormat": "raw"}

        return self._post(GETDATA_PATH, body)

    def get_collection(
        self,
        collection: str,
        datapoints: Iterable[str],
        geographies: Iterable[str],
        *,
        item_datapoint: str | None = None,
        item_codes: list[str] | None = None,
        include_metadata: bool = True,
    ) -> tuple[dict[str, Any], RawCall]:
        """Fetch a collection (code-broken-out or point-level data) for geographies.

        ``item_codes`` narrows the collection via Atlas scope filtering, which matters
        because an unfiltered industry collection returns every NAICS code.
        """
        datapoint_list = list(datapoints)
        geography_list = list(geographies)
        if not datapoint_list:
            raise ValueError("At least one collection datapoint is required")
        if not geography_list:
            raise ValueError("At least one geography is required")

        collection_spec: dict[str, Any] = {
            "collection": collection,
            "datapoints": datapoint_list,
        }
        if item_codes and item_datapoint:
            collection_spec["scope"] = {"datapoints": {item_datapoint: list(item_codes)}}

        criteria: dict[str, Any] = (
            {"geography": geography_list[0]}
            if len(geography_list) == 1
            else {"geographies": geography_list}
        )

        body: dict[str, Any] = {
            "data": {"collections": [collection_spec]},
            "criteria": criteria,
        }
        if include_metadata:
            body["options"] = {"includeMetadata": True, "outputFormat": "raw"}

        return self._post(GETDATA_PATH, body)

    def _post(self, path: str, body: dict[str, Any]) -> tuple[dict[str, Any], RawCall]:
        call_id = uuid.uuid4().hex[:12]
        url = f"{self._settings.atlas_base_url}{path}"
        # The token lives only in this header dict; the persisted RawCall never sees it.
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

        started = time.perf_counter()
        attempts = 0
        last_error: str | None = None
        status_code: int | None = None
        response_body: dict[str, Any] | None = None

        for attempt in range(self._settings.max_retries + 1):
            attempts = attempt + 1
            try:
                response = self._client.post(path, json=body, headers=headers)
                status_code = response.status_code

                if status_code in _RETRYABLE_STATUS and attempt < self._settings.max_retries:
                    last_error = f"HTTP {status_code}"
                    self._backoff(attempt)
                    continue

                try:
                    response_body = response.json()
                except ValueError:
                    response_body = None
                    last_error = f"Atlas returned non-JSON body (HTTP {status_code})"
                    break

                if status_code >= 400:
                    last_error = _extract_error_message(response_body) or f"HTTP {status_code}"
                    break

                last_error = None
                break

            except httpx.TimeoutException as exc:
                last_error = f"timeout after {self._settings.timeout_seconds}s"
                if attempt < self._settings.max_retries:
                    self._backoff(attempt)
                    continue
                call = self._record(call_id, url, body, None, None, started, attempts, last_error)
                raise AtlasTimeoutError(
                    f"Atlas request timed out after {attempts} attempt(s).", call=call
                ) from exc
            except httpx.HTTPError as exc:
                last_error = f"transport error: {type(exc).__name__}"
                if attempt < self._settings.max_retries:
                    self._backoff(attempt)
                    continue
                call = self._record(call_id, url, body, None, None, started, attempts, last_error)
                raise AtlasError(
                    f"Could not reach Atlas after {attempts} attempt(s): {type(exc).__name__}",
                    call=call,
                ) from exc

        call = self._record(
            call_id, url, body, response_body, status_code, started, attempts, last_error
        )

        if last_error is not None:
            if status_code is not None and status_code >= 400:
                if status_code in (401, 403):
                    raise AtlasHTTPError(
                        "Atlas rejected the credentials or the requested geography is not "
                        f"licensed for this token ({last_error}).",
                        status_code=status_code,
                        call=call,
                    )
                raise AtlasHTTPError(
                    f"Atlas request failed: {last_error}", status_code=status_code, call=call
                )
            raise AtlasError(f"Atlas request failed: {last_error}", call=call)

        if response_body is None:
            raise AtlasError("Atlas returned an empty body.", call=call)

        # Atlas can report failures inside a 200 response.
        if isinstance(response_body.get("error"), dict):
            raise AtlasResponseError(
                f"Atlas reported an error: {_extract_error_message(response_body)}", call=call
            )

        if "resultset" not in response_body:
            raise AtlasResponseError("Atlas response is missing the 'resultset' key.", call=call)

        return response_body, call

    def _backoff(self, attempt: int) -> None:
        time.sleep(min(0.5 * (2**attempt), 4.0))

    def _record(
        self,
        call_id: str,
        url: str,
        request_body: dict[str, Any],
        response_body: dict[str, Any] | None,
        status_code: int | None,
        started: float,
        attempts: int,
        error: str | None,
    ) -> RawCall:
        call = RawCall(
            call_id=call_id,
            method="POST",
            url=url,
            request_body=redact(request_body),
            response_body=redact(response_body) if response_body is not None else None,
            status_code=status_code,
            elapsed_seconds=round(time.perf_counter() - started, 4),
            attempts=attempts,
            error=error,
        )
        self.calls.append(call)
        log_event(
            logger,
            logging.INFO if error is None else logging.WARNING,
            "atlas_call",
            call_id=call_id,
            url=url,
            status_code=status_code,
            attempts=attempts,
            elapsed_seconds=call.elapsed_seconds,
            datapoint_count=len(request_body.get("data", {}).get("datapoints", [])),
            error=error,
        )
        return call


def _extract_error_message(body: dict[str, Any] | None) -> str | None:
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        code = error.get("code")
        if message:
            return f"{message} (code={code})" if code else str(message)
    return None
