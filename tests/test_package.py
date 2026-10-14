import ontospan


def test_the_package_states_its_version_and_schema_version() -> None:
    assert ontospan.__version__ == "1.0.0.dev0"
    assert ontospan.SCHEMA_VERSION == "1.0.0"
