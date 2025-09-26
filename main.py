from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
from datetime import datetime, timedelta

app = FastAPI()

# -------------------- CORS --------------------
# Allow frontend (GitHub Pages) to access this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or restrict to ["https://gabriellaraney.github.io"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Cache --------------------
CACHE = {}
CACHE_TTL = timedelta(minutes=30)  # cache responses for 30 minutes


def get_cached_data(symbol: str):
    """Return cached data if fresh, otherwise fetch new data."""
    now = datetime.utcnow()
    if symbol in CACHE:
        entry = CACHE[symbol]
        if now - entry["timestamp"] < CACHE_TTL:
            return entry["data"]

    # Fetch fresh data with yfinance
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period="6mo")  # last 6 months for charts
    if hist.empty:
        raise ValueError(f"No data returned for symbol {symbol}")

    latest = hist["Close"].iloc[-1]

    data = {
        "symbol": symbol,
        "latest": float(latest),
        "history": {
            "dates": hist.index.strftime("%Y-%m-%d").tolist(),
            "values": hist["Close"].round(5).tolist()
        }
    }

    CACHE[symbol] = {"data": data, "timestamp": now}
    return data


# -------------------- Routes --------------------
@app.get("/")
def home():
    return {"message": "Economic Dashboard Backend is running ✅"}


@app.get("/quote/{symbol}")
def get_quote(symbol: str):
    try:
        data = get_cached_data(symbol)
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)
