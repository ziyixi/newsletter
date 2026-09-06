# Editable editorial DAG and measured usage

## Configuration, not executable code

Live environment deployments default to `NEWSLETTER_WORKFLOW=dag`. The packaged
recipe is `src/newsletter/workflows/daily.yaml`; its six operator directions are
under `src/newsletter/instructions/discovery/`. Override them with an explicit,
read-only `NEWSLETTER_WORKFLOW_FILE` / `NEWSLETTER_DISCOVERY_DIR` mount. No HTTP
caller can supply local paths, prompts, YAML or credentials. Existing mock mode
and `NEWSLETTER_WORKFLOW=legacy` retain the old deterministic/serialized adapter
path for compatibility, never as a fallback from failed live research.

Version 1 supports registered node types, literal bounded parameters, `needs`,
and a bounded `map: {from: <direct-dependency>.<field>, max_items: N}`. The only
run-level map in the default recipe is `run.instructions`. YAML aliases, tags,
duplicate keys, unknown types, cycles, shell/Python/import hooks, secret keys and
environment expansion are not a workflow feature. Definitions are checked at
startup and each new run; the service additionally verifies mandatory editorial
roles, dependency paths and the single gap-research stage. Renaming node IDs is
fine when all references are updated. New APIs require a reviewed adapter.

The default stages are history, public metadata feeds, per-direction discovery,
deduplication, selection, per-question research, composition, gap planning,
optional follow-up research, finalization and a new-session review. Private
Todofy, rendering, Notion confirmation and delivery remain a protected service
tail: YAML cannot grant publication or remove its safety checks.

## Breadth, depth and resource budgets

- Discovery: up to five candidates per direction; no quota to fill.
- Candidate pool: up to 30 deduplicated lightweight leads.
- Selection: up to eight research questions by default; configurable up to 12.
- Research: usually one self-contained packet per question, at most two; all
  source URLs require fresh individual open provenance. Metadata is not evidence
  of full-text reading. The existing 32-packet contract ceiling still applies.
- Gap planning: at most three questions in one explicit follow-up stage. Empty
  follow-up is a persisted skipped node, not a loop. Finalization cannot produce
  another set of supplemental packets; unresolved critical claims must be removed
  or held. Independent-session review is not independent-model verification.
- Models execute serially against one dedicated login. More map items are not
  automatically more concurrent processes. Node deadlines are in the recipe;
  `NEWSLETTER_WORKFLOW_TIMEOUT_SECONDS=5400` bounds total elapsed collection time.
  Use `newsletter-trigger --send --timeout 7200` to leave persistence/render/send
  headroom. Cron remains external and unchanged at 15:00 UTC daily.

Crossref's Nature/Science journal metadata and Nature RSS provide a small,
keyless supplement. Fixed public HTTPS endpoints have bounded response sizes,
timeouts, no redirects/proxies/credentials and no automatic retry. Provider
failure is an explicit diagnostic, not proof that no publications exist. DOI,
arXiv versions, URL aliases and shared event identities reduce repeated coverage.
Historical candidate dispositions are machine-maintained, not inferred clicks.
An unchanged watch item is not automatically republished.

## State, recovery and Notion

SQLite remains authoritative. `collection_workflow_snapshots` freezes the DAG,
operator instructions, editorial policies, date, model, public history and total
budget before the HTTP run is accepted. `workflow_runs`, `workflow_attempts` and
`workflow_artifacts` record each node/item and immutable outputs. Map input items
are fixed once with stable IDs. New maps preserve the upstream array's priority
order; replaying different order conflicts, and existing expansions are never
reordered or migrated. No transaction spans a model or provider call.

Already completed stages survive restart. An in-flight request becomes `unknown`
and is not blindly reissued; operators must inspect before arranging a retry.
Optional source/research failures can be marked degraded and their missing
coverage is passed into drafting/review. Authentication, configuration and model
quota failures always stop, regardless of `on_error: continue`. There is no
general retry endpoint, distributed executor, internal cron or implicit backfill.

The candidate index in Notion is a bounded readable list, explicitly marked as
unverified discovery metadata. Full research packets are separate pages. It is
one-way projection, not a bidirectional Notion database editor or manual rating
requirement. Optional index/unused packet projection failure does not block the
edition. All packets used by body citations, graph points or the research
introduction card must be confirmed projected before the *first send attempt*.
This is checked in Store, independently of graph shape. Unknown writes are never
automatically recreated. A ready preview may exist while the outer run is held
for required Notion persistence.

`GET /v1/runs/{id}` exposes the frozen definition hash, node states, candidate and
completed research-task counts, and usage summary. It does not expose credentials
or raw model transcripts. Candidate/history and archive diagnostics are private
SQLite state, not a public web endpoint. An interrupted or rejected run retains
its already acquired materials.

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

The small lower-right footer says **recorded** tokens, with partial/unknown labels
when necessary. It is not a cost estimate or a ChatGPT plan allowance meter.
Todofy's current response does not return its upstream Gemini usage: that usage
is explicitly excluded, not invented from logs or assumed zero. Mock footer text
is explicitly demonstration-only. Old editions are not retroactively rewritten.

Official reference: [Codex app-server token usage events](https://learn.chatgpt.com/docs/app-server).
The implementation also checks the installed SDK's pinned event schema; no raw
account/login or model transcript is persisted for accounting.

## Release checks

Run `make check`, `make smoke`, `make smoke-codex`, `make build` and the installed
wheel smoke. Tests cover graph validation, stable maps, failure coverage,
transactional edition bindings, replay conflicts, usage deduplication, partial
usage, Notion adopted/unused separation, and same-date send idempotency. GitHub
builds and probes the exact final native Linux/amd64 image before pushing it.
Update the deployment's immutable digest and trigger timeout together. Preserve
private env, current Codex login and existing SQLite delivery records; never use
an empty database or new issue date to bypass a previous delivery attempt.
