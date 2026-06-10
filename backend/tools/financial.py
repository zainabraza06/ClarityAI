"""
Yahoo Finance financial data tool.

Wraps yfinance as an async LangChain tool so the research agent can
pull real-time market cap, revenue, margins, and key ratios for any
publicly traded company. Private companies return a graceful notice.
"""

import asyncio
import logging
from langchain_core.tools import tool

logger = logging.getLogger("clarityai.financial")


def _fmt(value, prefix: str = "$", suffix: str = "") -> str:
    """Format a large number into a human-readable string (T/B/M)."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
        if abs(v) >= 1e12:
            return f"{prefix}{v / 1e12:.2f}T{suffix}"
        if abs(v) >= 1e9:
            return f"{prefix}{v / 1e9:.2f}B{suffix}"
        if abs(v) >= 1e6:
            return f"{prefix}{v / 1e6:.2f}M{suffix}"
        return f"{prefix}{v:,.0f}{suffix}"
    except (TypeError, ValueError):
        return "N/A"


def _fetch_sync(company_or_ticker: str) -> str:
    """Blocking yfinance call — must be run in a thread pool."""
    try:
        import yfinance as yf
    except ImportError:
        return "yfinance is not installed — financial data unavailable."

    ticker_symbol = company_or_ticker.strip()

    # 1. Try the input as a direct ticker symbol
    stock = yf.Ticker(ticker_symbol.upper())
    info = stock.info or {}

    # 2. If no price/cap found, try yfinance search to resolve company name → ticker
    has_data = bool(
        info.get("regularMarketPrice")
        or info.get("currentPrice")
        or info.get("marketCap")
    )
    if not has_data:
        try:
            search = yf.Search(company_or_ticker, max_results=5)
            for q in search.quotes or []:
                if q.get("quoteType") in ("EQUITY", "ETF"):
                    ticker_symbol = q["symbol"]
                    stock = yf.Ticker(ticker_symbol)
                    info = stock.info or {}
                    has_data = bool(
                        info.get("regularMarketPrice")
                        or info.get("currentPrice")
                        or info.get("marketCap")
                    )
                    if has_data:
                        break
        except Exception:
            pass

    if not has_data:
        return (
            f"No public financial data found for '{company_or_ticker}'. "
            "This may be a private company or the ticker could not be resolved."
        )

    lines: list[str] = []
    name = info.get("longName") or info.get("shortName") or ticker_symbol.upper()
    lines.append(f"**{name}** ({ticker_symbol.upper()})")

    sector = info.get("sector", "")
    industry = info.get("industry", "")
    if sector:
        lines.append(f"Sector: {sector}" + (f"  •  Industry: {industry}" if industry else ""))

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price:
        lines.append(f"Stock Price: ${float(price):.2f}")

    mktcap = info.get("marketCap")
    if mktcap:
        lines.append(f"Market Cap: {_fmt(mktcap)}")

    revenue = info.get("totalRevenue")
    if revenue:
        lines.append(f"Annual Revenue (TTM): {_fmt(revenue)}")

    net_income = info.get("netIncomeToCommon")
    if net_income:
        lines.append(f"Net Income: {_fmt(net_income)}")

    gross_margin = info.get("grossMargins")
    if gross_margin is not None:
        lines.append(f"Gross Margin: {gross_margin * 100:.1f}%")

    op_margin = info.get("operatingMargins")
    if op_margin is not None:
        lines.append(f"Operating Margin: {op_margin * 100:.1f}%")

    pe = info.get("trailingPE")
    if pe:
        lines.append(f"P/E Ratio (TTM): {float(pe):.1f}x")

    fwd_pe = info.get("forwardPE")
    if fwd_pe:
        lines.append(f"Forward P/E: {float(fwd_pe):.1f}x")

    eps = info.get("trailingEps")
    if eps:
        lines.append(f"EPS (TTM): ${float(eps):.2f}")

    rev_growth = info.get("revenueGrowth")
    if rev_growth is not None:
        lines.append(f"Revenue Growth (YoY): {rev_growth * 100:+.1f}%")

    earnings_growth = info.get("earningsGrowth")
    if earnings_growth is not None:
        lines.append(f"Earnings Growth (YoY): {earnings_growth * 100:+.1f}%")

    high52 = info.get("fiftyTwoWeekHigh")
    low52 = info.get("fiftyTwoWeekLow")
    if high52 and low52:
        lines.append(f"52-Week Range: ${float(low52):.2f} — ${float(high52):.2f}")

    employees = info.get("fullTimeEmployees")
    if employees:
        lines.append(f"Full-Time Employees: {int(employees):,}")

    div_yield = info.get("dividendYield")
    if div_yield:
        lines.append(f"Dividend Yield: {div_yield * 100:.2f}%")

    cash = info.get("totalCash")
    if cash:
        lines.append(f"Cash & Equivalents: {_fmt(cash)}")

    debt = info.get("totalDebt")
    if debt:
        lines.append(f"Total Debt: {_fmt(debt)}")

    return "\n".join(lines)


@tool
async def get_financial_data(company_or_ticker: str) -> str:
    """
    Fetch real-time financial data for a publicly traded company from Yahoo Finance.
    Returns market cap, annual revenue, profit margins, P/E ratio, EPS, stock price,
    revenue/earnings growth, 52-week range, employee count, and balance sheet highlights.
    Accepts a company name (e.g. 'Apple', 'NVIDIA') or ticker symbol (e.g. 'AAPL', 'NVDA').
    Returns a notice for private companies that are not publicly listed.
    """
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _fetch_sync, company_or_ticker)
    except Exception as exc:
        logger.warning("Financial data fetch failed for '%s': %s", company_or_ticker, exc)
        return f"Financial data temporarily unavailable for '{company_or_ticker}'."
