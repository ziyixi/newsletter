"""Full default DAG + durable service tail, with deliberately synthetic node outputs.

No lifecycle/live preflight, SDK execution, provider HTTP, or mail adapter is used.
Only the content handlers are replaced; scheduling, artifacts, packets, projection
dispatch, edition binding, rendering, usage accounting and send guards stay real.
"""

from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import pytest
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.adapters import AdapterError
from newsletter.collection.collector import MockCollector
from newsletter.collection.repository import RunRepository
from newsletter.contracts import parse_message, to_dict, validate_draft
from newsletter.editor import CodexEditor, MockEditor
from newsletter.settings import Settings
from newsletter.store import Store, StoreError
from newsletter.usage import codex_usage, observe_codex_usage
from newsletter.worker import Worker
from newsletter.workflow.nodes import EditorialNodes
from newsletter.workflow.pipeline import DagPipeline, freeze_workflow
from newsletter.workflow.state import WorkflowState

ISSUE_DATE = "2026-09-06"
MODEL_KINDS = {
    "discovery",
    "selection",
    "research",
    "composition",
    "gap_plan",
    "finalization",
    "review",
}


def candidate(direction):
    return {
        "id": direction,
        "direction": direction,
        "title": "Synthetic candidate " + direction,
        "url": "https://example.org/" + direction,
        "doi": "",
        "version": "",
        "event_key": "",
        "published_at": ISSUE_DATE,
        "summary": "离线构造的候选，不是真实研究。",
        "why_now": "仅检验六方向发现、选题和深读之间的数据流。",
        "access_scope": "metadata",
        "provenance": "fixture-handler",
    }


def task(identifier, source=None):
    return {
        "id": identifier,
        "candidate_ids": [source["id"]] if source else [],
        "question": "检验固定材料中的证据边界。",
        "why": "这是离线集成测试，不生成真实报道。",
        "priority": 1,
        "evidence_context": "补查任务可以没有候选 ID，但必须携带明确的证据问题。",
        "source_urls": [source["url"]] if source else ["https://example.org/gap"],
    }


def draft(packets):
    adopted = [p for p in packets if "unused" not in p["content"]["tags"]]
    return {
        "subject": "MOCK · DAG 集成验收",
        "title": "只用于离线测试的报纸",
        "introduction": "这些段落不是新闻，不能作为事实证据。",
        "sections": [
            {
                "kind": "feature",
                "heading": "固定研究与补查",
                "paragraphs": [
                    {
                        "text": "这是一个构造的研究结果，只检验引用是否完整。",
                        "citations": [p["id"] + "/source"],
                    }
                    for p in adopted
                ],
                "limitations": "无真实研究结论。",
            }
        ],
        "recommended_reading": {
            "citation": adopted[0]["id"] + "/source",
            "reason": "问题、方法、结果和限制均为测试构造；这里检验自足介绍卡及出处渲染。",
        },
        "limitations": "本稿全部为 fixture。",
    }


def record_synthetic_usage():
    # Exercise the real ContextVar sink and cumulative-snapshot replacement.
    with codex_usage("synthetic-no-model") as usage:
        usage.start_turn()
        for count in (80, 100, 100):
            observe_codex_usage(
                "thread/tokenUsage/updated",
                {
                    "tokenUsage": {
                        "total": {
                            "inputTokens": count,
                            "cachedInputTokens": 40,
                            "outputTokens": 20,
                            "reasoningOutputTokens": 5,
                            "totalTokens": count + 20,
                        }
                    }
                },
            )
        observe_codex_usage("turn/completed", {})


class FakeNotion:
    def __init__(self):
        self.calls = []
        self.failed_tags = set()
        self.ambiguous = False

    async def project(self, packet):
        assert packet["is_fixture"] is True
        self.calls.append(packet["id"])
        if self.failed_tags.intersection(packet["content"]["tags"]):
            raise AdapterError("NOTION_FIXTURE_FAILURE", ambiguous=self.ambiguous)


