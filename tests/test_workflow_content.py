"""Offline discovery/planning/research boundaries, with synthetic engine responses."""

import json
import re
from pathlib import Path

import pytest
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.collection.instructions import Instruction, load_instructions
from newsletter.contracts import ContractError, content_hash, parse_message, to_dict
from newsletter.errors import EditorError
from newsletter.settings import Settings
from newsletter.store import Store
from newsletter.workflow.content import (
    _DISCOVERY,
    _SAFETY,
    _SELECTION,
    ContentPreparation,
    _candidate_view,
    parse_discovery,
    parse_plan,
    public_context,
)
from newsletter.workflow.definition import load_definition
from newsletter.workflow.engine import NodeContext
from newsletter.workflow.nodes import EditorialNodes
from newsletter.workflow.schema import (
    CANDIDATE_FIELDS,
    CANDIDATE_LEGACY_FIELDS,
    CANDIDATE_RESEARCH_FIELDS,
    TASK_FIELDS,
    discovery_schema,
    planning_schema,
)
from newsletter.workflow.sources import (
    Candidate,
    candidate_id,
    deduplicate_candidates,
    identity_keys,
)
from newsletter.workflow.story_nodes import StoryNodes

DAY = "2026-09-06"
URL = "https://arxiv.org/abs/2609.00001v2"


def candidate(**changes):
    result = Candidate(
        id="candidate-1",
        direction="01-ai-ml",
        title="Synthetic research candidate",
        url=URL,
        doi="",
        version="v2",
        event_key="",
        published_at=DAY,
        summary="Synthetic research question; its claims require independent primary reading.",
        why_now="A new controlled experiment changes the previous reported result and merits verification.",
        access_scope="abstract",
        provenance="web_open",
    )
    result.update(changes)
    return result


def discovered(*items):
    return json.dumps(
        {
            "note": "Synthetic public discovery",
            "candidates": [
                {
                    key: item.get(key, [] if key == "evidence_urls" else "")
                    for key in CANDIDATE_FIELDS
                }
                for item in items
            ],
        }
    )


def task(**changes):
    return {
        "id": "research-1",
        "candidate_ids": ["candidate-1"],
        "question": "Check methods and controls",
        "why": "A decision needs evidence",
        "priority": 1,
        "evidence_context": "The abstract omits the matched-data comparison.",
        "source_urls": [URL],
        **changes,
    }


def planned(*items):
    return json.dumps(
        {"research_tasks": list(items), "note": "Synthetic selection, not verification"}
    )


def material(url=URL):
    return {
        "title": "Synthetic material",
        "body": "Synthetic findings with explicit limitations.",
        "sources": [
            {
                "id": "source-1",
                "title": "Original source",
                "url": url,
                "published_at": DAY,
                "access_scope": "abstract",
                "excerpt": "",
            }
        ],
        "tags": ["fixture"],
    }


class Engine:
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    async def execute(self, prompt, schema, instructions, workspace):
        self.calls.append((json.loads(prompt), schema, instructions, workspace))
        return self.outputs.pop(0)


def test_discovery_ids_are_local_stable_and_exact_open_url_is_preserved():
    c = candidate(url=URL + "#abstract")
    result = parse_discovery(discovered(c), {URL}, True, c["direction"], DAY)
    assert result.candidates[0]["id"] == candidate_id(c)
    assert result.candidates[0]["url"] == URL + "#abstract"
    assert result.candidates[0]["provenance"] == "web_open"
    parse_message(result.candidates[0], pb.Candidate)


@pytest.mark.parametrize(
    "value,opened,searched",
    [
        (candidate(url="https://arxiv.org/pdf/2609.00001v2"), {URL}, True),
        (candidate(), {URL}, False),
        (candidate(), set(), True),
        (candidate(access_scope="verified"), {URL}, True),
        (candidate(published_at="2026-09-07"), {URL}, True),
        (candidate(published_at="2026-09"), {URL}, True),
        (candidate(doi="made-up DOI"), {URL}, True),
        (candidate(url="http://127.0.0.1/private"), {"http://127.0.0.1/private"}, True),
    ],
)
def test_discovery_rejects_unopened_canonical_switches_bad_dates_scopes_and_ssrf(
    value, opened, searched
):
    with pytest.raises((EditorError, ContractError)):
        parse_discovery(discovered(value), opened, searched, "01-ai-ml", DAY)


