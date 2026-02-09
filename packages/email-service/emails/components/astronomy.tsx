import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading } from "./styles";

// ─────────────────────────────────────────────
// Astronomy Today — 天文快报
// Sunrise/sunset, golden hour, etc.
// ─────────────────────────────────────────────

export interface AstronomyData {
  sunrise: string; // e.g. "06:58"
  sunset: string; // e.g. "17:42"
  dayLength: string; // e.g. "10小时44分"
  goldenHour: string; // e.g. "17:12"
  note?: string; // optional fun fact
}

interface AstronomyProps {
  astronomy: AstronomyData;
}

export function Astronomy({ astronomy }: AstronomyProps) {
  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="🔭">天文快报 · Astronomy</SectionHeading>

      <table width="100%" cellPadding={0} cellSpacing={0}>
        <tbody>
          {/* Sun row */}
          <tr>
            <td style={{ padding: "6px 0" }}>
              <table width="100%" cellPadding={0} cellSpacing={0}>
                <tbody>
                  <tr>
                    <td style={{ width: "33%" }}>
                      <Text
                        style={{
                          fontFamily: tokens.fontSans,
                          fontSize: "11px",
                          color: tokens.inkMuted,
                          margin: "0 0 2px 0",
                          textTransform: "uppercase" as const,
                          letterSpacing: "1px",
                        }}
                      >
                        🌅 日出
                      </Text>
                      <Text
                        style={{
                          fontFamily: tokens.fontMono,
                          fontSize: "18px",
                          fontWeight: 700,
                          color: tokens.ink,
                          margin: "0",
                        }}
                      >
                        {astronomy.sunrise}
                      </Text>
                    </td>
                    <td style={{ width: "33%", textAlign: "center" as const }}>
                      <Text
                        style={{
                          fontFamily: tokens.fontSans,
                          fontSize: "11px",
                          color: tokens.inkMuted,
                          margin: "0 0 2px 0",
                          textTransform: "uppercase" as const,
                          letterSpacing: "1px",
                        }}
                      >
                        🌇 日落
                      </Text>
                      <Text
                        style={{
                          fontFamily: tokens.fontMono,
                          fontSize: "18px",
                          fontWeight: 700,
                          color: tokens.ink,
                          margin: "0",
                        }}
                      >
                        {astronomy.sunset}
                      </Text>
                    </td>
                    <td style={{ width: "33%", textAlign: "right" as const }}>
                      <Text
                        style={{
                          fontFamily: tokens.fontSans,
                          fontSize: "11px",
                          color: tokens.inkMuted,
                          margin: "0 0 2px 0",
                          textTransform: "uppercase" as const,
                          letterSpacing: "1px",
                        }}
                      >
                        ☀️ 日照
                      </Text>
                      <Text
                        style={{
                          fontFamily: tokens.fontMono,
                          fontSize: "18px",
                          fontWeight: 700,
                          color: tokens.ink,
                          margin: "0",
                        }}
                      >
                        {astronomy.dayLength}
                      </Text>
                    </td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>

          {/* Golden hour row */}
          <tr>
            <td style={{ padding: "10px 0 4px 0" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSerif,
                  fontSize: "14px",
                  color: tokens.inkLight,
                  margin: "0",
                  lineHeight: "1.6",
                }}
              >
                🌅 黄金时刻 <strong style={{ color: tokens.ink }}>{astronomy.goldenHour}</strong>
              </Text>
            </td>
          </tr>

          {/* Optional note */}
          {astronomy.note && (
            <tr>
              <td style={{ padding: "4px 0 0 0" }}>
                <Text
                  style={{
                    fontFamily: tokens.fontSerif,
                    fontSize: "13px",
                    fontStyle: "italic" as const,
                    color: tokens.inkMuted,
                    lineHeight: "1.6",
                    margin: "0",
                  }}
                >
                  💡 {astronomy.note}
                </Text>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </Section>
  );
}
