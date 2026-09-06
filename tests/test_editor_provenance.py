"""Offline URL provenance regressions; no SDK, redirects, or network requests."""

import json

import pytest

from newsletter.contracts import validate_draft
from newsletter.editor import EditorError, _result

SHORT_URL = "https://example.org/article/synthetic-123"
CANONICAL_URL = "https://example.org/article/synthetic-news-story-synthetic-123"


@pytest.fixture
def bundle():
    # The same small packet/draft shape as the editor fixtures, with public
    # example URLs and conspicuously synthetic content rather than live data.
    return {
        "draft": {
            "subject": "Synthetic provenance fixture",
            "title": "Synthetic provenance fixture",
            "sections": [
                {
                    "kind": "feature",
                    "heading": "Synthetic statement",
                    "paragraphs": [
                        {"text": "Synthetic evidence only.", "citations": ["supplement-1/s1"]}
                    ],
                }
            ],
        },
        "review": {"passed": True, "findings": ["Synthetic review only."]},
        "supplemental_packets": [
            {
                "id": "supplement-1",
                "content": {
                    "title": "Synthetic source packet",
                    "body": "Synthetic fixture, not a real news report.",
                    "sources": [
                        {
                            "id": "s1",
                            "title": "Synthetic source",
                            "url": CANONICAL_URL,
                            "excerpt": "Synthetic evidence only.",
                            "access_scope": "full_text",
                        }
                    ],
                    "tags": ["fixture"],
                },
            }
        ],
    }


@pytest.mark.parametrize(
    ("source_url", "other_url"),
    [(CANONICAL_URL, SHORT_URL), (SHORT_URL, CANONICAL_URL)],
)
def test_same_host_and_content_id_do_not_prove_exact_source_was_opened(
    bundle, source_url, other_url
):
    bundle["supplemental_packets"][0]["content"]["sources"][0]["url"] = source_url
    text = json.dumps(bundle)
    with pytest.raises(EditorError) as error:
        _result(text, [], {other_url}, searched=True)
    assert error.value.code == "invalid_output"

    # A possible redirect/canonical relationship is not evidence. Only after
    # the exact cited URL also appears in the observed opens can it be accepted.
    result = _result(text, [], {other_url, source_url}, searched=True)
    assert result.review["passed"] is True
    added = result.supplemental_packets[0]
    assert added["content"]["sources"][0]["url"] == source_url
    assert result.draft["sections"][0]["paragraphs"][0]["citations"] == [added["id"] + "/s1"]
    validate_draft(result.draft, result.supplemental_packets)


@pytest.mark.parametrize(
    ("source_url", "opened_url"),
    [
        (CANONICAL_URL + "#table-1", CANONICAL_URL),
        (CANONICAL_URL + "#different-section", CANONICAL_URL),
        (CANONICAL_URL + "?edition=first#table-1", CANONICAL_URL + "?edition=first"),
    ],
)
def test_fragment_is_the_only_ignored_url_component(bundle, source_url, opened_url):
    bundle["supplemental_packets"][0]["content"]["sources"][0]["url"] = source_url
    # _collect already removes fragments from observed opens before _result.
    result = _result(json.dumps(bundle), [], {opened_url}, searched=True)
    assert result.review["passed"] is True
    assert result.supplemental_packets[0]["content"]["sources"][0]["url"] == source_url
    validate_draft(result.draft, result.supplemental_packets)


@pytest.mark.parametrize(
    ("source_suffix", "opened_suffix"),
    [
        ("?edition=first", ""),
        ("", "?edition=first"),
        ("?edition=first", "?edition=second"),
        ("?edition=first#table-1", "?edition=second"),
        ("?edition=first&view=full", "?view=full&edition=first"),
    ],
)
def test_query_parameters_are_not_removed_or_normalized(bundle, source_suffix, opened_suffix):
    bundle["supplemental_packets"][0]["content"]["sources"][0]["url"] = (
        CANONICAL_URL + source_suffix
    )
    with pytest.raises(EditorError) as error:
        _result(json.dumps(bundle), [], {CANONICAL_URL + opened_suffix}, searched=True)
    assert error.value.code == "invalid_output"
