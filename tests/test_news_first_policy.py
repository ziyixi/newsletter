"""Deterministic news/research budgets, not a claim of perfect LLM judgement."""

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from test_publication import result as publication_result
from test_publication import task as publication_task
from test_workflow_content import DAY, Engine, candidate, discovered, planned, task
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.collection.instructions import Instruction
from newsletter.content_config import build_snapshot, packaged_snapshot
from newsletter.contracts import parse_message
from newsletter.errors import EditorError
from newsletter.store import Store
from newsletter.workflow.content import (
    _DISCOVERY,
    _SAFETY,
    _SELECTION,
    DEFAULT_DISCOVERY_POLICY,
    DEFAULT_SELECTION_POLICY,
    ContentPreparation,
    candidate_budget,
    candidate_classification,
    editorial_limits,
    parse_classified_plan,
    parse_discovery,
)
from newsletter.workflow.definition import load_definition
from newsletter.workflow.engine import NodeContext
from newsletter.workflow.publication import PublicationRepository
from newsletter.workflow.schema import discovery_schema, planning_schema
from newsletter.workflow.story_nodes import StoryNodes, freeze_publication


def config(**limits):
    return {
        "schema_version": 1,
        "revision": "fixture-config",
        "digest": "fixture-only",
        "editorial": {
            "max_public_items": 6,
            "max_research_items": 1,
            "max_deep": 1,
            "max_research_candidates": 10,
            **limits,
        },
        "files": {},
    }


def news(number=1, **changes):
    result = candidate(
        id=f"news-{number}",
        direction="03-world",
        doi="",
        version="",
        title=f"A concrete real-world development {number}",
        url=f"https://example.org/developments/{number}",
    )
    result.update(changes)
    return result


def paper(number=1, **changes):
    return candidate(
        id=f"paper-{number}",
        title=f"Synthetic research candidate {number}",
        url=f"https://arxiv.org/abs/2609.{number:05d}",
        **changes,
    )


def classifications(*candidates):
    return {
        c["id"]: {
            "kind": "news",
            "basis": "Previously unavailable treatment is now approved for a defined population.",
        }
        for c in candidates
    }


def topic(c, number=1, **changes):
    return task(
        id=f"topic-{number}",
        candidate_ids=[c["id"]],
        source_urls=[c["url"]],
        priority=number,
        editorial_kind="news",
        **changes,
    )


def selected(candidates, tasks, **limits):
    return parse_classified_plan(
        planned(*tasks),
        candidates,
        classifications(*candidates),
        8,
        editorial_limits(config(**limits)),
    )


def test_internal_classifications_do_not_expand_shared_proto_contract():
    c = news()
    output = json.loads(discovered(c))
    output["candidates"][0].update(
        editorial_kind="news", change_basis="A new rule has entered force."
    )
    parsed = parse_discovery(
        json.dumps(output), {c["url"]}, True, c["direction"], DAY, classified=True
    )
    parse_message(parsed.candidates[0], pb.Candidate)
    assert parsed.classifications[parsed.candidates[0]["id"]]["kind"] == "news"
    plan = selected([c], [topic(c)])
    parse_message(plan.research_tasks[0], pb.ResearchTask)
    assert plan.task_classifications == {"topic-1": "news"}
    assert "editorial_kind" not in plan.research_tasks[0]
    assert (
        "editorial_kind"
        in discovery_schema(classified=True)["properties"]["candidates"]["items"]["properties"]
    )
    assert (
        "editorial_kind"
        in planning_schema([c["id"]], [c["url"]], 6, classified=True)["properties"][
            "research_tasks"
        ]["items"]["properties"]
    )


@pytest.mark.parametrize(
    "c",
    [
        paper(),
        news(doi="10.1234/test"),
        news(publication_status="preprint"),
        news(url="https://doi.org/10.1234/test", doi=""),
        news(url="https://dx.doi.org/10.1234/test", doi=""),
    ],
)
def test_paper_candidate_cannot_become_news_by_changing_its_title_or_declared_kind(c):
    c["title"] = "Game-changing industry news"
    assert candidate_classification(c, classifications(c)[c["id"]])["kind"] == "research"


