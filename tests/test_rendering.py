"""Offline rendering fixtures; SAMPLE_* may also be used for screenshot QA."""

import base64
import copy
import hashlib
import io
import json
import re
from html.parser import HTMLParser

import pytest
from PIL import Image, ImageDraw
from test_charts import compact, final_text, record_draw_text

from newsletter.adapters import _frozen
from newsletter.charts import chart_metadata, render_chart_png
from newsletter.contracts import ContractError, content_hash
from newsletter.rendering import CHART_CID, render_edition
from newsletter.todofy import unavailable_digest

SAMPLE_PACKETS = [
    {
        "id": "sample-packet",
        "workflow_id": "sample-workflow",
        "producer_id": "sample-producer",
        "content_hash": "sample-only",
        "created_at": "2026-09-05T00:00:00Z",
        "is_fixture": True,
        "content": {
            "title": "模拟研究：从试用到流程改造",
            "body": "以下材料与数字均为模拟，只用于验证编辑和排版。",
            "sources": [
                {
                    "id": "survey",
                    "title": "模拟调查：工具使用与流程变化",
                    "url": "https://example.org/research/adoption",
                    "excerpt": "模拟数据：试用42，稳定使用18，流程改造7，另一组暂未公布。",
                    "access_scope": "dataset",
                    "published_at": "2026-09-04",
                },
                {
                    "id": "methods",
                    "title": "模拟方法说明：为什么采用率不是生产率",
                    "url": "https://example.org/research/methods",
                    "excerpt": "本模拟采用横截面调查，不能据此识别因果或推断总体。",
                    "access_scope": "full_text",
                    "published_at": "2026-09-04",
                },
            ],
            "tags": ["fixture"],
        },
    }
]

SAMPLE_DRAFT = {
    "subject": "试刊｜工具普及之后，真正改变了什么",
    "title": "工具普及之后，真正改变了什么",
    "introduction": "当新工具变得触手可及，最容易统计的是有多少人试过它。更难回答的问题是：它是否改变了工作的组织方式？今天的模拟样张沿着这条差距展开。",
    "sections": [
        {
            "kind": "world",
            "heading": "同一个数字，可能藏着不同故事",
            "paragraphs": [
                {
                    "text": "演示材料把“试用过”“稳定使用”和“流程改造”分成三层。这不是三个可以相加的独立群体，而是需要分别解释的观察指标。",
                    "citations": ["sample-packet/survey"],
                }
            ],
            "limitations": "",
        },
        {
            "kind": "feature",
            "heading": "从会用，到工作真的变了",
            "paragraphs": [
                {
                    "text": "试用门槛下降，可以让一项技术很快拥有庞大的使用者。但试用本身没有告诉我们，任务交接、审核责任或错误处理是否发生了变化。这些往往才是工具进入工作流程后真正困难的部分。",
                    "citations": ["sample-packet/survey"],
                },
                {
                    "text": "下一次看到一份漂亮的采用率调查，值得多问一步：问卷究竟测量了接触、熟练，还是可持续的工作改变？若只有一张横截面照片，就不能把几个群体之间的差异，解释成同一群体随时间进步的轨迹。",
                    "citations": ["sample-packet/methods"],
                },
            ],
            "limitations": "这组材料和数值均为模拟。不同层级不能相加，也不能据此计算生产率提升。",
        },
    ],
    "chart": {
        "kind": "bar",
        "question": "同样是“采用”，测量的是哪一层？",
        "metric": "受访者占比",
        "unit": "%",
        "period": "模拟横截面",
        "caption": "三种定义呈现出不同规模。这里比较的是指标，不是一个漏斗转化率。",
        "alt_text": "模拟数值：试用42%，稳定使用18%，流程改造7%；另一组数据缺失，不能记作零。",
        "limitations": "展示为独立条形；群体可能重叠。数据缺失不代表没有人采用。",
        "points": [
            {
                "label": "试用过",
                "decimal_value": "42",
                "citations": ["sample-packet/survey"],
            },
            {
                "label": "稳定使用",
                "decimal_value": "18",
                "citations": ["sample-packet/survey"],
            },
            {
                "label": "流程改造",
                "decimal_value": "7",
                "citations": ["sample-packet/survey"],
            },
            {"label": "另一组", "missing_reason": "尚未公布", "citations": []},
        ],
    },
    "recommended_reading": {
        "citation": "sample-packet/methods",
        "reason": (
            "问题：采用率能说明工作方式真的改变了吗？\n\n"
            "方法与结果：这份模拟方法说明用横截面问卷区分试用、稳定使用与流程改造。"
            "它能描述同一时点的不同指标，不能证明同一批人逐步改善。\n\n"
            "限制与意义：横截面比较不能识别因果，也不足以推断总体。"
            "理解问卷测了什么，才能避免把采用率直接写成生产率提升。"
        ),
    },
    "limitations": "本期为离线排版样张，不代表真实调查、新闻事实或投资判断。",
}


