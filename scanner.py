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
ENFORCE_MARKET_TREND = True

# Paste your BRAND NEW Telegram Token from BotFather here:
import os
TG_TOKEN = os.getenv("TG_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")
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
    return ["SBIN", "ITC", "ICICIBANK", "AXISBANK", "INFY", "NTPC", "ONGC", "RELIANCE", "TCS", "HDFCBANK"]

def get_market_trend():
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
            "ts": pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None),
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
        return "BULLISH" if float(df["close"].iloc[-1]) >= float(df["vwap"].iloc[-1]) else "BEARISH"
    except Exception:
        return "NEUTRAL"

def get_candles(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
    resp = SESSION.get(url, params={"interval": "5m", "range": "5d"}, timeout=8)
    result = resp.json().get("chart", {}).get("result")
    if not result:
        return pd.DataFrame()

    res = result[0]
    ts = res.get("timestamp", [])
    quote = res.get("indicators", {}).get("quote", [{}])[0]
    if not ts or not quote:
        return pd.DataFrame()

    df = pd.DataFrame({
        "ts": pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None),
        "open": quote.get("open"),
        "high": quote.get("high"),
        "low": quote.get("low"),
        "close": quote.get("close"),
        "volume": quote.get("volume"),
    }).dropna()

    if df.empty:
        return pd.DataFrame()

    latest_day = df["ts"].dt.date.max()
    df = df[df["ts"].dt.date == latest_day].copy().reset_index(drop=True)
    tp = (df["high"] + df["low"] + df["close"]) / 3
    df["vwap"] = (tp * df["volume"]).cumsum() / df["volume"].replace(0, 1).cumsum()
    return df

def evaluate_candles(df, symbol, market_trend):
    if df.empty or len(df) < 4:
        return None
    day = df["ts"].dt.date.iloc[0]
    open_end = pd.Timestamp(f"{day} 09:30:00")
    opening = df[df["ts"] < open_end]
    after = df[df["ts"] >= open_end]
    if len(opening) < 3 or after.empty:
        return None

    r_high, r_low = opening["high"].max(), opening["low"].min()
    last = after.iloc[-1]
    last_close, last_vwap, last_vol = float(last["close"]), float(last["vwap"]), float(last["volume"])
    avg_vol = float(df["volume"].mean())
    prev_close = float(after.iloc[-2]["close"]) if len(after) > 1 else float(opening["close"].iloc[-1])

    if last_close > r_high and prev_close <= r_high:
        if USE_VWAP_FILTER and last_close < last_vwap:
            return None
        if ENFORCE_MARKET_TREND and market_trend == "BEARISH":
            return None
        side, entry, sl = "BUY", r_high, r_low
    elif last_close < r_low and prev_close >= r_low:
        if USE_VWAP_FILTER and last_close > last_vwap:
            return None
        if ENFORCE_MARKET_TREND and market_trend == "BULLISH":
            return None
        side, entry, sl = "SELL", r_low, r_high
    else:
        return None

    if VOL_MULTIPLIER > 0 and last_vol < (avg_vol * VOL_MULTIPLIER):
        return None

    risk = abs(entry - sl)
    if risk == 0 or (risk / entry * 100) > MAX_RISK_PCT:
        return None

    qty = int(min(MAX_LOSS // risk, CAPITAL // entry))
    if qty < 1:
        return None

    target = entry + RR * risk if side == "BUY" else entry - RR * risk
    return {
        "Stock": symbol, "Side": side, "Time": last["ts"].strftime("%H:%M"),
        "Entry": round(entry, 2), "SL": round(sl, 2), "Target": round(target, 2),
        "Qty": qty, "MaxLoss": round(qty * risk), "VWAP": round(last_vwap, 2), "Market": market_trend
    }

def send_telegram(text):
    if not (TG_TOKEN and TG_CHAT_ID):
        return
    try:
        resp = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        print("Telegram Response:", resp.status_code, resp.text)
    except Exception as e:
        print("Telegram error:", e)

def fmt(s):
    icon = "🟢 BUY" if s["Side"] == "BUY" else "🔴 SELL"
    return f"{icon} {s['Stock']} ({s['Time']}) [Nifty: {s['Market']}]\nEntry: {s['Entry']} | SL: {s['SL']} | Target: {s['Target']}\nVWAP: {s['VWAP']} | Qty: {s['Qty']} | Risk: Rs{s['MaxLoss']}"

def scan_stock(sym, market_trend):
    try:
        return evaluate_candles(get_candles(sym), sym, market_trend)
    except Exception:
        return None

if __name__ == "__main__":
    watchlist = get_nifty200_symbols()
    seen = set()
    send_telegram(f"🚀 Cloud NIFTY 200 Trend-Filtered Scanner Started ({len(watchlist)} stocks)")

    while True:
        now_ist = get_ist_now()
        if now_ist.time() >= dt.time(15, 15):
            send_telegram("⏹ 3:15 PM - Cloud Scanner finished for today.")
            break
        if now_ist.time() < dt.time(9, 30):
            time.sleep(30)
            continue

        current_trend = get_market_trend()
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(scan_stock, sym, current_trend): sym for sym in watchlist}
            for future in as_completed(futures):
                sig = future.result()
                if sig and (sig["Stock"], sig["Side"]) not in seen:
                    seen.add((sig["Stock"], sig["Side"]))
                    msg = fmt(sig)
                    print(msg)
                    send_telegram(msg)
        time.sleep(60)
        
