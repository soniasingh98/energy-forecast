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

Requires Python 3.11+ and Node.js 20+.

Terminal 1:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Terminal 2:

```powershell
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` requests to the Python service on port 8000.

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

## Validate

```powershell
python -m unittest discover -s backend\tests -v
cd frontend
npm run build
```

The API health check is `GET /api/health`; analysis is `GET /api/analysis?delivery_date=2026-01-15&cutoff_time=11:00`.

## Deploy frontend and backend separately on Vercel

**Public application URL:** Not deployed yet. Deploy the backend and frontend as two Vercel projects from this same GitHub repository. The backend entry point/configuration is in `backend/api.py` and `backend/vercel.json`; the frontend calls the backend using `VITE_API_BASE_URL`.

### 1. Deploy the backend

1. Import the GitHub repository as a Vercel project.
2. Set **Root Directory** to `backend`. The FastAPI source and `requirements.txt` are inside this directory.
3. Keep the framework preset as **Other** and deploy. Vercel uses `vercel.json` to route requests to the FastAPI app exported by `api.py`.
4. In the backend project's **Settings → Environment Variables**, add:
   - `FRONTEND_ORIGINS` = `http://localhost:5173,https://<your-frontend-project>.vercel.app`
   - Replace the example frontend origin with the actual frontend URL after creating that project. Include the scheme and do not add a trailing slash.
5. Redeploy after setting or changing environment variables.
6. Test `https://<your-backend-project>.vercel.app/api/health` and `https://<your-backend-project>.vercel.app/api/analysis?delivery_date=2026-01-31&cutoff_time=11:00`.

### 2. Deploy the frontend

1. Create a second Vercel project and import the same GitHub repository again.
2. Set **Root Directory** to `frontend`. Vercel should detect Vite; use build command `npm run build` and output directory `dist`.
3. Add `VITE_API_BASE_URL` = `https://<your-backend-project>.vercel.app` (backend origin only; no `/api` suffix and no trailing slash).
4. Deploy. The frontend calls `${VITE_API_BASE_URL}/api/...`. Locally, when the variable is unset, Vite continues to proxy relative `/api` requests to localhost.
5. Open the deployed frontend. If it was deployed before configuring the backend's `FRONTEND_ORIGINS`, redeploy the backend after adding the frontend's exact production URL.

The backend permits only explicitly configured frontend origins and the local Vite development origins by default. For Vercel preview URLs, add the preview origin to `FRONTEND_ORIGINS` or test using the production frontend domain. Redeploy a project after changing its environment variables.

Vercel's current FastAPI guidance: [Deploy a FastAPI app on Vercel](https://vercel.com/docs/frameworks/backend/fastapi).

**Suggested anonymous public repository name:** `q7v4m2x9`. Create the public GitHub repository under an account you control, push this project, and add its URL here. Repository creation, external deployment, YouTube upload, and Microsoft Forms submission require your account authorization and are not performed from this local workspace.

## Video demo plan

The requested two-part recording should be no longer than 10 minutes: a client-facing overview (up to 5 minutes) followed by a technical review (up to 5 minutes). A concise recording outline is in [`docs/video-script.md`](docs/video-script.md). The video itself still needs to be recorded, uploaded as unlisted, and linked in the submission form by the applicant.

## AI assistance

AI tools (GitHub Copilot) were used to assist with domain/API research, implementation, and test authoring. The Elexon API response shape and supported forecast date-filter names were checked against the live API and Elexon documentation. The applicant should review the code, test the deployed app, and be prepared to explain all design choices before submission.