def test_unopened_feed_candidate_can_only_reuse_actual_metadata_not_model_claims():
    seed = candidate(
        provenance="crossref_metadata", access_scope="metadata", summary="Only a title record"
    )
    output = candidate(access_scope="metadata", summary="Invented clinical results")
    result = parse_discovery(discovered(output), set(), True, "02-science", DAY, seeds=[seed])
    assert result.candidates[0]["summary"] == "Only a title record"
    assert result.candidates[0]["provenance"] == "crossref_metadata"
    with pytest.raises(EditorError):
        parse_discovery(
            discovered(candidate(access_scope="full_text")),
            set(),
            True,
            "02-science",
            DAY,
            seeds=[seed],
        )


def test_discovery_cap_empty_note_and_shape_fail_closed():
    with pytest.raises(EditorError):
        parse_discovery(discovered(*[candidate()] * 6), {URL}, True, "01-ai-ml", DAY)
    for raw in ('{"candidates":[],"note":""}', '{"candidates":[],"note":"x","extra":1}'):
        with pytest.raises(EditorError):
            parse_discovery(raw, set(), True, "01-ai-ml", DAY)
    assert parse_discovery(discovered(), set(), True, "01-ai-ml", DAY).candidates == []


def test_discovery_schema_exposes_parser_string_and_empty_value_boundaries():
    schema = discovery_schema()
    props = schema["properties"]["candidates"]["items"]["properties"]
    optional = {"doi", "version", "event_key", "published_at", *CANDIDATE_RESEARCH_FIELDS}
    for name, field in props.items():
        if name == "evidence_urls":
            assert field == {
                "type": "array",
                "maxItems": 4,
                "items": {"type": "string", "minLength": 1, "maxLength": 1200},
            }
            continue
        assert field["minLength"] == (0 if name in optional else 1)
        assert field["maxLength"] == {"title": 500, "why_now": 1000, "published_at": 10}.get(
            name, 1200
        )
    assert schema["properties"]["note"] == {
        "type": "string",
        "minLength": 1,
        "maxLength": 2000,
    }


@pytest.mark.parametrize(
    "field,maximum",
    [
        ("title", 500),
        ("summary", 1200),
        ("why_now", 1000),
        ("version", 1200),
        ("event_key", 1200),
        *((name, 1200) for name in CANDIDATE_RESEARCH_FIELDS),
    ],
)
def test_discovery_schema_lengths_match_actual_parser(field, maximum):
    props = discovery_schema()["properties"]["candidates"]["items"]["properties"]
    assert props[field]["maxLength"] == maximum
    result = parse_discovery(
        discovered(candidate(**{field: "x" * maximum})), {URL}, True, "01-ai-ml", DAY
    )
    assert result.candidates[0][field] == "x" * maximum
    with pytest.raises(EditorError):
        parse_discovery(
            discovered(candidate(**{field: "x" * (maximum + 1)})), {URL}, True, "01-ai-ml", DAY
        )


@pytest.mark.parametrize(
    "value", ["2026-09", "20260906", "2026-9-06", "2026-09-06T00:00:00Z", "unknown"]
)
def test_discovery_schema_rejects_non_date_shapes(value):
    field = discovery_schema()["properties"]["candidates"]["items"]["properties"]["published_at"]
    assert re.fullmatch(field["pattern"], value) is None
    with pytest.raises(ContractError):
        parse_discovery(discovered(candidate(published_at=value)), {URL}, True, "01-ai-ml", DAY)


