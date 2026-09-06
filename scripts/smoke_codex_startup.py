"""Exercise two real, credential-free SDK/runtime startups in one temporary home.

Only initialize and skills/list are called. No login, account read, model turn,
provider request, .env, or existing auth directory is used. Synthetic poisoned
environment entries are passed only to an isolated child, never to os.environ.
The entire child run has a 30-second deadline; each SDK client closes in finally.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path


async def check_startups(root: Path) -> None:
    from newsletter.codex_runtime import (
        assert_no_skills,
        check_codex_home,
        launch_args,
        load_sdk,
        runtime_env,
        runtime_overrides,
    )

    workspace = root / "workspace"
    codex_home = root / "codex-state"
    sdk = load_sdk()
    for _ in range(2):
        # The second pass must accept the system cache created by the first.
        check_codex_home(codex_home, workspace)
        overrides = runtime_overrides(codex_home)
        client = sdk.AsyncCodex(
            sdk.CodexConfig(
                cwd=str(workspace),
                env=runtime_env(codex_home),
                config_overrides=overrides,
                launch_args_override=launch_args(overrides),
                client_name="newsletter_startup_smoke",
            )
        )
        try:
            async with asyncio.timeout(10):
                await client.__aenter__()
                check_codex_home(codex_home, workspace)
                await assert_no_skills(client, workspace, codex_home)
        finally:
            await asyncio.wait_for(client.close(), timeout=3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child_root is not None:
        asyncio.run(check_startups(args.child_root.resolve()))
        return

    with tempfile.TemporaryDirectory(prefix="newsletter-codex-startup-") as directory:
        root = Path(directory).resolve()
        for name in ("workspace", "codex-state", "isolated-user", "tmp"):
            (root / name).mkdir(mode=0o700)
        # Re-exec the probe so both Path.home() and SDK inheritance are isolated.
        # All values below are non-secret fixtures, not copied account settings.
        environment = {
            "PATH": os.defpath,
            "HOME": str(root / "isolated-user"),
            "CODEX_HOME": str(root / "codex-state"),
            "TMPDIR": str(root / "tmp"),
            "LANG": "C.UTF-8",
            "CODEX_INTERNAL_ORIGINATOR_OVERRIDE": "synthetic-startup-originator",
            "OPENAI_API_KEY": "synthetic-not-a-key",
            "OPENAI_BASE_URL": "https://synthetic.invalid",
            "NOTION_TOKEN": "synthetic-notion-token",
            "RESEND_API_KEY": "synthetic-mail-key",
        }
        subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--child-root", str(root)],
            cwd=root,
            env=environment,
            timeout=30,
            check=True,
        )
    print(
        "Codex startup smoke passed: two real initializations, generated system skills "
        "disabled, poisoned environment removed; no login/account/model calls."
    )


if __name__ == "__main__":
    main()
