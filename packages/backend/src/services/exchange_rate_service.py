"""Exchange rate service — uses yfinance (free, no API key)."""

from __future__ import annotations

from ..config import cfg


def fetch_exchange_rates() -> list[dict]:
    """Fetch exchange rates for configured currency pairs via yfinance."""
    import yfinance as yf

    results: list[dict] = []

    for pair in cfg.exchange_rate_pairs:
        ticker_symbol = pair.replace("/", "") + "=X"  # e.g. "USDCNY=X"

        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.fast_info

            rate = info.last_price
            prev_close = info.previous_close

            if rate is None:
                continue

            change = (rate - prev_close) if prev_close else 0
            change_pct = (change / prev_close * 100) if prev_close else 0

            results.append(
                {
                    "pair": pair,
                    "rate": round(rate, 4),
                    "change": round(change, 4),
                    "change_percent": round(change_pct, 2),
                    "display_name": cfg.exchange_rate_names.get(pair, pair),
                }
            )
        except Exception as e:
            print(f"⚠️  Failed to fetch rate for {pair}: {e}")

    return results
