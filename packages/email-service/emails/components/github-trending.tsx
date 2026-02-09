import * as React from "react";
import { Section, Text, Link } from "@react-email/components";
import { tokens, SectionHeading, ThinRule } from "./styles";
import type { GitHubRepo } from "../types";

// ─────────────────────────────────────────────
// GitHub Trending — 每日 GitHub 热门仓库
// Filtered by language (Rust / Go / Python)
// ─────────────────────────────────────────────

interface GitHubTrendingProps {
  repos: GitHubRepo[];
}

export function GitHubTrending({ repos }: GitHubTrendingProps) {
  if (!repos.length) return null;

  // Group by language for visual clarity
  const byLang = repos.reduce(
    (acc, repo) => {
      const lang = repo.language || "Other";
      if (!acc[lang]) acc[lang] = [];
      acc[lang].push(repo);
      return acc;
    },
    {} as Record<string, GitHubRepo[]>,
  );

  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon="🔥">GitHub 热门趋势</SectionHeading>

      {Object.entries(byLang).map(([lang, langRepos], gi) => (
        <React.Fragment key={lang}>
          {gi > 0 && <ThinRule />}

          {/* Language badge */}
          <Text
            style={{
              fontFamily: tokens.fontSans,
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "1.5px",
              textTransform: "uppercase" as const,
              color: tokens.accent,
              margin: "12px 0 4px 0",
            }}
          >
            {lang}
          </Text>

          {langRepos.map((repo, i) => (
            <table
              key={i}
              width="100%"
              cellPadding={0}
              cellSpacing={0}
              style={{ padding: "6px 0" }}
            >
              <tbody>
                <tr>
                  <td style={{ verticalAlign: "top" }}>
                    {/* Repo name */}
                    <Link
                      href={repo.url}
                      style={{
                        fontFamily: tokens.fontMono,
                        fontSize: "13px",
                        fontWeight: 700,
                        color: tokens.ink,
                        textDecoration: "none",
                      }}
                    >
                      {repo.name}
                    </Link>

                    {/* Description (Chinese) */}
                    {repo.descriptionCn && (
                      <Text
                        style={{
                          fontFamily: tokens.fontKai,
                          fontSize: "12px",
                          color: tokens.inkLight,
                          lineHeight: "1.5",
                          margin: "2px 0 0 0",
                        }}
                      >
                        {repo.descriptionCn}
                      </Text>
                    )}

                    {/* Meta: stars */}
                    <Text
                      style={{
                        fontFamily: tokens.fontSans,
                        fontSize: "11px",
                        color: tokens.inkMuted,
                        margin: "2px 0 0 0",
                      }}
                    >
                      ⭐ {repo.stars.toLocaleString()}
                      {repo.todayStars > 0 && (
                        <span style={{ color: tokens.accent }}>
                          {" "}
                          · +{repo.todayStars} today
                        </span>
                      )}
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
