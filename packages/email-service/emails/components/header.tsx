import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, DoubleRule, ThickRule } from "./styles";
import { templateConfig } from "../template-config";

interface HeaderProps {
  date: string;
  recipientName: string;
}

export function Header({ date, recipientName }: HeaderProps) {
  const tagline = templateConfig.tagline.replace(
    "{recipientName}",
    recipientName
  );

  return (
    <Section style={{ padding: "0" }}>
      {/* Top bar: date — refined editorial meta */}
      <table
        width="100%"
        cellPadding={0}
        cellSpacing={0}
        style={{ margin: "16px 0 8px 0" }}
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

          </tr>
        </tbody>
      </table>

      <ThickRule />

      {/* Masthead — calligraphic 书法 title */}
      <Text
        style={{
          fontFamily: tokens.fontCalligraphy,
          fontSize: "52px",
          fontWeight: 400,
          textAlign: "center" as const,
          color: tokens.ink,
          margin: "12px 0 0 0",
          lineHeight: "1.2",
          letterSpacing: "8px",
        }}
      >
        {templateConfig.title}
      </Text>

      {/* Decorative ornament */}
      <Text
        style={{
          textAlign: "center" as const,
          fontSize: "14px",
          color: tokens.ruleLight,
          margin: "8px 0 12px 0",
          letterSpacing: "6px",
        }}
      >
        ✦
      </Text>

      <DoubleRule />
    </Section>
  );
}
