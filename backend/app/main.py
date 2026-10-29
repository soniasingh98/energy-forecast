from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


ELEXON_API = "https://data.elexon.co.uk/bmrs/api/v1"
UK_TIME = ZoneInfo("Europe/London")
JANUARY_2026 = (date(2026, 1, 1), date(2026, 1, 31))
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Wind Market Desk API",
    description="Day-ahead UK wind forecast analysis using Elexon BMRS data.",
    version="1.0.0",
)
frontend_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "https://energy-forecast-umyx.vercel.app,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _parse_utc(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def aggregate_actuals(records: list[dict[str, Any]]) -> dict[datetime, float]:
    """Average FUELHH half-hour values into the hourly forecast resolution."""
    grouped: dict[datetime, list[float]] = defaultdict(list)
    for record in records:
        start = _parse_utc(record.get("startTime"))
        generation = record.get("generation")
        if start is None or generation is None:
            continue
        try:
            value = float(generation)
        except (TypeError, ValueError):
            continue
        hour = start.replace(minute=0, second=0, microsecond=0)
        grouped[hour].append(value)
    return {hour: sum(values) / len(values) for hour, values in grouped.items()}


def select_forecast_snapshot(
    records: list[dict[str, Any]],
    delivery_date: date,
    cutoff: datetime,
) -> tuple[datetime | None, dict[datetime, float]]:
    snapshots: dict[datetime, dict[datetime, float]] = defaultdict(dict)
    target_start = datetime.combine(delivery_date, time.min, tzinfo=timezone.utc)
    target_end = target_start + timedelta(days=1)

    for record in records:
        published = _parse_utc(record.get("publishTime"))
        start = _parse_utc(record.get("startTime"))
        generation = record.get("generation")
        if published is None or start is None or generation is None:
            continue
        if published > cutoff or not target_start <= start < target_end:
            continue
        try:
            snapshots[published][start] = float(generation)
        except (TypeError, ValueError):
            continue

    if not snapshots:
        return None, {}

    complete_snapshots = [
        published
        for published, values in snapshots.items()
        if len(values) == 24
    ]
    published = max(complete_snapshots or list(snapshots))
    return published, snapshots[published]


def calculate_metrics(
    series: list[dict[str, Any]],
) -> dict[str, float | int | None]:
    matched = [
        row
        for row in series
        if row["actual_mw"] is not None and row["forecast_mw"] is not None
    ]
    if not matched:
        return {
            "matched_intervals": 0,
            "mae_mw": None,
            "rmse_mw": None,
            "bias_mw": None,
            "wape_percent": None,
        }

    errors = [
        row["forecast_mw"] - row["actual_mw"] for row in matched
    ]
    absolute_error = sum(abs(error) for error in errors)
    actual_total = sum(abs(row["actual_mw"]) for row in matched)
    return {
        "matched_intervals": len(matched),
        "mae_mw": absolute_error / len(matched),
        "rmse_mw": (sum(error**2 for error in errors) / len(errors)) ** 0.5,
        "bias_mw": sum(errors) / len(errors),
        "wape_percent": (
            100 * absolute_error / actual_total if actual_total else None
        ),
    }


async def fetch_dataset(
    client: httpx.AsyncClient, dataset: str, params: dict[str, str]
) -> list[dict[str, Any]]:
    url = f"{ELEXON_API}/datasets/{dataset}/stream"
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Elexon returned HTTP {exc.response.status_code} for {dataset}.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach the Elexon {dataset} data service.",
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Elexon returned invalid JSON for {dataset}.",
        ) from exc

    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        payload = payload["data"]
    if not isinstance(payload, list):
        raise HTTPException(
            status_code=502,
            detail=f"Elexon returned an unexpected response for {dataset}.",
        )
    return [record for record in payload if isinstance(record, dict)]


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/analysis")
async def analysis(
    delivery_date: date = Query(..., description="Delivery date in January 2026."),
    cutoff_time: time = Query(
        default=time(11, 0), description="UK local day-ahead forecast cutoff."
    ),
) -> dict[str, Any]:
    if not JANUARY_2026[0] <= delivery_date <= JANUARY_2026[1]:
        raise HTTPException(
            status_code=400,
            detail="This pilot is scoped to delivery dates in January 2026.",
        )
    if cutoff_time.tzinfo is not None:
        raise HTTPException(
            status_code=400,
            detail="cutoff_time must be a UK local time without a timezone.",
        )

    previous_day = delivery_date - timedelta(days=1)
    cutoff_local = datetime.combine(previous_day, cutoff_time, tzinfo=UK_TIME)
    publish_from = datetime.combine(previous_day, time.min, tzinfo=UK_TIME)
    cutoff_utc = cutoff_local.astimezone(timezone.utc)
    request_timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=request_timeout) as client:
        actuals, forecasts = await asyncio.gather(
            fetch_dataset(
                client,
                "FUELHH",
                {
                    "settlementDateFrom": delivery_date.isoformat(),
                    "settlementDateTo": delivery_date.isoformat(),
                    "fuelType": "WIND",
                },
            ),
            fetch_dataset(
                client,
                "WINDFOR",
                {
                    "publishDateTimeFrom": _to_utc_iso(publish_from),
                    "publishDateTimeTo": _to_utc_iso(cutoff_utc),
                },
            ),
        )

    actual_by_hour = aggregate_actuals(actuals)
    latest_publish, forecast_by_hour = select_forecast_snapshot(
        forecasts, delivery_date, cutoff_utc
    )

    day_start = datetime.combine(delivery_date, time.min, tzinfo=timezone.utc)
    series = []
    for hour_index in range(24):
        start = day_start + timedelta(hours=hour_index)
        actual_mw = actual_by_hour.get(start)
        forecast_mw = forecast_by_hour.get(start)
        series.append(
            {
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "forecast_mw": forecast_mw,
                "actual_mw": actual_mw,
            }
        )

    return {
        "delivery_date": delivery_date.isoformat(),
        "forecast_cutoff": cutoff_local.isoformat(),
        "latest_publish_time": (
            latest_publish.isoformat().replace("+00:00", "Z")
            if latest_publish
            else None
        ),
        "forecast_intervals": len(forecast_by_hour),
        "actual_intervals": sum(row["actual_mw"] is not None for row in series),
        "actual_source_intervals": len(actuals),
        "resolution": "Hourly; each actual is the mean of available FUELHH half-hours.",
        "metrics": calculate_metrics(series),
        "series": series,
        "sources": {
            "actuals": "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream",
            "forecasts": "https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream",
        },
    }


if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def serve_frontend(full_path: str) -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend build is not installed.")
    return FileResponse(index_file)
