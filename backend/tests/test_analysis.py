from datetime import date, datetime, time, timezone
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.main import (
    app,
    analysis,
    aggregate_actuals,
    calculate_metrics,
    select_forecast_snapshot,
)


class AnalysisTests(unittest.TestCase):
    def test_actuals_are_averaged_to_hourly_forecast_resolution(self) -> None:
        values = aggregate_actuals(
            [
                {"startTime": "2026-01-01T00:00:00Z", "generation": 100},
                {"startTime": "2026-01-01T00:30:00Z", "generation": 120},
                {"startTime": "2026-01-01T01:00:00Z", "generation": 80},
            ]
        )
        self.assertEqual(
            values,
            {
                datetime(2026, 1, 1, 0, tzinfo=timezone.utc): 110.0,
                datetime(2026, 1, 1, 1, tzinfo=timezone.utc): 80.0,
            },
        )

    def test_selects_latest_complete_snapshot_before_cutoff(self) -> None:
        records = []
        for publish_time, generation in (
            ("2026-01-01T09:30:00Z", 100),
            ("2026-01-01T10:30:00Z", 200),
        ):
            for hour in range(24):
                records.append(
                    {
                        "publishTime": publish_time,
                        "startTime": f"2026-01-02T{hour:02}:00:00Z",
                        "generation": generation,
                    }
                )
        published, snapshot = select_forecast_snapshot(
            records,
            date(2026, 1, 2),
            datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            published, datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(len(snapshot), 24)
        self.assertEqual(snapshot[datetime(2026, 1, 2, 0, tzinfo=timezone.utc)], 100)

    def test_ignores_forecast_versions_after_cutoff(self) -> None:
        records = [
            {
                "publishTime": "2026-01-01T10:30:00Z",
                "startTime": "2026-01-02T00:00:00Z",
                "generation": 100,
            },
            {
                "publishTime": "2026-01-01T11:30:00Z",
                "startTime": "2026-01-02T00:00:00Z",
                "generation": 200,
            },
        ]
        published, snapshot = select_forecast_snapshot(
            records,
            date(2026, 1, 2),
            datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            published, datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc)
        )
        self.assertEqual(
            snapshot[datetime(2026, 1, 2, 0, tzinfo=timezone.utc)], 100
        )

    def test_metrics_use_forecast_minus_actual_for_bias(self) -> None:
        metrics = calculate_metrics(
            [
                {"forecast_mw": 120.0, "actual_mw": 100.0},
                {"forecast_mw": 90.0, "actual_mw": 100.0},
                {"forecast_mw": None, "actual_mw": 50.0},
            ]
        )
        self.assertEqual(metrics["matched_intervals"], 2)
        self.assertEqual(metrics["mae_mw"], 15.0)
        self.assertAlmostEqual(metrics["rmse_mw"], (250.0) ** 0.5)
        self.assertEqual(metrics["bias_mw"], 5.0)
        self.assertEqual(metrics["wape_percent"], 15.0)

    def test_metrics_are_null_when_no_intervals_match(self) -> None:
        metrics = calculate_metrics(
            [{"forecast_mw": None, "actual_mw": 10.0}]
        )
        self.assertEqual(metrics["matched_intervals"], 0)
        self.assertIsNone(metrics["mae_mw"])
        self.assertIsNone(metrics["wape_percent"])


class AnalysisEndpointTests(unittest.IsolatedAsyncioTestCase):
    def test_cors_allows_local_vite_frontend(self) -> None:
        response = TestClient(app).options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "http://localhost:5173",
        )

    async def test_analysis_returns_cutoff_aligned_january_series(self) -> None:
        actuals = [
            {
                "startTime": f"2026-01-15T{hour:02}:{minute:02}:00Z",
                "generation": 100 + hour,
            }
            for hour in range(24)
            for minute in (0, 30)
        ]
        forecasts = [
            {
                "publishTime": publish_time,
                "startTime": f"2026-01-15T{hour:02}:00:00Z",
                "generation": 110 + hour,
            }
            for publish_time in ("2026-01-14T10:30:00Z", "2026-01-14T11:30:00Z")
            for hour in range(24)
        ]

        async def fake_fetch(_client, dataset, _params):
            return actuals if dataset == "FUELHH" else forecasts

        with patch("backend.app.main.fetch_dataset", side_effect=fake_fetch):
            result = await analysis(date(2026, 1, 15), time(11, 0))

        self.assertEqual(result["delivery_date"], "2026-01-15")
        self.assertEqual(result["latest_publish_time"], "2026-01-14T10:30:00Z")
        self.assertEqual(result["forecast_intervals"], 24)
        self.assertEqual(result["actual_intervals"], 24)
        self.assertEqual(result["metrics"]["matched_intervals"], 24)
        self.assertEqual(result["metrics"]["bias_mw"], 10.0)
        self.assertEqual(result["series"][0]["actual_mw"], 100.0)
        self.assertEqual(result["series"][-1]["forecast_mw"], 133.0)


if __name__ == "__main__":
    unittest.main()
