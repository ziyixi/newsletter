import * as React from "react";
import { Section, Text, Link } from "@react-email/components";
import { tokens, SectionHeading, ThinRule } from "./styles";

// ─────────────────────────────────────────────
// Hacker News Top Stories — HN 热榜
// ─────────────────────────────────────────────

export interface HNStory {
  title: string;
  titleCn: string;
  url: string;
  points: number;
  commentCount: number;
  hnUrl: string; // link to HN discussion
}

interface HNProps {
  stories: HNStory[];
}

export function HackerNews({ stories }: HNProps) {
  if (!stories.length) return null;

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="🔶">黑客新闻热榜</SectionHeading>

      {stories.map((story, i) => (
        <React.Fragment key={i}>
          {i > 0 && <ThinRule />}
          <table
            width="100%"
            cellPadding={0}
            cellSpacing={0}
            style={{
              padding: "10px 0",
              backgroundColor: i % 2 === 1 ? tokens.rowAlt : "transparent",
            }}
          >
            <tbody>
              <tr>
                {/* Rank number — gold accent */}
                <td
                  style={{
                    verticalAlign: "top",
                    width: "28px",
                    paddingRight: "10px",
                    paddingLeft: i % 2 === 1 ? "8px" : "0",
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontSerif,
                      fontSize: "20px",
                      fontWeight: 700,
                      color: tokens.gold,
                      margin: "0",
                      lineHeight: "1.2",
                    }}
                  >
                    {i + 1}
                  </Text>
                </td>

                {/* Content */}
                <td style={{ verticalAlign: "top" }}>
                  <Link
                    href={story.url}
                    style={{ textDecoration: "none", color: tokens.ink }}
                  >
                    <Text
                      style={{
                        fontFamily: tokens.fontKai,
                        fontSize: "14px",
                        fontWeight: 700,
                        color: tokens.ink,
                        lineHeight: "1.4",
                        margin: "0 0 2px 0",
                      }}
                    >
                      {story.titleCn || story.title}
                    </Text>
                  </Link>

                  {/* Original English title — smaller reference */}
                  {story.titleCn && story.title && (
                    <Text
                      style={{
                        fontFamily: tokens.fontDisplay,
                        fontSize: "11px",
                        color: tokens.inkMuted,
                        lineHeight: "1.4",
                        margin: "0 0 3px 0",
                        fontStyle: "italic" as const,
                      }}
                    >
                      {story.title}
                    </Text>
                  )}

                  {/* Meta: points + comments */}
                  <Text
                    style={{
                      fontFamily: tokens.fontSans,
                      fontSize: "11px",
                      color: tokens.inkMuted,
                      margin: "0",
                    }}
                  >
                    <span style={{ color: tokens.goldLight }}>▲</span>{" "}
                    <span style={{ color: tokens.accent, fontWeight: 700 }}>
                      {story.points}
                    </span>{" "}
                    分 ·{" "}
                    <Link
                      href={story.hnUrl}
                      style={{
                        color: tokens.inkMuted,
                        textDecoration: "underline",
                      }}
                    >
                      {story.commentCount} 条评论
                    </Link>
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
