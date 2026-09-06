"""Offline discovery/planning/research boundaries, with synthetic engine responses."""

import json
import re
from pathlib import Path

import pytest
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.collection.instructions import Instruction, load_instructions
from newsletter.contracts import ContractError, parse_message, to_dict
from newsletter.errors import EditorError
from newsletter.workflow.content import (
    ContentPreparation,
    parse_discovery,
    parse_plan,
    public_context,
)
from newsletter.workflow.schema import (
    CANDIDATE_FIELDS,
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
            "candidates": [{key: item[key] for key in CANDIDATE_FIELDS} for item in items],
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
    optional = {"doi", "version", "event_key", "published_at"}
    for name, field in props.items():
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


def test_schema_agrees_with_shared_proto_and_directions_are_six_separate_files():
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
    ]
    assert all("最多5" in d.text for d in directions)
    assert len(load_instructions(directory.parent)) == 3


def test_public_context_is_bounded_and_allowlisted():
    assert public_context([{"title": "Public", "token": "secret", "personal_digest": {}}]) == [
        {"title": "Public"}
    ]
    with pytest.raises(EditorError):
        public_context([{}] * 101)