class ParsedEmail(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.links = []
        self.images = []
        self.text = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        attributes = dict(attrs)
        if tag == "a":
            self.links.append(attributes.get("href"))
        if tag == "img":
            self.images.append(attributes)
        assert not any(name.startswith("on") for name in attributes)

    def handle_data(self, data):
        self.text.append(data)


def sample_without_chart():
    draft = copy.deepcopy(SAMPLE_DRAFT)
    draft.pop("chart")
    return draft


def test_safe_static_email_and_plain_text_sources():
    result = render_edition(SAMPLE_DRAFT, SAMPLE_PACKETS, "2026-09-05")
    parsed = ParsedEmail(result["html"])
    assert not {"script", "svg", "details", "summary", "iframe"}.intersection(
        parsed.tags
    )
    assert parsed.images[0]["src"] == CHART_CID
    assert parsed.images[0]["alt"] == SAMPLE_DRAFT["chart"]["alt_text"]
    assert "图表原始数据" in result["html"]
    assert (
        "42" in result["text"] and "另一组：缺失（尚未公布）" in result["text"]
    )
    assert "[1] 模拟调查：工具使用与流程变化" in result["text"]
    assert "https://example.org/research/methods" in result["text"]
    assert result["html"].count("研究介绍") == 1
    assert "如果今天只读一篇" not in result["html"]
    assert "试刊样张 · 模拟材料，非真实新闻" in result["html"]


def test_render_does_not_mutate_inputs_and_is_byte_deterministic():
    draft, packets = copy.deepcopy(SAMPLE_DRAFT), copy.deepcopy(SAMPLE_PACKETS)
    first = render_edition(draft, packets, "2026-09-05")
    second = render_edition(draft, packets, "2026-09-05")
    assert first == second
    assert draft == SAMPLE_DRAFT and packets == SAMPLE_PACKETS
    payload = {key: first[key] for key in ("html", "text", "chart_png")}
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert hashlib.sha256(canonical).hexdigest() == first["render_hash"]
    image = Image.open(io.BytesIO(base64.b64decode(first["chart_png"])))
    assert image.format == "PNG" and image.width == 1280
    assert "timestamp" not in image.info


def test_rendered_png_contains_chart_context_and_only_its_own_source_titles(
    monkeypatch,
):
    records = record_draw_text(monkeypatch)
    rendered = render_edition(SAMPLE_DRAFT, SAMPLE_PACKETS, "2026-09-05")
    image = Image.open(io.BytesIO(base64.b64decode(rendered["chart_png"])))
    drawn = "".join(record["text"] for record in final_text(records, image))
    chart = SAMPLE_DRAFT["chart"]
    for field in ("question", "caption", "limitations"):
        assert compact(chart[field]) in compact(drawn)
    assert compact(chart_metadata(chart)) in compact(drawn)
    assert "来源：[1]" in drawn
    assert "模拟调查：工具使用与流程变化" in drawn
    assert "2026-09-04" in drawn
    assert "模拟方法说明：为什么采用率不是生产率" not in drawn
    assert "模拟数据 · 试刊样张" in drawn


@pytest.mark.parametrize("kind", ["bar", "line"])
def test_graph_card_without_images_or_body_preserves_supplied_explanation_and_data(
    kind,
):
    draft = copy.deepcopy(SAMPLE_DRAFT)
    chart = draft["chart"]
    chart.update(
        kind=kind,
        question="虚构两组训练后，测试成绩差异意味着什么？",
        caption=(
            "离线样张比较测试组与参照组。Cohen's d 用组内分散程度衡量均值差异："
            "正值表示测试组分数较高，零表示均值相同；这不是百分比或真实疗效。"
        ),
        metric="成绩均值标准化差异（Cohen's d）",
        unit="Cohen's d",
        period="虚构短期测试，非长期随访",
        limitations="仅用于绘图测试；不能推断真实人群、持久效果或通用效应阈值。",
    )
    chart["points"][0]["decimal_value"] = "-0.4"
    chart["points"][1]["decimal_value"] = "0"
    chart["points"][2]["decimal_value"] = "0.7"
    rendered = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    degraded_html = re.sub(
        r"<style\b[^>]*>.*?</style>|<img\b[^>]*>",
        "",
        rendered["html"],
        flags=re.S,
    )
    card_html = degraded_html.split("一图看懂 / 数据视角", 1)[1].split(
        "研究介绍", 1
    )[0]
    parsed = ParsedEmail(card_html)
    visible = "".join(parsed.text)
    assert not parsed.images
    assert "图表原始数据" in card_html
    for field in ("question", "caption", "limitations"):
        assert chart[field] in visible
    assert chart_metadata(chart) in visible
    assert "Cohen's d）（Cohen's d）" not in visible
    assert "来源：[1] 模拟调查：工具使用与流程变化 · 2026-09-04" in visible
    for point in chart["points"]:
        assert point["label"] in visible
        expected = point.get(
            "decimal_value", f"缺失（{point.get('missing_reason')}）"
        )
        assert expected in visible
    assert "小效应" not in visible and "大效应" not in visible
    for section in draft["sections"]:
        assert section["paragraphs"][0]["text"] not in visible


@pytest.mark.parametrize("with_chart", [False, True])
def test_legacy_frozen_artifacts_never_use_the_current_chart_or_template(
    monkeypatch, with_chart
):
    # A synthetic old-format payload: no current renderer is used to build it.
    buffer = io.BytesIO()
    if with_chart:
        Image.new("RGB", (2, 2), "white").save(buffer, format="PNG")
    png = buffer.getvalue()
    rendered = {
        "html": "<p>离线旧版样张</p>"
        + ('<img src="cid:newsletter-chart" alt="旧图">' if png else ""),
        "text": "离线旧版样张\n",
        "chart_png": base64.b64encode(png).decode("ascii"),
    }
    rendered["render_hash"] = content_hash(rendered)
    rendered["renderer_version"] = "python-editorial/5"
    edition = {"draft": {"subject": "离线旧版样张"}, "rendered": rendered}
    original = copy.deepcopy(edition)

    def fail_rerender(*args, **kwargs):
        pytest.fail(
            "frozen delivery must not rerender an earlier approved edition"
        )

    monkeypatch.setattr("newsletter.rendering.render_edition", fail_rerender)
    monkeypatch.setattr("newsletter.rendering.render_chart_png", fail_rerender)
    monkeypatch.setattr("newsletter.rendering.load_template", fail_rerender)
    monkeypatch.setattr("newsletter.charts.render_chart_png", fail_rerender)
    assert _frozen(edition) == (
        "离线旧版样张",
        rendered["html"],
        rendered["text"],
        png,
    )
    assert edition == original


def test_reading_support_is_numbered_without_adding_primary_reading_links():
    draft, packets = copy.deepcopy(SAMPLE_DRAFT), copy.deepcopy(SAMPLE_PACKETS)
    packets[0]["content"]["sources"].append(
        {
            "id": "journal",
            "title": "模拟期刊收录记录",
            "url": "https://example.org/journal",
            "excerpt": "模拟收录信息，非真实新闻。",
            "access_scope": "metadata",
        }
    )
    original = render_edition(draft, packets, "2026-09-05")
    draft["recommended_reading"]["supporting_citations"] = [
        "sample-packet/journal"
    ]
    rendered = render_edition(draft, packets, "2026-09-05")
    assert rendered["render_hash"] != original["render_hash"]
    assert "补充证据：[3]" in rendered["html"]
    assert "补充证据：[3]" in rendered["text"]
    assert "[3] 模拟期刊收录记录" in rendered["text"]
    assert rendered["html"].count('href="https://example.org/journal"') == 1
    reading_card = (
        rendered["html"].split("研究介绍", 1)[1].split("来源与核对", 1)[0]
    )
    assert reading_card.count("href=") == 1
    assert "原文与方法 [2]" in reading_card
    assert render_edition(draft, packets, "2026-09-05") == rendered


def test_html_injection_is_text_not_markup():
    draft = sample_without_chart()
    attack = '<img src="x" onerror="alert(1)"> & <script>alert(2)</script>'
    draft["title"] = attack
    draft["sections"][0]["paragraphs"][0]["text"] = attack
    result = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    parsed = ParsedEmail(result["html"])
    assert "script" not in parsed.tags and not parsed.images
    assert "&lt;script&gt;" in result["html"]
    assert attack in result["text"]


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "http://127.0.0.1/private",
        "http://localhost/private",
        "https://user:secret@example.org/",
        "https://example.org/\r\nInjected: header",
        "//example.org/path",
    ],
)
def test_unsafe_source_url_rejected(url):
    packets = copy.deepcopy(SAMPLE_PACKETS)
    packets[0]["content"]["sources"][0]["url"] = url
    with pytest.raises(ValueError):
        render_edition(sample_without_chart(), packets, "2026-09-05")


