import * as React from "react";
import { Section, Text, Link } from "@react-email/components";
import { tokens, SectionHeading, ThinRule, CategoryPill } from "./styles";
import type { ArxivPaper } from "../types";

// ─────────────────────────────────────────────
// arXiv 速递 — Daily paper highlights
// Summarized by Gemini AI
// ─────────────────────────────────────────────

interface ArxivProps {
  papers: ArxivPaper[];
}

export function Arxiv({ papers }: ArxivProps) {
  if (!papers.length) return null;

  // Group by category (LLM / HPC)
  const byCat = papers.reduce(
    (acc, paper) => {
      const cat = paper.category || "Other";
      if (!acc[cat]) acc[cat] = [];
      acc[cat].push(paper);
      return acc;
    },
    {} as Record<string, ArxivPaper[]>,
  );

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="📄">arXiv 论文速递</SectionHeading>

      {Object.entries(byCat).map(([cat, catPapers], ci) => (
        <React.Fragment key={cat}>
          {ci > 0 && <ThinRule />}

          {/* Category pill badge */}
          <table cellPadding={0} cellSpacing={0} style={{ margin: "12px 0 6px 0" }}>
            <tbody>
              <tr>
                <td>
                  <CategoryPill>{cat}</CategoryPill>
                </td>
              </tr>
            </tbody>
          </table>

          {catPapers.map((paper, i) => (
            <table
              key={i}
              width="100%"
              cellPadding={0}
              cellSpacing={0}
              style={{
                padding: "8px 0 8px 12px",
                borderLeft: `2px solid ${tokens.ruleLight}`,
                marginBottom: "4px",
              }}
            >
              <tbody>
                <tr>
                  <td style={{ verticalAlign: "top" }}>
                    {/* Chinese title */}
                    <Link
                      href={paper.url}
                      style={{
                        fontFamily: tokens.fontKai,
                        fontSize: "14px",
                        fontWeight: 700,
                        color: tokens.ink,
                        textDecoration: "none",
                        lineHeight: "1.4",
                      }}
                    >
                      {paper.titleCn || paper.title}
                    </Link>

                    {/* Original English title */}
                    {paper.titleCn && paper.title && (
                      <Text
                        style={{
                          fontFamily: tokens.fontDisplay,
                          fontSize: "11px",
                          color: tokens.inkMuted,
                          fontStyle: "italic" as const,
                          lineHeight: "1.4",
                          margin: "2px 0 0 0",
                        }}
                      >
                        {paper.title}
                      </Text>
                    )}

                    {/* One-line AI summary — warm highlight strip */}
                    {paper.summary && (
                      <table width="100%" cellPadding={0} cellSpacing={0} style={{ marginTop: "4px" }}>
                        <tbody>
                          <tr>
                            <td
                              style={{
                                backgroundColor: tokens.pillBg,
                                padding: "4px 8px",
                                borderLeft: `2px solid ${tokens.gold}`,
                              }}
                            >
                              <Text
                                style={{
                                  fontFamily: tokens.fontKai,
                                  fontSize: "12px",
                                  color: tokens.inkLight,
                                  lineHeight: "1.5",
                                  margin: "0",
                                }}
                              >
                                💡 {paper.summary}
                              </Text>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    )}

                    {/* Authors */}
                    <Text
                      style={{
                        fontFamily: tokens.fontSans,
                        fontSize: "11px",
                        color: tokens.inkMuted,
                        margin: "3px 0 0 0",
                      }}
                    >
                      {paper.authors}
                    </Text>
                  </td>
                </tr>
              </tbody>
            </table>
          ))}
        </React.Fragment>
      ))}
    </Section>
  );
}
