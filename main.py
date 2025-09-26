from fastapi import FastAPI
from fastapi.responses import JSONResponse
import yfinance as yf
from datetime import datetime, timedelta

app = FastAPI()

# Simple in-memory cache
CACHE = {}
CACHE_TTL = timedelta(minutes=30)  # refresh every 30 minutes

def get_cached_data(symbol: str):
    now = datetime.utcnow()
    if symbol in CACHE:
        entry = CACHE[symbol]
        if now - entry["timestamp"] < CACHE_TTL:
            return entry["data"]  # return cached result

    # Fetch fresh data if cache is stale
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo")  # 6 months for chart
    latest = hist["Close"].iloc[-1]

    data = {
        "symbol": symbol,
        "latest": float(round(latest, 5)),
        "history": {
            "dates": hist.index.strftime("%Y-%m-%d").tolist(),
            "values": [round(v, 5) for v in hist["Close"].tolist()]
        }
    }
    CACHE[symbol] = {"data": data, "timestamp": now}
    return data

@app.get("/quote/{symbol}")
def get_quote(symbol: str):
    try:
        data = get_cached_data(symbol)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
