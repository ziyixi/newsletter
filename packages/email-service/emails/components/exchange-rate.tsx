import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading } from "./styles";
import type { ExchangeRate } from "../types";

// ─────────────────────────────────────────────
// Exchange Rate Monitor — 汇率监控
// ─────────────────────────────────────────────

interface ExchangeRateProps {
  rates: ExchangeRate[];
}

export function ExchangeRates({ rates }: ExchangeRateProps) {
  if (!rates.length) return null;

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="💱">汇率监控</SectionHeading>

      <table
        width="100%"
        cellPadding={0}
        cellSpacing={0}
        style={{ borderCollapse: "collapse" as const }}
      >
        <thead>
          <tr>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkMuted,
                textAlign: "left" as const,
                padding: "0 0 8px 0",
                borderBottom: `2px solid ${tokens.rule}`,
              }}
            >
              货币对
            </th>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkMuted,
                textAlign: "right" as const,
                padding: "0 0 8px 0",
                borderBottom: `2px solid ${tokens.rule}`,
              }}
            >
              汇率
            </th>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkMuted,
                textAlign: "right" as const,
                padding: "0 0 8px 0",
                borderBottom: `2px solid ${tokens.rule}`,
              }}
            >
              涨跌
            </th>
          </tr>
        </thead>

        <tbody>
          {rates.map((rate, i) => {
            const isPositive = rate.change >= 0;
            const changeColor = isPositive ? tokens.green : tokens.red;
            const arrow = isPositive ? "▲" : "▼";
            const sign = isPositive ? "+" : "";

            return (
              <tr key={i}>
                <td
                  style={{
                    padding: "10px 8px 10px 0",
                    borderBottom: `1px solid ${tokens.ruleLight}`,
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontMono,
                      fontSize: "14px",
                      fontWeight: 700,
                      color: tokens.ink,
                      margin: "0",
                    }}
                  >
                    {rate.pair}
                  </Text>
                  <Text
                    style={{
                      fontFamily: tokens.fontKai,
                      fontSize: "11px",
                      color: tokens.inkMuted,
                      margin: "2px 0 0 0",
                    }}
                  >
                    {rate.displayName}
                  </Text>
                </td>

                <td
                  style={{
                    padding: "10px 8px",
                    borderBottom: `1px solid ${tokens.ruleLight}`,
                    textAlign: "right" as const,
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontMono,
                      fontSize: "16px",
                      fontWeight: 700,
                      color: tokens.ink,
                      margin: "0",
                    }}
                  >
                    {rate.rate.toFixed(4)}
                  </Text>
                </td>

                <td
                  style={{
                    padding: "10px 0 10px 8px",
                    borderBottom: `1px solid ${tokens.ruleLight}`,
                    textAlign: "right" as const,
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontMono,
                      fontSize: "13px",
                      fontWeight: 700,
                      color: changeColor,
                      margin: "0",
                    }}
                  >
                    {arrow} {sign}
                    {rate.change.toFixed(4)} ({sign}
                    {rate.changePercent.toFixed(2)}%)
                  </Text>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Section>
  );
}