@pytest.mark.parametrize(
    "value,valid", [("", True), (DAY, True), ("2026-02-30", False), ("2026-09-07", False)]
)
def test_date_shape_is_not_a_substitute_for_calendar_and_issue_date_validation(value, valid):
    field = discovery_schema()["properties"]["candidates"]["items"]["properties"]["published_at"]
    assert re.fullmatch(field["pattern"], value) is not None
    if valid:
        result = parse_discovery(
            discovered(candidate(published_at=value)), {URL}, True, "01-ai-ml", DAY
        )
        assert result.candidates[0]["published_at"] == value
    else:
        with pytest.raises((ContractError, EditorError)):
            parse_discovery(discovered(candidate(published_at=value)), {URL}, True, "01-ai-ml", DAY)


def test_dedup_matches_doi_alias_arxiv_versions_tracking_urls_and_events():
    assert identity_keys(candidate()) & identity_keys(
        candidate(url="https://arxiv.org/pdf/2609.00001v1")
    )
    doi = candidate(url="https://doi.org/10.1234/ABC", doi="10.1234/abc")
    publisher = candidate(url="https://example.org/article", doi="https://doi.org/10.1234/ABC")
    assert len(deduplicate_candidates([doi, publisher])) == 1
    original = candidate(
        url="https://example.org/story?article=1&utm_source=feed", title="First title"
    )
    alias = candidate(url="https://example.org/story?article=1#section", title="Another title")
    assert len(deduplicate_candidates([original, alias])) == 1
    same_event = candidate(
        url="https://example.net/other", title="Different title", event_key="storm:2026-09-06"
    )
    original["event_key"] = "storm:2026-09-06"
    assert len(deduplicate_candidates([original, same_event])) == 1


def test_dedup_retains_meaningful_query_parameters():
    first = candidate(url="https://example.org/story?id=1", title="first")
    second = candidate(url="https://example.org/story?id=2", title="second")
    assert len(deduplicate_candidates([first, second])) == 2


def test_history_suppresses_repetition_but_preserves_explained_new_versions_not_downgrades():
    c = candidate()
    assert deduplicate_candidates([c], [c]) == []
    old = candidate(version="v1")
    assert deduplicate_candidates([c], [old]) == [c]
    assert deduplicate_candidates([old], [c]) == []
    assert deduplicate_candidates([candidate(why_now="New")], [old]) == []
    assert deduplicate_candidates([c], [{"title": c["title"]}]) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_ids": ["invented"]},
        {"candidate_ids": []},
        {"candidate_ids": ["candidate-1"] * 2},
        {"source_urls": ["https://example.org/unprovided"]},
        {"priority": True},
        {"priority": "1"},
        {"priority": 13},
        {"question": ""},
        {"evidence_context": ""},
        {"id": "../bad"},
    ],
)
def test_plan_only_selects_known_unique_identifiers_and_bounded_tasks(changes):
    with pytest.raises((EditorError, ContractError)):
        parse_plan(planned(task(**changes)), {"candidate-1"}, {URL}, 12)


def test_duplicate_tasks_and_duplicate_selected_candidate_rejected():
    with pytest.raises(EditorError):
        parse_plan(planned(task(), task(id="other", priority=2)), {"candidate-1"}, {URL}, 8)


def test_gap_plan_can_have_no_candidate_but_has_context_and_only_given_urls():
    result = parse_plan(planned(task(candidate_ids=[])), set(), {URL}, 3, gaps=True)
    assert result.research_tasks[0]["evidence_context"]
    assert to_dict(parse_message(result.research_tasks[0], pb.ResearchTask))["priority"] == 1


async def test_discover_passes_public_history_watchlist_and_never_private_fields(tmp_path):
    engine = Engine((discovered(candidate()), {URL}, True))
    service = ContentPreparation(engine)
    instruction = Instruction("01-ai-ml", "Find substantial public research", "a" * 64)
    await service.discover(
        instruction,
        DAY,
        tmp_path.resolve() / "discover",
        history=[{"title": "Old paper", "personal_digest": "private marker"}],
        watchlist=[{"question": "Watch future replication", "password": "secret marker"}],
    )
    prompt = json.dumps(engine.calls[0][0])
    assert "private marker" not in prompt and "secret marker" not in prompt
    assert "Watch future replication" in prompt
    assert "不得读本地文件" in engine.calls[0][2]


