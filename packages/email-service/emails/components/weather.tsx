import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading, ThinRule } from "./styles";
import type { WeatherForecast } from "../types";

interface WeatherProps {
  weather: WeatherForecast;
}

export function Weather({ weather }: WeatherProps) {
  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="☁️">天气与天文</SectionHeading>

      {/* ── Weather ───────────────────────── */}
      <table width="100%" cellPadding={0} cellSpacing={0}>
        <tbody>
          <tr>
            {/* Icon + Temp */}
            <td style={{ verticalAlign: "top", width: "120px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "48px",
                  lineHeight: "1",
                  margin: "0",
                  textAlign: "center" as const,
                }}
              >
                {weather.icon}
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontMono,
                  fontSize: "28px",
                  fontWeight: 700,
                  color: tokens.ink,
                  margin: "4px 0 0 0",
                  textAlign: "center" as const,
                  lineHeight: "1",
                }}
              >
                {weather.tempCurrent}°C
              </Text>
            </td>

            {/* Details */}
            <td style={{ verticalAlign: "top", paddingLeft: "16px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontCalligraphy,
                  fontSize: "20px",
                  fontWeight: 400,
                  color: tokens.ink,
                  margin: "0 0 2px 0",
                }}
              >
                {weather.location}
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "14px",
                  color: tokens.inkLight,
                  margin: "0 0 4px 0",
                }}
              >
                {weather.condition} · 最高 {weather.tempHigh}° / 最低{" "}
                {weather.tempLow}°
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontKai,
                  fontSize: "14px",
                  color: tokens.inkLight,
                  margin: "0",
                  lineHeight: "1.6",
                }}
              >
                {weather.summary}
              </Text>
            </td>
          </tr>
        </tbody>
      </table>

      {/* ── Astronomy (sunrise / sunset / day length) ── */}
      <ThinRule />
      <table
        width="100%"
        cellPadding={0}
        cellSpacing={0}
        style={{
          marginTop: "0",
          backgroundColor: tokens.paperDark,
          borderTop: `2px solid ${tokens.gold}`,
        }}
      >
        <tbody>
          <tr>
            <td style={{ width: "25%", padding: "12px 8px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.gold,
                  margin: "0 0 2px 0",
                  textTransform: "uppercase" as const,
                  letterSpacing: "1px",
                  fontWeight: 700,
                }}
              >
                🌅 日出
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontMono,
                  fontSize: "16px",
                  fontWeight: 700,
                  color: tokens.ink,
                  margin: "0",
                }}
              >
                {weather.sunrise}
              </Text>
            </td>
            <td style={{ width: "25%", textAlign: "center" as const, padding: "12px 8px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.gold,
                  margin: "0 0 2px 0",
                  textTransform: "uppercase" as const,
                  letterSpacing: "1px",
                  fontWeight: 700,
                }}
              >
                🌇 日落
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontMono,
                  fontSize: "16px",
                  fontWeight: 700,
                  color: tokens.ink,
                  margin: "0",
                }}
              >
                {weather.sunset}
              </Text>
            </td>
            <td style={{ width: "25%", textAlign: "center" as const, padding: "12px 8px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.gold,
                  margin: "0 0 2px 0",
                  textTransform: "uppercase" as const,
                  letterSpacing: "1px",
                  fontWeight: 700,
                }}
              >
                ☀️ 日照
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontMono,
                  fontSize: "16px",
                  fontWeight: 700,
                  color: tokens.ink,
                  margin: "0",
                }}
              >
                {weather.dayLength}
              </Text>
            </td>
            <td style={{ width: "25%", textAlign: "right" as const, padding: "12px 8px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.gold,
                  margin: "0 0 2px 0",
                  textTransform: "uppercase" as const,
                  letterSpacing: "1px",
                  fontWeight: 700,
                }}
              >
                🌅 黄金时刻
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontMono,
                  fontSize: "16px",
                  fontWeight: 700,
                  color: tokens.ink,
                  margin: "0",
                }}
              >
                {weather.goldenHour}
              </Text>
            </td>
          </tr>
        </tbody>
      </table>

      {/* ── 3-Day Forecast ────────────────────── */}
      {weather.forecasts && weather.forecasts.length > 0 && (
        <>
          <ThinRule />
          <table
            width="100%"
            cellPadding={0}
            cellSpacing={0}
            style={{ marginTop: "12px" }}
          >
            <tbody>
              <tr>
                {weather.forecasts.map((day, i) => (
                  <td
                    key={i}
                    style={{
                      width: `${100 / weather.forecasts.length}%`,
                      textAlign: "center" as const,
                      verticalAlign: "top",
                      padding: "0 4px",
                      borderLeft: i > 0 ? `1px solid ${tokens.ruleLight}` : "none",
                    }}
                  >
                    <Text
                      style={{
                        fontFamily: tokens.fontSans,
                        fontSize: "11px",
                        fontWeight: 700,
                        color: tokens.inkMuted,
                        margin: "0 0 4px 0",
                        textTransform: "uppercase" as const,
                        letterSpacing: "1px",
                      }}
                    >
                      {day.label}
                    </Text>
                    <Text
                      style={{
                        fontSize: "24px",
                        lineHeight: "1",
                        margin: "0 0 4px 0",
                      }}
                    >
                      {day.icon}
                    </Text>
                    <Text
                      style={{
                        fontFamily: tokens.fontMono,
                        fontSize: "14px",
                        fontWeight: 700,
                        color: tokens.ink,
                        margin: "0 0 2px 0",
                      }}
                    >
                      {day.high}° / {day.low}°
                    </Text>
                    <Text
                      style={{
                        fontFamily: tokens.fontSans,
                        fontSize: "11px",
                        color: tokens.inkLight,
                        margin: "0",
                      }}
                    >
                      {day.condition}
                    </Text>
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </>
      )}

      {/* Optional astronomy note */}
      {weather.astroNote && (
        <table width="100%" cellPadding={0} cellSpacing={0} style={{ marginTop: "10px" }}>
          <tbody>
            <tr>
              <td
                style={{
                  backgroundColor: tokens.pillBg,
                  border: `1px solid ${tokens.pillBorder}`,
                  padding: "8px 12px",
                }}
              >
                <Text
                  style={{
                    fontFamily: tokens.fontKai,
                    fontSize: "13px",
                    color: tokens.inkMuted,
                    lineHeight: "1.6",
                    margin: "0",
                  }}
                >
                  💡 {weather.astroNote}
                </Text>
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </Section>
  );
}
