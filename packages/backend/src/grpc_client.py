"""
gRPC client for the email-service.

Sends a SendNewsletterRequest and returns the response.
"""

from __future__ import annotations

import sys
from pathlib import Path

import grpc

# Add the generated directory to the path so proto imports work
_generated_dir = str(Path(__file__).resolve().parent.parent / "generated")
if _generated_dir not in sys.path:
    sys.path.insert(0, _generated_dir)

from generated import newsletter_pb2, newsletter_pb2_grpc  # noqa: E402

from .config import cfg  # noqa: E402


def send_newsletter(request: newsletter_pb2.SendNewsletterRequest) -> newsletter_pb2.SendNewsletterResponse:
    """
    Send a SendNewsletterRequest to the email-service gRPC server.
    Returns the SendNewsletterResponse.
    """
    channel = grpc.insecure_channel(cfg.grpc_target)
    stub = newsletter_pb2_grpc.NewsletterServiceStub(channel)

    print(f"📡  Connecting to email-service at {cfg.grpc_target}…")
    response = stub.SendNewsletter(request, timeout=60)
    channel.close()

    return response


def build_request(
    *,
    weather: dict,
    top_news: list[dict],
    stocks: list[dict],
    hn_stories: list[dict],
    date_str: str,
) -> newsletter_pb2.SendNewsletterRequest:
    """Build a SendNewsletterRequest proto from Python dicts."""
    req = newsletter_pb2.SendNewsletterRequest(
        recipient_email=cfg.recipient_email,
        recipient_name=cfg.recipient_name,
        date=date_str,
    )

    # Weather
    if weather:
        req.weather.CopyFrom(
            newsletter_pb2.WeatherForecast(**weather)
        )

    # Top news
    for n in top_news:
        req.top_news.append(newsletter_pb2.NewsItem(**n))

    # Stocks
    for s in stocks:
        req.stocks.append(newsletter_pb2.StockInfo(**s))

    # HN stories
    for s in hn_stories:
        req.hn_stories.append(newsletter_pb2.HNStory(**s))

    return req
