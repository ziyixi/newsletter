"""Stocks service — uses yfinance (free, no API key)."""

from __future__ import annotations

from ..config import cfg


def fetch_stocks() -> list[dict]:
    """Fetch latest stock data for configured symbols."""
    import yfinance as yf

    results: list[dict] = []

    for symbol in cfg.stock_symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info

            price = info.last_price
            prev_close = info.previous_close

            if price is None or prev_close is None:
                continue

            change = price - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0

            results.append(
                {
                    "symbol": symbol,
                    "company_name": cfg.stock_names.get(symbol, symbol),
                    "price": round(price, 2),
                    "change": round(change, 2),
                    "change_percent": round(change_pct, 2),
                }
            )
        except Exception as e:
            print(f"⚠️  Failed to fetch stock {symbol}: {e}")

    return results
