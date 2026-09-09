"""Project frozen DAG artifacts and editions; never use mutable candidate history.

The importer is repeatable and bounded per pass. An invalid historical artifact
gets its own diagnostic receipt, without preventing other materials or editions
from being archived. These receipts are not editorial admission decisions.
"""

from __future__ import annotations

import json
from datetime import datetime

from newsletter.contracts import canonical_json
from newsletter.notion_content import edition_projection, material_projection
from newsletter.notion_journal import NotionJournal, material_aliases
from newsletter.store import now
from newsletter.types import Payload


def citations(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "citation" and isinstance(item, str):
                found.add(item)
            elif key in {"citations", "supporting_citations"} and isinstance(
                item, list
            ):
                found.update(text for text in item if isinstance(text, str))
            else:
                found.update(citations(item))
    elif isinstance(value, list):
        for item in value:
            found.update(citations(item))
    return found


class NotionIntake:
    def __init__(
        self, journal: NotionJournal, *, include_personal: bool
    ) -> None:
        self.journal = journal
        self.include_personal = include_personal
        journal.execute(
            "INSERT OR IGNORE INTO metadata VALUES('notion_v2_bootstrap_at',?)",
            (now(),),
        )
        self.bootstrap_at = journal.rows(
            "SELECT value FROM metadata WHERE key='notion_v2_bootstrap_at'"
        )[0]["value"]

    def historical(self, created_at: str) -> bool:
        return datetime.fromisoformat(created_at) < datetime.fromisoformat(
            self.bootstrap_at
        )

    def scan(self) -> int:
        imported = self._candidates() + self._research() + self._editions()
        self._repair_links()
        return imported

    def _candidates(self) -> int:
        j = self.journal
        if not j.exists("workflow_artifacts"):
            return 0
        rows = j.rows(
            "SELECT a.*,r.definition FROM workflow_artifacts a JOIN workflow_runs r "
            "ON r.id=a.run_id WHERE a.item_id='' AND NOT EXISTS(SELECT 1 FROM notion_imports i "
            "WHERE i.kind='candidates' AND i.source_id=a.id) ORDER BY a.rowid LIMIT 40"
        )
        for row in rows:
            error = ""
            try:
                definition = json.loads(row["definition"])
                node = next(
                    n for n in definition["nodes"] if n["id"] == row["node_id"]
                )
                if node["type"] == "deduplicate":
                    for candidate in json.loads(row["body"])["candidates"]:
                        try:
                            self._candidate(row, candidate)
                        except (ValueError, KeyError, TypeError):
                            # One malformed lead must not discard its siblings.
                            error = "notion_candidate_import_failed"
            except (ValueError, KeyError, TypeError, StopIteration):
                error = "notion_candidate_import_failed"
            j.mark_import("candidates", row["id"], row["content_hash"], error)
        return len(rows)

    def _candidate(self, row: Payload, candidate: Payload) -> None:
        j = self.journal
        body = canonical_json(candidate)
        previous = j.rows(
            "SELECT body FROM notion_candidates WHERE run_id=? AND candidate_id=?",
            (row["run_id"], candidate["id"]),
        )
        if previous and previous[0]["body"] != body:
            raise ValueError("notion_candidate_snapshot_changed")
        key, aliases = j.identity(candidate)
        first = (
            j.rows(
                "SELECT MIN(first_seen) AS first_seen FROM notion_candidates WHERE entity_key=?",
                (key,),
            )[0]["first_seen"]
            or row["created_at"]
        )
        projection = material_projection(
            candidate,
            key=key,
            first_seen=datetime.fromisoformat(first).date().isoformat(),
            run_id=row["run_id"],
            fixture=self.historical(row["created_at"]),
        )
        j.enqueue("material", projection, aliases)
        # A crash here is recoverable: enqueue is idempotent and import has not
        # been acknowledged. Every validation preceded either local write.
        j.execute(
            "INSERT OR IGNORE INTO notion_candidates VALUES(?,?,?,?,?)",
            (row["run_id"], candidate["id"], key, body, first),
        )

    def _research(self) -> int:
        j = self.journal
        if not j.exists("publication_units"):
            return 0
        rows = j.rows(
            "SELECT u.* FROM publication_units u WHERE NOT EXISTS(SELECT 1 FROM notion_imports i "
            "WHERE i.kind='research' AND i.source_id=u.digest) "
            "AND EXISTS(SELECT 1 FROM notion_candidates c WHERE c.run_id=u.run_id) "
            "ORDER BY u.rowid LIMIT 20"
        )
        for row in rows:
            error = ""
            try:
                task, result = json.loads(row["task"]), json.loads(row["body"])
                for candidate_id in task["candidate_ids"]:
                    try:
                        matches = j.rows(
                            "SELECT * FROM notion_candidates WHERE run_id=? AND candidate_id=?",
                            (row["run_id"], candidate_id),
                        )
                        if not matches:
                            continue  # Supplemental tasks may not name a discovered lead.
                        candidate = matches[0]
                        projection = material_projection(
                            json.loads(candidate["body"]),
                            key=candidate["entity_key"],
                            first_seen=datetime.fromisoformat(
                                candidate["first_seen"]
                            )
                            .date()
                            .isoformat(),
                            run_id=row["run_id"],
                            evidence=result["packets"],
                            progress="已研究",
                            fixture=self.historical(row["created_at"]),
                        )
                        j.enqueue("material", projection)
                    except (ValueError, KeyError, TypeError):
                        error = "notion_research_import_failed"
            except (ValueError, KeyError, TypeError):
                error = "notion_research_import_failed"
            j.mark_import("research", row["digest"], row["digest"], error)
        return len(rows)

    def _repair_links(self) -> None:
        # Discovery imports and a ready edition can arrive in different passes.
        # Relations therefore converge independently of edition updated_at and
        # without regenerating/reappending its frozen body.
        for row in self.journal.rows(
            "SELECT e.body,e.snapshot,w.run_id,n.key FROM editions e "
            "JOIN workflow_editions w ON w.edition_id=e.id "
            "JOIN notion_entities n ON n.key='edition:'||e.id WHERE e.state='ready'"
        ):
            try:
                self._link(
                    row["key"],
                    row["run_id"],
                    json.loads(row["body"]),
                    json.loads(row["snapshot"]),
                )
            except (ValueError, KeyError, TypeError):
                self.journal.mark_import(
                    "relations",
                    row["key"],
                    "invalid",
                    "notion_relation_import_failed",
                )

    def _editions(self) -> int:
        j = self.journal
        rows = j.rows(
            "SELECT e.*,w.run_id FROM editions e LEFT JOIN workflow_editions w ON w.edition_id=e.id "
            "WHERE e.state='ready' AND NOT EXISTS(SELECT 1 FROM notion_imports i "
            "WHERE i.kind='edition' AND i.source_id=e.id "
            "AND i.digest=CASE WHEN json_valid(e.body) THEN "
            "COALESCE(json_extract(e.body,'$.updated_at'),'invalid') ELSE 'invalid' END) "
            "ORDER BY e.rowid LIMIT 20"
        )
        for row in rows:
            edition: Payload = {}
            error = ""
            try:
                edition = json.loads(row["body"])
                if not edition.get("rendered"):
                    continue
                packets = json.loads(row["snapshot"])
                edition_type = "日常"
                run_id = row["run_id"] or ""
                if edition["is_fixture"] or self.historical(
                    edition["created_at"]
                ):
                    edition_type = "测试"
                elif j.rows(
                    "SELECT 1 FROM verification_sends WHERE edition_id=?",
                    (edition["id"],),
                ):
                    edition_type = "修订"
                elif j.exists("collection_runs"):
                    request = j.rows(
                        "SELECT request_key FROM collection_runs WHERE id=?",
                        (run_id,),
                    )
                    if (
                        not request
                        or request[0]["request_key"]
                        != "daily-" + edition["issue_date"]
                    ):
                        edition_type = "测试"
                projection = edition_projection(
                    edition,
                    run_id=run_id,
                    packets=packets,
                    include_personal=self.include_personal,
                    edition_type=edition_type,
                )
                j.enqueue("edition", projection)
                self._link(projection.key, run_id, edition, packets)
            except (ValueError, KeyError, TypeError):
                error = "notion_edition_import_failed"
            j.mark_import(
                "edition",
                row["id"],
                edition.get("updated_at", "invalid"),
                error,
            )
        return len(rows)

    def _link(
        self,
        edition_key: str,
        run_id: str,
        edition: Payload,
        packets: list[Payload],
    ) -> None:
        """Only actually cited source identities create adopted-material relations."""
        used = citations(edition["draft"])
        keys: set[str] = set()
        for packet in packets:
            for source in packet["content"]["sources"]:
                if packet["id"] + "/" + source["id"] in used:
                    try:
                        keys.update(material_aliases(source))
                    except ValueError:
                        pass
        for candidate in self.journal.rows(
            "SELECT body,entity_key FROM notion_candidates WHERE run_id=?",
            (run_id,),
        ):
            if set(material_aliases(json.loads(candidate["body"]))) & keys:
                self.journal.execute(
                    "INSERT OR IGNORE INTO notion_links VALUES(?,?)",
                    (edition_key, candidate["entity_key"]),
                )
