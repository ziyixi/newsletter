"""Offline projection contracts, not model quality or a live Notion acceptance."""

import base64
import copy
import json

import pytest
from test_rendering import SAMPLE_DRAFT, SAMPLE_PACKETS

from newsletter.contracts import content_hash
from newsletter.notion_content import (
    CHART_PLACEHOLDER,
    _blocks,
    _chunks,
    _text_property,
    edition_projection,
    material_projection,
)

DAY = "2026-09-07"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
)


def candidate(**changes):
    value = {
        "id": "candidate-fixture",
        "direction": "01-ai-ml",
        "title": "Synthetic work with a defined comparison",
        "url": "https://example.org/paper",
        "doi": "10.1234/synthetic",
        "version": "v2",
        "event_key": "synthetic-event",
        "published_at": "2026-09-06",
        "summary": "The synthetic earlier baseline has a limitation. This work tests one change.",
        "why_now": "A new synthetic comparison is available.",
        "access_scope": "abstract",
        "provenance": "discovery",
        "authors": "Synthetic Author",
        "affiliations": "Synthetic Institute",
        "venue": "Synthetic journal",
        "publication_status": "已发表",
        "contribution": "Tests a specific previous assumption, not a new product name.",
        "source_basis": "The synthetic primary abstract identifies the work.",
        "evidence_urls": [
            "https://example.org/paper",
            "https://example.org/authors",
        ],
    }
    return {**value, **changes}


def packet(identifier="sample-packet"):
    value = copy.deepcopy(SAMPLE_PACKETS[0])
    value["id"] = identifier
    value["is_fixture"] = False
    value["content_hash"] = content_hash(value["content"])
    return value


def edition(**changes):
    return {
        "id": "edition-fixture",
        "issue_date": DAY,
        "state": "ready",
        "delivery_state": "not_requested",
        "packet_ids": ["sample-packet"],
        "is_fixture": False,
        "draft": copy.deepcopy(SAMPLE_DRAFT),
        "rendered": {
            "html": "<p>PRIVATE RENDERED BODY SHOULD NEVER BE COPIED</p>",
            "text": "PRIVATE RENDERED BODY SHOULD NEVER BE COPIED",
            "chart_png": base64.b64encode(PNG).decode(),
            "render_hash": "a" * 64,
        },
        "personal_digest": {
            "state": "current",
            "title": "私人事件",
            "summary": "PRIVATE SUMMARY",
            "items": [
                {"rank": 1, "title": "PRIVATE TASK", "detail": "PRIVATE DETAIL"}
            ],
            "task_count": 7,
            "time_window_hours": 24,
            "fetched_at": "2026-09-07T15:00:00Z",
            "source_label": "PRIVATE SOURCE",
            "limitations": "PRIVATE BOUNDARY",
            "is_fixture": False,
        },
        "usage": {
            "usage": {
                "input_tokens": "900",
                "cached_input_tokens": "700",
                "output_tokens": "100",
                "reasoning_output_tokens": "40",
                "total_tokens": "1000",
            },
            "invocations": 3,
            "missing_invocations": 0,
            "partial": False,
        },
        "publication": {
            "mode": "partial",
            "reason": "completed",
            "stories": [
                {
                    "story_id": "story-fixture",
                    "title": "Synthetic pending topic",
                    "candidate_ids": ["candidate-fixture"],
                    "priority": 1,
                    "disposition": "deferred",
                    "reason": "Synthetic independent review was not finished.",
                }
            ],
        },
        **changes,
    }


def block_text(blocks):
    return "\n".join(
        "".join(
            item["text"]["content"]
            for item in block[block["type"]].get("rich_text", [])
        )
        for block in blocks
    )


def property_text(projection, name):
    prop = projection.properties[name]
    return "".join(
        item["text"]["content"]
        for item in prop.get("rich_text", prop.get("title", []))
    )


def project_material(value=None, **kwargs):
    return material_projection(
        candidate() if value is None else value,
        key="material:synthetic",
        first_seen=DAY,
        run_id="run-fixture",
        **kwargs,
    )


