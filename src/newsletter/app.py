"""Private ProtoJSON HTTP service. No model, Notion, or mail I/O during import."""

import asyncio
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import replace
from functools import partial
from typing import Any, cast
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from google.protobuf.message import Message
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response
from ziyixi_protos.newsletter import editorial_pb2 as pb

from newsletter.adapters import AdapterError, MailAdapter, NotionAdapter
from newsletter.collection.collector import Collector
from newsletter.collection.instructions import (
    InstructionError,
    load_instructions,
)
from newsletter.collection.repository import RunRepository
from newsletter.contracts import (
    ContractError,
    parse_message,
    to_dict,
    validate_request,
)
from newsletter.editor import Editor
from newsletter.lifecycle import service_lifespan
from newsletter.rendering import preview_html as preview_html
from newsletter.rendering import render_edition
from newsletter.settings import Settings
from newsletter.store import Store, StoreError
from newsletter.todofy import TodofyAdapter
from newsletter.types import Payload, Role
from newsletter.worker import Worker
from newsletter.workflow.definition import DefinitionError
from newsletter.workflow.pipeline import DagPipeline, freeze_workflow
from newsletter.workflow.story_replay import StoryReplay


def create_app(
    settings: Settings | None = None,
    *,
    editor: Editor | None = None,
    notion: NotionAdapter | None = None,
    mail: MailAdapter | None = None,
    todofy: TodofyAdapter | None = None,
    collector: Collector | None = None,
    start_worker: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    # macOS system temp ancestors (/var, /tmp) are symlinks. Canonicalize the
    # validated service root before handing isolated paths to the strict editor.
    settings = replace(settings, data_dir=settings.data_dir.resolve())

    app = FastAPI(
        title="Personal Newsletter",
        version="0.1.0",
        lifespan=partial(
            service_lifespan,
            settings=settings,
            editor=editor,
            notion=notion,
            mail=mail,
            todofy=todofy,
            collector=collector,
            start_worker=start_worker,
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    def auth(*roles: Role) -> Callable[[Request], Awaitable[None]]:
        async def check(request: Request) -> None:
            header = request.headers.get("authorization", "")
            token = header[7:] if header.startswith("Bearer ") else ""
            accepted = [getattr(settings, f"{role}_token") for role in roles]
            if not any(
                secrets.compare_digest(token.encode(), value.encode())
                for value in accepted
            ):
                raise HTTPException(
                    401,
                    "Valid bearer token required",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        return check

    async def body(request: Request, message_type: type[Message]) -> Payload:
        if (
            request.headers.get("content-type", "").split(";")[0].strip()
            != "application/json"
        ):
            raise HTTPException(415, "Use application/json ProtoJSON")
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > settings.max_body_bytes:
                raise HTTPException(413, "Request body exceeds limit")
        message = parse_message(bytes(data), message_type)
        validate_request(message)
        return to_dict(message)

    def response(
        value: Mapping[str, Any], message_type: type[Message], status: int = 200
    ) -> JSONResponse:
        return JSONResponse(
            to_dict(parse_message(value, message_type)), status_code=status
        )

    @app.middleware("http")
    async def private_responses(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        result = await call_next(request)
        result.headers["Cache-Control"] = "no-store"
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox allow-popups"
        )
        return result

    @app.exception_handler(ContractError)
    @app.exception_handler(StoreError)
    async def known_error(
        request: Request, exc: ContractError | StoreError
    ) -> JSONResponse:
        code = exc.code.lower()
        status = {
            "not_found": 404,
            "conflict": 409,
            "busy": 429,
            "too_large": 413,
        }.get(code, 400)
        return JSONResponse(
            {"error": {"code": code, "message": str(exc)}}, status_code=status
        )

    @app.get("/healthz")
    async def health() -> JSONResponse:
        worker_ok = not start_worker or task_healthy(app)
        return JSONResponse(
            {
                "status": "ok" if worker_ok else "degraded",
                "mode": settings.mode,
            },
            status_code=200 if worker_ok else 503,
        )

    @app.post("/v1/packets", dependencies=[Depends(auth("ingest"))])
    async def put_packet(request: Request) -> JSONResponse:
        value = await body(request, pb.PutPacketRequest)
        packet = _store(app).put_packet(value)
        _worker(app).wake.set()
        return response(packet, pb.Packet)

    @app.post("/v1/runs", dependencies=[Depends(auth("editor"))])
    async def start_run(request: Request) -> JSONResponse:
        if start_worker and not task_healthy(app):
            raise HTTPException(503, "Collection worker is unavailable")
        value = await body(request, pb.StartRunRequest)
        runs: RunRepository = app.state.runs
        if previous := runs.existing(value):
            pipeline = _worker(app).pipeline
            if isinstance(pipeline, DagPipeline):
                previous = pipeline.receipt(previous["id"])
            return response(previous, pb.CollectionRun, 202)
        if settings.mode == "live" and settings.notion_backend != "notion":
            raise HTTPException(
                409, "Full live collection requires Notion persistence"
            )
        try:
            workflow_snapshot = None
            if isinstance(_worker(app).pipeline, DagPipeline):
                instructions, workflow_snapshot = freeze_workflow(
                    settings, app.state.workflow_state, value["issue_date"]
                )
            else:
                instructions = load_instructions(settings.instructions_dir)
        except (InstructionError, DefinitionError, OSError, ValueError):
            raise HTTPException(
                503, "Collection instructions are invalid"
            ) from None
        run = runs.start(
            value, instructions, workflow_snapshot=workflow_snapshot
        )
        _worker(app).wake.set()
        return response(run, pb.CollectionRun, 202)

    @app.post(
        "/v1/runs/{run_id}/retry-stories",
        dependencies=[Depends(auth("editor"))],
    )
    async def retry_stories(run_id: str, request: Request) -> JSONResponse:
        if start_worker and not task_healthy(app):
            raise HTTPException(503, "Collection worker is unavailable")
        pipeline = _worker(app).pipeline
        if not isinstance(pipeline, DagPipeline):
            raise HTTPException(
                409, "Story continuation requires the topic workflow"
            )
        value = await body(request, pb.StartRunRequest)
        child = StoryReplay(_store(app)).start(run_id, value)
        _worker(app).wake.set()
        return response(pipeline.receipt(child["id"]), pb.CollectionRun, 202)

    @app.get("/v1/runs/{run_id}", dependencies=[Depends(auth("editor"))])
    async def get_run(run_id: str) -> JSONResponse:
        validate_request(parse_message({"id": run_id}, pb.GetRunRequest))
        pipeline = _worker(app).pipeline
        value = (
            pipeline.receipt(run_id)
            if isinstance(pipeline, DagPipeline)
            else app.state.runs.get(run_id)
        )
        return response(value, pb.CollectionRun)

    @app.post("/v1/inbox/query", dependencies=[Depends(auth("editor"))])
    async def read_inbox(request: Request) -> JSONResponse:
        value = await body(request, pb.ReadInboxRequest)
        return response(
            _store(app).read_inbox(value["limit"] or 20, value["cursor"]),
            pb.ReadInboxResponse,
        )

    @app.post("/v1/editions", dependencies=[Depends(auth("editor"))])
    async def prepare(request: Request) -> JSONResponse:
        if start_worker and not task_healthy(app):
            raise HTTPException(503, "Editor worker is unavailable")
        value = await body(request, pb.PrepareEditionRequest)
        if value["request_key"].startswith("collection:"):
            raise HTTPException(
                400, "request_key uses a reserved internal prefix"
            )
        if len(value["packet_ids"]) > settings.max_packets:
            raise HTTPException(400, "Too many packets for one editor job")
        edition = _store(app).prepare(value)
        _worker(app).wake.set()
        return response(edition, pb.Edition, 202)

    @app.get(
        "/v1/editions/{edition_id}",
        dependencies=[Depends(auth("editor", "send"))],
    )
    async def get_edition(edition_id: str) -> JSONResponse:
        validate_request(
            parse_message({"id": edition_id}, pb.GetEditionRequest)
        )
        return response(_store(app).get(edition_id), pb.Edition)

    @app.get(
        "/v1/editions/{edition_id}/preview",
        dependencies=[Depends(auth("editor", "send"))],
    )
    async def preview(edition_id: str) -> HTMLResponse:
        edition = _store(app).get(edition_id)
        if edition["state"] != "ready":
            raise StoreError("conflict", "Preview is not ready")
        return HTMLResponse(preview_html(edition["rendered"]))

    @app.post("/v1/render", dependencies=[Depends(auth("editor"))])
    async def render(request: Request) -> JSONResponse:
        value = await body(request, pb.RenderEditionRequest)
        # This utility cannot publish: SendEdition uses only a persisted, reviewed issue.
        value["is_fixture"] = (
            settings.mode == "mock"
            or value["is_fixture"]
            or any(p["is_fixture"] for p in value["packets"])
        )
        rendered = await asyncio.to_thread(render_edition, **value)
        return response(rendered, pb.RenderedEdition)

    async def dispatch(
        edition_id: str, request: Request, *, verification: bool = False
    ) -> JSONResponse:
        value = await body(request, pb.SendEditionRequest)
        if value["id"] != edition_id:
            raise StoreError("conflict", "Body ID must match the resource path")
        if (
            settings.mail_backend == "resend"
            and _store(app).get(edition_id)["is_fixture"]
        ):
            raise StoreError("conflict", "Fixtures cannot be published")
        predecessors = request.headers.getlist(
            "x-newsletter-verification-after"
        )
        predecessor = None
        if predecessors:
            if not verification or len(predecessors) != 1:
                raise StoreError(
                    "invalid_argument",
                    "Use one predecessor header on verification only",
                )
            predecessor = predecessors[0]
            try:
                if str(UUID(predecessor)) != predecessor:
                    raise ValueError
            except ValueError:
                raise StoreError(
                    "invalid_argument",
                    "Verification predecessor must be a canonical UUID",
                ) from None
        if verification:
            edition, first_attempt = _store(app).reserve_verification_send(
                value, previous_verification_id=predecessor
            )
        else:
            edition, first_attempt = _store(app).reserve_send(value)
        if first_attempt:
            try:
                async with asyncio.timeout(35):
                    prefix = (
                        "newsletter-verification-"
                        if verification
                        else "newsletter-"
                    )
                    result = await _mail(app).send(
                        edition, prefix + edition["id"]
                    )
                edition = _store(app).finish(edition_id, **result)
            except AdapterError as exc:
                edition = _store(app).finish(
                    edition_id,
                    delivery_state="unknown" if exc.ambiguous else "rejected",
                    error_code=exc.code,
                )
            except BaseException as exc:
                edition = _store(app).finish(
                    edition_id,
                    delivery_state="unknown",
                    error_code="delivery_unknown",
                )
                if isinstance(exc, asyncio.CancelledError):
                    raise
        return response(edition, pb.Edition)

    @app.post(
        "/v1/editions/{edition_id}/send", dependencies=[Depends(auth("send"))]
    )
    async def send(edition_id: str, request: Request) -> JSONResponse:
        return await dispatch(edition_id, request)

    @app.post(
        "/v1/editions/{edition_id}/send-verification",
        dependencies=[Depends(auth("send"))],
    )
    async def send_verification(
        edition_id: str, request: Request
    ) -> JSONResponse:
        # Same strict public SendEditionRequest, but a distinct explicit purpose.
        # Normal trigger/cron never calls this explicit approval route. Without
        # an exact predecessor header it remains one verification per date.
        return await dispatch(edition_id, request, verification=True)

    return app


def _store(app: FastAPI) -> Store:
    # Starlette State is dynamic; service_lifespan owns these concrete instances.
    return cast(Store, app.state.store)


def _worker(app: FastAPI) -> Worker:
    return cast(Worker, app.state.worker)


def _mail(app: FastAPI) -> MailAdapter:
    return cast(MailAdapter, app.state.mail)


def task_healthy(app: FastAPI) -> bool:
    # The lifespan owns the worker; no queue can be silently accepted after it dies.
    task = cast(
        asyncio.Task[None] | None, getattr(app.state, "worker_task", None)
    )
    return task is not None and not task.done()
