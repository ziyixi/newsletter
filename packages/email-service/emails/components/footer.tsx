import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, DoubleRule } from "./styles";

export function Footer() {
  return (
    <Section style={{ padding: "24px 0 36px 0" }}>
      <DoubleRule />

      {/* Closing message */}
      <Text
        style={{
          fontFamily: tokens.fontCalligraphy,
          fontSize: "16px",
          textAlign: "center" as const,
          color: tokens.inkMuted,
          margin: "18px 0 4px 0",
          letterSpacing: "3px",
        }}
      >
        明日再见
      </Text>
      <Text
        style={{
          fontFamily: tokens.fontDisplay,
          fontSize: "11px",
          fontStyle: "italic" as const,
          textAlign: "center" as const,
          color: tokens.ruleLight,
          margin: "0 0 16px 0",
          letterSpacing: "1px",
        }}
      >
        See you tomorrow
      </Text>

      {/* Decorative gold ornament */}
      <Text
        style={{
          textAlign: "center" as const,
          fontSize: "10px",
          color: tokens.gold,
          margin: "0",
          letterSpacing: "10px",
        }}
      >
        ✦ ✦ ✦
      </Text>
    </Section>
  );
}