def test_unknown_citation_rejected():
    draft = sample_without_chart()
    draft["sections"][0]["paragraphs"][0]["citations"] = ["unknown/source"]
    with pytest.raises(ValueError):
        render_edition(draft, SAMPLE_PACKETS, "2026-09-05")


def test_chart_zero_and_missing_are_distinct():
    draft = copy.deepcopy(SAMPLE_DRAFT)
    draft["chart"]["points"][0]["decimal_value"] = "0"
    result = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    assert "试用过：0[" in result["text"]
    assert "另一组：缺失（尚未公布）" in result["text"]
    changed = copy.deepcopy(draft)
    changed["chart"]["points"][-1] = {
        "label": "另一组",
        "decimal_value": "0",
        "citations": ["sample-packet/survey"],
    }
    assert (
        render_edition(changed, SAMPLE_PACKETS, "2026-09-05")["chart_png"]
        != result["chart_png"]
    )


def test_line_chart_breaks_at_missing_instead_of_connecting(monkeypatch):
    chart = copy.deepcopy(SAMPLE_DRAFT["chart"])
    chart["kind"] = "line"
    chart["points"] = [
        {"label": "甲", "decimal_value": "10"},
        {"label": "乙", "missing_reason": "未公布"},
        {"label": "丙", "decimal_value": "10"},
    ]
    segments = []
    original = ImageDraw.ImageDraw.line

    def line(draw, xy, *args, **kwargs):
        if kwargs.get("fill") == "#28604e":
            segments.append(xy)
        return original(draw, xy, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "line", line)
    render_chart_png(chart, False)
    # Observe data segments, not a pixel strip whose Y coordinates move with
    # self-contained chart headers. Missing resets the previous point.
    assert segments == []
    chart["points"][1] = {"label": "乙", "decimal_value": "10"}
    render_chart_png(chart, False)
    assert len(segments) == 2
    assert segments[0][2:] == segments[1][:2]


