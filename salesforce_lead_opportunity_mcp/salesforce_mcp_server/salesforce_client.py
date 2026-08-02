"""Safe Salesforce query client for Lead and Opportunity only."""

import os
import re
from collections.abc import Mapping
from typing import Any

import httpx

from .salesforce_auth import get_salesforce_session
from .schema import OBJECT_FIELDS


SALESFORCE_API_VERSION = os.environ.get(
    "SALESFORCE_API_VERSION",
    "v60.0",
).strip()

_ID_PATTERN = re.compile(r"^[a-zA-Z0-9]{15}(?:[a-zA-Z0-9]{3})?$")
_ORDER_DIRECTIONS = {"ASC", "DESC"}
_MAX_PAGE_SIZE = 2000
_DEFAULT_MAX_RECORDS = 5000
_HARD_MAX_RECORDS = int(os.environ.get("SALESFORCE_MAX_RECORDS", "10000"))


def _escape_soql_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _extract(record: Mapping[str, Any], field_path: str) -> Any:
    value: Any = record
    for part in field_path.split("."):
        if value is None or not isinstance(value, Mapping):
            return None
        value = value.get(part)
    return value


def _parse_record(object_name: str, record: Mapping[str, Any]) -> dict[str, Any]:
    field_map = OBJECT_FIELDS[object_name]
    return {
        clean_name: _extract(record, api_path)
        for clean_name, api_path in field_map.items()
    }


def _validate_object_name(object_name: str) -> str:
    normalized = object_name.strip().lower()
    lookup = {"lead": "Lead", "opportunity": "Opportunity"}
    if normalized not in lookup:
        raise ValueError("Only Lead and Opportunity are allowed.")
    return lookup[normalized]


def _select_clause(object_name: str) -> str:
    return ", ".join(dict.fromkeys(OBJECT_FIELDS[object_name].values()))


def _validated_limit(limit: int) -> int:
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    return min(limit, _HARD_MAX_RECORDS)


async def _request_json(
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    retry_auth: bool = True,
) -> dict[str, Any]:
    access_token, _ = await get_salesforce_session()

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.request(
            method,
            url,
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.status_code == 401 and retry_auth:
        access_token, _ = await get_salesforce_session(force_refresh=True)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method,
                url,
                params=params,
                headers={"Authorization": f"Bearer {access_token}"},
            )

    if response.is_error:
        raise RuntimeError(
            f"Salesforce API request failed ({response.status_code}): "
            f"{response.text}"
        )

    return response.json()


async def run_soql(soql: str, max_records: int = _DEFAULT_MAX_RECORDS) -> list[dict]:
    """Execute an internally-built SOQL query and follow nextRecordsUrl."""
    max_records = _validated_limit(max_records)
    _, instance_url = await get_salesforce_session()
    query_url = (
        f"{instance_url}/services/data/"
        f"{SALESFORCE_API_VERSION}/query"
    )

    payload = await _request_json("GET", query_url, params={"q": soql})
    records = list(payload.get("records", []))

    while not payload.get("done", True) and len(records) < max_records:
        next_url = payload.get("nextRecordsUrl")
        if not next_url:
            break
        payload = await _request_json("GET", f"{instance_url}{next_url}")
        records.extend(payload.get("records", []))

    return records[:max_records]


async def fetch_records(
    object_name: str,
    *,
    limit: int = 100,
    order_by: str = "CreatedDate",
    order_direction: str = "DESC",
    modified_since: str | None = None,
) -> dict[str, Any]:
    """Fetch records from an allowlisted Salesforce object."""
    object_name = _validate_object_name(object_name)
    limit = _validated_limit(limit)

    allowed_api_fields = set(OBJECT_FIELDS[object_name].values())
    if order_by not in allowed_api_fields:
        raise ValueError(
            f"order_by must be one of: {sorted(allowed_api_fields)}"
        )

    direction = order_direction.strip().upper()
    if direction not in _ORDER_DIRECTIONS:
        raise ValueError("order_direction must be ASC or DESC.")

    where_parts: list[str] = []
    if modified_since:
        # Expected Salesforce UTC datetime format, e.g. 2026-07-01T00:00:00Z.
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z",
            modified_since,
        ):
            raise ValueError(
                "modified_since must be UTC ISO format, "
                "for example 2026-07-01T00:00:00Z."
            )
        where_parts.append(f"LastModifiedDate >= {modified_since}")

    where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    soql = (
        f"SELECT {_select_clause(object_name)} "
        f"FROM {object_name}"
        f"{where_clause} "
        f"ORDER BY {order_by} {direction} "
        f"LIMIT {limit}"
    )

    records = await run_soql(soql, max_records=limit)
    return {
        "object": object_name,
        "count": len(records),
        "records": [_parse_record(object_name, r) for r in records],
    }


async def fetch_record_by_id(object_name: str, record_id: str) -> dict[str, Any]:
    """Fetch one Lead or Opportunity by Salesforce record Id."""
    object_name = _validate_object_name(object_name)
    record_id = record_id.strip()

    if not _ID_PATTERN.fullmatch(record_id):
        raise ValueError("record_id must be a 15- or 18-character Salesforce Id.")

    soql = (
        f"SELECT {_select_clause(object_name)} "
        f"FROM {object_name} "
        f"WHERE Id = '{_escape_soql_string(record_id)}' "
        "LIMIT 1"
    )
    records = await run_soql(soql, max_records=1)
    return {
        "object": object_name,
        "record": _parse_record(object_name, records[0]) if records else None,
    }


async def fetch_opportunities_for_lead(
    converted_opportunity_id: str,
) -> dict[str, Any]:
    """Resolve a Lead's standard ConvertedOpportunityId to an Opportunity."""
    result = await fetch_record_by_id(
        "Opportunity",
        converted_opportunity_id,
    )
    return {
        "converted_opportunity_id": converted_opportunity_id,
        "opportunity": result["record"],
    }