def test_news_can_cite_a_background_paper_without_becoming_a_paper_topic():
    c = news(evidence_urls=["https://arxiv.org/abs/2609.00001"])
    assert candidate_classification(c, classifications(c)[c["id"]])["kind"] == "news"


def test_missing_classification_or_change_basis_is_not_assumed_to_be_news():
    c = news()
    assert candidate_classification(c)["kind"] == "unknown"
    assert candidate_classification(c, {"kind": "news", "basis": " "})["kind"] == "unknown"
    output = json.loads(discovered(c))
    parsed = parse_discovery(
        json.dumps(output), {c["url"]}, True, c["direction"], DAY, classified=True
    )
    assert parsed.classifications[parsed.candidates[0]["id"]]["kind"] == "unknown"


def test_large_research_pool_cannot_crowd_actual_news_out_of_candidate_budget():
    papers, events = [paper(n) for n in range(1, 31)], [news(n) for n in range(1, 21)]
    retained, kinds = candidate_budget(
        papers + events, classifications(*events), maximum=30, research_maximum=10
    )
    assert retained == events + papers[:10]
    assert sum(c["kind"] != "news" for c in kinds.values()) == 10


def test_news_short_edition_does_not_fill_its_empty_slots_with_weak_papers():
    candidates = [paper(1), paper(2), news(1), news(2)]
    result = selected(candidates, [topic(c, n) for n, c in enumerate(candidates, 1)])
    assert [t["candidate_ids"] for t in result.research_tasks] == [
        ["paper-1"],
        ["news-1"],
        ["news-2"],
    ]
    assert result.omitted_tasks[0]["reason"] == "research_quota"
    assert result.omitted_tasks[0]["task"]["candidate_ids"] == ["paper-2"]
    assert len(result.research_tasks) == 3  # No second approval gate and no filler.


def test_mixed_task_cannot_hide_multiple_papers_in_one_news_slot():
    a, b, event = paper(1), paper(2), news()
    mixed = topic(a)
    mixed["candidate_ids"] = [a["id"], b["id"]]
    mixed["source_urls"] = [a["url"], b["url"]]
    result = selected([a, b, event], [mixed, topic(event, 2)])
    assert [t["id"] for t in result.research_tasks] == ["topic-2"]
    assert result.omitted_tasks[0]["reason"] == "mixed_research_topics"


def test_reference_only_paper_cannot_evade_task_subject_budget():
    a, b, event = paper(1), paper(2), news()
    mixed = topic(event)
    mixed["source_urls"] = [a["url"], b["url"]]
    result = selected([a, b, event], [mixed])
    assert not result.research_tasks
    assert result.omitted_tasks[0]["reason"] == "mixed_research_topics"


def test_unknown_candidates_cannot_bundle_themselves_into_an_unmetered_news_task():
    a, b, known = news(1), news(2), news(3)
    mixed = topic(a)
    mixed["candidate_ids"] = [a["id"], b["id"]]
    mixed["source_urls"] = [a["url"], b["url"]]
    result = parse_classified_plan(
        planned(mixed, topic(known, 2)),
        [a, b, known],
        classifications(known),
        6,
        editorial_limits(config()),
    )
    assert [task["id"] for task in result.research_tasks] == ["topic-2"]
    assert result.omitted_tasks[0]["reason"] == "mixed_research_topics"
    assert result.omitted_tasks[0]["editorial_kind"] == "research"


def test_public_and_research_caps_are_configuration_not_fixed_constants():
    candidates = [paper(1), paper(2), news(1), news(2)]
    tasks = [topic(c, n) for n, c in enumerate(candidates, 1)]
    result = selected(candidates, tasks, max_public_items=3, max_research_items=2)
    assert (
        len(result.research_tasks) == 3 and result.omitted_tasks[0]["reason"] == "public_item_quota"
    )
    result = selected(candidates, tasks, max_research_items=0)
    assert [t["candidate_ids"] for t in result.research_tasks] == [["news-1"], ["news-2"]]


