"""Durable Notion projection receipts, separate from publication and email receipts.

SQLite owns identities and immutable body versions. A timed-out create/append is
reconciled by reading Notion; it is never blindly repeated. No network call is
made inside a transaction, and this module cannot enqueue research or send mail.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from newsletter.contracts import canonical_json, content_hash
from newsletter.notion_content import Projection
from newsletter.store import Store
from newsletter.types import Payload
from newsletter.workflow.sources import identity_keys


def material_aliases(candidate: Payload) -> list[str]:
    """Never merge by title; generic landing pages need a dated event identity."""
    keys = identity_keys(candidate)
    keys = {key for key in keys if not key.startswith("title:")}
    strong = {key for key in keys if key.startswith(("doi:", "arxiv:"))}
    if strong:
        # A broad topic such as "new architecture" does not identify a paper.
        keys = {key for key in keys if not key.startswith("event:")}
    if not strong:
        for key in list(keys):
            if key.startswith("url:") and urlsplit(key[4:]).path.rstrip("/") in {
                "",
                "/news",
                "/research",
                "/publications",
                "/papers",
                "/blog",
            }:
                keys.remove(key)
                event = str(candidate.get("event_key") or candidate.get("published_at") or "")
                if event:
                    keys.add(key + "#event:" + event.casefold())
    if not keys:
        raise ValueError("notion_material_identity_missing")
    return sorted(
        keys,
        key=lambda key: (
            next(
                i
                for i, prefix in enumerate(("doi:", "arxiv:", "url:", "event:"))
                if key.startswith(prefix)
            ),
            key,
        ),
    )


class NotionJournal:
    def __init__(self, store: Store, destination: Payload) -> None:
        self.store = store
        with store.lock:
            store.db.executescript("""
                CREATE TABLE IF NOT EXISTS notion_entities (
                    key TEXT PRIMARY KEY, kind TEXT NOT NULL, page_id TEXT NOT NULL DEFAULT '',
                    create_state TEXT NOT NULL DEFAULT 'new', properties TEXT NOT NULL,
                    applied_hash TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    retry_at REAL NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS notion_versions (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, entity_key TEXT NOT NULL,
                    digest TEXT NOT NULL, blocks TEXT NOT NULL, chart TEXT NOT NULL,
                    upload_id TEXT NOT NULL DEFAULT '', upload_at REAL NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'pending',
                    offset INTEGER NOT NULL DEFAULT 0, pending_chunk TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '', UNIQUE(entity_key,digest),
                    FOREIGN KEY(entity_key) REFERENCES notion_entities(key));
                CREATE TABLE IF NOT EXISTS notion_aliases (
                    alias TEXT PRIMARY KEY, entity_key TEXT NOT NULL,
                    FOREIGN KEY(entity_key) REFERENCES notion_entities(key));
                CREATE TABLE IF NOT EXISTS notion_candidates (
                    run_id TEXT NOT NULL, candidate_id TEXT NOT NULL, entity_key TEXT NOT NULL,
                    body TEXT NOT NULL, first_seen TEXT NOT NULL,
                    PRIMARY KEY(run_id,candidate_id));
                CREATE TABLE IF NOT EXISTS notion_imports (
                    kind TEXT NOT NULL, source_id TEXT NOT NULL, digest TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '', PRIMARY KEY(kind,source_id));
                CREATE TABLE IF NOT EXISTS notion_links (
                    edition_key TEXT NOT NULL, material_key TEXT NOT NULL,
                    PRIMARY KEY(edition_key,material_key));
            """)
        with store.transaction():
            if "upload_at" not in {
                row["name"] for row in store.db.execute("PRAGMA table_info(notion_versions)")
            }:
                store.db.execute(
                    "ALTER TABLE notion_versions ADD COLUMN upload_at REAL NOT NULL DEFAULT 0"
                )
            digest = content_hash(destination)
            old = store.db.execute(
                "SELECT value FROM metadata WHERE key='notion_v2_destination'"
            ).fetchone()
            if old and old[0] != digest:
                raise ValueError("Notion destination/privacy changed; explicit migration required")
            store.db.execute(
                "INSERT OR IGNORE INTO metadata VALUES ('notion_v2_destination',?)", (digest,)
            )
            # A crash after dispatch but before acknowledgement is an unknown
            # external result, not permission to repeat the mutation.
            store.db.execute(
                "UPDATE notion_entities SET create_state='unknown' WHERE create_state='creating'"
            )
            store.db.execute("UPDATE notion_versions SET state='unknown' WHERE state='appending'")

    def rows(self, sql: str, args: tuple[Any, ...] = ()) -> list[Payload]:
        with self.store.lock:
            return [dict(row) for row in self.store.db.execute(sql, args).fetchall()]

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> None:
        with self.store.transaction():
            self.store.db.execute(sql, args)

    def exists(self, table: str) -> bool:
        return bool(
            self.rows("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
        )

    def identity(self, candidate: Payload) -> tuple[str, list[str]]:
        aliases = material_aliases(candidate)
        found = {
            row["entity_key"]
            for row in self.rows(
                "SELECT entity_key FROM notion_aliases WHERE alias IN ("
                + ",".join("?" for _ in aliases)
                + ")",
                tuple(aliases),
            )
        }
        if len(found) > 1:
            raise ValueError("notion_material_identity_conflict")
        if found:
            existing_aliases = {
                row["alias"]
                for row in self.rows(
                    "SELECT alias FROM notion_aliases WHERE entity_key=?",
                    (next(iter(found)),),
                )
            }
            for prefix in ("doi:", "arxiv:"):
                incoming = {key for key in aliases if key.startswith(prefix)}
                previous = {key for key in existing_aliases if key.startswith(prefix)}
                if incoming and previous and incoming.isdisjoint(previous):
                    raise ValueError("notion_material_identity_conflict")
        return (next(iter(found)) if found else "material:v1:" + content_hash(aliases[0]), aliases)

    def enqueue(self, kind: str, projection: Projection, aliases: Sequence[str] = ()) -> None:
        with self.store.transaction():
            old = self.store.db.execute(
                "SELECT kind,properties FROM notion_entities WHERE key=?", (projection.key,)
            ).fetchone()
            if old and old[0] != kind:
                raise ValueError("notion_entity_kind_conflict")
            if (
                kind == "edition"
                and self.store.db.execute(
                    "SELECT 1 FROM notion_versions WHERE entity_key=? AND digest!=?",
                    (projection.key, projection.digest),
                ).fetchone()
            ):
                # Updating delivery columns must never mutate a frozen edition.
                raise ValueError("notion_frozen_edition_changed")
            properties = json.loads(canonical_json(projection.properties))
            if old and kind == "material":
                previous = json.loads(old["properties"])
                for name in ("direction", "topics"):
                    names = {
                        item["name"]
                        for source in (previous, properties)
                        for item in source.get(name, {}).get("multi_select", [])
                    }
                    properties[name] = {"multi_select": [{"name": name} for name in sorted(names)]}
                ranks = ["候选", "继续跟进", "已研究", "已刊出"]
                progress = [
                    source.get("progress", {}).get("select", {}).get("name", "候选")
                    for source in (previous, properties)
                ]
                properties["progress"] = {"select": {"name": max(progress, key=ranks.index)}}
                properties["fixture"] = {
                    "checkbox": all(
                        source.get("fixture", {}).get("checkbox", False)
                        for source in (previous, properties)
                    )
                }
                for name in ("authors", "affiliations", "venue", "publication_status"):
                    if not properties.get(name, {}).get("rich_text") and name in previous:
                        properties[name] = previous[name]
            self.store.db.execute(
                "INSERT INTO notion_entities(key,kind,properties) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET properties=excluded.properties",
                (projection.key, kind, canonical_json(properties)),
            )
            self.store.db.execute(
                "INSERT OR IGNORE INTO notion_versions(entity_key,digest,blocks,chart) "
                "VALUES(?,?,?,?)",
                (
                    projection.key,
                    projection.digest,
                    canonical_json(projection.blocks),
                    base64.b64encode(projection.chart_png or b"").decode(),
                ),
            )
            for alias in aliases:
                old_alias = self.store.db.execute(
                    "SELECT entity_key FROM notion_aliases WHERE alias=?", (alias,)
                ).fetchone()
                if old_alias and old_alias[0] != projection.key:
                    raise ValueError("notion_material_identity_conflict")
                self.store.db.execute(
                    "INSERT OR IGNORE INTO notion_aliases VALUES (?,?)", (alias, projection.key)
                )

    def imported(self, kind: str, source_id: str, digest: str) -> bool:
        return bool(
            self.rows(
                "SELECT 1 FROM notion_imports WHERE kind=? AND source_id=? AND digest=?",
                (kind, source_id, digest),
            )
        )

    def mark_import(self, kind: str, source_id: str, digest: str, error: str = "") -> None:
        self.execute(
            "INSERT INTO notion_imports VALUES(?,?,?,?) ON CONFLICT(kind,source_id) "
            "DO UPDATE SET digest=excluded.digest,error=excluded.error",
            (kind, source_id, digest, error),
        )

    def entity(self, key: str) -> Payload:
        return self.rows("SELECT * FROM notion_entities WHERE key=?", (key,))[0]

    def versions(self, key: str) -> list[Payload]:
        return self.rows("SELECT * FROM notion_versions WHERE entity_key=? ORDER BY seq", (key,))

    def desired(self, entity: Payload) -> Payload:
        properties = json.loads(entity["properties"])
        edition = entity["kind"] == "edition"
        source, target = (
            ("edition_key", "material_key") if edition else ("material_key", "edition_key")
        )
        related = self.rows(
            f"SELECT DISTINCT e.page_id FROM notion_links l JOIN notion_entities e "
            f"ON e.key=l.{target} WHERE l.{source}=? AND e.page_id!='' ORDER BY e.page_id",
            (entity["key"],),
        )
        if len(related) > 100:
            raise ValueError("notion_relation_capacity")
        properties["material_ids" if edition else "edition_ids"] = {
            "relation": [{"id": row["page_id"]} for row in related]
        }
        if not edition and related:
            properties["progress"] = {"select": {"name": "已刊出"}}
        done = all(v["state"] == "done" for v in self.versions(entity["key"]))
        properties["sync_state"] = {"select": {"name": "已同步" if done else "同步中"}}
        return properties

    def retry(self, key: str, code: str) -> None:
        entity = self.entity(key)
        attempts = entity["attempts"] + 1
        delay = min(3600, 30 * 2 ** min(attempts - 1, 7))
        self.execute(
            "UPDATE notion_entities SET error=?,retry_at=?,attempts=? WHERE key=?",
            (code, time.time() + delay, attempts, key),
        )

    def clear_error(self, key: str) -> None:
        self.execute(
            "UPDATE notion_entities SET error='',retry_at=0,attempts=0 WHERE key=?", (key,)
        )

    def summary(self) -> Payload:
        return {
            "entities": self.rows(
                "SELECT kind,create_state,COUNT(*) AS count FROM notion_entities "
                "GROUP BY kind,create_state"
            ),
            "versions": self.rows(
                "SELECT state,COUNT(*) AS count FROM notion_versions GROUP BY state"
            ),
            "errors": self.rows(
                "SELECT error,COUNT(*) AS count FROM notion_entities WHERE error!='' GROUP BY error"
            ),
            "import_errors": self.rows(
                "SELECT error,COUNT(*) AS count FROM notion_imports WHERE error!='' GROUP BY error"
            ),
        }
