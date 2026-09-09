"""Application resource ownership and explicit backend composition.

This is the only place that opens storage, checks dependencies and starts/stops
the worker. Request handlers do not construct providers or own their lifetime.
"""

import asyncio
import fcntl
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import cast

from fastapi import FastAPI

from newsletter.adapters import (
    DisabledNotion,
    FakeMail,
    FakeNotion,
    MailAdapter,
    Notion,
    NotionAdapter,
    Resend,
)
from newsletter.collection.collector import (
    CodexCollector,
    Collector,
    MockCollector,
)
from newsletter.collection.instructions import load_instructions
from newsletter.collection.pipeline import CollectionPipeline
from newsletter.collection.repository import RunRepository
from newsletter.editor import CodexEditor, Editor, MockEditor
from newsletter.notion_api import NotionWorkspace
from newsletter.notion_journal import NotionJournal
from newsletter.notion_sync import NotionSync
from newsletter.preflight import preflight
from newsletter.settings import Settings
from newsletter.store import Store
from newsletter.todofy import DisabledTodofy, FakeTodofy, Todofy, TodofyAdapter
from newsletter.worker import Worker
from newsletter.workflow.pipeline import DagPipeline, freeze_workflow
from newsletter.workflow.state import WorkflowState


@asynccontextmanager
async def service_lifespan(
    app: FastAPI,
    *,
    settings: Settings,
    editor: Editor | None = None,
    notion: NotionAdapter | None = None,
    mail: MailAdapter | None = None,
    todofy: TodofyAdapter | None = None,
    collector: Collector | None = None,
    start_worker: bool = True,
) -> AsyncIterator[None]:
    settings.data_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    settings.data_dir.chmod(0o700)
    with (settings.data_dir / "service.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Only one service process may own this data directory"
            ) from None
        store = Store(
            settings.data_dir / "newsletter.sqlite3",
            settings.mode,
            settings.max_pending_jobs,
        )
        try:
            store.bind_delivery_target(
                {
                    "backend": settings.mail_backend,
                    "from": settings.from_email,
                    "to": settings.recipient_email,
                }
            )
            store.recover()
            # A process must not advertise readiness with broken enabled dependencies.
            app.state.preflight = await preflight(settings, store=store)
            load_instructions(settings.instructions_dir)
            runs = RunRepository(store)
            runs.recover()
            workflow_state = WorkflowState(store)
            dag_enabled = (
                settings.workflow_backend == "dag" and settings.mode == "live"
            )
            if dag_enabled:
                # Fail startup on malformed graphs or missing instruction resources.
                freeze_workflow(settings, workflow_state, "2000-01-01")
            chosen_editor: Editor = editor or (
                MockEditor()
                if settings.editor_backend == "mock"
                else CodexEditor(
                    codex_home=cast(Path, settings.codex_home),
                    model=settings.model,
                )
            )
            notion_factories: dict[str, Callable[[], NotionAdapter]] = {
                "disabled": lambda: DisabledNotion(),
                "fake": lambda: FakeNotion(settings.data_dir / "notion"),
                "notion": lambda: Notion(
                    settings.notion_token, settings.notion_data_source_id
                ),
            }
            notion_v2 = (
                settings.notion_backend == "notion" and settings.notion_v2
            )
            chosen_notion = notion or (
                DisabledNotion()
                if notion_v2
                else notion_factories[settings.notion_backend]()
            )
            app.state.mail = mail or (
                FakeMail(settings.data_dir / "outbox")
                if settings.mail_backend == "fake"
                else Resend(
                    settings.resend_api_key,
                    settings.from_email,
                    settings.recipient_email,
                )
            )
            todofy_factories: dict[str, Callable[[], TodofyAdapter]] = {
                "disabled": lambda: DisabledTodofy(),
                "fake": lambda: FakeTodofy(),
                "todofy": lambda: Todofy(
                    settings.todofy_base_url,
                    settings.todofy_user,
                    settings.todofy_password,
                    mode=settings.todofy_mode,
                    top=settings.todofy_top,
                    time_zone=settings.time_zone,
                ),
            }
            research_editor = (
                CodexEditor(
                    cast(Path, settings.codex_home),
                    model=settings.model,
                    timeout_seconds=settings.collection_timeout_seconds,
                )
                if settings.mode == "live"
                else None
            )
            chosen_collector = collector or (
                MockCollector()
                if settings.mode == "mock"
                else CodexCollector(cast(CodexEditor, research_editor))
            )
            pipeline_args = (
                runs,
                chosen_collector,
                settings.data_dir / "collection-jobs",
                settings.collection_timeout_seconds,
                settings.max_packets,
            )
            pipeline: CollectionPipeline = (
                DagPipeline(
                    *pipeline_args,
                    editor=cast(CodexEditor, research_editor),
                    recipe_path=settings.workflow_file,
                )
                if dag_enabled
                else CollectionPipeline(*pipeline_args)
            )
            if isinstance(pipeline, DagPipeline):
                pipeline.recover()
            worker = Worker(
                store,
                chosen_editor,
                chosen_notion,
                settings.data_dir / "editor-jobs",
                settings.job_timeout_seconds,
                todofy=todofy or todofy_factories[settings.todofy_backend](),
                pipeline=pipeline,
                skip_packet_projection=notion_v2,
            )
            app.state.store, app.state.worker = store, worker
            app.state.runs = runs
            app.state.workflow_state = workflow_state
            sync = None
            if notion_v2:
                sync = NotionSync(
                    NotionJournal(
                        store,
                        {
                            "materials": settings.notion_materials_data_source_id,
                            "editions": settings.notion_editions_data_source_id,
                            "include_personal": settings.notion_archive_private,
                        },
                    ),
                    NotionWorkspace(
                        settings.notion_token,
                        settings.notion_materials_data_source_id,
                        settings.notion_editions_data_source_id,
                    ),
                    include_personal=settings.notion_archive_private,
                )
            app.state.notion_sync = sync
            task = asyncio.create_task(worker.run()) if start_worker else None
            app.state.worker_task = task
            sync_task = (
                asyncio.create_task(sync.run())
                if sync and start_worker
                else None
            )
            app.state.notion_sync_task = sync_task
            try:
                yield
            finally:
                if sync_task:
                    sync_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await sync_task
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
        finally:
            store.close()
