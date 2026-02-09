import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading } from "./styles";

// ─────────────────────────────────────────────
// Chinese Idiom of the Day — 每日成语
// ─────────────────────────────────────────────

export interface ChineseIdiom {
  idiom: string; // e.g. "画龙点睛"
  pinyin: string; // e.g. "huà lóng diǎn jīng"
  meaning: string; // Chinese explanation
  story?: string; // Optional: origin story
}

interface IdiomProps {
  idiom: ChineseIdiom;
}

export function IdiomBlock({ idiom }: IdiomProps) {
  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="🏮">每日成语 · Idiom of the Day</SectionHeading>

      <table width="100%" cellPadding={0} cellSpacing={0}>
        <tbody>
          <tr>
            {/* Decorative left bar */}
            <td
              style={{
                width: "4px",
                backgroundColor: tokens.accent,
                borderRadius: "2px",
              }}
            />
            <td style={{ paddingLeft: "16px" }}>
              {/* Idiom characters — large and prominent */}
              <Text
                style={{
                  fontFamily: tokens.fontSerif,
                  fontSize: "32px",
                  fontWeight: 900,
                  color: tokens.ink,
                  letterSpacing: "8px",
                  margin: "0 0 4px 0",
                  lineHeight: "1.3",
                }}
              >
                {idiom.idiom}
              </Text>

              {/* Pinyin */}
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "13px",
                  color: tokens.inkMuted,
                  margin: "0 0 8px 0",
                  fontStyle: "italic" as const,
                }}
              >
                {idiom.pinyin}
              </Text>

              {/* Meaning */}
              <Text
                style={{
                  fontFamily: tokens.fontSerif,
                  fontSize: "14px",
                  color: tokens.inkLight,
                  lineHeight: "1.7",
                  margin: "0 0 4px 0",
                }}
              >
                <strong style={{ color: tokens.ink }}>释义：</strong>
                {idiom.meaning}
              </Text>

              {/* Story (optional) */}
              {idiom.story && (
                <Text
                  style={{
                    fontFamily: tokens.fontSerif,
                    fontSize: "13px",
                    color: tokens.inkMuted,
                    lineHeight: "1.7",
                    margin: "4px 0 0 0",
                  }}
                >
                  <strong>典故：</strong>
                  {idiom.story}
                </Text>
              )}
            </td>
          </tr>
        </tbody>
      </table>
    </Section>
  );
}
