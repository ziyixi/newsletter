import * as React from "react";
import { Section, Text } from "@react-email/components";
import { tokens, SectionHeading, ThinRule } from "./styles";
import type { TodoTask } from "../types";

// ─────────────────────────────────────────────
// Todo Tasks — 今日待办
// ─────────────────────────────────────────────

interface TodoTasksProps {
    tasks: TodoTask[];
}

export function TodoTasks({ tasks }: TodoTasksProps) {
    if (!tasks.length) return null;

    return (
        <Section style={{ padding: tokens.sectionPadding }}>
            <SectionHeading icon="📋">今日待办</SectionHeading>

            <table
                width="100%"
                cellPadding={0}
                cellSpacing={0}
                style={{
                    backgroundColor: tokens.sectionBg,
                    border: `1px solid ${tokens.sectionBorder}`,
                }}
            >
                <tbody>
                    {tasks.map((task, i) => (
                        <React.Fragment key={i}>
                            {i > 0 && (
                                <tr>
                                    <td colSpan={2} style={{ padding: "0 12px" }}>
                                        <table width="100%" cellPadding={0} cellSpacing={0}>
                                            <tbody>
                                                <tr>
                                                    <td style={{ borderTop: `1px solid ${tokens.ruleLight}` }} />
                                                </tr>
                                            </tbody>
                                        </table>
                                    </td>
                                </tr>
                            )}
                            <tr>
                                {/* Rank number — gold accent */}
                                <td
                                    style={{
                                        verticalAlign: "top",
                                        width: "36px",
                                        padding: "10px 4px 10px 12px",
                                    }}
                                >
                                    <Text
                                        style={{
                                            fontFamily: tokens.fontSerif,
                                            fontSize: "16px",
                                            fontWeight: 700,
                                            color: tokens.gold,
                                            margin: "0",
                                            lineHeight: "1.2",
                                        }}
                                    >
                                        {task.rank}
                                    </Text>
                                </td>

                                {/* Content */}
                                <td style={{ verticalAlign: "top", padding: "10px 12px 10px 4px" }}>
                                    <Text
                                        style={{
                                            fontFamily: tokens.fontKai,
                                            fontSize: "12px",
                                            fontWeight: 700,
                                            color: tokens.ink,
                                            lineHeight: "1.4",
                                            margin: "0 0 2px 0",
                                        }}
                                    >
                                        {task.title}
                                    </Text>

                                    <Text
                                        style={{
                                            fontFamily: tokens.fontSans,
                                            fontSize: "11px",
                                            color: tokens.inkMuted,
                                            lineHeight: "1.5",
                                            margin: "0",
                                        }}
                                    >
                                        {task.reason}
                                    </Text>
                                </td>
                            </tr>
                        </React.Fragment>
                    ))}
                </tbody>
            </table>
        </Section>
    );
}
