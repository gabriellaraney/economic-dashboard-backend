from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fredapi import Fred
import yfinance as yf
from datetime import datetime, timedelta
import os

app = FastAPI()

# -------------------- CORS --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production: ["https://gabriellaraney.github.io"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Cache --------------------
CACHE = {}
CACHE_TTL = timedelta(minutes=30)

def cache_get(key: str):
    now = datetime.utcnow()
    if key in CACHE:
        entry = CACHE[key]
        if now - entry["timestamp"] < CACHE_TTL:
            return entry["data"]
    return None

def cache_set(key: str, data: dict):
    CACHE[key] = {"data": data, "timestamp": datetime.utcnow()}

# -------------------- FRED Setup --------------------
from fredapi import Fred
import pandas as pd

fred = Fred(api_key=os.getenv("FRED_API_KEY"))

def _infer_yoy_lag(index) -> int:
    # 12 for monthly, 4 for quarterly, default 12
    if isinstance(index, pd.PeriodIndex):
        if index.freqstr and index.freqstr.upper().startswith("Q"):
            return 4
        if index.freqstr and index.freqstr.upper().startswith("M"):
            return 12
    inferred = pd.infer_freq(index)
    if inferred and inferred.upper().startswith("Q"):
        return 4
    return 12

def fetch_fred_series(series_id: str, transform: str = None, max_points: int = 240):
    """Fetch FRED series, drop NaNs, normalize dates, optional YoY, and trim history."""
    s = fred.get_series(series_id)
    if s is None or s.empty:
        raise ValueError(f"No data returned for FRED series {series_id}")

    df = s.to_frame(name="value")

    # Normalize index → Timestamp (handles PeriodIndex and DatetimeIndex)
    if isinstance(df.index, pd.PeriodIndex):
        df.index = df.index.to_timestamp(how="end")
    else:
        df.index = pd.to_datetime(df.index)

    # Clean, compute transform if requested
    df = df.dropna(subset=["value"])

    if transform == "yoy":
        lag = _infer_yoy_lag(df.index)
        df["value"] = df["value"].pct_change(lag) * 100.0
        df = df.dropna(subset=["value"])

    # Trim payload (e.g., last 240 points ≈ 20 years monthly / 60 years quarterly)
    if max_points:
        df = df.tail(max_points)

    data = [{"date": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in df["value"].items()]
    if not data:
        raise ValueError(f"No usable observations for {series_id}")

    return {"series_id": series_id, "history": data, "latest": data[-1]["value"]}


# -------------------- Yahoo Finance --------------------
def fetch_yahoo(symbol: str):
    ticker = yf.Ticker(symbol)

    # Pull from Jan 1 of current year so YTD is precise
    year = datetime.utcnow().year
    jan1 = datetime(year, 1, 1)

    # Pull full-year-to-date for chart, not just 6mo
    hist = ticker.history(start=jan1)  # daily granularity
    if hist.empty:
        raise ValueError(f"No data returned for {symbol}")

    # First trading day of the year (not Jan 1 if holiday/weekend)
    first_price = float(hist["Close"].iloc[0])
    latest_price = float(hist["Close"].iloc[-1])
    pct_ytd = ((latest_price - first_price) / first_price) * 100.0

    data = {
        "symbol": symbol,
        "latest": latest_price,
        "ytd_change": pct_ytd,
        "history": {
            "dates": hist.index.strftime("%Y-%m-%d").tolist(),
            "values": hist["Close"].round(5).tolist(),
        },
    }
    return data

# -------------------- Routes --------------------
@app.get("/")
def home():
    return {"message": "Economic Dashboard Backend is running ✅"}

@app.get("/quote/{symbol}")
def get_quote(symbol: str):
    key = f"quote:{symbol}"
    cached = cache_get(key)
    if cached: return cached
    try:
        data = fetch_yahoo(symbol)
        cache_set(key, data)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/fred/{series_id}")
def get_fred(series_id: str, transform: str = None):
    key = f"fred:{series_id}:{transform}"
    cached = cache_get(key)
    if cached: return cached
    try:
        data = fetch_fred_series(series_id, transform)
        cache_set(key, data)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