def attach(rig):
    rig.runs = RunRepository(rig.store)
    rig.pipeline = DagPipeline(
        rig.runs,
        MockCollector(),
        rig.path / "collection",
        10,
        32,
        editor=CodexEditor(rig.path / "nonexistent-auth-home"),
    )
    rig.worker = Worker(
        rig.store,
        MockEditor(),
        rig.notion,
        rig.path / "editor",
        10,
        pipeline=rig.pipeline,
    )


@pytest.fixture
def rig(tmp_path, monkeypatch):
    rig = SimpleNamespace(
        path=tmp_path,
        store=Store(tmp_path / "state.sqlite3", "mock"),
        notion=FakeNotion(),
        calls=Counter(),
        forbidden_calls=[],
        review_passed=True,
    )

    async def forbidden(*args, **kwargs):
        rig.forbidden_calls.append("model-or-legacy-collector")
        raise AssertionError("The frozen DAG must never run an SDK or a second editor")

    monkeypatch.setattr(CodexEditor, "execute", forbidden)
    monkeypatch.setattr(CodexEditor, "prepare", forbidden)
    monkeypatch.setattr(MockEditor, "prepare", forbidden)
    monkeypatch.setattr(MockCollector, "collect", forbidden)

    async def execute(nodes, kind, ctx, path):
        rig.calls[(ctx.node_id, ctx.item_id)] += 1
        assert path.is_dir()
        if kind in MODEL_KINDS:
            record_synthetic_usage()
        if kind == "history":
            return {"candidates": [], "editions": [], "watchlist": []}
        if kind == "api_feed":
            return {"candidates": [], "diagnostics": ["offline fixture: no HTTP"]}
        if kind == "discovery":
            return {"candidates": [candidate(ctx.item["id"])], "note": "fixture"}
        if kind == "deduplicate":
            candidates = [c for batch in nodes.one(ctx, "discovery") for c in batch["candidates"]]
            nodes.state.remember(candidates, ISSUE_DATE)
            return {"candidates": candidates}
        if kind == "selection":
            candidates = nodes.one(ctx, "deduplicate")["candidates"]
            return {
                "research_tasks": [task("adopted", candidates[0]), task("unused", candidates[1])],
                "note": "只选两项，不凑满默认八项。",
            }
        if kind == "research":
            supplied = ctx.item
            packet = nodes.store.put_packet(
                {
                    "request_key": f"{ctx.run_id}:{ctx.node_id}:{supplied['id']}",
                    "workflow_id": ctx.node_id,
                    "content": {
                        "title": "Synthetic " + supplied["id"],
                        "body": "仅用于离线流程验收。",
                        "sources": [
                            {
                                "id": "source",
                                "title": "Synthetic source",
                                "url": supplied["source_urls"][0],
                                "excerpt": "",
                                "access_scope": "full_text",
                                "published_at": ISSUE_DATE,
                            }
                        ],
                        "tags": ["fixture", supplied["id"]],
                    },
                },
                principal="workflow-research",
            )
            return {
                "packets": [packet],
                "note": "fixture",
                "candidate_ids": supplied["candidate_ids"],
            }
        if kind in {"composition", "finalization"}:
            packets = nodes.packets(ctx)
            return {
                "draft": draft(packets),
                "packets": packets,
                "review": {"passed": True, "findings": []},
            }
        if kind == "gap_plan":
            return {"research_tasks": [task("gap")], "note": "只执行一轮有界补查。"}
        if kind == "review":
            result = deepcopy(nodes.one(ctx, "finalization"))
            result["review"] = {
                "passed": rig.review_passed,
                "findings": [] if rig.review_passed else ["HOLD: synthetic unresolved evidence"],
            }
            return result
        raise AssertionError("Unexpected registered node type")

    monkeypatch.setattr(EditorialNodes, "execute", execute)
    attach(rig)
    instructions, snapshot = freeze_workflow(
        Settings(data_dir=tmp_path), rig.pipeline.state, ISSUE_DATE
    )
    assert len(instructions) == 6
    rig.snapshot = snapshot
    rig.run = rig.runs.start(
        {"request_key": "synthetic-daily", "issue_date": ISSUE_DATE},
        instructions,
        workflow_snapshot=snapshot,
    )
    try:
        yield rig
    finally:
        rig.store.close()


