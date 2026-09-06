# Editable editorial DAG and measured usage

## Topic-first publication

Live deployments default to `NEWSLETTER_WORKFLOW=dag` and the packaged
`src/newsletter/workflows/daily.yaml` (`daily-topics`). Six discovery directions
remain under `instructions/discovery/`. The service, not an app routine or a
human watching logs, performs the entire bounded preparation flow:

```text
public history + unresolved topics + metadata feeds
                  ↓
six-direction discovery → deduplicate → select up to 8 topics
                  ↓
freeze complete topic plan
                  ↓
each topic: research a brief + independently review → checkpoint
                  ↓
top topics: deeper investigation + independently review → checkpoint
                  ↓
deterministic publication from approved whole versions
                  ↓
private Todofy → render + frozen hash → protected external send
```

All brief attempts precede deep attempts. Selection compares the supplied pool
without another research pass; discovery collects bounded leads, not full papers.
Up to four selected topics receive a
deepening attempt; at most two complete deep pieces are displayed. Other topics
use their separately researched and approved brief, not a truncated deep piece.
Discovery and ranking do not count as verified writing. A minimal watch signal
must independently verify that an event occurred, not merely attach a disclaimer.

Each story has independent body, recommended-reading card, chart and signal
assessments. The body includes its title, paragraphs and limitations as one
indivisible version. An optional chart/card problem removes that component, not
the body or another topic. The body must stand alone without referring to a
missing graphic/card. A blocked body gets at most one targeted rewrite and a new
review; there is no whole-issue HOLD/rewrite/review loop. Review sessions search
and open every cited source. Observed opens and exact hashes are necessary
provenance, not a guarantee of factual correctness or independent-model review.

Each published topic retains its own heading, paragraphs, category and local
limitations in the email. Up to 12 sections are accepted; briefs are not merged
into a single world section. New writing uses explicit AI/ML, science, world,
economy, technology or health categories, while legacy feature/context values
remain readable. Graphs can accompany a brief when verified comparable data
help explain it; they do not depend on successful deepening. No data means no
invented graph. Empty drafts do not receive an empty review; malformed components
receive bounded, specific diagnostics for the existing repair opportunity.

An approved brief/signal is synchronously checkpointed before further repair or
deepening. Every selected topic receives an explicit `deep`, `brief`, `watch`
or `deferred` disposition. Deferred/watch questions and relevant unfinished
depth remain public follow-up context for future discovery; no reader clicks or
manual rating workflow is required. This history is a lead, never recycled
evidence. A later confirmed material factual error can withdraw only the exact
affected approved version (and exact signal if affected), with a source-backed
independent receipt. Ordinary deepening failure never retracts a brief.

## Deadline and failure behavior

The total elapsed research budget remains 5400 seconds from the accepted run's
frozen start. Discovery is bounded per direction; brief attempts have 300 seconds,
deep attempts 420 seconds. Models execute serially against one dedicated login.
More map items do not imply concurrent model processes. The default pool holds
30 candidates; selection allows at most eight topics (operator ceiling 12).

At completion, deadline, provider fatal failure, or recovery of an unknown model
attempt, a local deterministic tail freezes the best already approved complete
units. It performs no model call and changes no completed attempt or review.
Authentication, configuration and quota failure stop further model work; they
do not invalidate previously approved unaffected content. A frozen publication
is immutable and restartable through the local edition/render tail.

If nothing has independently passed, the run remains blocked with
`no_publishable_content`: no invented article, empty mock issue, old issue
relabelled as today, or unverified emergency email is sent. Storage corruption,
privacy/recipient failure, render/hash mismatch and ambiguous previous send
remain hard stops. Daily delivery is more resilient, not an unconditional
guarantee during a total source/account/mail outage.

Use the external `newsletter-trigger --send --timeout 7200` for collection,
render and delivery headroom. Cron stays external at 15:00 UTC daily, and the
service never schedules its own next run. The research deadline is relative to
the trigger, not a promise that the email arrives precisely at 15:00.

