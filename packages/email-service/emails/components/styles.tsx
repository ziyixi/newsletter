import * as React from "react";
import { Section, Text, Hr } from "@react-email/components";

// ─────────────────────────────────────────────
// Shared style tokens — NYT-inspired editorial
// with Chinese calligraphy (书法) accents
// ─────────────────────────────────────────────

export const tokens = {
  // Colors — warm ivory paper, rich ink, crimson accent
  ink: "#121212", // rich black (NYT-style)
  inkLight: "#363636", // warm dark gray
  inkMuted: "#727272", // refined muted
  paper: "#faf8f3", // warm ivory / parchment
  paperDark: "#f0ece2", // warmer off-white
  paperEdge: "#e8e4d9", // warm edge
  accent: "#a01a2f", // editorial crimson / deep wine
  gold: "#9e7c0c", // warm deep gold for highlights
  goldLight: "#d4a017", // brighter gold for ornaments
  green: "#2d6a4f", // forest green (elegant)
  red: "#b71c1c", // classic red
  rule: "#121212", // dark rule
  ruleLight: "#d5d0c4", // warm gray rule

  // Section card surfaces
  sectionBg: "#fdfcf9", // barely-warm white card
  sectionBorder: "#eae6db", // warm card border

  // Pill badge
  pillBg: "#f3efe6", // warm cream pill background
  pillBorder: "#e0dbd0", // pill border

  // Alternating row
  rowAlt: "#f8f6f1", // subtle alternating row tint

  // Typography — calligraphy for display, 楷体 for body, serif fallback
  fontCalligraphy:
    "'Ma Shan Zheng', 'ZCOOL XiaoWei', 'Noto Serif SC', 'Songti SC', cursive, serif",
  fontKai:
    "'LXGW WenKai', 'KaiTi', 'STKaiti', 'AR PL UKai CN', 'Noto Serif SC', Georgia, serif",
  fontSerif:
    "'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', Georgia, 'Times New Roman', serif",
  fontSans:
    "'Noto Sans SC', 'Source Han Sans SC', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, Helvetica, Arial, sans-serif",
  fontMono:
    "'SF Mono', 'Fira Code', Menlo, Consolas, monospace",
  fontDisplay:
    "Georgia, 'Noto Serif SC', 'Times New Roman', serif",

  // Spacing
  containerWidth: 640,
  sectionPadding: "28px 0",
} as const;

// ─────────────────────────────────────────────
// Reusable thin rule — warm, elegant
// ─────────────────────────────────────────────

export function ThinRule() {
  return (
    <Hr
      style={{
        borderTop: `1px solid ${tokens.ruleLight}`,
        borderBottom: "none",
        margin: "0",
      }}
    />
  );
}

// ─────────────────────────────────────────────
// Reusable thick rule (editorial weight)
// ─────────────────────────────────────────────

export function ThickRule() {
  return (
    <Hr
      style={{
        borderTop: `3px solid ${tokens.rule}`,
        borderBottom: "none",
        margin: "0",
      }}
    />
  );
}

// ─────────────────────────────────────────────
// Double rule — classic NYT-style divider
// thick on top, thin below, tight spacing
// ─────────────────────────────────────────────

export function DoubleRule() {
  return (
    <Section style={{ padding: "0" }}>
      <Hr
        style={{
          borderTop: `2px solid ${tokens.rule}`,
          borderBottom: "none",
          margin: "0 0 2px 0",
        }}
      />
      <Hr
        style={{
          borderTop: `0.5px solid ${tokens.rule}`,
          borderBottom: "none",
          margin: "0",
        }}
      />
    </Section>
  );
}

// ─────────────────────────────────────────────
// Section heading — refined editorial label
// centered with warm gold accent underline
// ─────────────────────────────────────────────

export function SectionHeading({
  icon,
  children,
}: {
  icon?: string;
  children: React.ReactNode;
}) {
  return (
    <table width="100%" cellPadding={0} cellSpacing={0}>
      <tbody>
        <tr>
          <td
            style={{
              borderBottom: `1px solid ${tokens.ruleLight}`,
              width: "15%",
            }}
          />
          <td style={{ textAlign: "center" as const, padding: "0 16px", whiteSpace: "nowrap" as const }}>
            <Text
              style={{
                fontFamily: tokens.fontCalligraphy,
                fontSize: "15px",
                fontWeight: 400,
                letterSpacing: "4px",
                color: tokens.inkLight,
                margin: "0 0 6px 0",
              }}
            >
              {icon ? `${icon}  ` : ""}
              {children}
            </Text>
            {/* Gold accent underline */}
            <table cellPadding={0} cellSpacing={0} style={{ margin: "0 auto 12px auto" }}>
              <tbody>
                <tr>
                  <td
                    style={{
                      width: "40px",
                      height: "2px",
                      backgroundColor: tokens.gold,
                    }}
                  />
                </tr>
              </tbody>
            </table>
          </td>
          <td
            style={{
              borderBottom: `1px solid ${tokens.ruleLight}`,
              width: "15%",
            }}
          />
        </tr>
      </tbody>
    </table>
  );
}

// ─────────────────────────────────────────────
// Section divider — decorative spacer between
// major sections (centered dot ornament)
// ─────────────────────────────────────────────

export function SectionDivider() {
  return (
    <table width="100%" cellPadding={0} cellSpacing={0}>
      <tbody>
        <tr>
          <td
            style={{
              textAlign: "center" as const,
              padding: "8px 0",
            }}
          >
            <Text
              style={{
                fontSize: "8px",
                color: tokens.ruleLight,
                margin: "0",
                letterSpacing: "8px",
              }}
            >
              ◆ ◆ ◆
            </Text>
          </td>
        </tr>
      </tbody>
    </table>
  );
}

// ─────────────────────────────────────────────
// Category pill badge — warm tinted pill
// ─────────────────────────────────────────────

export function CategoryPill({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        fontFamily: tokens.fontSans,
        fontSize: "9px",
        fontWeight: 700,
        textTransform: "uppercase" as const,
        letterSpacing: "1.5px",
        color: tokens.accent,
        backgroundColor: tokens.pillBg,
        border: `1px solid ${tokens.pillBorder}`,
        padding: "2px 8px",
        display: "inline-block",
      }}
    >
      {children}
    </span>
  );
}
