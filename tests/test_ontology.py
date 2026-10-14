from builders import FIXTURES

from ontospan.ontology import ObographOntology, is_under, release_of


def test_loads_labels_versions_and_obsolete_terms() -> None:
    hp = ObographOntology.load(FIXTURES / "hp-mini.json")
    assert hp.label("HP:0001250") == "Seizure"
    assert hp.version == "http://purl.obolibrary.org/obo/hp/releases/2026-06-23/hp.json"
    assert hp.is_active("HP:0001250")
    assert not hp.is_active("HP:0000057")
    assert not hp.is_active("HP:9999999")


def test_the_release_is_taken_from_the_version_iri() -> None:
    assert ObographOntology.load(FIXTURES / "hp-mini.json").release == "2026-06-23"
    assert release_of("2025-01-01") == "2025-01-01"
    assert release_of(None) is None


def test_ancestors_are_transitive_and_exclude_the_term() -> None:
    hp = ObographOntology.load(FIXTURES / "hp-mini.json")
    assert hp.ancestors("HP:0011146") == frozenset(
        {"HP:0001250", "HP:0012638", "HP:0000707", "HP:0000118", "HP:0000001"}
    )
    assert hp.ancestors("HP:0000001") == frozenset()


def test_is_under_includes_the_root_itself() -> None:
    hp = ObographOntology.load(FIXTURES / "hp-mini.json")
    assert is_under(hp, "HP:0003593", "HP:0003674")
    assert is_under(hp, "HP:0003674", "HP:0003674")
    assert not is_under(hp, "HP:0001250", "HP:0012823")
