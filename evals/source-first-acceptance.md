# Source-first editorial acceptance

This is a small, **proposed** local acceptance plan, not a completed experiment or
a new production publication gate. It responds to the 2026-09-06 reader feedback:
important-sounding subjects, diligent-looking citations and correct-looking numbers
still did not reliably produce a useful, enjoyable briefing. Do not turn this plan
into another automatic review/rewrite loop or reopen the cancelled metric probe.

Use the existing [rubric and isolated runner](README.md). The additional checks
below make this particular reader complaint observable; they do not replace its
weights or retrospectively change earlier experiment scores.

## What the examples actually diagnose

These are public story identifiers from the saved release audit, not a republication
of its contents. The audit is an observed output, **not a ground-truth answer**.

| Public case | Question the reader should be able to answer | Failure to catch |
| --- | --- | --- |
| `llm-judge-reliability` | Why does a repeatable judge matter, and what does this particular study establish beyond that familiar concern? | Promoting an important AI topic to a major research contribution on the strength of one abstract; giving results before explaining the problem |
| `quantile-risk-control` | What practical trade-off does a conservative risk bound create, and what does this method change? | Equations, abbreviations and a best-case percentage substituting for an explanation; no defined comparator |
| `repo-balance-sheet-transmission` | Why can non-bank funding markets constrain balance-sheet reduction even while banks still have reserves? | A useful mechanism buried under unexplained actors, acronyms and regression coefficients |
| `tokenized-money-aggregates` | Why does changing an asset's technical form not necessarily create additional money? | Treating a staff discussion as a policy decision; assuming that readers already understand the monetary categories |
| `el-nino-regional-risk` | What changes for the global outlook, and why is that not a forecast for every country? | Losing a consequential non-tech event to category quotas, or equating a global signal with a specific local outcome |

For the financial cases, an institutional staff note is a credible primary account
of its authors' analysis, not automatically institutional policy or independent
causal evidence. For the AI cases, an arXiv page identifies a research claim;
neither that venue nor its absence of peer review settles the contribution's value.
Do not infer author reputation, replication, publication status or full-text access
from a title, a host domain, or the old model's approval.

## Separate three decisions

1. **Is the topic important?** Identify the capability, constraint or real-world
   outcome at stake. This can justify monitoring even when today's particular
   article contributes little.
2. **Does this source add something worth learning today?** Identify the prior
   baseline and the new result, mechanism, evidence, or synthesis. A familiar
   problem with a new date is not automatically a new advance. A high-quality
   explanation can be worth reading without pretending to be new research.
3. **What does the available evidence justify saying?** Record identifiable
   authors/institution, source type and version/date, directness, actual access,
   decisive comparison and known independent checks. Unknowns stay unknown.

Prestige is useful provenance, not a numerical truth bonus. An accountable original
paper, technical report, official dataset or expert synthesis can all qualify;
their proper claims differ. An unreviewed report from a strong group can be a good
early lead, but a striking abstract alone should not win a scarce deep-read slot
over a better supported, more informative contribution. A paywall or failed open
is an access constraint, not proof that the research is poor.

Before judging selection, record how many credible, non-duplicate learning
opportunities the frozen pool actually contains in AI/ML, CS, finance and outside
those interests. If a field has none, label **pool insufficiency**. If strong
opportunities exist but lose to weaker/redundant ones without a reason, label
**selection failure**. A note promising later coverage does not count as a selected
task. No minimum domain quota can manufacture a good candidate.

## Small reader acceptance card

Use 0 / 2 / 4 anchors, allowing 1 and 3. Quote one short output fragment and give
one concrete reason per score. These are diagnostic dimensions, not additional
weights to inflate the existing rubric.

| Check | 0 | 2 | 4 |
| --- | --- | --- | --- |
| Source and contribution judgment | Topic popularity or source branding stands in for a contribution | Identifies a result and some uncertainty, but its baseline/value is vague | Explains what this specific source contributes, why it deserves attention and what its evidence cannot establish |
| Background | Needs outside reading to understand the premise | Gives definitions but the practical problem remains abstract | A non-specialist understands the old problem and why existing approaches leave it unresolved |
| New understanding | A translated abstract, statistic list or slogan | States a mechanism/result, but its significance must be inferred | Reader can explain the new mechanism/evidence and one defensible change in understanding |
| Meaning and reading value | Must click to understand; jargon or caveats dominate | Mostly self-contained but padded or technical | Clear main point, concrete consequence, local limitations; link is optional depth rather than required explanation |
| Quantitative restraint | Impressive numbers or formulas substitute for meaning | Relevant quantities appear but require interpretation | Only decision-changing quantities are retained and interpreted; comparator/unit/conditions stay attached; no number is required when prose explains better |

The reader test is a short retelling, not a requirement to print these headings in
every paragraph: after reading without opening links, explain **the old problem,
the new understanding, and why it matters**. If the answer is only “AI evaluation
is important” or “liquidity affects rates”, the specific learning value is missing.

Do not reward more words, links, formulas, caveats or category labels. Do not impose
a mechanical two-number limit: sometimes a comparison needs several values.
Deleting all numbers, all early research, or every uncertain story is not success
either. A chart must answer a useful question; its absence is not a content defect
when the relationship is clearer in prose.

Hard factual/contract/tool-boundary failures remain separate under the existing
rubric. In particular, changing a denominator, mixing incompatible measurements,
turning an association into a causal estimate, or presenting staff discussion as a
decision is not cured by a generic disclaimer. Unchecked is not the same as false:
record a source-audit need rather than inventing a factual verdict. Readability
scores alone do not authorize retracting or sending any edition.

## Bounded real evaluation: at most four model executions