async def test_shortlist_accepts_12_cap_and_empty_candidates_do_not_invoke_model(tmp_path):
    engine = Engine((planned(task()), set(), False))
    service = ContentPreparation(engine)
    assert (await service.shortlist([], DAY, tmp_path.resolve() / "empty")).research_tasks == []
    assert not engine.calls
    selected = await service.shortlist(
        [candidate()], DAY, tmp_path.resolve() / "select", max_tasks=12
    )
    assert selected.research_tasks[0]["id"] == "research-1"
    assert engine.calls[0][1]["properties"]["research_tasks"]["maxItems"] == 12
    assert engine.calls[0][0]["reader_profile"] == ""


def test_promoted_selection_keeps_evaluated_text_and_public_safety_boundary():
    directory = Path(__file__).resolve().parents[1]
    evaluated = (directory / "evals/prompts/v3-selection.md").read_text(encoding="utf-8")
    assert evaluated.strip() in _SELECTION
    assert _SELECTION.startswith(_SAFETY)
    assert "不得读本地文件、密钥、个人事件、登录信息" in _SELECTION
    assert "不search/open，不新增ID或URL" in _SELECTION
    assert "question只提出一个核心问题和一两项决定性核查" in _SELECTION
    assert "不承诺执行列表之外的研究" in _SELECTION
    assert "reader_profile仅表达本次冻结的显式读者偏好" in _SELECTION


@pytest.mark.parametrize(
    "production,evaluated",
    [
        ("04-economy.md", "v2-discovery-economy.md"),
        ("06-technology.md", "v2-discovery-technology.md"),
    ],
)
def test_current_discovery_instructions_match_versioned_evaluation_inputs(production, evaluated):
    directory = Path(__file__).resolve().parents[1]
    actual = directory / "src/newsletter/instructions/discovery" / production
    expected = directory / "evals/prompts" / evaluated
    assert actual.read_text(encoding="utf-8") == expected.read_text(encoding="utf-8")


async def test_discovery_explicitly_requires_real_search_even_when_no_candidates(tmp_path):
    engine = Engine((discovered(), set(), False), (discovered(), set(), True))
    service = ContentPreparation(engine)
    instruction = Instruction("04-economy", "Find public finance research", "a" * 64)
    seed = candidate(provenance="crossref_metadata", access_scope="metadata")
    with pytest.raises(EditorError) as error:
        await service.discover(instruction, DAY, tmp_path.resolve() / "bad", seeds=[seed])
    assert error.value.code == "invalid_output"
    result = await service.discover(instruction, DAY, tmp_path.resolve() / "good", seeds=[seed])
    assert result.candidates == []
    assert engine.calls[0][2] == _DISCOVERY
    assert _DISCOVERY.startswith(_SAFETY)
    assert "必须实际调用hosted web search" in _DISCOVERY
    assert "已有metadata线索或最后没有合格候选" in _DISCOVERY
    assert "不能伪造搜索或打开记录" in _DISCOVERY


@pytest.mark.parametrize(
    "profile", [None, {}, ["preferences"], "x" * 100_001], ids=["null", "object", "list", "long"]
)
async def test_shortlist_rejects_invalid_reader_profile_before_model(tmp_path, profile):
    engine = Engine()
    with pytest.raises(EditorError) as error:
        await ContentPreparation(engine).shortlist(
            [candidate()], DAY, tmp_path.resolve() / "bad", reader_profile=profile
        )
    assert error.value.code == "invalid_input"
    assert not engine.calls