def test_material_properties_are_typed_and_metadata_is_not_repeated_in_prose():
    source = candidate()
    result = project_material(source)
    body = block_text(result.blocks)
    assert result.properties["title"] == {
        "title": [{"type": "text", "text": {"content": source["title"]}}]
    }
    assert property_text(result, "authors") == source["authors"]
    assert property_text(result, "affiliations") == source["affiliations"]
    assert result.properties["category"] == {"select": {"name": "AI/ML"}}
    assert result.properties["direction"] == {
        "multi_select": [{"name": "01-ai-ml"}]
    }
    assert result.properties["first_seen"] == {"date": {"start": DAY}}
    assert result.properties["access_scope"] == {"select": {"name": "摘要"}}
    assert result.properties["material_type"] == {"select": {"name": "论文"}}
    assert result.properties["sync_state"] == {"select": {"name": "同步中"}}
    assert "edition_ids" not in result.properties
    for value in (
        source["authors"],
        source["affiliations"],
        "run-fixture",
        result.digest,
        "Fixture:",
    ):
        assert value not in body
    for field in ("summary", "contribution", "why_now", "source_basis"):
        assert source[field] in body
    assert result.chart_png is None


def test_material_never_infers_authors_from_associated_multisource_research():
    source = candidate(
        authors="", affiliations="", venue="", publication_status=""
    )
    research = packet()
    research["content"]["body"] = (
        "An unrelated source mentions Famous Author from Famous Institute."
    )
    result = project_material(
        source, evidence=[research, copy.deepcopy(research)]
    )
    assert (
        property_text(result, "authors")
        == property_text(result, "affiliations")
        == ""
    )
    assert result.properties["material_type"] == {"select": {"name": "未分类"}}
    text = block_text(result.blocks)
    assert text.count(research["content"]["body"]) == 1
    assert "不代表该候选的全部主张都已独立核实" in text
    assert all(
        source["excerpt"] in text for source in research["content"]["sources"]
    )


def test_legacy_candidate_unknown_fields_stay_empty():
    old = candidate()
    for field in (
        "authors",
        "affiliations",
        "venue",
        "publication_status",
        "contribution",
        "source_basis",
        "evidence_urls",
    ):
        old.pop(field)
    original = copy.deepcopy(old)
    result = project_material(old)
    assert property_text(result, "authors") == ""
    assert property_text(result, "value") == old["why_now"]
    assert old == original


def test_conflicting_packet_identity_cannot_be_silently_overwritten():
    first = packet()
    other = copy.deepcopy(first)
    other["content"]["body"] = "Different synthetic research."
    with pytest.raises(ValueError, match="Conflicting"):
        project_material(evidence=[first, other])


def test_material_determinism_and_property_only_progress_updates():
    source, evidence = candidate(), [packet("packet-b"), packet("packet-a")]
    before = copy.deepcopy((source, evidence))
    first = project_material(source, evidence=evidence)
    second = project_material(
        source, evidence=list(reversed(evidence)), progress="已刊出"
    )
    assert first.blocks == second.blocks and first.digest == second.digest
    assert first.properties["progress"] != second.properties["progress"]
    assert (source, evidence) == before
    changed = project_material(
        candidate(summary="A different synthetic finding."), evidence=evidence
    )
    assert changed.digest != first.digest


@pytest.mark.parametrize(
    "scope,label",
    [
        ("metadata", "仅线索"),
        ("abstract", "摘要"),
        ("full_text", "全文"),
        ("dataset", "仅线索"),
    ],
)
def test_access_scope_does_not_upgrade_a_dataset_to_full_text(scope, label):
    result = project_material(candidate(access_scope=scope))
    assert result.properties["access_scope"] == {"select": {"name": label}}
    if scope == "dataset":
        assert "访问范围：数据集" in block_text(result.blocks)


