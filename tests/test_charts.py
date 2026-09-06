"""Chart boundary regressions; no cross-platform PNG golden hashes."""

import copy
import io

import pytest
from PIL import Image, ImageDraw

from newsletter.charts import chart_metadata, load_font, render_chart_png


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


def record_draw_text(monkeypatch):
    """Observe actual drawing, including its final image bounds; no PNG goldens."""
    records = []
    original = ImageDraw.ImageDraw.text

    def draw_text(draw, xy, text, *args, **kwargs):
        records.append(
            {
                "text": text,
                "bbox": draw.textbbox(xy, text, font=kwargs.get("font")),
                "image_size": draw._image.size,
            }
        )
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", draw_text)
    return records


def compact(text):
    return "".join(text.split())


def final_text(records, image):
    return [record for record in records if record["image_size"] == image.size]


@pytest.mark.parametrize("kind", ["bar", "line"])
@pytest.mark.parametrize("is_fixture", [False, True])
def test_chart_draws_its_own_question_explanation_metadata_limits_and_source(
    monkeypatch, kind, is_fixture
):
    chart = make_chart(kind, ["-0.4", "0", None, "0.7"])
    chart.update(
        question="离线测试：两组的标准化差异说明什么？",
        caption="虚构比较：正值表示测试组高于参照组，零表示无差异。这不是百分比。",
        metric="虚构标准化差异（测试单位）",
        limitations="仅是离线绘图数据，不能推出真实实验效果或通用阈值。",
        source_note="来源：[7] 离线测试材料 · https://example.org/synthetic",
    )
    original = copy.deepcopy(chart)
    records = record_draw_text(monkeypatch)
    image = Image.open(io.BytesIO(render_chart_png(chart, is_fixture)))
    drawn = "".join(record["text"] for record in final_text(records, image))
    for field in ("question", "caption", "limitations", "source_note"):
        assert compact(chart[field]) in compact(drawn), field
    assert compact(chart_metadata(chart)) in compact(drawn)
    assert compact(drawn).index(compact(chart["question"])) < compact(drawn).index(
        compact(chart["caption"])
    )
    assert compact(drawn).index(compact(chart["limitations"])) < compact(drawn).index(
        compact(chart["source_note"])
    )
    assert ("模拟数据 · 试刊样张" in drawn) is is_fixture
    assert "小效应" not in drawn and "大效应" not in drawn
    assert chart == original


@pytest.mark.parametrize("kind", ["bar", "line"])
@pytest.mark.parametrize("field", ["question", "caption", "metadata", "limitations", "source_note"])
def test_long_cjk_and_unbroken_latin_chart_copy_is_drawn_in_full_inside_png(
    monkeypatch, kind, field
):
    chart = make_chart(kind, ["-5", "0", None, "12"])
    chart.update(
        question="离线长文本测试",
        caption="这是绘图回归，不是研究。",
        limitations="",
        source_note="",
    )
    long_copy = ("中英混排边界检查UnbrokenLatinToken0123456789" * 18) + "终点END"
    if field == "metadata":
        chart["metric"] = long_copy
        expected = chart_metadata(chart)
    else:
        chart[field] = long_copy
        expected = long_copy
    records = record_draw_text(monkeypatch)
    image = Image.open(io.BytesIO(render_chart_png(chart, True)))
    final = final_text(records, image)
    assert compact(expected) in compact("".join(record["text"] for record in final))
    assert all(
        0 <= left <= right <= image.width and 0 <= top <= bottom <= image.height
        for record in final
        if record["text"].strip()
        for left, top, right, bottom in [record["bbox"]]
    ), [record for record in final if record["text"].strip()]
    # No fixed image height: wrapped text may grow on different CJK font stacks.
    assert image.width == 1280


@pytest.mark.parametrize("limitations", ["甲条限制。\n乙条限制。", ["甲条限制。", "乙条限制。"]])
def test_raw_and_rendering_normalized_limitations_remain_drawn(monkeypatch, limitations):
    chart = make_chart("bar", ["-1", "1"])
    chart["limitations"] = limitations
    records = record_draw_text(monkeypatch)
    image = Image.open(io.BytesIO(render_chart_png(chart, False)))
    drawn = "".join(record["text"] for record in final_text(records, image))
    assert "甲条限制。" in drawn and "乙条限制。" in drawn


@pytest.mark.parametrize("kind", ["bar", "line"])
def test_fixture_watermark_anchors_actual_glyph_bounds_above_canvas_bottom(monkeypatch, kind):
    # Run with the platform's actual font (Noto CJK in Linux, Hiragino on macOS).
    # In particular, Noto's 40px glyph bottom is below y + 48; fixed y offsets clip.
    chart = make_chart(kind, ["-1", "0", "1"])
    chart["limitations"] = "离线样张边界，水印不能覆盖这条说明。"
    chart["source_note"] = "来源：离线模拟材料"
    records = record_draw_text(monkeypatch)
    image = Image.open(io.BytesIO(render_chart_png(chart, True)))
    final = final_text(records, image)
    markers = [record for record in final if record["text"] == "模拟数据 · 试刊样张"]
    assert len(markers) == 1
    left, top, right, bottom = markers[0]["bbox"]
    assert image.height - bottom == 24
    assert image.width - right == 50
    assert left >= 0 and top >= 0
    assert max(record["bbox"][3] for record in final if record is not markers[0]) < top


@pytest.mark.parametrize(
    "metric,unit,expected",
    [
        ("Cohen's d", "Cohen's d", "指标：Cohen's d · 范围：离线时点"),
        ("标准化差异（Cohen's d）", "Cohen's d", "指标：标准化差异（Cohen's d） · 范围：离线时点"),
        ("Difference (Cohen's d)", "Cohen's d", "指标：Difference (Cohen's d) · 范围：离线时点"),
        (
            "Cohen's d sensitivity",
            "Cohen's d",
            "指标：Cohen's d sensitivity（Cohen's d） · 范围：离线时点",
        ),
        ("响应占比", "%", "指标：响应占比（%） · 范围：离线时点"),
    ],
)
def test_metadata_deduplicates_only_identical_or_parenthesized_unit(metric, unit, expected):
    assert chart_metadata({"metric": metric, "unit": unit, "period": "离线时点"}) == expected


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