def receipt(rig):
    value = rig.pipeline.receipt(rig.run["id"])
    # Exact public API conversion, including uint64 usage counts and optional data.
    message = parse_message(value, pb.CollectionRun)
    assert parse_message(to_dict(message), pb.CollectionRun) == message
    assert message.id == rig.run["id"]
    assert message.is_fixture
    return value


async def drain(rig):
    for _ in range(100):
        receipt(rig)
        if not await rig.worker.step():
            assert not rig.forbidden_calls
            return receipt(rig)
    pytest.fail("Offline DAG did not reach a bounded terminal state")


def approval(edition):
    return {
        "id": edition["id"],
        "request_key": "synthetic-approval",
        "expected_render_hash": edition.get("rendered", {}).get("render_hash", "not-rendered"),
    }


def assert_no_mail(rig):
    assert rig.store.db.execute("SELECT COUNT(*) FROM sends").fetchone()[0] == 0
    assert not list(rig.path.rglob("*.eml"))
    assert not rig.forbidden_calls


@pytest.mark.asyncio
async def test_default_dag_reaches_bound_ready_edition_with_usage_and_public_receipt(rig):
    assert receipt(rig)["state"] == "queued"
    finished = await drain(rig)
    assert finished["state"] == "ready", finished
    assert finished["workflow"]["state"] == "succeeded"
    assert finished["workflow"]["candidate_count"] == 6
    assert finished["workflow"]["research_count"] == 3
    assert all(count == 1 for count in rig.calls.values())
    edition = rig.store.get(finished["edition_id"])
    bound = WorkflowState(rig.store).edition(edition["id"])
    packets = rig.pipeline.repository.output(rig.run["id"], "review")["packets"]
    validate_draft(edition["draft"], packets)
    assert len(edition["packet_ids"]) == 3 and len(bound["required_packets"]) == 2
    assert edition["state"] == "ready" and edition["delivery_state"] == "not_requested"
    assert edition["review"]["passed"] and edition["is_fixture"]
    assert "补查任务" not in edition["rendered"]["text"]  # No internal task prompts rendered.
    assert "https://example.org/gap" in edition["rendered"]["text"]
    assert "MOCK · 用量统计仅为流程演示" in edition["rendered"]["html"]
    assert "MOCK · 用量统计仅为流程演示" in edition["rendered"]["text"]
    # 6 discovery + selection + 3 research + composition + gap + final + review.
    assert finished["usage"]["invocations"] == 14
    assert finished["usage"]["usage"]["total_tokens"] == 14 * 120
    assert not finished["usage"]["partial"]
    assert int(edition["usage"]["usage"]["total_tokens"]) == 14 * 120
    assert len(rig.notion.calls) == 4  # Three research packets plus optional candidate index.
    assert_no_mail(rig)

    with pytest.raises(StoreError):
        rig.store.reserve_send({**approval(edition), "expected_render_hash": "wrong"})
    adopted = bound["required_packets"][0]
    rig.store.projection_result(adopted, "pending")
    with pytest.raises(StoreError):
        rig.store.reserve_send(approval(edition))
    assert_no_mail(rig)
    rig.store.projection_result(adopted, "done")
    assert rig.store.reserve_send(approval(edition))[1] is True
    assert rig.store.reserve_send(approval(edition))[1] is False
    rig.store.recover()
    assert rig.store.reserve_send(approval(edition))[1] is False
    assert rig.store.get(edition["id"])["delivery_state"] == "unknown"
    assert not list(rig.path.rglob("*.eml"))  # Reservations are not adapter calls.


