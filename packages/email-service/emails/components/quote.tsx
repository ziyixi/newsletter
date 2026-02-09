import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading } from "./styles";

// Local type definition (section removed from active newsletter)
interface QuoteType {
  text: string;
  author: string;
}

interface QuoteProps {
  quote: QuoteType;
}

export function QuoteBlock({ quote }: QuoteProps) {
  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="💬">每日一言 · Quote of the Day</SectionHeading>

      <table width="100%" cellPadding={0} cellSpacing={0}>
        <tbody>
          <tr>
            {/* Decorative left border */}
            <td
              style={{
                width: "4px",
                backgroundColor: tokens.accent,
                borderRadius: "2px",
              }}
            />
            <td style={{ paddingLeft: "16px" }}>
              <Text
                style={{
                  fontFamily: tokens.fontSerif,
                  fontSize: "18px",
                  fontStyle: "italic" as const,
                  color: tokens.ink,
                  lineHeight: "1.6",
                  margin: "0 0 8px 0",
                }}
              >
                &ldquo;{quote.text}&rdquo;
              </Text>
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "13px",
                  color: tokens.inkMuted,
                  margin: "0",
                }}
              >
                — {quote.author}
              </Text>
            </td>
          </tr>
        </tbody>
      </table>
    </Section>
  );
}
