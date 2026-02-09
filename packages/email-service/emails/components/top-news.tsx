import * as React from "react";
import { Section, Text, Link } from "@react-email/components";
import { tokens, SectionHeading, ThinRule } from "./styles";
import type { NewsItem } from "../types";

interface TopNewsProps {
  news: NewsItem[];
}

export function TopNews({ news }: TopNewsProps) {
  if (!news.length) return null;

  const [lead, ...rest] = news;

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="📰">今日要闻</SectionHeading>

      {/* Lead story — editorial treatment */}
      <table width="100%" cellPadding={0} cellSpacing={0}>
        <tbody>
          <tr>
            <td>
              {/* Category tag */}
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  fontWeight: 700,
                  textTransform: "uppercase" as const,
                  letterSpacing: "2px",
                  color: tokens.accent,
                  margin: "0 0 6px 0",
                }}
              >
                {lead.category}
              </Text>

              {/* Headline */}
              <Link
                href={lead.url}
                style={{
                  textDecoration: "none",
                  color: tokens.ink,
                }}
              >
                <Text
                  style={{
                    fontFamily: tokens.fontCalligraphy,
                    fontSize: "28px",
                    fontWeight: 400,
                    color: tokens.ink,
                    lineHeight: "1.3",
                    margin: "0 0 8px 0",
                  }}
                >
                  {lead.headline}
                </Text>
              </Link>

              {/* Summary */}
              <Text
                style={{
                  fontFamily: tokens.fontKai,
                  fontSize: "15px",
                  color: tokens.inkLight,
                  lineHeight: "1.7",
                  margin: "0 0 6px 0",
                }}
              >
                {lead.summary}
              </Text>

              {/* Source */}
              <Text
                style={{
                  fontFamily: tokens.fontSans,
                  fontSize: "10px",
                  color: tokens.inkMuted,
                  margin: "0",
                  fontStyle: "italic" as const,
                }}
              >
                — {lead.source}
              </Text>
            </td>
          </tr>
        </tbody>
      </table>

      {/* Remaining stories */}
      {rest.map((item, i) => (
        <React.Fragment key={i}>
          <ThinRule />
          <table
            width="100%"
            cellPadding={0}
            cellSpacing={0}
            style={{ padding: "10px 0" }}
          >
            <tbody>
              <tr>
                {/* Number label */}
                <td
                  style={{
                    verticalAlign: "top",
                    width: "32px",
                    paddingRight: "8px",
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontSerif,
                      fontSize: "24px",
                      fontWeight: 700,
                      color: tokens.ruleLight,
                      margin: "0",
                      lineHeight: "1",
                    }}
                  >
                    {i + 2}
                  </Text>
                </td>

                {/* Content */}
                <td style={{ verticalAlign: "top" }}>
                  <Text
                    style={{
                      fontFamily: tokens.fontSans,
                      fontSize: "9px",
                      fontWeight: 700,
                      textTransform: "uppercase" as const,
                      letterSpacing: "2px",
                      color: tokens.accent,
                      margin: "0 0 2px 0",
                    }}
                  >
                    {item.category}
                  </Text>
                  <Link
                    href={item.url}
                    style={{
                      textDecoration: "none",
                      color: tokens.ink,
                    }}
                  >
                    <Text
                      style={{
                        fontFamily: tokens.fontCalligraphy,
                        fontSize: "16px",
                        fontWeight: 400,
                        color: tokens.ink,
                        lineHeight: "1.4",
                        margin: "0 0 3px 0",
                      }}
                    >
                      {item.headline}
                    </Text>
                  </Link>
                  <Text
                    style={{
                      fontFamily: tokens.fontKai,
                      fontSize: "13px",
                      color: tokens.inkLight,
                      lineHeight: "1.6",
                      margin: "0 0 2px 0",
                    }}
                  >
                    {item.summary}
                  </Text>
                  <Text
                    style={{
                      fontFamily: tokens.fontSans,
                      fontSize: "10px",
                      color: tokens.inkMuted,
                      margin: "0",
                      fontStyle: "italic" as const,
                    }}
                  >
                    — {item.source}
                  </Text>
                </td>
              </tr>
            </tbody>
          </table>
        </React.Fragment>
      ))}
    </Section>
  );
}
