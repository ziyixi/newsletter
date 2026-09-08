# News-first editorial acceptance

The new defaults are a policy change, not a claim that an offline test measures
real editorial quality. Existing v1/v2/v3 results remain historical evidence for
their exact old prompts and must not be described as validating this policy.

## Deterministic contract

`tests/test_news_first_policy.py` checks the new, explicitly frozen
`content_config` path. Old runs retain their old parser and prompts.

| Scenario | Required behaviour |
| --- | --- |
| Research-heavy pool, concrete news late in input | Keep room for news; default research/unknown pool allowance is 10 of 30 |
| Multiple paper topics selected | Retain at most the configured allowance, before starting research/writers |
| One task hides several papers or references their candidate URLs | Do not count the bundle as one news topic |
| Paper changes title to industry news | Publication identity remains research evidence |
| Real-world event cites a background paper | A background evidence URL alone does not change the event into a paper topic |
| Classification or actual-change explanation missing | Treat as unknown; never silently fill a news seat |
| Too little eligible news | A shorter selected issue remains valid; do not refill with routine papers |
| Operator changes paper/deep/item limits | Frozen limits reach selection and planning; no constant-only policy |
| Restart or old replay | Stored run configuration and already-frozen publication remain authoritative |

Classification is not a proof of truth. Semantic choices can still be wrong;
source identity and conservative unknown handling limit obvious loopholes but do
not guarantee that a model recognises every press-release wrapper around a paper.
Changing the recipe does not add another late-stage whole-issue approval gate.

## Content-quality review when reviewing a real preview

Use the same candidate set to compare policies; do not call the new policy good
merely because it has fewer papers. Inspect whether a consequential real-world
event beats a routine increment, whether the explanation states the previous
situation and concrete change, and whether it distinguishes actual availability
from an announced ambition. Major original research can still justify the lead.

Look across energy/manufacturing, medical access, economic rules, world events
and technology availability; missing genuinely important coverage matters more
than filling a fixed list of sectors. Early signals may be valuable but should
state what is still missing. No forced daily “game changer”.

The v2 economy/technology discovery files are versioned inputs for this policy,
not newly measured live-model quality results. Run a separate authorised preview
before asserting improved real-world selection; never send email from evals.
