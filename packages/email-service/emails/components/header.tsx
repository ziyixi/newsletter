import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, DoubleRule, ThickRule } from "./styles";
import { templateConfig } from "../template-config";

interface HeaderProps {
  date: string;
  recipientName: string;
}

export function Header({ date, recipientName }: HeaderProps) {
  return (
    <Section style={{ padding: "0" }}>
      {/* Top bar: date + edition — refined editorial meta */}
      <table
        width="100%"
        cellPadding={0}
        cellSpacing={0}
        style={{ margin: "16px 0 10px 0" }}
      >
        <tbody>
          <tr>
            <td style={{ textAlign: "left" as const }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.inkMuted,
                  letterSpacing: "1.5px",
                  textTransform: "uppercase" as const,
                  margin: "0",
                }}
              >
                {date}
              </Text>
            </td>
            <td style={{ textAlign: "right" as const }}>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.inkMuted,
                  letterSpacing: "1.5px",
                  textTransform: "uppercase" as const,
                  margin: "0",
                }}
              >
                每日简报
              </Text>
            </td>
          </tr>
        </tbody>
      </table>

      <ThickRule />

      {/* Masthead — calligraphic 书法 title */}
      <Text
        style={{
          fontFamily: tokens.fontCalligraphy,
          fontSize: "56px",
          fontWeight: 400,
          textAlign: "center" as const,
          color: tokens.ink,
          margin: "16px 0 0 0",
          lineHeight: "1.2",
          letterSpacing: "10px",
        }}
      >
        {templateConfig.title}
      </Text>

      {/* Decorative gold ornament */}
      <Text
        style={{
          textAlign: "center" as const,
          fontSize: "10px",
          color: tokens.gold,
          margin: "6px 0 14px 0",
          letterSpacing: "10px",
        }}
      >
        ✦ ✦ ✦
      </Text>

      <DoubleRule />

      {/* Warm greeting band */}
      <table
        width="100%"
        cellPadding={0}
        cellSpacing={0}
        style={{
          backgroundColor: tokens.paperDark,
          borderBottom: `1px solid ${tokens.ruleLight}`,
        }}
      >
        <tbody>
          <tr>
            <td style={{ padding: "14px 20px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontKai,
                  fontSize: "14px",
                  color: tokens.inkLight,
                  margin: "0",
                  lineHeight: "1.5",
                }}
              >
                {recipientName}，早安 ☀️ 以下是今日为你精选的资讯
              </Text>
            </td>
          </tr>
        </tbody>
      </table>
    </Section>
  );
}