async def test_configured_prompts_and_budgets_reach_only_new_run_models(tmp_path):
    c = news()
    cfg = config(max_public_items=3, max_research_candidates=0)
    cfg["files"] = {"prompts/selection.md": "Frozen editorial marker; real-world changes first."}
    engine = Engine((planned(topic(c)), set(), False))
    result = await ContentPreparation(engine).shortlist(
        [paper(), c],
        DAY,
        tmp_path.resolve() / "new",
        content_config=cfg,
        classifications=classifications(c),
    )
    assert result.research_tasks[0]["candidate_ids"] == [c["id"]]
    prompt, schema, instructions, _ = engine.calls[0]
    assert prompt["candidates_untrusted"] == [c]
    assert prompt["max_tasks"] == 3 and schema["properties"]["research_tasks"]["maxItems"] == 3
    assert instructions.startswith(_SAFETY) and "Frozen editorial marker" in instructions
    assert "只比较给定候选" in instructions
    assert cfg["files"]["prompts/selection.md"] in instructions


async def test_configured_discovery_policy_and_classifications_reach_the_run(tmp_path):
    c = news()
    cfg = config()
    cfg["files"] = {
        "prompts/discovery.md": "Frozen discovery marker: transport access and real deployment."
    }
    output = json.loads(discovered(c))
    output["candidates"][0].update(
        editorial_kind="news", change_basis="A new transport route is now operating."
    )
    engine = Engine((json.dumps(output), {c["url"]}, True))
    result = await ContentPreparation(engine).discover(
        Instruction("03-world", "Frozen direction", "fixture"),
        DAY,
        tmp_path.resolve() / "discover",
        content_config=cfg,
    )
    assert result.classifications[result.candidates[0]["id"]]["kind"] == "news"
    assert engine.calls[0][2].startswith(_SAFETY)
    assert "Frozen discovery marker" in engine.calls[0][2]
    assert "evidence_urls" in engine.calls[0][2] and "不得读本地文件" in engine.calls[0][2]


async def test_valid_larger_configured_pool_has_the_same_core_and_runtime_limits(tmp_path):
    frozen = packaged_snapshot()
    files = dict(frozen["files"])
    files["workflow.yaml"] = files["workflow.yaml"].replace(
        "max_candidates: 30", "max_candidates: 60"
    )
    files["editorial.yaml"] = files["editorial.yaml"].replace(
        "max_research_candidates: 10", "max_research_candidates: 50"
    )
    cfg = build_snapshot(files, "c" * 40)
    assert editorial_limits(cfg).max_research_candidates == 50
    candidates = [paper(number) for number in range(1, 46)] + [
        news(number) for number in range(1, 6)
    ]
    engine = Engine((planned(topic(candidates[-1])), set(), False))
    result = await ContentPreparation(engine).shortlist(
        candidates,
        DAY,
        tmp_path.resolve() / "large-pool",
        content_config=cfg,
        classifications=classifications(*candidates[-5:]),
    )
    assert len(engine.calls[0][0]["candidates_untrusted"]) == 50
    assert len(result.research_tasks) == 1


def test_malformed_internal_task_identifier_is_a_finite_output_error():
    c = news()
    malformed = topic(c)
    malformed["id"] = []
    with pytest.raises(EditorError) as error:
        selected([c], [malformed])
    assert error.value.code == "invalid_output"


async def test_legacy_selection_and_discovery_keep_exact_old_envelopes_and_instructions(tmp_path):
    c = paper()
    t = topic(c)
    t.pop("editorial_kind")
    engine = Engine((planned(t), set(), False), (discovered(c), {c["url"]}, True))
    service = ContentPreparation(engine)
    selection = await service.shortlist([c], DAY, tmp_path.resolve() / "legacy-selection")
    discovery = await service.discover(
        Instruction("01-ai-ml", "Frozen old instruction", "digest"),
        DAY,
        tmp_path.resolve() / "legacy-discovery",
    )
    assert set(asdict(selection)) == {"research_tasks", "note"}
    assert set(asdict(discovery)) == {"candidates", "note"}
    assert engine.calls[0][2] == _SELECTION and engine.calls[1][2] == _DISCOVERY
    assert (
        "editorial_kind"
        not in engine.calls[0][1]["properties"]["research_tasks"]["items"]["properties"]
    )


