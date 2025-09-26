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
fred = Fred(api_key=os.getenv("FRED_API_KEY"))  # keep your key safe in Render

def fetch_fred_series(series_id: str, transform: str = None):
    """Fetch and transform FRED series data"""
    obs = fred.get_series(series_id)
    if obs is None or obs.empty:
        raise ValueError(f"No data returned for FRED series {series_id}")

    data = [{"date": str(idx.date()), "value": float(val)} for idx, val in obs.items()]

    if transform == "yoy" and len(data) > 12:
        yoy = []
        for i in range(12, len(data)):
            prev, curr = data[i-12]["value"], data[i]["value"]
            yoy.append({"date": data[i]["date"], "value": ((curr - prev) / prev) * 100})
        data = yoy

    return {"series_id": series_id, "history": data, "latest": data[-1]["value"]}

# -------------------- Yahoo Finance --------------------
def fetch_yahoo(symbol: str):
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo")
    if hist.empty:
        raise ValueError(f"No data returned for {symbol}")

    data = {
        "symbol": symbol,
        "latest": float(hist["Close"].iloc[-1]),
        "history": {
            "dates": hist.index.strftime("%Y-%m-%d").tolist(),
            "values": hist["Close"].round(5).tolist()
        }
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