@pytest.mark.parametrize(
    "node_class,recipe", [(EditorialNodes, "legacy-daily.yaml"), (StoryNodes, "daily.yaml")]
)
async def test_selection_uses_only_reader_profile_from_frozen_run_policy(
    tmp_path, node_class, recipe
):
    directory = Path(__file__).resolve().parents[1]
    definition = load_definition(directory / "src/newsletter/workflows" / recipe)
    ids = {node.type: node.id for node in definition.nodes}
    engine = Engine((planned(task()), set(), False))
    store = Store(tmp_path / "selection.sqlite3", "mock")
    profile = "Frozen explicit preference: understand AI/ML/CS and financial mechanisms.\n"
    try:
        nodes = node_class(store, definition, engine, tmp_path.resolve())
        ctx = NodeContext(
            run_id="synthetic-selection",
            node_id=ids["selection"],
            item_id="",
            params={"max_tasks": 8},
            inputs={
                ids["deduplicate"]: {"candidates": [candidate()]},
                ids["history"]: {"candidates": [], "watchlist": [], "editions": []},
            },
            run_inputs={
                "issue_date": DAY,
                "policy": {
                    "reader-profile.md": profile,
                    "editorial.md": "Unrelated editorial policy marker",
                    "private_extra": "Secret configuration marker",
                },
                "personal_digest": "Private event marker",
            },
        )
        selected = await nodes.execute("selection", ctx, tmp_path.resolve() / "select")
        assert selected["research_tasks"][0]["id"] == "research-1"
        assert len(engine.calls) == 1
        prompt = engine.calls[0][0]
        assert prompt["reader_profile"] == profile
        assert "policy" not in prompt
        assert "Unrelated editorial policy marker" not in json.dumps(prompt)
        assert "Secret configuration marker" not in json.dumps(prompt)
        assert "Private event marker" not in json.dumps(prompt)
        assert engine.calls[0][2] == _SELECTION
    finally:
        store.close()


async def test_research_uses_existing_fresh_search_open_provenance_even_for_old_candidate(tmp_path):
    output = json.dumps(
        {"state": "collected", "note": "Read actual abstract", "packets": [material()]}
    )
    engine = Engine((output, set(), True), (output, {URL}, True))
    service = ContentPreparation(engine)
    with pytest.raises(EditorError):
        await service.research(task(), [candidate()], DAY, tmp_path.resolve() / "bad")
    result = await service.research(task(), [candidate()], DAY, tmp_path.resolve() / "good")
    assert result.packets[0]["sources"][0]["url"] == URL


async def test_gap_research_accepts_empty_candidates_with_explicit_question(tmp_path):
    output = json.dumps(
        {"state": "no_findings", "note": "Could not verify the claim", "packets": []}
    )
    engine = Engine((output, set(), True))
    result = await ContentPreparation(engine).research(
        task(candidate_ids=[]), [], DAY, tmp_path.resolve() / "gap-research"
    )
    assert not result.packets


async def test_plan_gaps_uses_public_draft_and_strips_packet_record_extras(tmp_path):
    packet = {"id": "packet-1", "content": material()}
    draft = {
        "subject": "Test",
        "title": "Test",
        "sections": [
            {
                "kind": "feature",
                "heading": "Research",
                "paragraphs": [
                    {"text": "A claim worth checking", "citations": ["packet-1/source-1"]}
                ],
            }
        ],
    }
    engine = Engine((planned(task(candidate_ids=[])), set(), False))
    result = await ContentPreparation(engine).plan_gaps(
        draft, [packet], DAY, tmp_path.resolve() / "gap-plan"
    )
    assert result.research_tasks[0]["candidate_ids"] == []
    assert engine.calls[0][1]["properties"]["research_tasks"]["maxItems"] == 3
    assert "唯一一轮共享预算" in engine.calls[0][2]


async def test_extra_private_fields_on_candidates_are_rejected_before_model(tmp_path):
    engine = Engine()
    c = candidate(personal_digest="private marker")
    with pytest.raises(ContractError):
        await ContentPreparation(engine).shortlist([c], DAY, tmp_path.resolve() / "bad")
    assert not engine.calls


