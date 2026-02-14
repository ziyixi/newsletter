// ─────────────────────────────────────────────
// Shared TypeScript interfaces for the newsletter.
//
// These types define the contract between the Python backend
// (which outputs JSON) and the React Email frontend.
// See: packages/backend/src/main.py for the producer.
// ─────────────────────────────────────────────

/** A single day in the 3-day weather forecast. */
export interface ForecastDay {
  label: string;       // e.g. "周一"
  icon: string;        // emoji
  condition: string;
  high: number;
  low: number;
}

/** Current weather conditions plus astronomy data. */
export interface WeatherForecast {
  location: string;
  condition: string;
  icon: string;        // emoji
  tempCurrent: number; // °C
  tempHigh: number;
  tempLow: number;
  summary: string;
  forecasts: ForecastDay[];
  // Astronomy (merged from astronomy_service)
  sunrise: string;
  sunset: string;
  dayLength: string;
  goldenHour: string;
  astroNote?: string;
}

/** A top-news headline item. */
export interface NewsItem {
  headline: string;
  summary: string;
  source: string;      // e.g. "Reuters"
  url: string;
  category: string;    // e.g. "Technology", "World"
}

/** A stock or ETF quote. */
export interface StockInfo {
  symbol: string;      // e.g. "AAPL"
  companyName: string;
  price: number;
  change: number;
  changePercent: number;
}

/** A Hacker News front-page story. */
export interface HNStory {
  title: string;
  titleCn: string;
  url: string;
  points: number;
  commentCount: number;
  hnUrl: string;
}

/** A GitHub trending repository. */
export interface GitHubRepo {
  name: string;
  description: string;
  descriptionCn: string;
  language: string;
  stars: number;
  todayStars: number;
  url: string;
}

/** An arXiv paper with AI-generated summary. */
export interface ArxivPaper {
  title: string;
  titleCn: string;
  summary: string;     // one-line Gemini summary
  authors: string;
  url: string;
  category: string;    // e.g. "LLM", "HPC"
}

/** A currency exchange rate. */
export interface ExchangeRate {
  pair: string;        // e.g. "USD/CNY"
  rate: number;
  change: number;
  changePercent: number;
  displayName: string; // e.g. "美元/人民币"
}

/** A recommended todo task. */
export interface TodoTask {
  rank: number;
  title: string;
  reason: string;
}

// ── Main props for the newsletter template ──

/** Top-level props passed to the newsletter React Email template. */
export interface NewsletterProps {
  recipientName: string;
  date: string;
  weather: WeatherForecast;
  topNews: NewsItem[];
  stocks: StockInfo[];
  hnStories: HNStory[];
  githubTrending: GitHubRepo[];
  arxivPapers: ArxivPaper[];
  exchangeRates: ExchangeRate[];
  todoTasks: TodoTask[];
}