def test_without_chart_or_reading_is_valid_and_no_fixture_claim_without_flag():
    draft = sample_without_chart()
    draft.pop("recommended_reading")
    packets = copy.deepcopy(SAMPLE_PACKETS)
    packets[0]["is_fixture"] = False
    result = render_edition(draft, packets, "2026-09-05")
    assert result["chart_png"] == ""
    assert not ParsedEmail(result["html"]).images
    assert "研究介绍" not in result["html"]
    assert "试刊样张 · 模拟材料，非真实新闻" not in result["html"]


def test_optional_protojson_defaults_are_rendered_consistently():
    draft = sample_without_chart()
    draft.pop("introduction")
    draft.pop("limitations")
    absent = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    draft.update(introduction=None, limitations=None)
    nulls = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    assert absent == nulls
    assert "None" not in nulls["html"]


def test_source_title_and_query_attribute_are_escaped():
    packets = copy.deepcopy(SAMPLE_PACKETS)
    packets[0]["content"]["sources"][0]["title"] = (
        '<b onclick="alert(1)">来源</b>'
    )
    packets[0]["content"]["sources"][0]["url"] = (
        'https://example.org/?q="quoted"&x=1'
    )
    rendered = render_edition(sample_without_chart(), packets, "2026-09-05")
    parsed = ParsedEmail(rendered["html"])
    assert "b" not in parsed.tags
    assert 'https://example.org/?q="quoted"&x=1' in parsed.links
    assert "&lt;b" in rendered["html"]


