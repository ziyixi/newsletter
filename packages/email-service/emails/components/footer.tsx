import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, DoubleRule } from "./styles";

export function Footer() {
  const now = new Date().toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    dateStyle: "full",
    timeStyle: "short",
  });

  return (
    <Section style={{ padding: "24px 0 32px 0" }}>
      <DoubleRule />

      {/* Decorative ornament */}
      <Text
        style={{
          textAlign: "center" as const,
          fontSize: "12px",
          color: tokens.ruleLight,
          margin: "12px 0 0 0",
          letterSpacing: "6px",
        }}
      >
        ✦ ✦ ✦
      </Text>
    </Section>
  );
}
