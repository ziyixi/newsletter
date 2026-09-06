"""Chart boundary regressions; no cross-platform PNG golden hashes."""

import copy
import io

import pytest
from PIL import Image

from newsletter.charts import load_font, render_chart_png


def make_chart(kind, values):
    return {
        "kind": kind,
        "metric": "测试指标",
        "unit": "测试单位",
        "period": "离线样张",
        "points": [
            {
                "label": f"观察项 {index}",
                **({"decimal_value": value} if value is not None else {"missing_reason": "未公布"}),
            }
            for index, value in enumerate(values)
        ],
    }


@pytest.mark.parametrize(
    "kind,values",
    [
        ("bar", ["-5", "0", None, "12"]),
        ("bar", ["0", "0"]),
        ("line", ["-5", "0", None, "12"]),
        ("line", ["0"]),
        ("line", ["10", None, "10"]),
        ("line", ["1e30", "2e30"]),
    ],
)
@pytest.mark.parametrize("is_fixture", [False, True])
def test_chart_boundary_is_deterministic_and_does_not_mutate_input(kind, values, is_fixture):
    chart = make_chart(kind, values)
    before = copy.deepcopy(chart)
    first = render_chart_png(chart, is_fixture)
    assert first == render_chart_png(chart, is_fixture)
    assert chart == before
    image = Image.open(io.BytesIO(first))
    assert image.format == "PNG" and image.width == 1280
    assert "timestamp" not in image.info


@pytest.mark.parametrize("values", [[], ["1"] * 33])
def test_chart_point_count_remains_bounded(values):
    with pytest.raises(ValueError, match="CHART_SIZE_UNSUPPORTED"):
        render_chart_png(make_chart("bar", values), False)


@pytest.mark.parametrize("values", [[None], ["NaN"], ["Infinity"]])
def test_chart_requires_at_least_one_finite_observation(values):
    with pytest.raises(ValueError, match="CHART_VALUES_INVALID"):
        render_chart_png(make_chart("bar", values), False)


def test_configured_missing_font_does_not_silently_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWSLETTER_CHART_FONT", str(tmp_path / "missing.ttf"))
    with pytest.raises(ValueError, match="CHART_FONT_UNAVAILABLE"):
        load_font(24)