def test_research_card_paragraphs_preserve_plain_text_and_escape_markup():
    draft = sample_without_chart()
    attack = '<script>alert(1)</script> & <img src="x" onerror="alert(2)">'
    first = "问题：这份模拟研究测了什么？\n方法：比较两个测试组。"
    second = "结果与边界：" + attack
    third = "意义：只验证离线排版，不是真实发现。"
    reason = first + "\r\n \t\r\n" + second + "\n\n" + third
    draft["recommended_reading"]["reason"] = reason
    result = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    card = (
        result["html"]
        .split('class="reading-panel"', 1)[1]
        .split("</table>", 1)[0]
    )
    parsed = ParsedEmail(card)
    assert not {"script", "img", "details", "summary"}.intersection(parsed.tags)
    assert card.count('class="body-copy ink"') == 3
    assert "方法：比较两个测试组。" in card and "<br>" in card
    assert attack in "".join(parsed.text)
    assert "&lt;script&gt;" in card
    assert reason in result["text"]
    assert card.index(third) < card.index("原文与方法")


def test_research_card_keeps_full_contract_length_without_silent_truncation():
    draft = sample_without_chart()
    reason = "研" * 1000
    draft["recommended_reading"]["reason"] = reason
    result = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    assert reason in result["html"] and reason in result["text"]
    draft["recommended_reading"]["reason"] += "究"
    with pytest.raises(
        ContractError,
        match="recommended_reading.reason exceeds its length limit",
    ):
        render_edition(draft, SAMPLE_PACKETS, "2026-09-05")


def test_ai_and_cross_disciplinary_research_can_both_be_feature_sections():
    draft = sample_without_chart()
    draft.pop("recommended_reading")
    draft["sections"] = []
    for heading, source in (
        ("AI/ML 研究：模拟效率比较", "survey"),
        ("跨学科研究：模拟生态测量", "methods"),
    ):
        draft["sections"].append(
            {
                "kind": "feature",
                "heading": heading,
                "paragraphs": [
                    {
                        "text": f"{label}：{heading}的离线测试说明。",
                        "citations": [f"sample-packet/{source}"],
                    }
                    for label in ("问题", "方法", "结果", "限制", "意义")
                ],
                "limitations": "仅是结构 fixture，不描述真实研究。",
            }
        )
    result = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    assert result["html"].count('class="feature-title ink"') == 2
    for section in draft["sections"]:
        for output in (result["html"], result["text"]):
            assert section["heading"] in output
            assert all(p["text"] in output for p in section["paragraphs"])
    assert result["text"].index(draft["sections"][0]["heading"]) < result[
        "text"
    ].index(draft["sections"][1]["heading"])