def test_schema_agrees_with_shared_proto_and_directions_are_eight_separate_files():
    assert set(CANDIDATE_FIELDS) == set(pb.Candidate.DESCRIPTOR.fields_by_name) - {
        "id",
        "direction",
        "provenance",
    }
    assert set(TASK_FIELDS) == set(pb.ResearchTask.DESCRIPTOR.fields_by_name)
    assert discovery_schema()["properties"]["candidates"]["maxItems"] == 5
    assert (
        planning_schema([], [], 3, gaps=True)["properties"]["research_tasks"]["items"][
            "properties"
        ]["candidate_ids"]["maxItems"]
        == 0
    )
    directory = Path(__file__).resolve().parents[1] / "src/newsletter/instructions/discovery"
    directions = load_instructions(directory)
    assert [d.id for d in directions] == [
        "01-ai-ml",
        "02-science",
        "03-world",
        "04-economy",
        "05-health",
        "06-technology",
        "07-search-ads-recs",
        "08-llm-architectures",
    ]
    assert all("最多5" in d.text for d in directions)
    assert len(load_instructions(directory.parent)) == 3


@pytest.mark.parametrize("identifier", ["07-search-ads-recs", "08-llm-architectures"])
def test_specialized_discovery_instructions_keep_source_and_dedup_boundaries(identifier):
    directory = Path(__file__).resolve().parents[1] / "src/newsletter/instructions/discovery"
    directions = {item.id: item for item in load_instructions(directory)}
    text = directions[identifier].text
    for required in (
        "最多5",
        "不凑数",
        "近两周",
        "六周",
        "首发日期",
        "未知留空",
        "history",
        "metadata_seeds",
        "DOI",
        "arXiv",
        "event_key",
        "01-ai-ml",
        "search",
        "open",
        *CANDIDATE_RESEARCH_FIELDS,
        "evidence_urls",
    ):
        assert required in text
    assert directions[identifier].digest == content_hash(text)
    # Prompt/packaging contracts only, not a claim about live retrieval quality.


def test_eight_retrieval_directions_do_not_expand_selection_output_or_model_timeouts():
    root = Path(__file__).resolve().parents[1]
    definition = load_definition(root / "src/newsletter/workflows/daily.yaml")
    roles = {node.type: node for node in definition.nodes}
    assert roles["discovery"].map.max_items == 8
    assert roles["discovery"].params == {"timeout_seconds": 150}
    assert roles["api_feed"].params == {"timeout_seconds": 45}
    assert roles["deduplicate"].params == {"max_candidates": 30}
    assert roles["selection"].params == {"max_tasks": 8, "timeout_seconds": 150}
    assert roles["story_plan"].params == {"max_deep": 4}
    assert roles["story_brief"].params == {"timeout_seconds": 300}
    assert roles["story_deep"].params == {"timeout_seconds": 420}
    assert len([node for node in definition.nodes if node.type == "selection"]) == 1
    assert Settings().workflow_timeout_seconds == 5400


def test_one_paper_from_broad_and_specialized_retrievers_is_not_three_candidates():
    records = [
        parse_discovery(discovered(candidate()), {URL}, True, direction, DAY).candidates[0]
        for direction in ("01-ai-ml", "07-search-ads-recs", "08-llm-architectures")
    ]
    assert len({record["id"] for record in records}) == 1
    assert len(deduplicate_candidates(records)) == 1


def test_legacy_candidate_view_and_discovery_do_not_rewrite_old_hashes():
    old = candidate()
    old["id"] = candidate_id(old)
    digest = content_hash(old)
    assert not set(CANDIDATE_RESEARCH_FIELDS) & set(old)
    assert _candidate_view(old) == old
    assert content_hash(old) == digest
    raw = json.dumps(
        {
            "candidates": [{key: old[key] for key in CANDIDATE_LEGACY_FIELDS}],
            "note": "Legacy public discovery checkpoint",
        }
    )
    parsed = parse_discovery(raw, {URL}, True, "01-ai-ml", DAY).candidates[0]
    assert parsed == old and content_hash(parsed) == digest


