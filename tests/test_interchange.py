import json
import xml.etree.ElementTree as ET
from typing import Any

import pytest
from builders import FIXTURES, SEIZURE, SEVERE, annotation, axes, unit

from ontospan.bioc import to_bioc_json, to_bioc_xml
from ontospan.brat import to_brat
from ontospan.models import (
    Actor,
    AnnotatedDocument,
    Annotation,
    AnnotationSet,
    ReviewResolution,
)
from ontospan.ontology import ObographOntology

# Emoji are one codepoint, two UTF-16 units and four UTF-8 bytes.
# Krampfanfälle 2-15, schwere 19-26, Hypotonie 27-36, Fieber 41-47.
T = "🧒 Krampfanfälle, 😷 schwere\nHypotonie und Fieber."
HYPOTONIA, FEVER, DIALEPTIC = "HP:0001252", "HP:0001945", "HP:0011146"


def a(aid: str, term: str, *spans: Any, **kw: Any) -> Annotation:
    return annotation(aid, term, list(spans), text=T, **kw)


def items() -> list[Annotation]:
    return [
        a("a1", SEIZURE, (2, 15), cues=[(0, 1)], modifiers=[(SEVERE, [(19, 26)])]),
        a("a2", HYPOTONIA, [(19, 26), (27, 36)]),
        a("a3", HYPOTONIA, (27, 36), axes_=axes("absent", basis="defaulted")),
        a("a4", FEVER, (41, 47), (2, 15)),
        a("a5", HYPOTONIA, (19, 36)),
        a("d1", DIALEPTIC, document_level=True),
    ]


def sample(annotations: list[Annotation] | None = None, **kw: Any) -> AnnotatedDocument:
    return unit(items() if annotations is None else annotations, text=T, **kw)


@pytest.fixture(scope="module")
def hp() -> ObographOntology:
    return ObographOntology.load(FIXTURES / "hp-mini.json")


def reversed_sample() -> AnnotatedDocument:
    item = sample()
    annotation_set = AnnotationSet.model_validate(
        {
            **item.annotation_set.model_dump(),
            "annotations": list(reversed(item.annotation_set.annotations)),
        }
    )
    return item.model_copy(update={"annotation_set": annotation_set})


# brat


def entities(ann: str) -> list[tuple[str, str, list[tuple[int, int]], str]]:
    found = []
    for line in ann.splitlines():
        if line.startswith("T"):
            entity, middle, quoted = line.split("\t")
            kind, spans = middle.split(" ", 1)
            fragments = [
                (int(start), int(end))
                for start, end in (part.split(" ") for part in spans.split(";"))
            ]
            found.append((entity, kind, fragments, quoted))
    return found


def test_brat_writes_codepoint_offsets_terms_attributes_and_notes(
    hp: ObographOntology,
) -> None:
    files, report = to_brat(sample([items()[0]]), hp, bundle_id="b-1")
    assert files.txt == T
    assert files.ann == (
        "T1\thpo 2 15\tKrampfanfälle\n"
        "N1\tReference T1 HP:0001250\tSeizure\n"
        "A1\tassertion T1 present\n"
        "A2\texperiencer T1 patient\n"
        "A3\ttemporality T1 current\n"
        "#1\tAnnotatorNotes T1\tref=urn:ontospan:b-1:set-1:a1; mention=1; "
        "modifiers=HP:0012828; annotator=ann-03; annotator_kind=human; "
        "method=manual\n"
    )
    assert (report.cue_segments_dropped, report.modifier_segments_dropped) == (1, 1)
    assert report.axis_basis_dropped == 3


def test_brat_entities_quote_the_text_and_split_at_line_breaks() -> None:
    files, report = to_brat(sample())
    found = entities(files.ann)
    for _, kind, fragments, quoted in found:
        assert kind == "hpo"
        assert quoted == " ".join(files.txt[s:e] for s, e in fragments)
    # Text order, one entity per mention; a2 is discontinuous, a5 crosses "\n".
    assert [fragments for _, _, fragments, _ in found] == [
        [(2, 15)],
        [(2, 15)],
        [(19, 26), (27, 36)],
        [(19, 26), (27, 36)],
        [(27, 36)],
        [(41, 47)],
    ]
    assert "ref=urn:ontospan:set-1:a5; mention=1" in files.ann
    assert "ref=urn:ontospan:set-1:a4; mention=2" in files.ann
    assert report.split_at_line_breaks == 1
    assert (report.exported, report.mentions, report.discontinuous) == (5, 6, 1)


def test_brat_drops_spanless_annotations_into_the_report() -> None:
    files, report = to_brat(sample())
    assert "HP:0011146" not in files.ann
    assert report.spanless == 1
    assert report.dropped == ["urn:ontospan:set-1:d1"]


def test_brat_output_is_deterministic() -> None:
    assert to_brat(sample())[0] == to_brat(reversed_sample())[0]


def test_brat_notes_keep_provenance_and_review_on_one_line() -> None:
    resolution = ReviewResolution(
        outcome="uncertain",
        reviewer=Actor(actor_id="rev-1", kind="human"),
        note="check\nagain",
    )
    item = a("a1", SEIZURE, (2, 15), source_refs=["urn:ontospan:tool:x1"])
    item = item.model_copy(update={"review_resolution": resolution})
    files, report = to_brat(sample([item]))
    note = files.ann.splitlines()[-1]
    assert note.endswith(
        "source_refs=urn:ontospan:tool:x1; review_outcome=uncertain; "
        "reviewer=rev-1; reviewer_kind=human; review_note=check again"
    )
    assert report.note_text_flattened == 1


