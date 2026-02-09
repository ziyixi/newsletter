// ─────────────────────────────────────────────
// Shared types for the newsletter email template
// ─────────────────────────────────────────────

export interface ForecastDay {
  label: string; // e.g. "周一"
  icon: string; // emoji
  condition: string;
  high: number;
  low: number;
}

export interface WeatherForecast {
  location: string;
  condition: string;
  icon: string; // emoji
  tempCurrent: number; // °C
  tempHigh: number;
  tempLow: number;
  summary: string;
  // 3-day forecast
  forecasts: ForecastDay[];
  // Astronomy (merged)
  sunrise: string;
  sunset: string;
  dayLength: string;
  goldenHour: string;
  astroNote?: string;
}

export interface NewsItem {
  headline: string;
  summary: string;
  source: string;
  url: string;
  category: string;
}

export interface StockInfo {
  symbol: string;
  companyName: string;
  price: number;
  change: number;
  changePercent: number;
}

export interface ContentSection {
  title: string;
  contentHtml: string;
  icon: string;
}

// ── New section types ───────────────────────

export interface HNStory {
  title: string;
  titleCn: string;
  url: string;
  points: number;
  commentCount: number;
  hnUrl: string;
}

// ── Main props ──────────────────────────────

export interface NewsletterProps {
  recipientName: string;
  date: string;
  editionNumber: number;
  weather: WeatherForecast;
  topNews: NewsItem[];
  stocks: StockInfo[];
  customSections: ContentSection[];
  hnStories: HNStory[];
}