@pytest.mark.asyncio
async def test_restart_after_completed_research_preserves_artifacts_and_does_not_repeat(rig):
    for _ in range(40):
        assert await rig.worker.step()
        if ("research", "adopted") in rig.calls:
            break
    else:
        pytest.fail("First selected research item was never executed")
    before_calls = rig.calls.copy()
    before_artifacts = rig.pipeline.repository.artifacts(rig.run["id"])
    before_attempts = rig.pipeline.repository.attempts(rig.run["id"])
    frozen = rig.runs.workflow_snapshot(rig.run["id"])
    rig.store.close()
    rig.store = Store(rig.path / "state.sqlite3", "mock")
    attach(rig)
    rig.store.recover()
    rig.runs.recover()
    rig.pipeline.recover()
    assert rig.runs.workflow_snapshot(rig.run["id"]) == frozen == rig.snapshot
    assert rig.pipeline.repository.artifacts(rig.run["id"]) == before_artifacts
    assert (await drain(rig))["state"] == "ready"
    assert all(rig.calls[key] == count == 1 for key, count in before_calls.items())
    attempts = rig.pipeline.repository.attempts(rig.run["id"])
    assert all(attempt in attempts for attempt in before_attempts)
    assert all(count == 1 for count in rig.calls.values())
    assert len(rig.notion.calls) == len(set(rig.notion.calls)) == 4
    assert receipt(rig)["usage"]["invocations"] == 14
    assert_no_mail(rig)


@pytest.mark.asyncio
async def test_independent_review_hold_blocks_worker_render_and_send(rig):
    rig.review_passed = False
    finished = await drain(rig)
    assert finished["state"] == "blocked", finished
    assert finished["error_code"] == "editorial_review_failed"
    edition = rig.store.get(finished["edition_id"])
    assert edition["state"] == "blocked" and not edition["review"]["passed"]
    assert not edition.get("rendered")
    with pytest.raises(StoreError):
        rig.store.reserve_send(approval(edition))
    assert_no_mail(rig)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["write", "projection"])
async def test_optional_archive_and_unused_projection_failure_do_not_block_adopted_packets(
    rig, monkeypatch, failure
):
    rig.notion.failed_tags.add("unused")
    if failure == "write":
        put_packet = Store.put_packet

        def fail_only_archive(store, request, principal="ingest"):
            if request["workflow_id"] == "candidate-index":
                raise OSError("synthetic optional archive failure")
            return put_packet(store, request, principal)

        monkeypatch.setattr(Store, "put_packet", fail_only_archive)
    else:
        rig.notion.failed_tags.add("candidate-index")
    finished = await drain(rig)
    assert finished["state"] == "ready", finished
    edition = rig.store.get(finished["edition_id"])
    binding = rig.pipeline.state.edition(edition["id"])
    assert rig.runs.projection_states(binding["required_packets"]) == ["done", "done"]
    unused = set(edition["packet_ids"]) - set(binding["required_packets"])
    assert rig.runs.projection_states(list(unused)) == ["failed"]
    archive = rig.store.db.execute(
        "SELECT * FROM workflow_archives WHERE run_id=?", (rig.run["id"],)
    ).fetchone()
    if failure == "write":
        assert archive["error_code"] == "candidate_archive_failed"
    else:
        assert rig.runs.projection_states([archive["packet_id"]]) == ["failed"]
    assert_no_mail(rig)
    assert rig.store.reserve_send(approval(edition))[1] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("ambiguous", [False, True])
async def test_adopted_projection_failure_blocks_publication_and_is_never_auto_retried(
    rig, ambiguous
):
    rig.notion.failed_tags.add("adopted")
    rig.notion.ambiguous = ambiguous
    finished = await drain(rig)
    assert finished["state"] == "blocked", finished
    assert finished["error_code"] == "notion_projection_unconfirmed"
    edition = rig.store.get(finished["edition_id"])
    assert edition["state"] == "ready"  # Rendering success alone does not authorize sending.
    with pytest.raises(StoreError):
        rig.store.reserve_send(approval(edition))
    calls = list(rig.notion.calls)
    rig.store.recover()
    rig.runs.recover()
    rig.pipeline.recover()
    assert await rig.worker.step() is False
    assert rig.notion.calls == calls
    assert len(calls) == len(set(calls)) == 4
    assert_no_mail(rig)
