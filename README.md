# Wind Market Desk

A focused pilot dashboard for UK energy market teams reviewing national wind forecasts before day-ahead procurement decisions. The app reads Elexon BMRS `WINDFOR` forecasts and `FUELHH` wind actuals for delivery days in January 2026.

## What it does

- Select a January 2026 delivery day and a UK-local day-ahead decision cutoff (default 11:00).
- Select the latest published forecast snapshot available on or before that cutoff.
- Compare the hourly WINDFOR series with hourly means of the half-hourly FUELHH actuals.
- Quantify matched-interval MAE, RMSE, signed bias (forecast minus actual), and WAPE.
- Show the time series, interval table, source publication time, and coverage warnings.

This pilot deliberately does not calculate the net procurement requirement: demand, non-wind generation, prices, and plant availability are outside the supplied data scope. Forecast accuracy is descriptive and is not a trading recommendation.

## Start the application

### Docker (recommended)

Docker Desktop / Docker Compose must be installed and running:

```powershell
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). Stop the app with `Ctrl+C`.

### Local development

Requires Node.js 20+.

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The development environment file points the frontend directly to the deployed backend at `https://energy-forecast-neon.vercel.app`; a local Python backend is not required. The Vite `/api` proxy is used only when `VITE_API_BASE_URL` is unset (for example, if you remove or rename `.env.development`).

## Data and analysis

- Actual generation: [Elexon FUELHH stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream), filtered to `fuelType=WIND`.
- Forecast generation: [Elexon WINDFOR stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream), filtered by `publishDateTimeFrom` and `publishDateTimeTo`.
- API requests are made server-side; Elexon is the system of record. There is no fabricated or synthetic fallback.
- In January, the UK local cutoff is GMT. For other dates, the backend uses the `Europe/London` timezone and converts the cutoff to UTC before querying Elexon.
- The selected forecast is the newest complete 24-hour snapshot available by the cutoff. If Elexon has no complete snapshot, the newest available partial snapshot is shown and marked as partial.
- MAE = mean of `abs(forecast - actual)`; RMSE = square root of the mean squared error; bias = mean of `forecast - actual`; WAPE = sum of absolute errors divided by sum of absolute actual generation.
- Actuals are averaged by UTC hour to match the one-hour WINDFOR resolution. Metrics use only intervals where both values are present.

## Project structure

```text
.
├── backend/
│   ├── app/
│   │   └── main.py           # FastAPI routes, Elexon client, alignment and metrics
│   ├── tests/
│   │   └── test_analysis.py  # Unit tests for aggregation, snapshot selection and metrics
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx           # Dashboard, chart, metrics and interval table
│   │   ├── main.jsx          # React entry point
│   │   └── styles.css        # Responsive dashboard styling
│   ├── index.html
│   ├── package.json
│   └── vite.config.js        # Local API proxy
├── Dockerfile                # Builds React and serves it with FastAPI
├── docker-compose.yml
└── README.md
```
used AI to assist with domain/API research, implementation, and test authoring. The Elexon API response shape and supported forecast date-filter names were checked against the live API and Elexon documentation. 
