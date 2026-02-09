import { render } from "@react-email/render";
import React from "react";
import Newsletter from "../emails/newsletter";
import type { NewsletterProps } from "../emails/types";

/**
 * Render the newsletter template to an HTML string.
 */
export async function renderNewsletter(
  props: NewsletterProps
): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const element = React.createElement(Newsletter as any, props);
  const html = await render(element);
  return html;
}

/**
 * Render the newsletter template to plain text (fallback).
 */
export async function renderNewsletterText(
  props: NewsletterProps
): Promise<string> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const element = React.createElement(Newsletter as any, props);
  const text = await render(element, { plainText: true });
  return text;
}