def test_eight_semantic_topics_have_independent_titles_bodies_and_local_boundaries():
    kinds = [
        ("ai_ml", "AI / ML 进展"),
        ("science", "科学进展"),
        ("economy", "经济与产业"),
        ("technology", "技术与工程"),
        ("health", "健康与公共卫生"),
        ("world", "世界简报"),
        ("feature", "研究与进展"),
        ("context", "背景与观察"),
    ]
    draft = {
        "title": "分类排版离线样张",
        "subject": "分类排版离线样张",
        "introduction": "模拟数据，仅验证邮件排版。",
        "sections": [
            {
                "kind": kind,
                "heading": f"第{index}题：已经审阅的完整标题",
                "paragraphs": [
                    {
                        "text": f"第{index}题的完整已审段落{part}。",
                        "citations": ["sample-packet/methods"],
                    }
                    for part in range(1, 3)
                ],
                "limitations": f"第{index}题的独立边界，不属于下一题。",
            }
            for index, (kind, _) in enumerate(kinds, 1)
        ],
    }
    frozen = copy.deepcopy(draft)
    rendered = render_edition(
        draft,
        SAMPLE_PACKETS,
        "2026-09-05",
        personal_digest=unavailable_digest(),
    )
    panels = rendered["html"].split('class="story-panel"')[1:]
    assert len(panels) == 8
    for index, ((_, label), section, panel) in enumerate(
        zip(kinds, draft["sections"], panels, strict=True), 1
    ):
        assert label in panel
        assert f">{section['heading']}</h2>" in panel
        assert "font-weight:700" in panel
        assert section["limitations"] in panel
        assert 'class="story-note"' in panel
        for paragraph in section["paragraphs"]:
            assert paragraph["text"] in panel
        assert panel.index(section["paragraphs"][-1]["text"]) < panel.index(
            section["limitations"]
        )
        assert f"{label}｜{section['heading']}" in rendered["text"]
        assert rendered["html"].count(section["heading"]) == 1
        if index < 8:
            assert draft["sections"][index]["limitations"] not in panel
    assert "今日简讯" not in rendered["html"]
    assert (
        "今日深读" not in rendered["html"]
    )  # The category cannot imply a brief is a deep dive.
    assert rendered["chart_png"] == ""
    assert not ParsedEmail(
        rendered["html"]
    ).images  # No invented chart when no approved data exists.
    assert rendered["html"].index("TODOFY / 与你有关") > rendered["html"].index(
        draft["sections"][-1]["limitations"]
    )
    assert rendered["text"].index("TODOFY / 与你有关") > rendered["text"].index(
        draft["sections"][-1]["limitations"]
    )
    assert draft == frozen
    assert (
        render_edition(
            draft,
            SAMPLE_PACKETS,
            "2026-09-05",
            personal_digest=unavailable_digest(),
        )
        == rendered
    )


def test_topic_boundary_preserves_newlines_and_escapes_markup_without_parsing_titles():
    draft = sample_without_chart()
    draft.pop("recommended_reading")
    draft["sections"] = [
        {
            "kind": "feature",
            "heading": "原样标题，不按字面猜分类",
            "paragraphs": [
                {
                    "text": "段落首行不是另一个标题。\n第二行仍属正文。",
                    "citations": ["sample-packet/methods"],
                }
            ],
            "limitations": "第一条限制。\n第二条限制 <b>不是HTML</b>。",
        }
    ]
    rendered = render_edition(draft, SAMPLE_PACKETS, "2026-09-05")
    assert "研究与进展" in rendered["html"]
    assert (
        "第一条限制。<br>第二条限制 &lt;b&gt;不是HTML&lt;/b&gt;。"
        in rendered["html"]
    )
    assert "段落首行不是另一个标题。<br>第二行仍属正文。" in rendered["html"]
    assert "<h2" in rendered["html"] and "font-size:27px" in rendered["html"]
    assert "<b>不是HTML</b>" not in rendered["html"]
    assert draft["sections"][0]["limitations"] in rendered["text"]
