# Editorial prompt experiments

These are **local quality experiments**, not email delivery or production acceptance.
Live calls require an explicit opt-in and the service's isolated ChatGPT login. No
Notion, mailbox, service database writes, production deployment or email delivery.
Raw datasets, requests, outputs and usage belong in a new private directory outside
the repository and cloud-synchronised folders; do not commit credentials or personal events.

Recorded experiment: [2026-09-06 — 34 real calls, three revisions and held-out comparisons](results/2026-09-06.md).

## Running a comparison

Use `uv run --locked --extra codex python scripts/evaluate_prompts.py --help`.
Each invocation requires `--suite /private/path/suite.json`, a **new** `--output`
directory, `--codex-home /private/path/isolated-login`, and `--allow-model-calls`.
The runner does not load `.env`; its default model is the production
`gpt-5.6-sol`. Use the same model and timeout for both sides of a comparison.
Known macOS cloud-sync roots, Git checkouts, auth homes and symlinks are rejected
as output locations. Other custom sync folders must also be avoided by the operator.

A suite has `cases`, each with an `id`, `kind`, `prompt` object, `instructions`,
production-compatible `schema`, `validation`, and optional `allow_web` (default
false). `validation` has the following stage-specific fields:

| kind | validation fields | accepted output |
| --- | --- | --- |
| `selection` | `candidate_ids`, `source_urls`, `max_tasks` | production planning envelope |
| `summary` | `story_id`, `packets`, `paragraph_limit` | body-only StoryContent; no approval, chart or reading card |
| `discovery` | `direction`, `issue_date`, `seeds`, `history` | production discovery envelope; requires actual search/open |

Capture production inputs before making a prompt revision; strip personal event,
mailbox, auth and unrelated service data. Do not substitute mock packets when
claiming editorial quality. Synthetic fixtures in the runner's unit tests test
only execution boundaries, not newsletter quality.

The output directory contains `suite.json`, a version/hash manifest, each exact
request, raw output when available, validated output, elapsed time, observed web
actions and cumulative usage events. `summary.json` includes failures and skips.
`valid` means the application contract passed, **not** that facts or prose passed.
The runner never retries a call. Any bounded correction inside production execute
is recorded separately; account-level errors stop remaining calls. Usage covers
these local model invocations, not the surrounding assistant conversation or judges.

## Success criteria, fixed before the first comparison

The reader should understand consequential changes and acquire useful new ways of
thinking. Technological progress, especially AI/ML/CS, and finance deserve editorial
attention, without suppressing consequential events in science, health and society.
An interesting topic is not automatically a verified breakthrough. More categories,
more citations, more confident language and more words do not themselves earn points.

### Hard gates (reported separately, cannot be offset by a high score)

- Output passes the actual application contract; selection references only supplied
  candidate IDs/URLs; summaries cite only supplied evidence in closed-book trials.
- No invented data, source, publication status, first-ever claim or causal effect.
  Material disagreements with the supplied evidence are marked for source audit.
- Distinguish event/publication/update dates, new result versus new announcement,
  author claims versus independent checks, abstract versus full paper.
- Follow the experiment's tool boundary. No tools for frozen-input comparisons;
  research trials permit public search/open but no business side effects.
- Carry a concrete contradiction or known correction into the conclusion and title;
  a generic disclaimer does not neutralise a false headline.

### Selection rubric (0–4 per criterion, weighted to 100)

| Criterion | Weight | 0 | 2 | 4 |
| --- | ---: | --- | --- | --- |
| Substantive progress / importance | 25 | Prestige or headline only | Useful event, unclear bottleneck | Identifies changed capability, constraint or consequential real-world mechanism |
| Learning opportunity | 20 | Repeats familiar slogans | Topic is relevant | Asks a precise question whose answer can change the reader's mental model |
| Evidence and novelty calibration | 20 | Treats metadata or claims as proof | Names some missing evidence | Separates prior baseline, new evidence and decisive unknowns without discarding informative early work |
| Portfolio opportunity cost | 20 | Redundant or arbitrary quotas | Several useful fields | Protects strong AI/ML/CS and finance learning opportunities while retaining genuinely consequential outside-domain events; explains scarce deep-read slots |
| Research tractability | 15 | “Investigate everything” | Generic method/result checklist | A bounded question, necessary comparison and decision-changing check achievable in the workflow budget |

### Summary rubric (0–4 per criterion, weighted to 100)

| Criterion | Weight | 0 | 2 | 4 |
| Explanation | 30 | Title translation / jargon | Describes method and outcome | Explains bottleneck, how the mechanism changes it, baseline and evidence in ordinary precise language |
| Evidence fidelity | 25 | Material unsupported conclusion | Generally accurate, vague boundary | Quantities, attribution, access scope and the conclusion-changing limitation match the actual evidence |
| Perspective gained | 20 | “Important / promising” | Plausible generic implication | One specific, defensible change in understanding or open question; no forced cross-domain analogy |
| Reading value | 15 | Must click to understand / repetitive caveats | Understandable but padded | Self-contained, concise, prioritised; limitations beside affected claims, no repeated abstract or legalistic padding |
| Temporal framing | 10 | Recycled event as first/new breakthrough | Dates correct, baseline unclear | Precisely states what changed and what was already true; uncertainty about dates is explicit |

Intermediate scores 1 and 3 are allowed. Scores require a concrete quoted output
fragment and a reason. “Could not verify” is not automatically a hard factual error;
label the uncertainty and audit the claim before making that determination.

### Discovery and engineering diagnostics (not added to prose scores)

- Qualified learning opportunities per direction and per 100k total tokens;
  new bottleneck/mechanism, source accessibility, date and decisive unknown recorded.
- Pool sufficiency: count strong AI/ML, CS and finance opportunities before judging
  the selector. If they are absent, diagnose retrieval, not failed selection recall.
- Marginal variety: distinct mechanisms/questions, not number of topic labels;
  record substantive non-core opportunities, including inconvenient counterevidence.
- Schema success, tool-policy compliance, latency, input/cache/output tokens, retries
  and missing usage. Cached input is part of input, not extra token consumption.

## Comparison protocol

1. Freeze real public inputs and hashes before each comparison. Keep development
   and held-out pools separate. Two independent collections on one day are not a
   cross-day holdout; explicitly report that limitation.
2. Compare the current prompt (baseline), a first candidate, then a revised candidate
   driven by observed weaknesses. Keep model, schema, input and budgets identical.
3. Closed-book summary trials isolate writing from search variability; production
   search/review acceptance is a separate test and is never claimed by these scores.
4. Repeat selection with reordered candidates. Score anonymised outputs using the
   same rubric; pairwise judges do not see prompt names. A second, order-swapped
   judgement checks obvious positional preference. Root audits decisive claims.
5. Use a held-out pool only after choosing the revision. Report every attempted
   call, including failures and ties. Do not select the best random sample.
6. Promotion is provisional only: no new hard failures, at least +8/100 mean on the
   targeted stage, and a majority of non-tied pairwise comparisons. Fewer cases or
   inconsistent results mean “promising / inconclusive”, not proven improvement.
   Source evidence and user judgement outrank a model judge's score.
7. Keep the accepted change narrow. Do not deploy or send an email as part of this
   experiment. More days and actual reader feedback are needed for stable quality
   estimates; unit-test counts are not editorial accuracy estimates.

The methodology follows [OpenAI's evaluation guidance](https://developers.openai.com/api/docs/guides/evaluation-best-practices):
task-specific cases, explicit criteria, held-out comparisons and human calibration.
The experiments use the existing local SDK transport, not a hosted Evals service.
