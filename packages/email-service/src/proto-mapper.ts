import type { NewsletterProps } from "../emails/types";

/**
 * Map a gRPC SendNewsletterRequest message (plain JS object from proto-loader)
 * to the typed NewsletterProps used by the React Email template.
 *
 * proto-loader uses snake_case by default (keepCase: true), so we map to camelCase.
 */
export function mapProtoToProps(req: Record<string, any>): {
  props: NewsletterProps;
  recipientEmail: string;
} {
  return {
    recipientEmail: req.recipient_email ?? "",
    props: {
      recipientName: req.recipient_name ?? "Reader",
      date: req.date ?? new Date().toLocaleDateString("zh-CN", { dateStyle: "full" }),
      editionNumber: req.edition_number ?? 0,

      weather: req.weather
        ? {
            location: req.weather.location ?? "",
            condition: req.weather.condition ?? "",
            icon: req.weather.icon ?? "🌤",
            tempCurrent: req.weather.temp_current ?? 0,
            tempHigh: req.weather.temp_high ?? 0,
            tempLow: req.weather.temp_low ?? 0,
            summary: req.weather.summary ?? "",
            sunrise: req.weather.sunrise ?? "",
            sunset: req.weather.sunset ?? "",
            dayLength: req.weather.day_length ?? "",
            goldenHour: req.weather.golden_hour ?? "",
            astroNote: req.weather.astro_note ?? "",
            forecasts: (req.weather.forecasts ?? []).map((f: any) => ({
              label: f.label ?? "",
              icon: f.icon ?? "❓",
              condition: f.condition ?? "",
              high: f.high ?? 0,
              low: f.low ?? 0,
            })),
          }
        : {
            location: "N/A",
            condition: "N/A",
            icon: "❓",
            tempCurrent: 0,
            tempHigh: 0,
            tempLow: 0,
            summary: "",
            sunrise: "",
            sunset: "",
            dayLength: "",
            goldenHour: "",
            forecasts: [],
          },

      topNews: (req.top_news ?? []).map((n: any) => ({
        headline: n.headline ?? "",
        summary: n.summary ?? "",
        source: n.source ?? "",
        url: n.url ?? "#",
        category: n.category ?? "",
      })),

      hnStories: (req.hn_stories ?? []).map((s: any) => ({
        title: s.title ?? "",
        titleCn: s.title_cn ?? "",
        url: s.url ?? "#",
        points: s.points ?? 0,
        commentCount: s.comment_count ?? 0,
        hnUrl: s.hn_url ?? "#",
      })),

      stocks: (req.stocks ?? []).map((s: any) => ({
        symbol: s.symbol ?? "",
        companyName: s.company_name ?? "",
        price: s.price ?? 0,
        change: s.change ?? 0,
        changePercent: s.change_percent ?? 0,
      })),

      customSections: (req.custom_sections ?? []).map((c: any) => ({
        title: c.title ?? "",
        contentHtml: c.content_html ?? "",
        icon: c.icon ?? "",
      })),
    },
  };
}
