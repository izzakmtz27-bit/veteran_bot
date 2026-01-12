import os
import time
import math
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

# =========================
# CONFIG
# =========================
TICKERS = ["SPY", "QQQ", "NVDA"]
SCAN_INTERVAL = 300  # 5 minutes
STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", 10000))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", 0.01))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

balance = STARTING_BALANCE
open_trades = {}  # ticker -> trade dict

# =========================
# TELEGRAM
# =========================
def tg(msg):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "disable_web_page_preview": True
    })

# =========================
# INDICATORS
# =========================
def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def rsi(series, length=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(length).mean()
    avg_loss = loss.rolling(length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

# =========================
# DATA
# =========================
def fetch_data(ticker, interval, lookback):
    df = yf.download(
        ticker,
        interval=interval,
        period=lookback,
        progress=False
    )
    if df.empty:
        return None
    return df

# =========================
# STRATEGY LOGIC
# =========================
def bullish_trend_1h(df):
    df["EMA50"] = ema(df["Close"], 50)
    return df["Close"].iloc[-1] > df["EMA50"].iloc[-1]

def pullback_entry_15m(df):
    df["EMA20"] = ema(df["Close"], 20)
    df["RSI"] = rsi(df["Close"])
    last = df.iloc[-1]
    prev = df.iloc[-2]

    pullback = last["Close"] > last["EMA20"] and prev["Close"] < prev["EMA20"]
    rsi_ok = last["RSI"] < 70

    return pullback and rsi_ok

# =========================
# PAPER TRADE
# =========================
def open_paper_trade(ticker, price):
    global balance
    risk_amount = balance * RISK_PER_TRADE
    stop = price * 0.99
    target = price * 1.02
    size = risk_amount / (price - stop)

    open_trades[ticker] = {
        "entry": price,
        "stop": stop,
        "target": target,
        "size": size
    }

    tg(
        f"📈 PAPER BUY {ticker}\n"
        f"Entry: {price:.2f}\n"
        f"Stop: {stop:.2f}\n"
        f"Target: {target:.2f}"
    )

def manage_trade(ticker, price):
    global balance
    trade = open_trades[ticker]

    if price <= trade["stop"]:
        pnl = (trade["stop"] - trade["entry"]) * trade["size"]
        balance += pnl
        tg(f"❌ STOP HIT {ticker} | PnL: {pnl:.2f}")
        del open_trades[ticker]

    elif price >= trade["target"]:
        pnl = (trade["target"] - trade["entry"]) * trade["size"]
        balance += pnl
        tg(f"✅ TARGET HIT {ticker} | PnL: {pnl:.2f}")
        del open_trades[ticker]

# =========================
# MAIN LOOP
# =========================
def main():
    tg("✅ Veteran Paper Bot ONLINE\nAuto-scan + auto-paper-trading active")

    while True:
        try:
            for ticker in TICKERS:
                # Manage open trades
                if ticker in open_trades:
                    df = fetch_data(ticker, "1m", "1d")
                    if df is not None:
                        manage_trade(ticker, df["Close"].iloc[-1])
                    continue

                # Scan for new trades
                df_1h = fetch_data(ticker, "1h", "5d")
                df_15m = fetch_data(ticker, "15m", "5d")

                if df_1h is None or df_15m is None:
                    continue

                if bullish_trend_1h(df_1h) and pullback_entry_15m(df_15m):
                    entry_price = df_15m["Close"].iloc[-1]
                    open_paper_trade(ticker, entry_price)

            print(f"[{datetime.now(timezone.utc)}] Balance: {balance:.2f}")
        except Exception as e:
            print("Error:", e)

        time.sleep(SCAN_INTERVAL)

if __name__ == "__main__":
    main()
