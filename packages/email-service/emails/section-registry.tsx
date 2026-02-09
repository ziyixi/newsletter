import * as React from "react";
import type { NewsletterProps } from "./types";

// ── Section components ──────────────────────
import { Header } from "./components/header";
import { Weather } from "./components/weather";
import { TopNews } from "./components/top-news";
import { Stocks } from "./components/stocks";
import { CustomSections } from "./components/custom-section";
import { Footer } from "./components/footer";
import { HackerNews } from "./components/hacker-news";
import { GitHubTrending } from "./components/github-trending";
import { Arxiv } from "./components/arxiv";
import { ExchangeRates } from "./components/exchange-rate";

// ─────────────────────────────────────────────
// Section Registry
//
// Maps section IDs (from template-config.ts) to render functions.
// Each render function receives the full NewsletterProps and returns JSX.
//
// To add a new section:
//   1. Create a component in emails/components/your-section.tsx
//   2. Import it here
//   3. Add an entry: "your-section": (data) => <YourSection ... />
// ─────────────────────────────────────────────

export type SectionRenderer = (data: NewsletterProps) => React.ReactNode;

export const sectionRegistry: Record<string, SectionRenderer> = {
  header: (data) => (
    <Header
      date={data.date}
      recipientName={data.recipientName}
    />
  ),

  weather: (data) => <Weather weather={data.weather} />,

  "top-news": (data) => <TopNews news={data.topNews} />,

  "hacker-news": (data) => <HackerNews stories={data.hnStories} />,

  stocks: (data) => <Stocks stocks={data.stocks} />,

  "github-trending": (data) => (
    <GitHubTrending repos={data.githubTrending} />
  ),

  arxiv: (data) => <Arxiv papers={data.arxivPapers} />,

  "exchange-rates": (data) => (
    <ExchangeRates rates={data.exchangeRates} />
  ),

  "custom-sections": (data) => (
    <CustomSections sections={data.customSections} />
  ),

  footer: (_data) => <Footer />,

  // ── Register new sections here ──
};
