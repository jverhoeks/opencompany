import pytest
import yaml

from opencompany.company.config import delete_role, load_company_config, update_role


@pytest.fixture
def config_file(tmp_path):
    data = {
        "org_style": "hierarchical",
        "org_styles": {"hierarchical": {"routing": {"ceo": "pm"}, "max_depth": 3}},
        "roles": {
            "ceo": {"type": "manager", "responsibilities": "Lead."},
            "dev": {"type": "solver", "responsibilities": "Code.", "tag_match": ["backend"]},
        },
        "personas": {},
    }
    path = tmp_path / "company.yaml"
    path.write_text(yaml.dump(data, default_flow_style=False))
    return str(path)


def test_update_role(config_file):
    update_role("dev", {"responsibilities": "Code and test."}, path=config_file)
    config = load_company_config(config_file)
    assert config.roles["dev"]["responsibilities"] == "Code and test."


def test_update_role_not_found(config_file):
    with pytest.raises(KeyError, match="not-exist"):
        update_role("not-exist", {"responsibilities": "x"}, path=config_file)


def test_delete_role(config_file):
    delete_role("dev", path=config_file)
    config = load_company_config(config_file)
    assert "dev" not in config.roles


def test_delete_role_not_found(config_file):
    with pytest.raises(KeyError, match="nope"):
        delete_role("nope", path=config_file)
