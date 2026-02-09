import * as React from "react";
import {
  Html,
  Head,
  Body,
  Container,
  Font,
  Preview,
} from "@react-email/components";
import { tokens } from "./components/styles";
import type { NewsletterProps } from "./types";
import { fakeData } from "./fixtures/fake-data";
import { templateConfig, type SectionDef } from "./template-config";
import { sectionRegistry } from "./section-registry";

// ─────────────────────────────────────────────
// The Daily Briefing — main newsletter template
// Driven by template-config.ts for easy extensibility.
// ─────────────────────────────────────────────

export default function Newsletter(props: Partial<NewsletterProps> = {}) {
  // Merge with fake data defaults for preview
  const data: NewsletterProps = { ...fakeData, ...props };
  const previewText = `☀ ${templateConfig.title} — ${data.date}`;

  return (
    <Html lang="zh-CN">
      <Head>
        {/* Google Fonts — Ma Shan Zheng (书法), Noto Serif SC, Noto Sans SC */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=LXGW+WenKai:wght@400;700&family=Ma+Shan+Zheng&family=Noto+Serif+SC:wght@400;700;900&family=Noto+Sans+SC:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
        <Font
          fontFamily="LXGW WenKai"
          fallbackFontFamily="Georgia"
          fontWeight={400}
          fontStyle="normal"
        />
        <Font
          fontFamily="Ma Shan Zheng"
          fallbackFontFamily="Georgia"
          fontWeight={400}
          fontStyle="normal"
        />
        <Font
          fontFamily="Noto Serif SC"
          fallbackFontFamily="Georgia"
          fontWeight={400}
          fontStyle="normal"
        />
        <meta name="color-scheme" content="light" />
        <meta name="supported-color-schemes" content="light" />
      </Head>

      <Preview>{previewText}</Preview>

      <Body
        style={{
          backgroundColor: tokens.paperEdge,
          margin: "0",
          padding: "32px 0",
          fontFamily: tokens.fontSerif,
          WebkitTextSizeAdjust: "100%",
        }}
      >
        <Container
          style={{
            maxWidth: `${tokens.containerWidth}px`,
            margin: "0 auto",
            backgroundColor: tokens.paper,
            padding: "0 36px",
            borderTop: `3px solid ${tokens.ink}`,
            boxShadow: "0 1px 8px rgba(60, 50, 30, 0.08)",
          }}
        >
          {/* Render sections in order from template config */}
          {templateConfig.sections.map((sectionDef: SectionDef) => {
            const renderer = sectionRegistry[sectionDef.id];
            if (!renderer) {
              console.warn(`Unknown section: ${sectionDef.id}`);
              return null;
            }
            return (
              <React.Fragment key={sectionDef.id}>
                {renderer(data)}
              </React.Fragment>
            );
          })}
        </Container>
      </Body>
    </Html>
  );
}