@pytest.mark.parametrize(
    "status,url,kind",
    [
        ("", "https://arxiv.org/abs/2609.12345", "预印本"),
        ("已发表（合成刊会）", "https://arxiv.org/abs/2609.12345", "论文"),
        ("技术报告", "https://example.org/report", "技术报告"),
        ("尚未接收", "https://openreview.net/forum?id=synthetic", "未分类"),
    ],
)
def test_material_type_does_not_treat_doi_or_openreview_as_acceptance(
    status, url, kind
):
    result = project_material(candidate(publication_status=status, url=url))
    assert result.properties["material_type"] == {"select": {"name": kind}}


def test_material_evidence_is_complete_above_old_6000_character_limit():
    research = packet()
    research["content"]["body"] = "😀合成正文\n" * 8000
    result = project_material(evidence=[research])
    assert research["content"]["body"] in block_text(result.blocks)
    assert "已截断" not in block_text(result.blocks)
    for block in result.blocks:
        rich = block[block["type"]]["rich_text"]
        assert len(rich) <= 100
        assert all(
            len(item["text"]["content"].encode("utf-16-le")) // 2 <= 2000
            for item in rich
        )


def test_text_chunking_preserves_astral_unicode_whitespace_and_literal_markup():
    value = " 😀 <script>not executable</script> **literal**\n" * 10_000
    chunks = _chunks(value)
    assert "".join(chunks) == value
    blocks = _blocks(value)
    assert len(blocks) > 1
    assert (
        "".join(
            item["text"]["content"]
            for block in blocks
            for item in block["paragraph"]["rich_text"]
        )
        == value
    )
    with pytest.raises(ValueError, match="surrogate"):
        _chunks("bad\ud800")
    with pytest.raises(ValueError, match="capacity"):
        _text_property(value)


def test_edition_preserves_sections_reading_chart_context_sources_and_pending_topics():
    value = edition()
    result = edition_projection(value, packets=[packet()])
    text = block_text(result.blocks)
    for section in value["draft"]["sections"]:
        assert section["heading"] in text
        assert all(p["text"] in text for p in section["paragraphs"])
        assert section["limitations"] in text
    for field in (
        "question",
        "caption",
        "alt_text",
        "metric",
        "unit",
        "period",
        "limitations",
    ):
        assert value["draft"]["chart"][field] in text
    assert "另一组：缺失（尚未公布）" in text
    assert value["draft"]["recommended_reading"]["reason"] in text
    assert "来源与核对" in text and "[1]" in text and "[2]" in text
    assert "Synthetic pending topic｜暂缓刊出" in text
    links = [
        item["text"].get("link", {}).get("url")
        for b in result.blocks
        if b["type"] != CHART_PLACEHOLDER
        for item in b[b["type"]]["rich_text"]
    ]
    assert all(s["url"] in links for s in packet()["content"]["sources"])
    assert result.chart_png == PNG
    assert sum(b["type"] == CHART_PLACEHOLDER for b in result.blocks) == 1
    assert result.key == "edition:edition-fixture"
    assert "material_ids" not in result.properties


def test_private_default_excludes_even_frozen_email_text_and_does_not_parse_private_payload():
    value = edition()
    result = edition_projection(value, packets=[packet()])
    assert "PRIVATE" not in json.dumps(result.blocks)
    assert result.properties["contains_personal"] == {"checkbox": False}
    value["personal_digest"] = {"invalid": "PRIVATE MALFORMED"}
    assert edition_projection(value, packets=[packet()]).digest == result.digest
    with pytest.raises(ValueError):
        edition_projection(value, packets=[packet()], include_personal=True)


def test_explicit_private_archive_is_complete_and_after_public_sources():
    result = edition_projection(
        edition(), packets=[packet()], include_personal=True
    )
    text = block_text(result.blocks)
    for value in (
        "PRIVATE SUMMARY",
        "PRIVATE TASK",
        "PRIVATE DETAIL",
        "PRIVATE SOURCE",
        "PRIVATE BOUNDARY",
        "7 条来源记录",
        "最近 24 小时",
        "2026-09-07T15:00:00Z",
    ):
        assert value in text
    assert (
        text.index("来源与核对")
        < text.index("TODOFY / 与你有关")
        < text.index("Codex 已记录")
    )
    assert "PRIVATE RENDERED BODY" not in text
    assert result.properties["contains_personal"] == {"checkbox": True}
    with pytest.raises(ValueError, match="explicit"):
        edition_projection(
            edition(), packets=[packet()], include_personal="true"
        )


