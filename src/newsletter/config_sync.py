"""Pull validated editorial bundles without accessing service data or providers.

The writer is a separate, least-privileged process. GitHub supplies one immutable
commit, never independently fetched moving files. Failed pulls keep the last
usable release; an explicit local pin survives future polls and restarts.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from newsletter.content_config import (
    install_snapshot,
    load_active,
    packaged_snapshot,
    validate_snapshot,
)

MAX_BUNDLE_BYTES = 2_000_000
REPOSITORY = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z"
)
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class SyncError(ValueError):
    """Only fixed, credential-free error codes cross the CLI boundary."""


@dataclass(frozen=True)
class SyncSettings:
    root: Path
    repository: str = "ziyixi/newsletter"
    interval: int = 900

    @classmethod
    def from_env(cls) -> SyncSettings:
        try:
            interval = int(
                os.environ.get("NEWSLETTER_CONFIG_POLL_SECONDS", "900")
            )
        except ValueError:
            raise SyncError("CONFIG_INTERVAL_INVALID") from None
        if not 60 <= interval <= 86400:
            raise SyncError("CONFIG_INTERVAL_INVALID")
        directory = os.environ.get("NEWSLETTER_CONTENT_CONFIG_DIR", "")
        if not directory or not Path(directory).is_absolute():
            raise SyncError("CONFIG_DIRECTORY_REQUIRED")
        repository = os.environ.get(
            "NEWSLETTER_CONFIG_REPOSITORY", "ziyixi/newsletter"
        )
        if not REPOSITORY.fullmatch(repository) or any(
            part in {".", ".."} for part in repository.split("/")
        ):
            raise SyncError("CONFIG_REPOSITORY_INVALID")
        return cls(Path(directory), repository, interval)


def _read_json(path: Path, limit: int = MAX_BUNDLE_BYTES) -> dict[str, Any]:
    if (
        any(part.is_symlink() for part in (path, *path.parents))
        or not path.is_file()
    ):
        raise SyncError("CONFIG_LOCAL_STATE_INVALID")
    try:
        with path.open("rb") as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ValueError
        value = _decode_json(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise SyncError("CONFIG_LOCAL_STATE_INVALID") from None
    if not isinstance(value, dict):
        raise SyncError("CONFIG_LOCAL_STATE_INVALID")
    return value


def _decode_json(raw: bytes) -> Any:
    def unique_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("CONFIG_JSON_DUPLICATE_KEY")
            result[key] = value
        return result

    return json.loads(raw, object_pairs_hook=unique_pairs)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".sync-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _sync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _writer_lock(root: Path) -> Iterator[None]:
    if (
        any(part.is_symlink() for part in (root, *root.parents))
        or not root.is_dir()
    ):
        raise SyncError("CONFIG_DIRECTORY_REQUIRED")
    fd = os.open(
        root / ".sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise SyncError("CONFIG_LOCAL_STATE_INVALID")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SyncError("CONFIG_WRITER_BUSY") from None
        yield
    finally:
        os.close(fd)


class GitHubSource:
    def __init__(
        self, repository: str, transport: httpx.BaseTransport | None = None
    ):
        if not REPOSITORY.fullmatch(repository):
            raise SyncError("CONFIG_REPOSITORY_INVALID")
        self.repository = repository
        self.transport = transport

    def _get(
        self, suffix: str, *, raw: bool = False, limit: int = MAX_BUNDLE_BYTES
    ) -> bytes:
        # Public configuration requires no credential. Only the fixed TLS
        # origin is read; redirects and download_url values are never followed.
        try:
            with httpx.Client(
                timeout=30,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
                headers={
                    "Accept": "application/vnd.github.raw+json"
                    if raw
                    else "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            ) as client:
                with client.stream(
                    "GET",
                    f"https://api.github.com/repos/{self.repository}/{suffix}",
                ) as response:
                    if response.status_code in {401, 403}:
                        raise SyncError("CONFIG_GITHUB_ACCESS_OR_RATE_LIMIT")
                    if response.status_code == 404:
                        raise SyncError(
                            "CONFIG_GITHUB_REPOSITORY_OR_RELEASE_UNAVAILABLE"
                        )
                    if response.status_code != 200:
                        raise SyncError("CONFIG_GITHUB_UNAVAILABLE")
                    result = bytearray()
                    for chunk in response.iter_bytes():
                        result.extend(chunk)
                        if len(result) > limit:
                            raise SyncError("CONFIG_DOWNLOAD_TOO_LARGE")
                    return bytes(result)
        except httpx.HTTPError:
            raise SyncError("CONFIG_GITHUB_NETWORK_ERROR") from None

    def resolve(self) -> str:
        raw = self._get("git/ref/heads/published", limit=16000)
        try:
            data = _decode_json(raw)
            commit = data["object"]["sha"]
            if data["object"]["type"] != "commit" or not COMMIT.fullmatch(
                commit
            ):
                raise ValueError
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SyncError("CONFIG_PUBLISHED_REF_INVALID") from None
        return str(commit)

    def fetch(self, commit: str) -> dict[str, Any]:
        if not COMMIT.fullmatch(commit):
            raise SyncError("CONFIG_PUBLISHED_REF_INVALID")
        raw = self._get(f"contents/bundle.json?ref={commit}", raw=True)
        try:
            return validate_snapshot(_decode_json(raw))
        except (ValueError, TypeError, KeyError, RecursionError):
            raise SyncError("CONFIG_BUNDLE_INVALID") from None


class ConfigSync:
    def __init__(
        self, settings: SyncSettings, source: GitHubSource | None = None
    ):
        self.settings = settings
        self.root = settings.root
        self.source = source

    def _active(self) -> dict[str, Any]:
        try:
            return load_active(self.root)
        except (OSError, ValueError, KeyError):
            raise SyncError("CONFIG_BASELINE_MISSING_OR_INVALID") from None

    def _pin_digest(self) -> str | None:
        path = self.root / "pin.json"
        if not path.exists():
            return None
        value = _read_json(path, 1024).get("digest")
        if not isinstance(value, str) or not DIGEST.fullmatch(value):
            raise SyncError("CONFIG_PIN_INVALID")
        return value

    def _release(self, digest: str) -> dict[str, Any]:
        if not DIGEST.fullmatch(digest):
            raise SyncError("CONFIG_PIN_INVALID")
        try:
            value = validate_snapshot(
                _read_json(self.root / "releases" / digest / "bundle.json")
            )
            if value["digest"] != digest:
                raise ValueError
            return value
        except (OSError, ValueError, KeyError):
            raise SyncError("CONFIG_PIN_RELEASE_UNAVAILABLE") from None

    def status(self) -> dict[str, Any]:
        # This command is read-only and can run from the service's RO mount.
        path = self.root / "sync-status.json"
        report = _read_json(path, 8192) if path.exists() else {}
        allowed = {
            "last_attempt",
            "last_success",
            "error",
            "wanted_commit",
            "wanted_revision",
            "wanted_digest",
            "repository",
        }
        result = {key: value for key, value in report.items() if key in allowed}
        active = self._active()
        result.update(
            active_revision=active["revision"],
            active_digest=active["digest"],
            pinned_digest=self._pin_digest(),
        )
        return result

    def seed(self) -> dict[str, Any]:
        with _writer_lock(self.root):
            if (self.root / "active.json").exists():
                raise SyncError("CONFIG_ALREADY_INITIALIZED")
            install_snapshot(self.root, packaged_snapshot())
            _atomic_json(
                self.root / "sync-status.json",
                {"error": None, "last_success": None},
            )
            return self.status()

    def pin(self, digest: str | None = None) -> dict[str, Any]:
        with _writer_lock(self.root):
            active = self._active()
            digest = digest or active["digest"]
            release = self._release(digest)
            # Persist intent before activation. A crash between these writes
            # will complete the pin locally on the next poll, not fetch GitHub.
            _atomic_json(self.root / "pin.json", {"digest": digest})
            if active["digest"] != digest:
                install_snapshot(self.root, release)
            return self.status()

    def unpin(self) -> dict[str, Any]:
        with _writer_lock(self.root):
            self._active()
            (self.root / "pin.json").unlink(missing_ok=True)
            _sync_directory(self.root)
            return self.status()

    def once(self) -> dict[str, Any]:
        with _writer_lock(self.root):
            active = self._active()
            report = self.status()
            report.update(
                last_attempt=time.time(), repository=self.settings.repository
            )
            try:
                pinned = self._pin_digest()
                if pinned:
                    release = self._release(pinned)
                    if active["digest"] != pinned:
                        install_snapshot(self.root, release)
                else:
                    source = self.source or GitHubSource(
                        self.settings.repository
                    )
                    commit = source.resolve()
                    report["wanted_commit"] = commit
                    snapshot = source.fetch(commit)
                    report.update(
                        wanted_revision=snapshot["revision"],
                        wanted_digest=snapshot["digest"],
                    )
                    if active["digest"] != snapshot["digest"]:
                        install_snapshot(self.root, snapshot)
                report.update(error=None, last_success=time.time())
            except (OSError, ValueError, TypeError, KeyError) as error:
                report["error"] = (
                    str(error)
                    if isinstance(error, SyncError)
                    else "CONFIG_ACTIVATION_FAILED"
                )
            _atomic_json(self.root / "sync-status.json", report)
            return self.status()

    def health(self) -> bool:
        report = self.status()
        attempted = report.get("last_attempt")
        # A failed remote update is degraded, not a reason to kill the reader.
        # Liveness requires an active validated baseline and a recent poll.
        return (
            isinstance(attempted, (int, float))
            and 0 <= time.time() - attempted < self.settings.interval + 120
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("seed", "once", "run", "status", "health", "unpin"):
        commands.add_parser(command)
    commands.add_parser("pin").add_argument("digest", nargs="?")
    args = parser.parse_args()
    try:
        sync = ConfigSync(SyncSettings.from_env())
        if args.command == "run":
            sync._active()
            while True:
                try:
                    print(json.dumps(sync.once(), sort_keys=True), flush=True)
                except (OSError, ValueError, TypeError, KeyError) as error:
                    print(
                        json.dumps(
                            {
                                "error": str(error)
                                if isinstance(error, SyncError)
                                else "CONFIG_LOCAL_STATE_INVALID"
                            }
                        ),
                        flush=True,
                    )
                time.sleep(sync.settings.interval)
        elif args.command == "health":
            raise SystemExit(0 if sync.health() else 1)
        else:
            result = (
                sync.pin(args.digest)
                if args.command == "pin"
                else getattr(sync, args.command)()
            )
            print(json.dumps(result, sort_keys=True))
            if args.command == "once" and result.get("error"):
                raise SystemExit(1)
    except (OSError, ValueError, TypeError, KeyError) as error:
        code = (
            str(error)
            if isinstance(error, SyncError)
            else "CONFIG_LOCAL_STATE_INVALID"
        )
        print("Newsletter configuration: " + code, file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
