import * as React from "react";
import { Section, Text, Link } from "@react-email/components";
import { tokens, SectionHeading, ThinRule } from "./styles";

// ─────────────────────────────────────────────
// This Day in History — 历史上的今天
// Renders a list of historical events for today's date.
// ─────────────────────────────────────────────

export interface HistoryEvent {
  year: string;
  text: string;
  url?: string;
}

interface HistoryProps {
  events: HistoryEvent[];
}

export function History({ events }: HistoryProps) {
  if (!events.length) return null;

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="📜">历史上的今天 · On This Day</SectionHeading>

      {events.map((event, i) => (
        <React.Fragment key={i}>
          {i > 0 && <ThinRule />}
          <table
            width="100%"
            cellPadding={0}
            cellSpacing={0}
            style={{ padding: "8px 0" }}
          >
            <tbody>
              <tr>
                {/* Year badge */}
                <td
                  style={{
                    verticalAlign: "top",
                    width: "56px",
                    paddingRight: "12px",
                  }}
                >
                  <Text
                    style={{
                      fontFamily: tokens.fontMono,
                      fontSize: "13px",
                      fontWeight: 700,
                      color: tokens.accent,
                      margin: "0",
                      lineHeight: "1.6",
                      whiteSpace: "nowrap" as const,
                    }}
                  >
                    {event.year}年
                  </Text>
                </td>

                {/* Event text */}
                <td style={{ verticalAlign: "top" }}>
                  {event.url ? (
                    <Link
                      href={event.url}
                      style={{ textDecoration: "none", color: tokens.ink }}
                    >
                      <Text
                        style={{
                          fontFamily: tokens.fontSerif,
                          fontSize: "14px",
                          color: tokens.inkLight,
                          lineHeight: "1.6",
                          margin: "0",
                        }}
                      >
                        {event.text}
                      </Text>
                    </Link>
                  ) : (
                    <Text
                      style={{
                        fontFamily: tokens.fontSerif,
                        fontSize: "14px",
                        color: tokens.inkLight,
                        lineHeight: "1.6",
                        margin: "0",
                      }}
                    >
                      {event.text}
                    </Text>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </React.Fragment>
      ))}
    </Section>
  );
}