def test_property_only_delivery_updates_never_change_frozen_body_digest():
    first = edition_projection(
        edition(), packets=[packet()], include_personal=True
    )
    second = edition_projection(
        edition(
            delivery_state="provider_accepted",
            provider_message_id="provider-id",
            updated_at="later",
        ),
        packets=[packet()],
        include_personal=True,
    )
    assert first.digest == second.digest and first.blocks == second.blocks
    assert second.properties["delivery"] == {"select": {"name": "已提交"}}
    assert "已确认投递" not in json.dumps(second.properties, ensure_ascii=False)
    assert first.properties["tokens"] == {"number": 1000}
    assert first.properties["input_tokens"] == {"number": 900}
    assert first.properties["cached_tokens"] == {"number": 700}
    assert first.properties["output_tokens"] == {"number": 100}


def test_partial_and_absent_usage_are_not_fabricated_zeroes():
    partial = edition(
        usage={
            "usage": None,
            "partial": True,
            "invocations": 2,
            "missing_invocations": 2,
        }
    )
    for value in (partial, edition(usage=None)):
        result = edition_projection(value, packets=[packet()])
        assert result.properties["tokens"] == {"number": None}
        assert result.properties["usage_partial"] == {"checkbox": True}
        assert "模型用量未取得" in block_text(result.blocks)


def test_missing_chart_png_keeps_every_chart_explanation_without_fake_image():
    value = edition()
    value["rendered"]["chart_png"] = ""
    result = edition_projection(value, packets=[packet()])
    assert result.chart_png is None
    assert all(b["type"] != CHART_PLACEHOLDER for b in result.blocks)
    assert value["draft"]["chart"]["alt_text"] in block_text(result.blocks)


@pytest.mark.parametrize(
    "encoded", ["not base64", base64.b64encode(b"not PNG").decode()]
)
def test_corrupt_frozen_png_is_rejected_not_silently_replaced(encoded):
    value = edition()
    value["rendered"]["chart_png"] = encoded
    with pytest.raises(ValueError, match="chart"):
        edition_projection(value, packets=[packet()])


def test_missing_or_unresolved_sources_fail_instead_of_archiving_broken_citations():
    with pytest.raises(ValueError):
        edition_projection(edition())
    value = edition()
    value["draft"]["sections"][0]["paragraphs"][0]["citations"] = [
        "missing/source"
    ]
    with pytest.raises(ValueError):
        edition_projection(value, packets=[packet()])


def test_more_than_one_hundred_blocks_remain_available_for_transport_batching():
    value = edition()
    value["draft"]["sections"] = [
        {
            "kind": "science",
            "heading": f"Synthetic section {i}",
            "paragraphs": [
                {
                    "text": f"Synthetic paragraph {i}-{j}",
                    "citations": ["sample-packet/survey"],
                }
                for j in range(16)
            ],
            "limitations": "Synthetic boundary",
        }
        for i in range(12)
    ]
    result = edition_projection(value, packets=[packet()])
    assert len(result.blocks) > 200
    assert "Synthetic paragraph 11-15" in block_text(result.blocks)


def test_projection_is_deterministic_and_never_mutates_frozen_inputs():
    value, evidence = edition(), [packet()]
    before = copy.deepcopy((value, evidence))
    first = edition_projection(
        value, packets=evidence, run_id="run-test", include_personal=True
    )
    assert first == edition_projection(
        value, packets=evidence, run_id="run-test", include_personal=True
    )
    assert (value, evidence) == before
    assert property_text(first, "content_hash") == first.digest
    revised = copy.deepcopy(value)
    revised["draft"]["introduction"] += " A corrected synthetic introduction."
    assert (
        edition_projection(
            revised, packets=evidence, include_personal=True
        ).digest
        != first.digest
    )