async def test_story_plan_uses_frozen_depth_and_old_runs_keep_original_depth(tmp_path):
    directory = Path(__file__).resolve().parents[1]
    definition = load_definition(directory / "src/newsletter/workflows/daily.yaml")
    ids = {node.type: node.id for node in definition.nodes}
    store = Store(tmp_path / "plan.sqlite3", "mock")
    try:
        nodes = StoryNodes(store, definition, Engine(), tmp_path)
        tasks = [publication_task(n) for n in range(1, 5)]
        for run_id, frozen, expected in [
            ("new", config(), 1),
            ("no-depth", config(max_deep=0), 0),
            ("old", None, 4),
        ]:
            ctx = NodeContext(
                run_id=run_id,
                node_id=ids["story_plan"],
                item_id="",
                params={"max_deep": 4},
                inputs={ids["selection"]: {"research_tasks": tasks}},
                run_inputs={"issue_date": DAY, **({"content_config": frozen} if frozen else {})},
            )
            result = await nodes.execute("story_plan", ctx, tmp_path)
            assert result["brief_tasks"] == tasks and result["deep_tasks"] == tasks[:expected]
    finally:
        store.close()


async def test_deduplicate_node_applies_budget_before_remembering_candidates(tmp_path):
    directory = Path(__file__).resolve().parents[1]
    definition = load_definition(directory / "src/newsletter/workflows/daily.yaml")
    ids = {node.type: node.id for node in definition.nodes}
    store = Store(tmp_path / "pool.sqlite3", "mock")
    try:
        nodes = StoryNodes(store, definition, Engine(), tmp_path)
        papers, events = [paper(n) for n in range(1, 36)], [news(n) for n in range(1, 6)]
        ctx = NodeContext(
            run_id="pool",
            node_id=ids["deduplicate"],
            item_id="",
            params={"max_candidates": 30},
            inputs={
                ids["history"]: {"candidates": [], "editions": [], "watchlist": []},
                ids["discovery"]: [
                    {"candidates": papers + events, "classifications": classifications(*events)}
                ],
            },
            run_inputs={"issue_date": DAY, "content_config": config()},
        )
        result = await nodes.execute("deduplicate", ctx, tmp_path)
        assert [c["id"] for c in result["candidates"]] == [c["id"] for c in events + papers[:10]]
        assert len(result["classifications"]) == 15
        assert "classifications" not in result["candidates"][0]
        for c in result["candidates"]:
            parse_message(c, pb.Candidate)
    finally:
        store.close()


def test_one_deep_publication_receipt_roundtrips_and_old_freeze_remains_authoritative(tmp_path):
    store = Store(tmp_path / "publication.sqlite3", "mock")
    try:
        repository = PublicationRepository(store)
        tasks = [publication_task(n) for n in (1, 2)]
        repository.save_plan("run", DAY, tasks)
        for number, task_ in enumerate(tasks, 1):
            for mode in ("brief", "deep"):
                repository.save(
                    "run", task_, mode, publication_result(number, mode=mode), issue_date=DAY
                )
        frozen = freeze_publication(repository, "run", DAY, reason="completed", max_features=1)
        assert [s["disposition"] for s in frozen["coverage"]["stories"]] == ["deep", "brief"]
        assert (
            freeze_publication(repository, "run", DAY, reason="restart", max_features=0) == frozen
        )
    finally:
        store.close()


def test_default_editorial_rules_prioritize_real_change_without_exaggeration_or_filler():
    for text in (DEFAULT_DISCOVERY_POLICY, DEFAULT_SELECTION_POLICY):
        assert "论文" in text and "现实" in text
    assert "强公共事件和产业变化应挤掉弱增量论文" in DEFAULT_SELECTION_POLICY
    assert "新闻不足就短刊" in DEFAULT_SELECTION_POLICY
    assert "早期" in DEFAULT_SELECTION_POLICY and "不硬限大机构" in DEFAULT_SELECTION_POLICY
