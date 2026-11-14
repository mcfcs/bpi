"""Whether retrieved findings speak to the question's own concept (app/topicality.py), and how two-part
questions are split for search (app/retrieval.py), without a database."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import topicality
from app.config import topicality_config
from app.retrieval import split_question


def finding(text: str, title: str, metric_key: str | None = None, similarity: float = 0.5, kind: str = "quant_stat"):
    return SimpleNamespace(text=text, theme=None, metric_key=metric_key, study_title=title, finding_type=kind,
                           similarity=similarity)


BUDGET = finding("Ran out of money before payday in the last three months.", "Payday Budget Focus Groups 2025",
                 kind="qual_theme", similarity=0.51)
SCAM_TEXT = finding("7% said they had clicked a link in such a message.", "Bank Impersonation Text Survey 2026",
                    metric_key="fraud:clicked_fake_link")


def test_semantic_neighbours_that_miss_the_concept_do_not_answer():
    # Retirees' savings goals and payday budgeting sit close in embedding space; neither word is shared.
    assert not topicality.answers_question("What savings goals do retirees set?", [BUDGET], bypass_similarity=0.7)


def test_a_near_exact_match_answers_without_shared_words():
    assert topicality.answers_question("What savings goals do retirees set?",
                                       [finding(BUDGET.text, BUDGET.study_title, similarity=0.72)], bypass_similarity=0.7)


def test_paraphrases_meet_the_studys_own_words():
    # SMS is "a text" in the Philippines; impersonate / impersonation and merchant / vendor normalise together.
    assert topicality.answers_question("Are people falling for phishing SMS that impersonate banks?", [SCAM_TEXT], 0.7)
    vendor = finding("Participants described QR payments as convenient for small amounts.",
                     "Market Vendor QR Payments Groups 2026", kind="qual_theme")
    assert topicality.answers_question("What do merchants think about scan-to-pay?", [vendor], 0.7)


def test_verbatims_alone_do_not_answer_and_generic_questions_always_do():
    quote = finding("I ran out before payday again.", "Payday Budget Focus Groups 2025", kind="verbatim")
    assert not topicality.answers_question("How do workers stretch their pay until payday?", [quote], 0.7)
    assert topicality.answers_question("What do we know about our customers?", [BUDGET], 0.7)


def test_only_semantic_embedders_gate_briefs_on_the_concept():
    # The lexical embedder already drops off-topic findings one by one.
    assert topicality_config("hashing")["brief_needs_concept"] is False
    assert topicality_config("bedrock:cohere.embed-multilingual-v3")["brief_needs_concept"] is True


# Two-part questions are searched part by part (app/retrieval.split_question) -------------------------

@pytest.mark.parametrize("question, parts", [
    ("Are fees and approval time a problem for SME owners in Visayas?",
     ["Are fees a problem for SME owners in Visayas?", "Are approval time a problem for SME owners in Visayas?"]),
    ("How unpredictable is income for delivery riders and freelancers?",
     ["How unpredictable is income for delivery riders?", "How unpredictable is income for freelancers?"]),
    ("Is the selfie ID check and the annual fee putting young adults off card applications?",
     ["Is the selfie ID check putting young adults off card applications?",
      "Is the annual fee putting young adults off card applications?"]),
    ("How do typhoons affect household income and how do workshops change financial literacy?",
     ["How do typhoons affect household income?", "How do workshops change financial literacy?"]),
])
def test_two_things_joined_by_and_are_searched_separately(question, parts):
    assert split_question(question) == parts


@pytest.mark.parametrize("question", [
    "How long do merchants wait to hear back about credit decisions, and does it matter?",   # no second concept
    "Do business borrowers struggle with the ID and document checks on a loan?",            # one check, two words
    "Why do SME owners drop off during online loan applications?",
])
def test_one_thing_stays_one_question(question):
    assert split_question(question) == []


# Bedrock embeddings: Cohere v3 is cut to the column size; v4 is asked for it -------------------------
class _FakeRuntime:
    def __init__(self, payload):
        self.bodies, self._payload = [], payload

    def invoke_model(self, **kwargs):
        import io
        import json

        self.bodies.append(json.loads(kwargs["body"]))
        return {"body": io.BytesIO(json.dumps(self._payload).encode())}


def test_cohere_v4_is_asked_for_512_dimensions_and_v3_is_cut_to_them():
    from app.embeddings import EMBEDDING_DIM, BedrockEmbedder

    v4 = _FakeRuntime({"embeddings": {"float": [[0.5] * EMBEDDING_DIM]}})
    vec = BedrockEmbedder("global.cohere.embed-v4:0", "ap-southeast-1", client=v4).embed_query("fake bank text")
    assert v4.bodies[0]["output_dimension"] == EMBEDDING_DIM and v4.bodies[0]["input_type"] == "search_query"
    assert len(vec) == EMBEDDING_DIM and abs(sum(x * x for x in vec) - 1) < 1e-9

    v3 = _FakeRuntime({"embeddings": [[0.5] * 1024]})
    vec = BedrockEmbedder("cohere.embed-multilingual-v3", "ap-southeast-1", client=v3).embed("a finding")
    assert "output_dimension" not in v3.bodies[0] and len(vec) == EMBEDDING_DIM


# Extraction: a model's paraphrase rarely matches the PDF; the report's own words find the page ----------
def test_a_finding_is_placed_by_the_reports_own_words_before_the_paraphrase():
    from app.documents import map_finding_pages
    from app.schemas import ExtractedFinding, StudyCardExtraction

    pages = ["Contents and foreword.", "Highlights: account ownership rose sharply.",
             "Account ownership significantly increased to 56% in 2021 from 29% in 2019."]
    finding = ExtractedFinding(text="56% of adults owned an account in 2021, up from 29% in 2019.",
                               finding_type="quant_stat", theme=None, metric_key="inclusion:account", value=56,
                               unit="%", base_n=None, subgroup=None, direction="high",
                               source_text="Account ownership significantly increased to 56% in 2021 from 29% in 2019")
    card = StudyCardExtraction.model_construct(findings=[finding])
    found, excerpts = map_finding_pages(card, pages)
    assert found == {0: 3} and "56% in 2021" in excerpts[0]
    # Without the report's words, the paraphrase alone does not place it.
    finding.source_text = None
    assert map_finding_pages(card, pages)[0] == {0: None}
