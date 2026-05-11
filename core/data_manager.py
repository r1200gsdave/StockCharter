import yfinance as yf
import numpy as np
import pandas as pd


class DataManager:
    def __init__(self):
        self.cache = {}
        self.ohlcv_cache = {}  # (symbol, period, interval) -> (t,o,h,l,c,v)

    def get_symbol_data(self, symbol):
        data = self.cache.get(symbol)
        if data is None:
            return None
        x, y = data
        return (x.copy(), y.copy())

    def get_symbol_ohlcv_with_dates(self, symbol, period="6mo", interval="1d"):
        symbol = str(symbol).strip().upper()
        key = (symbol, period, interval)

        cached = self.ohlcv_cache.get(key)
        if cached is not None:
            t, o, h, l, c, v = cached
            return (t.copy(), o.copy(), h.copy(), l.copy(), c.copy(), v.copy())

        df = yf.download(
            tickers=symbol,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if df is None or df.empty:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.loc[:, ~df.columns.duplicated()]

        needed = {"Open", "High", "Low", "Close", "Volume"}
        if not needed.issubset(set(df.columns)):
            return None

        t_ns = df.index.to_numpy(dtype="datetime64[ns]").astype("int64")
        t = (t_ns / 1e9).astype(float)

        o = df["Open"].to_numpy(dtype=float)
        h = df["High"].to_numpy(dtype=float)
        l = df["Low"].to_numpy(dtype=float)
        c = df["Close"].to_numpy(dtype=float)
        v = df["Volume"].to_numpy(dtype=float)

        mask = ~(np.isnan(o) | np.isnan(h) | np.isnan(l) | np.isnan(c) | np.isnan(v))
        out = (t[mask], o[mask], h[mask], l[mask], c[mask], v[mask])

        # cache copies (protect against accidental mutation)
        self.ohlcv_cache[key] = tuple(arr.copy() for arr in out)
        return out

    def preload_all(self, symbols):
        symbols = list(dict.fromkeys(symbols))

        df = yf.download(
            tickers=symbols,
            period="6mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            group_by="ticker",
            threads=False,
        )

        if df is None or df.empty:
            return

        # Single symbol edge case
        if not isinstance(df.columns, pd.MultiIndex):
            sym = symbols[0]
            close = df["Close"].to_numpy(dtype=float).reshape(-1)
            close = close[~np.isnan(close)]
            x = np.arange(len(close), dtype=float)
            self.cache[sym] = (x.copy(), close.copy())
            return

        top = df.columns.get_level_values(0)

        for sym in symbols:
            if sym not in top:
                continue

            df_sym = df[sym]
            if isinstance(df_sym.columns, pd.MultiIndex):
                df_sym.columns = df_sym.columns.get_level_values(0)

            df_sym = df_sym.loc[:, ~df_sym.columns.duplicated()]
            if "Close" not in df_sym.columns:
                continue

            close = df_sym["Close"].to_numpy(dtype=float).reshape(-1)
            close = close[~np.isnan(close)]
            x = np.arange(len(close), dtype=float)

            self.cache[sym] = (x.copy(), close.copy())
