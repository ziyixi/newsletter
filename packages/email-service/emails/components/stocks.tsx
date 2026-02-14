import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading } from "./styles";
import type { StockInfo } from "../types";

interface StocksProps {
  stocks: StockInfo[];
}

export function Stocks({ stocks }: StocksProps) {
  if (!stocks.length) return null;

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="📈">行情观察</SectionHeading>

      <table
        width="100%"
        cellPadding={0}
        cellSpacing={0}
        style={{
          borderCollapse: "collapse" as const,
        }}
      >
        {/* Table header — warm accent strip */}
        <thead>
          <tr>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkLight,
                textAlign: "left" as const,
                padding: "8px 8px 8px 10px",
                borderBottom: `2px solid ${tokens.rule}`,
                backgroundColor: tokens.paperDark,
              }}
            >
              代码
            </th>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkLight,
                textAlign: "left" as const,
                padding: "8px 8px",
                borderBottom: `2px solid ${tokens.rule}`,
                backgroundColor: tokens.paperDark,
              }}
            >
              公司
            </th>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkLight,
                textAlign: "right" as const,
                padding: "8px 8px",
                borderBottom: `2px solid ${tokens.rule}`,
                backgroundColor: tokens.paperDark,
              }}
            >
              价格
            </th>
            <th
              style={{
                fontFamily: tokens.fontSans,
                fontSize: "10px",
                fontWeight: 700,
                textTransform: "uppercase" as const,
                letterSpacing: "1px",
                color: tokens.inkLight,
                textAlign: "right" as const,
                padding: "8px 10px 8px 8px",
                borderBottom: `2px solid ${tokens.rule}`,
                backgroundColor: tokens.paperDark,
              }}
            >
              涨跌
            </th>
          </tr>
        </thead>

        <tbody>
          {stocks.map((stock, i) => {
            const isPositive = stock.change >= 0;
            const changeColor = isPositive ? tokens.green : tokens.red;
            const arrow = isPositive ? "▲" : "▼";
            const sign = isPositive ? "+" : "";

            return (
              <tr
                key={i}
                style={{
                  backgroundColor: i % 2 === 1 ? tokens.rowAlt : "transparent",
                }}
              >
                <td
                  style={{
                    padding: "10px 8px 10px 10px",
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
                    {stock.symbol}
                  </Text>
                </td>

                <td
                  style={{
                    padding: "10px 8px",
                    borderBottom: `1px solid ${tokens.ruleLight}`,
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontKai,
                      fontSize: "13px",
                      color: tokens.inkLight,
                      margin: "0",
                    }}
                  >
                    {stock.companyName}
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
                      fontSize: "14px",
                      fontWeight: 700,
                      color: tokens.ink,
                      margin: "0",
                    }}
                  >
                    ${stock.price.toFixed(2)}
                  </Text>
                </td>

                <td
                  style={{
                    padding: "10px 10px 10px 8px",
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
                    {stock.change.toFixed(2)} ({sign}
                    {stock.changePercent.toFixed(2)}%)
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
