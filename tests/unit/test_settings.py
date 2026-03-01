from pathlib import Path

import pytest

from atp import settings

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "settings_migrations"


@pytest.mark.unit
def test_settings_upgrades_match_fixture_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    source_v1 = FIXTURES_DIR / "settings.v1.conf"
    source_docker = FIXTURES_DIR / "settings_docker.conf"
    (config_dir / "settings.conf").write_text(
        source_v1.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Docker config must exist for version_3/version_6 behaviors.
    (config_dir / "settings-docker.conf").write_text(
        source_docker.read_text(encoding="utf-8"), encoding="utf-8"
    )

    monkeypatch.setattr(settings, "get_config_dir", lambda: config_dir)

    current_version = settings.get_config_version()
    checked_versions = 0
    while True:
        next_version = current_version + 1
        expected = FIXTURES_DIR / f"settings.v{next_version}.conf"
        if not expected.exists():
            break
        settings.VERSIONS[current_version]()
        settings.set_config_value("CONFIG_VERSION", str(next_version))

        actual_text = (config_dir / "settings.conf").read_text(encoding="utf-8")
        expected_text = expected.read_text(encoding="utf-8")
        assert actual_text == expected_text
        checked_versions += 1
        current_version = next_version

    assert checked_versions >= 1

    assert not (config_dir / "settings-docker.conf").exists()


@pytest.mark.unit
def test_get_config_dir_uses_docker_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_CONFIG_DIR", raising=False)
    monkeypatch.setattr(settings, "DOCKER", True)
    assert settings.get_config_dir() == Path("/config")


@pytest.mark.unit
def test_set_config_value_updates_existing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cfg = config_dir / "settings.conf"
    cfg.write_text("A=1\nB=2\n# B=2\n", encoding="utf-8")
    monkeypatch.setattr(settings, "get_config_dir", lambda: config_dir)

    settings.set_config_value("B", "99")

    assert cfg.read_text(encoding="utf-8") == "A=1\nB=99\n# B=2\n"


@pytest.mark.unit
def test_get_config_version_reads_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.conf").write_text("CONFIG_VERSION=6\n", encoding="utf-8")
    monkeypatch.setattr(settings, "get_config_dir", lambda: config_dir)

    assert settings.get_config_version() == 6
