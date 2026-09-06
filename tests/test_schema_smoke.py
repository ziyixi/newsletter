"""Local diagnostic control-flow tests; these never make provider calls."""

import json
from unittest.mock import AsyncMock

import pytest

from newsletter.editor import CodexEditor
from newsletter.errors import EditorError
from newsletter.schema_smoke import check_schemas, main, smoke_cases


@pytest.mark.asyncio
async def test_schema_smoke_checks_all_cases_without_creating_publication(tmp_path):
    editor = CodexEditor(tmp_path)
    cases = smoke_cases()
    editor.execute = AsyncMock(side_effect=[(json.dumps(c[2]), set(), False) for c in cases])
    result = await check_schemas(editor)
    assert result["accepted"] is True
    assert result["schemas"] == ["brief", "deep", "brief_repair", "review"]
    assert editor.execute.await_count == 4
    assert list(tmp_path.iterdir()) == []
    for call in editor.execute.await_args_list:
        assert not call.args[3].exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply", [("{}", set(), False), ("invalid", set(), False), ("{}", set(), True)]
)
async def test_schema_smoke_fails_on_first_bad_response(tmp_path, reply):
    editor = CodexEditor(tmp_path)
    editor.execute = AsyncMock(return_value=reply)
    with pytest.raises(EditorError, match="invalid or unverifiable"):
        await check_schemas(editor)
    assert editor.execute.await_count == 1


def test_cli_does_not_read_credentials_without_explicit_opt_in(monkeypatch):
    monkeypatch.setattr("sys.argv", ["schema_smoke"])
    monkeypatch.setattr(
        "newsletter.schema_smoke.Settings.from_env", lambda: pytest.fail("env read")
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