def test_research_provenance_fields_preserve_opened_evidence_and_unknowns():
    evidence = "https://openreview.net/forum?id=synthetic"
    value = candidate(
        authors="Synthetic Researcher",
        affiliations="",  # The abstract does not establish the author's affiliation.
        venue="Synthetic workshop",
        publication_status="Accepted workshop paper; source record only",
        contribution="Tests an earlier error-bound assumption against a matched baseline.",
        source_basis="A specific workshop entry records the author and decision.",
        evidence_urls=[evidence, URL],
    )
    parsed = parse_discovery(discovered(value), {URL, evidence}, True, "01-ai-ml", DAY)
    for key in (*CANDIDATE_RESEARCH_FIELDS, "evidence_urls"):
        assert parsed.candidates[0][key] == value[key]
    assert parsed.candidates[0]["id"] == candidate_id(candidate())
    # A source-schema field is not a domain/author prestige allowlist.
    unlisted = candidate(
        authors="A new team",
        affiliations="Independent researchers",
        evidence_urls=["https://new-team.example.org/paper"],
    )
    assert parse_discovery(
        discovered(unlisted), {URL, *unlisted["evidence_urls"]}, True, "01-ai-ml", DAY
    ).candidates


@pytest.mark.parametrize(
    "urls,opened",
    [
        (["https://openreview.net/forum?id=synthetic"], {URL}),
        ([URL, URL], {URL}),
        ([URL] * 5, {URL}),
        ("https://openreview.net/", {URL}),
        ([None], {URL}),
        (["http://127.0.0.1/source"], {URL, "http://127.0.0.1/source"}),
        (["https://openreview.net/" + "a" * 1200], {URL}),
    ],
)
def test_discovery_rejects_unopened_duplicate_unsafe_or_unbounded_source_evidence(urls, opened):
    with pytest.raises((EditorError, ContractError)):
        parse_discovery(discovered(candidate(evidence_urls=urls)), opened, True, "01-ai-ml", DAY)


def test_unopened_metadata_seed_cannot_gain_model_written_reputation_or_proof_urls():
    seed = candidate(
        url="https://doi.org/10.1234/synthetic",
        access_scope="metadata",
        provenance="crossref_metadata",
    )
    seed["id"] = candidate_id(seed)
    model = candidate(
        **{
            **seed,
            "authors": "Invented famous author",
            "affiliations": "Invented prestigious lab",
            "venue": "Invented main conference",
            "publication_status": "Invented acceptance",
            "contribution": "Invented breakthrough",
            "source_basis": "Invented endorsement",
            "evidence_urls": ["https://example.org/unopened"],
        }
    )
    found = parse_discovery(discovered(model), set(), True, "02-science", DAY, seeds=[seed])
    assert found.candidates == [{**seed, "direction": "02-science"}]
    assert "Invented" not in json.dumps(found.candidates)
    assert "evidence_urls" not in found.candidates[0]


async def test_shortlist_hands_off_source_and_contribution_fields_without_extra_search(tmp_path):
    supplied = candidate(
        authors="Synthetic author",
        affiliations="Synthetic institution",
        venue="Synthetic journal",
        publication_status="Published according to the supplied entry",
        contribution="A matched-budget comparison changes the earlier claimed advantage.",
        source_basis="Original journal entry, not a ranking or reputation claim.",
        evidence_urls=[URL],
    )
    engine = Engine((planned(task()), set(), False))
    await ContentPreparation(engine).shortlist([supplied], DAY, tmp_path.resolve() / "sources")
    assert len(engine.calls) == 1
    assert engine.calls[0][0]["candidates_untrusted"] == [supplied]
    assert "不search/open" in engine.calls[0][2]
    assert "这个问题为什么重要" in engine.calls[0][2]
    assert "这篇工作实际增加了什么" in engine.calls[0][2]
    assert "声誉只是发现线索，不是硬白名单" in engine.calls[0][2]
    assert "未知" in engine.calls[0][2]
    # This verifies prompt routing and boundaries, not whether a model ranks well.


def test_public_context_is_bounded_and_allowlisted():
    assert public_context([{"title": "Public", "token": "secret", "personal_digest": {}}]) == [
        {"title": "Public"}
    ]
    with pytest.raises(EditorError):
        public_context([{}] * 101)
