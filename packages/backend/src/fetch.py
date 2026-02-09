"""
Fetch all newsletter content and export as JSON.

Usage:
  uv run python -m src.fetch              → writes to .cache/newsletter-data.json
  uv run python -m src.fetch --output /tmp/data.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import cfg
from .main import _date_string, _edition_number, _fetch_all


def fetch_to_json(output: Path) -> None:
    """Fetch all sections and write to a JSON file."""
    print("=" * 50)
    print("📰  每日简报 — Fetching content")
    print("=" * 50)
    print()

    date_str = _date_string()
    edition = _edition_number()
    print(f"📅  {date_str}  |  第 {edition} 期")
    print()

    print("🔄  Fetching content…")
    sections = _fetch_all()
    print()

    # Merge astronomy data into weather
    weather_data = dict(sections.get("weather", {}))
    astro_data = sections.get("astronomy", {})
    if astro_data:
        weather_data["sunrise"] = astro_data.get("sunrise", "")
        weather_data["sunset"] = astro_data.get("sunset", "")
        weather_data["day_length"] = astro_data.get("day_length", "")
        weather_data["golden_hour"] = astro_data.get("golden_hour", "")
        weather_data["astro_note"] = astro_data.get("note", "")

    # Assemble the full payload (camelCase keys to match TypeScript types)
    payload: dict[str, object] = {
        "recipientName": cfg.recipient_name,
        "date": date_str,
        "editionNumber": edition,
        "weather": weather_data,
        "topNews": sections.get("news", []),
        "stocks": sections.get("stocks", []),
        "hnStories": sections.get("hn", []),
        "customSections": [],
    }

    # Map snake_case service output to camelCase for TypeScript
    payload = _to_camel_case(payload)  # type: ignore[assignment]

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾  Data written to {output}")


def _to_camel_case(obj: object) -> object:
    """Recursively convert snake_case dict keys to camelCase."""
    if isinstance(obj, dict):
        return {_snake_to_camel(k): _to_camel_case(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_camel_case(item) for item in obj]
    return obj


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase, preserving already-camelCase keys."""
    if "_" not in name:
        return name
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch newsletter data to JSON")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path(__file__).resolve().parent.parent / ".cache" / "newsletter-data.json",
        help="Output JSON path (default: .cache/newsletter-data.json)",
    )
    args = parser.parse_args()

    try:
        fetch_to_json(args.output)
    except Exception as e:
        print(f"\n❌  Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