def test_same_date_distinct_editions_and_explicit_revision_type_keep_separate_identity():
    first = edition_projection(edition(), packets=[packet()])
    second = edition_projection(
        edition(id="second-edition"), packets=[packet()], edition_type="修订"
    )
    assert first.key != second.key
    assert second.properties["edition_type"] == {"select": {"name": "修订"}}
    assert first.properties["issue_date"] == second.properties["issue_date"]
    with pytest.raises(ValueError, match="edition type"):
        edition_projection(
            edition(), packets=[packet()], edition_type="unknown"
        )


def test_fixture_material_cannot_be_hidden_by_a_false_caller_flag():
    evidence = packet()
    evidence["is_fixture"] = True
    assert project_material(evidence=[evidence]).properties["fixture"] == {
        "checkbox": True
    }
    result = edition_projection(edition(), packets=[evidence])
    assert result.properties["fixture"] == {"checkbox": True}
    assert result.properties["edition_type"] == {"select": {"name": "测试"}}


def test_long_source_url_is_preserved_as_text_not_trimmed_into_a_different_url():
    url = "https://example.org/" + "a" * 1990
    result = project_material(candidate(url=url, evidence_urls=[url]))
    assert result.properties["url"] == {"url": None}
    assert url in block_text(result.blocks)


def test_invalid_property_date_fails_before_transport_would_create_a_page():
    with pytest.raises(ValueError):
        project_material(candidate(published_at="unknown"))


@pytest.mark.parametrize(
    "candidate_url,doi,source_url",
    [
        (
            "https://example.org/paper",
            "10.1234/synthetic",
            "https://doi.org/10.1234/synthetic",
        ),
        (
            "https://arxiv.org/abs/2609.12345",
            "",
            "https://arxiv.org/pdf/2609.12345v2",
        ),
        ("https://example.org/paper", "", "https://example.org/paper"),
    ],
)
def test_exact_research_source_identity_upgrades_read_column_but_keeps_discovery_record(
    candidate_url, doi, source_url
):
    lead = candidate(url=candidate_url, doi=doi, access_scope="abstract")
    research = packet()
    research["content"]["sources"][0].update(
        url=source_url, access_scope="full_text"
    )
    result = project_material(lead, evidence=[research])
    assert result.properties["access_scope"] == {"select": {"name": "全文"}}
    assert "发现记录的访问范围：摘要" in block_text(result.blocks)
    assert property_text(result, "authors") == lead["authors"]
    assert property_text(result, "affiliations") == lead["affiliations"]
    assert lead["access_scope"] == "abstract"


@pytest.mark.parametrize(
    "source_url",
    ["https://example.org/unrelated-paper", "https://example.org/news"],
)
def test_unrelated_full_text_or_shared_landing_page_cannot_upgrade_candidate(
    source_url,
):
    lead = candidate(
        url="https://example.org/news", doi="", access_scope="metadata"
    )
    research = packet()
    research["content"]["sources"] = [
        {
            **research["content"]["sources"][0],
            "title": lead["title"],
            "url": source_url,
            "access_scope": "full_text",
        }
    ]
    result = project_material(lead, evidence=[research])
    assert result.properties["access_scope"] == {"select": {"name": "仅线索"}}


@pytest.mark.parametrize(
    "discovered_scope,read_scope,expected",
    [
        ("metadata", "dataset", "仅线索"),
        ("metadata", "abstract", "摘要"),
        ("full_text", "abstract", "全文"),
    ],
)
def test_read_scope_uses_highest_exact_match_without_dataset_upgrade_or_downgrade(
    discovered_scope, read_scope, expected
):
    lead = candidate(access_scope=discovered_scope)
    research = packet()
    research["content"]["sources"][0].update(
        url=lead["url"], access_scope=read_scope
    )
    # The other source is full_text, but concerns a different work.
    result = project_material(lead, evidence=[research])
    assert result.properties["access_scope"] == {"select": {"name": expected}}
