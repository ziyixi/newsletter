"""Newsletter backend services — each module fetches one content section."""

from .weather_service import fetch_weather
from .news_service import fetch_news
from .stocks_service import fetch_stocks
from .hn_service import fetch_hn_stories
from .astronomy_service import fetch_astronomy
from .github_trending_service import fetch_github_trending
from .arxiv_service import fetch_arxiv_papers
from .exchange_rate_service import fetch_exchange_rates
from .ranking_service import rank_sections

__all__ = [
    "fetch_weather",
    "fetch_news",
    "fetch_stocks",
    "fetch_hn_stories",
    "fetch_astronomy",
    "fetch_github_trending",
    "fetch_arxiv_papers",
    "fetch_exchange_rates",
    "rank_sections",
]