def test_brat_refuses_names_with_whitespace() -> None:
    with pytest.raises(ValueError, match="whitespace"):
        to_brat(sample([a("a1", SEIZURE, (2, 15), axes_=axes("not sure"))]))


# BioC


def test_bioc_json_has_one_document_with_one_passage() -> None:
    collection, _ = to_bioc_json([sample(subject_id="P1")])
    assert collection["infons"]["offset_unit"] == "codepoint"
    assert (collection["source"], collection["date"]) == ("ontospan", "2026-10-14")
    (document,) = collection["documents"]
    assert document["id"] == "doc-1"
    assert document["infons"]["subject_id"] == "P1"
    assert document["infons"]["layer.hpo.version"] == "2026-06-23"
    (passage,) = document["passages"]
    assert (passage["offset"], passage["text"]) == (0, T)


def test_bioc_annotations_carry_locations_and_infons(hp: ObographOntology) -> None:
    collection, report = to_bioc_json([sample()], hp, bundle_id="b-1")
    annotations = collection["documents"][0]["passages"][0]["annotations"]
    assert [item["id"] for item in annotations] == [
        "a1",
        "a4/2",
        "a2",
        "a5",
        "a3",
        "a4/1",
    ]
    for item in annotations:
        quoted = [T[x["offset"] : x["offset"] + x["length"]] for x in item["locations"]]
        assert item["text"] == " ".join(quoted)
    first, _, discontinuous, *_ = annotations
    assert discontinuous["locations"] == [
        {"offset": 19, "length": 7},
        {"offset": 27, "length": 9},
    ]
    assert discontinuous["text"] == "schwere Hypotonie"
    assert first["infons"] == {
        "identifier": SEIZURE,
        "type": "hpo",
        "label": "Seizure",
        "assertion": "present",
        "assertion_basis": "chosen",
        "experiencer": "patient",
        "experiencer_basis": "chosen",
        "temporality": "current",
        "temporality_basis": "chosen",
        "modifiers": SEVERE,
        "annotator": "ann-03",
        "annotator_kind": "human",
        "method": "manual",
        "annotation_ref": "urn:ontospan:b-1:set-1:a1",
        "mention": "1",
    }
    assert annotations[4]["infons"]["assertion_basis"] == "defaulted"
    assert (report.exported, report.mentions, report.discontinuous) == (6, 6, 1)
    assert (report.cue_segments_dropped, report.modifier_segments_dropped) == (1, 1)
    assert report.dropped == []


def test_bioc_spanless_annotations_become_relations_without_nodes() -> None:
    collection, report = to_bioc_json([sample()])
    (relation,) = collection["documents"][0]["relations"]
    assert relation["id"] == "d1"
    assert relation["nodes"] == []
    assert relation["infons"]["identifier"] == DIALEPTIC
    assert relation["infons"]["document_level"] == "true"
    assert report.spanless == 1


def test_bioc_output_is_deterministic_and_json_serialisable() -> None:
    first, _ = to_bioc_json([sample()])
    second, _ = to_bioc_json([reversed_sample()])
    assert json.dumps(first, ensure_ascii=False) == json.dumps(
        second, ensure_ascii=False
    )


def test_bioc_alternative_sets_of_one_document_get_their_own_ids() -> None:
    collection, report = to_bioc_json([sample(set_id="set:A"), sample(set_id="set:B")])
    assert [d["id"] for d in collection["documents"]] == [
        "urn:ontospan:document:doc-1:set%3AA",
        "urn:ontospan:document:doc-1:set%3AB",
    ]
    assert report.exported == 12
    with pytest.raises(ValueError, match="at least one document"):
        to_bioc_json([])


def test_bioc_xml_follows_the_dtd_order_and_the_json_content() -> None:
    xml, report = to_bioc_xml([sample()])
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE')
    root = ET.fromstring(xml.encode("utf-8"))
    assert [child.tag for child in root][:4] == ["source", "date", "key", "infon"]
    document = root.find("document")
    assert document is not None
    assert document[0].tag == "id"
    passage = document.find("passage")
    assert passage is not None
    assert passage.findtext("text") == T
    item = passage.find("annotation[@id='a2']")
    assert item is not None
    assert [child.tag for child in item][-3:] == ["location", "location", "text"]
    assert [(x.get("offset"), x.get("length")) for x in item.iter("location")] == [
        ("19", "7"),
        ("27", "9"),
    ]
    assert item.findtext("infon[@key='identifier']") == HYPOTONIA
    relation = document.find("relation[@id='d1']")
    assert relation is not None
    assert relation.findtext("infon[@key='document_level']") == "true"
    assert root.findtext("infon[@key='offset_unit']") == "codepoint"
    assert report.spanless == 1
    assert to_bioc_xml([reversed_sample()])[0] == xml


def test_bioc_xml_refuses_characters_xml_cannot_hold() -> None:
    plain = a("a1", SEIZURE, (2, 15))
    provenance = plain.provenance.model_copy(update={"notes": ("bell \x07",)})
    item = sample([plain.model_copy(update={"provenance": provenance})])
    collection, _ = to_bioc_json([item])
    infons = collection["documents"][0]["passages"][0]["annotations"][0]["infons"]
    assert infons["note_1"] == "bell \x07"
    with pytest.raises(ValueError, match="XML 1"):
        to_bioc_xml([item])
