// ─────────────────────────────────────────────
// AUTO-GENERATED from newsletter.config.yaml
// Do not edit — run `make sync-config` to refresh.
// ─────────────────────────────────────────────

export interface SectionDef {
  /** Unique key — matches a key in the section registry */
  id: string;
  /** Human-readable label (for logging / debugging) */
  label: string;
}

export interface TemplateConfig {
  /** Newsletter title shown in the masthead */
  title: string;
  /** Tagline (supports {recipientName} placeholder) */
  tagline: string;
  /** Ordered list of sections to render */
  sections: SectionDef[];
}

export const templateConfig: TemplateConfig = {
  title: "每日简报",
  tagline: "为 {recipientName} 精心策划的晨间资讯",
  sections: [
    {
      "id": "header",
      "label": "Masthead / Header"
    },
    {
      "id": "weather",
      "label": "Weather & Astronomy"
    },
    {
      "id": "top-news",
      "label": "Top 5 News"
    },
    {
      "id": "hacker-news",
      "label": "Hacker News Top Stories"
    },
    {
      "id": "github-trending",
      "label": "GitHub Trending Repos"
    },
    {
      "id": "arxiv",
      "label": "arXiv Paper Highlights"
    },
    {
      "id": "stocks",
      "label": "Market Snapshot"
    },
    {
      "id": "exchange-rates",
      "label": "Exchange Rates"
    },
    {
      "id": "custom-sections",
      "label": "Custom / Personal Sections"
    },
    {
      "id": "footer",
      "label": "Footer"
    }
  ],
};