## Durable state and the Notion mirror

SQLite is authoritative. Frozen run inputs include the DAG, instructions,
editorial/reader policies, date, model, public history, pending topics and budget.
`workflow_runs`, `workflow_attempts` and `workflow_artifacts` retain exact
attempts and outputs. Map identities and priority order freeze once; replaying a
changed expansion conflicts. Unknown provider requests are not blindly replayed.

`publication_plans` records all selected tasks; `publication_units` is an
append-only version/checkpoint ledger; `publication_snapshots` freezes the
assembled result and coverage. A snapshot must reconstruct exactly from the
stored validated approvals and evidence. Every cited body, graph and reading
source remains bound to local packet snapshots; optional supporting references
are checked just like the primary reading citation.

For new topic editions, `projection_required=False` is an immutable internal
binding. Notion is a one-way outbox mirror, not a critical publication dependency.
The worker advances topic research before draining background projections.
Candidate-index pages are labelled unverified metadata; research pages are
separate. Failed or ambiguous Notion writes stay explicit and are never blindly
recreated. A temporary Notion/Todofy startup outage may be reported as degraded;
invalid credentials, schema or required local/Codex runtime still fail startup.

Old frozen editions retain `projection_required=True` and their original
adopted-material Notion confirmation barrier. The former whole-issue recipe is
kept as `workflows/legacy-daily.yaml` for compatibility and regression. Selecting
`NEWSLETTER_WORKFLOW=legacy` is the earlier per-direction adapter, a different
compatibility path; it is never an automatic fallback from failed live research.
Old continuations, receipts and deadlines are not rewritten by this upgrade.

`GET /v1/runs/{id}` exposes the actual graph progress, usage and final
`publication` coverage. The edition carries the same coverage. A failed research
graph can therefore coexist honestly with a successfully prepared partial issue.
No credential or raw model transcript is returned. Todofy remains a private
bounded tail, never entering public prompts, packets or Notion.

## Editing the recipe safely

Override `NEWSLETTER_WORKFLOW_FILE` and `NEWSLETTER_DISCOVERY_DIR` only via
explicit read-only operator mounts. HTTP callers cannot supply local paths,
prompts, YAML or credentials. Version 1 supports registered types, literal
bounded parameters, `needs` and bounded direct-dependency maps. The sole run
map is `run.instructions`. Aliases, tags, duplicate keys, unknown types, cycles,
shell/Python hooks and environment expansion are rejected.

The code validates all required roles and dependency paths, full selected-topic
brief coverage, bounded deepening and the non-model publication tail. A YAML
change cannot grant send authority or waive evidence checks. New APIs require a
reviewed adapter. Public fixed-endpoint Crossref/Nature metadata remain optional
discovery supplements, not full-text evidence; DOI/version/event deduplication
and historical dispositions reduce repetitive coverage.

## Token accounting

The pinned Python SDK emits `thread/tokenUsage/updated`. Its `tokenUsage.total`
is a cumulative thread snapshot. Each `CodexEditor.execute` creates one fresh
thread; a bounded source-provenance correction reuses that thread. We upsert the
latest snapshot per invocation in `model_usage`, never add snapshots or correction
totals again. Input, cached input, output, reasoning output and provider total
are retained. Cached input and reasoning output are subsets. SDK rounds are not
counts of underlying API requests.

All DAG stages run within the same durable run usage scope. The ledger preserves
reports received before failed/cancelled/invalid results; missing reports and
unfinished invocations mark the summary partial. Provider totals are retained,
not replaced by estimated context sizes. The frozen edition and HTML/text footer
include this summary, so changing it changes the approved render hash.
For upgrade continuations, querying either run includes the original and repair
usage by unique invocation ID; no ledger rows are copied or counted twice.

