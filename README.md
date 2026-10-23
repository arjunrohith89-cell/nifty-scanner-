import io
import time
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd

# ---------- SETTINGS ----------
MAX_LOSS = 500
CAPITAL = 20000
RR = 2
MAX_RISK_PCT = 1.0
USE_VWAP_FILTER = True
VOL_MULTIPLIER = 1.2
ENFORCE_MARKET_TREND = True  # Block BUYs if Nifty is down, block SELLs if Nifty is up

# Paste your Telegram credentials directly here:
TG_TOKEN = "8905260026:AAHXExujNUHsGbGbldHiEsGETsk-OM TXc0w"
TG_CHAT_ID = "945498377"
# ------------------------------

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"
})


def get_ist_now():
    return dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=5, minutes=30)


def get_nifty200_symbols():
    urls = [
        "https://www.niftyindices.com/IndexConstituent/ind_nifty200list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv"
    ]
    for url in urls:
        try:
            resp = SESSION.get(url, timeout=10)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.text))
                if "Symbol" in df.columns:
                    return [s.strip() for s in df["Symbol"].dropna().tolist()
                            if not str(s).startswith("DUMMY")]
        except Exception:
            pass
    return [
        "SBIN", "ITC", "ICICIBANK", "AXISBANK", "INFY", "NTPC", "ONGC",
        "COALINDIA", "POWERGRID", "BHARTIARTL", "RELIANCE", "TCS", "HDFCBANK",
        "LT", "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "BAJFINANCE", "MARUTI"
    ]


def get_market_trend():
    """Checks if the overall Nifty 50 index is Bullish or Bearish relative to VWAP."""
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/^NSEI"
        resp = SESSION.get(url, params={"interval": "5m", "range": "5d"}, timeout=8)
        result = resp.json().get("chart", {}).get("result")
        if not result:
            return "NEUTRAL"
        res = result[0]
        ts = res.get("timestamp", [])
        quote = res.get("indicators", {}).get("quote", [{}])[0]
        if not ts or not quote:
            return "NEUTRAL"

        df = pd.DataFrame({
            "ts": pd.to_datetime(ts, unit="s", utc=True)
                    .tz_convert("Asia/Kolkata").tz_localize(None),
            "close": quote.get("close"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "volume": quote.get("volume"),
        }).dropna()

        if df.empty:
            return "NEUTRAL"

        latest_day = df["ts"].dt.date.max()
        df = df[df["ts"].dt.date == latest_day].copy().reset_index(drop=True)
        if df.empty:
            return "NEUTRAL"

        tp = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (tp * df["volume"]).cumsum() / df["volume"].replace(0, 1).cumsum()
        
        last_close = float(df["close"].iloc[-1])
        last_vwap = float(df["vwap"].iloc[-1])
        return "BULLISH" if last
