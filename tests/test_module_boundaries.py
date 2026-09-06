"""Small import boundaries that keep offline tools independent of the server."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("module", "unneeded"),
    [
        ("cli", "app"),
        ("charts", "rendering"),
        ("model_io", "editor"),
        ("model_schema", "editor"),
    ],
)
def test_import_does_not_load_higher_layer(module, unneeded, tmp_path):
    # A fresh interpreter avoids depending on pytest's module import order.
    subprocess.run(
        [
            sys.executable,
            "-c",
            f"import newsletter.{module}; import sys; "
            f"assert 'newsletter.{unneeded}' not in sys.modules; "
            "assert 'newsletter.app' not in sys.modules",
        ],
        cwd=tmp_path,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        check=True,
        timeout=15,
    )


def test_app_keeps_existing_preview_import_without_owning_it():
    from newsletter.app import preview_html as old_import
    from newsletter.rendering import preview_html

    assert old_import is preview_html


@pytest.mark.parametrize("chart_png", ["abc", ""])
def test_preview_does_not_mutate_frozen_email(chart_png):
    from newsletter.rendering import preview_html

    frozen = {
        "html": '<p>cid:newsletter-chart</p><img src="cid:newsletter-chart">',
        "chart_png": chart_png,
        "render_hash": "unchanged",
    }
    original = frozen.copy()
    assert preview_html(frozen) == (
        '<p>cid:newsletter-chart</p><img src="data:image/png;base64,' + chart_png + '">'
    )
    assert frozen == original


def test_preview_without_chart_is_unchanged():
    from newsletter.rendering import preview_html

    assert preview_html({"html": "<p>No chart</p>"}) == "<p>No chart</p>"
