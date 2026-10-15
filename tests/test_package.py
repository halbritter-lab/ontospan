import ontospan


def test_the_package_states_its_version_and_schema_version() -> None:
    assert ontospan.__version__ == "1.1.0"
    assert ontospan.SCHEMA_VERSION == "1.1.0"


def test_the_public_api_is_importable_from_the_package() -> None:
    import ontospan

    names = {
        "AnnotatedDocument",
        "FormatError",
        "ObographOntology",
        "agreement",
        "annotation_ref",
        "load_annotated_document",
        "match_annotations",
        "parse_phenopacket",
        "read_bundle",
        "to_phenopacket",
        "to_phenopackets",
        "validate",
        "write_bundle",
    }
    assert names <= set(ontospan.__all__)
    assert all(hasattr(ontospan, name) for name in ontospan.__all__)