The small lower-right footer says **recorded** tokens, with mutually exclusive
uncached input, cached input and output counts, plus partial/unknown labels
when necessary. It is not a cost estimate or a ChatGPT plan allowance meter.
Todofy's current response does not return its upstream Gemini usage: that usage
is explicitly excluded, not invented from logs or assumed zero. Mock footer text
is explicitly demonstration-only. Old editions are not retroactively rewritten.

Official reference: [Codex app-server token usage events](https://learn.chatgpt.com/docs/app-server).
The implementation also checks the installed SDK's pinned event schema; no raw
account/login or model transcript is persisted for accounting.

## Release checks

After correcting a shared story-writer startup configuration failure, an
operator may explicitly call `POST /v1/runs/{parent_id}/retry-stories` with the
editor-role token and the existing `StartRunRequest` shape:
`{"request_key":"one-explicit-story-restart","issue_date":"YYYY-MM-DD"}`.
This creates at most **one new child per parent**, not a reset of the failed run.
The same key retrieves that child, including after restart; another key or a
retry of the child is rejected. The endpoint never sends mail.

Eligibility is deliberately narrow: the parent must be terminal
`no_publishable_content`, have no edition, frozen publication, approved body or
signal, and have intact successful history/feed/discovery/selection/plan
receipts. It accepts either a first-writer `configuration` failure or the older
all-writer `writer:unavailable` launch-failure shape with one failed completed
turn per writer and no token-usage report. Authentication, quota, timeout,
incomplete/unknown turns and editorial-review rejection are not launch retries.
Missing token reports remain **unknown consumption**, never zero.

The child's SQLite `workflow_story_replays` receipt binds the source definition,
inputs, selected tasks and every reused artifact hash. Local child attempts
recheck those hashes and original input/map receipts immediately before reuse;
they do not rerun feeds, discovery or ranking, nor repeat Notion side effects.
All story writing and independent review run afresh. The original issue date,
model, instructions, policy and recipe stay frozen; only the explicitly created
child gets its own bounded start time. Parent attempts remain unchanged.
The child's token footer includes parent and child invocation records exactly
once, including missing/partial parent usage, so reused research cost is visible.
The ordinary daily-send guard is unchanged; an explicitly authorized corrected
test still uses the separate verification route below.

An explicitly requested corrected-email test uses
`POST /v1/editions/{id}/send-verification` with the same public
`SendEditionRequest` body and send-role authentication. It requires a distinct
ready edition, its exact frozen render hash and a confirmed original delivery
for that date. Without any extra header, the separate `verification_sends`
ledger still allows only one such attempt per date. If the user explicitly
requests another new test edition, an operator must add
`X-Newsletter-Verification-After: <latest accepted verification edition UUID>`
alongside the new edition's exact render hash and stable request key. The entire
same-date chain must have confirmed acceptance; a predecessor permits only one
successor. Stale approvals and any failed/unknown ancestor block a new send.
A repeated frozen approval never calls the provider again, including after an
unknown outcome or a later successor. Original daily receipts remain unchanged.
Cron and the standard trigger never use this endpoint; it is not an automatic
retry or a way to bypass a failed/unknown daily send.

The ledger migration copies existing receipts in one SQLite transaction. Do not
downgrade to the old one-row-per-date schema after creating successors, or
restore a pre-send backup after any new delivery: either would discard evidence
needed to prevent duplicate sends. Code rollback must retain the current ledger
and its idempotency checks.

Run `make check`, `make smoke`, `make smoke-codex`, `make build` and the installed
wheel smoke. Tests cover graph validation, stable maps, failure coverage,
transactional edition bindings, replay conflicts, usage deduplication, partial
usage, Notion adopted/unused separation, and same-date send idempotency. GitHub
builds and probes the exact final native Linux/amd64 image before pushing it.
Update the deployment's immutable digest and trigger timeout together. Preserve
private env, current Codex login and existing SQLite delivery records; never use
an empty database or new issue date to bypass a previous delivery attempt.