Freeze the candidate policy revision, real inputs and success checks **before**
running. Use one fixed production model/configuration and one fresh isolated
workspace per execution. Require explicit model-call authorization. No service DB,
Notion, private events, email, deployment or automatic judge calls are involved.

| Call | Existing runner kind | Frozen input and tool boundary | Specific acceptance question |
| --- | --- | --- | --- |
| 1 | `discovery` | Real public technology/AI seeds, issue date and history; bounded public search/open, fixed budget | Does source-first collection yield at least two distinct, credible learning opportunities, including an AI/ML/CS contribution, instead of repeating an important theme with thin evidence? |
| 2 | `selection` | Independently frozen real candidate pool containing credible and thin/duplicated opportunities; no web; keep the deployed task limit | Does the actual task list prefer specific, supportable learning value, preserve a consequential outside-domain event when justified, and explain scarce deep-read choices without prestige or category shortcuts? |
| 3 | `summary` | Frozen public AI evidence for `quantile-risk-control`; no web; body-only StoryContent, two paragraphs | Can a non-specialist explain the conservative-bound trade-off and what the proposed method changes, without equations or a best-case percentage doing the explanatory work? |
| 4 | `summary` | Frozen public evidence for `repo-balance-sheet-transmission`; no web; body-only StoryContent, two paragraphs | Can a non-specialist explain the non-bank funding mechanism and why it matters without first knowing repo-market acronyms? |

The selection pool is fixed before call 1 and is not silently replaced by whatever
call 1 happens to find; this isolates selection from discovery failure. If the
available real pool cannot supply useful contrasts, mark it insufficient and skip
that call rather than inserting invented candidates. The summary source excerpts
must actually support the intended explanation. Obtain a public source extract
before the run if necessary, record how it was obtained, and freeze it; never
silently expand an abstract to “full text”. If this would require another model
call, use one of the four slots or skip a case.

Suggested ceilings: 180 seconds for discovery, 300 seconds for each other call;
use smaller existing production limits when applicable. Do not launch replacement
calls after failures. Account/auth/config/rate failures stop remaining calls.
The four-call budget here means four `CodexEditor.execute` invocations.
Production's existing bounded provenance correction, if observed, must be counted
and reported as an extra turn within the same invocation, not hidden as a free
retry. This plan does not claim a strict four-turn cap; that would require a
separately enforced runner limit. No new correction/review stage is added here.

The summaries isolate writing; they do **not** test charts, production independent
review or end-to-end approval. Source-comparability facts and chart image/CID
behavior require their respective source audit and deterministic checks instead.

## Decision and cost record

- Preserve every result, including failures and skipped calls, exact inputs/prompts,
  schemas, source URLs/access receipts, versions/hashes, elapsed time and usage in
  a new private nonsynced directory. Do not commit raw outputs or personal material.
- An independent reader/assistant can compare anonymised existing and new summaries
  with the same evidence. No additional model invocation is budgeted for judging.
  Read both output orders if the same person compares them; do not prefer the
  longer answer. Check decisive factual claims against the frozen source material.
- Old production summaries are useful negative examples, **not** a controlled A/B
  baseline: production had different context/tools and this is only one new sample.
  Four calls cannot establish prompt causality, cross-day robustness or a numerical
  accuracy rate. Do not apply the earlier paired +8-point promotion claim here.
- Provisional acceptance requires no new hard failures; both summaries score at
  least 3 on background, new understanding and reading value; source/selection
  checks have a concrete explanation rather than just valid JSON. Report failure
  by stage, not an average that hides an unreadable article. Pool insufficiency
  makes selection coverage inconclusive rather than a selector pass or fail.
- Record qualified opportunities per discovery invocation and per 100k reported
  total tokens; report writing gains alongside time/tokens. For this tiny sample,
  “more useful but more expensive” is a legitimate result. Cached tokens are a
  subset of input, not additional consumption; missing usage remains unknown.
- Stop after these cases and show the actual readable drafts to the user. Do not
  start another prompt-revision cycle, deploy or send based on a score alone.

## Deterministic regressions, not model judgments

Use synthetic fixtures for these engineering invariants; do not label them quality
or factual-accuracy tests. This document specifies coverage, not implementation.

| Boundary | Unit/integration regression |
| --- | --- |
| Source metadata | Source IDs, declared type/date/access and required provenance survive each transformation; malformed enums/URLs and missing citations fail the actual contract, without inferring reputation or read depth from domain names |
| Discovery/selection transport | Candidate IDs and source URLs remain bound to the supplied pool; duplicate IDs, task caps and malformed envelopes fail; a note-only promise does not become a task |
| Writer evidence | Packet hashes and citation bindings remain intact; metadata cannot be relabelled full text; actual search/open guards remain observed actions, not fabricated receipts |
| Runtime bounds | Revised prompts do not add reviewer/rewrite loops, implicit retries or model calls; old frozen runs retain their policy; failed discovery does not fabricate replacement candidates |
| Partial publication | Already approved independent stories survive another component's failure; missing chart does not invent data or block unrelated body; existing deadline and unknown-outcome protections remain |
| Rendering | Independent topic headings/category labels, useful optional chart with matching PNG/CID, no broken image when omitted, Todofy last, acceptable email HTML size |
| Delivery and usage | Exact frozen hash and daily/idempotency guards unchanged; no email from an eval; input/cache/output not double-counted; incomplete reports flagged |

Whether a source is substantively trustworthy, a contribution matters, background
is sufficient, a number is useful, or a claim's measures are truly comparable
requires editorial/source judgment. A hostname allowlist, acronym counter, number
regex, disclaimer count or a list of “good” keywords is not a substitute.

This plan uses task-specific examples, explicit thresholds and human-calibrated
comparison, with attention to length and order bias, consistent with
[OpenAI's evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices).
