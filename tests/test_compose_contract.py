from pathlib import Path

import yaml


def test_docker_compose_contract_matches_runtime_auth_logging_dependencies() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = yaml.safe_load((root / "compose.yml").read_text(encoding="utf-8"))
    includes = [root / item for item in compose["include"]]
    services = {}
    for include in includes:
        data = yaml.safe_load(include.read_text(encoding="utf-8"))
        services.update(data.get("services", {}))

    assert {"mysql", "redis", "openldap"}.issubset(services)
    assert "../databases-init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro" in services["mysql"]["volumes"]
    assert "AUTOOPSHUB_MYSQL_DATABASE" in services["mysql"]["environment"]["MYSQL_DATABASE"]
    assert services["redis"]["ports"]
    assert services["openldap"]["ports"]
