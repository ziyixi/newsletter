import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading } from "./styles";
import type { ContentSection } from "../types";

interface CustomSectionProps {
  section: ContentSection;
}

export function CustomSectionBlock({ section }: CustomSectionProps) {
  return (
    <Section style={{ padding: tokens.sectionPadding }}>
      <SectionHeading icon={section.icon || "📌"}>
        {section.title}
      </SectionHeading>

      {/* Render raw HTML content inside a styled container */}
      <div
        style={{
          fontFamily: tokens.fontKai,
          fontSize: "14px",
          color: tokens.inkLight,
          lineHeight: "1.8",
        }}
        dangerouslySetInnerHTML={{ __html: section.contentHtml }}
      />
    </Section>
  );
}

// ─────────────────────────────────────────────
// Render a list of custom sections
// ─────────────────────────────────────────────

interface CustomSectionsProps {
  sections: ContentSection[];
}

export function CustomSections({ sections }: CustomSectionsProps) {
  if (!sections.length) return null;

  return (
    <>
      {sections.map((section, i) => (
        <CustomSectionBlock key={i} section={section} />
      ))}
    </>
  );
}
