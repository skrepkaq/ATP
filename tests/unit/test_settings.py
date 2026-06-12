import os
from importlib import reload
from pathlib import Path

import pytest

from atp import settings

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "settings_migrations"


@pytest.mark.unit
def test_proxy_from_settings_conf_sets_all_proxy_on_module_import(tmp_path: Path) -> None:
    """PROXY from settings.conf is applied to ALL_PROXY only when settings.py imports.

    In the pytest process, ``atp.settings`` is usually already imported during test init.
    Reloading is required to re-run module-level initialization.
    """
    proxy_url = "socks5://user:lox@127.0.0.1:65520"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.conf").write_text(
        f"CONFIG_VERSION=9\nPROXY={proxy_url}\n",
        encoding="utf-8",
    )

    with pytest.MonkeyPatch.context() as context:
        context.setenv("TEST_CONFIG_DIR", str(config_dir))
        context.delenv("PROXY", raising=False)
        context.delenv("ALL_PROXY", raising=False)

        reload(settings)

        assert proxy_url == settings.PROXY
        assert os.environ.get("ALL_PROXY") == proxy_url

    reload(settings)


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


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw_env", "expected"),
    [
        ("@myuser", "myuser"),
        ("  @myuser  ", "myuser"),
        ("user@handle", "userhandle"),
    ],
)
def test_tiktok_user_strips_at_and_whitespace_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_env: str,
    expected: str,
) -> None:
    """TIKTOK_USER normalizes os.environ via .replace('@', '').strip() at import time."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.conf").write_text("CONFIG_VERSION=12\n", encoding="utf-8")

    monkeypatch.setenv("TEST_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("TIKTOK_USER", raw_env)
    monkeypatch.delenv("PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)

    reload(settings)

    try:
        assert expected == settings.TIKTOK_USER
    finally:
        reload(settings)


@pytest.mark.unit
def test_check_dir_permission_ok(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good_dir = tmp_path / "good"
    good_dir.mkdir()

    settings.check_dir_permission(good_dir)

    assert capsys.readouterr().out == ""


@pytest.mark.unit
def test_check_dir_permission_missing_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"

    settings.check_dir_permission(missing)

    out = capsys.readouterr().out
    assert f"Directory {missing} does not exist" in out
    assert f"Path {missing} is not a directory" in out
    assert "is not writable" in out


@pytest.mark.unit
def test_check_dir_permission_not_a_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")

    settings.check_dir_permission(file_path)

    out = capsys.readouterr().out
    assert f"Path {file_path} is not a directory" in out
    assert f"Directory {file_path} does not exist" not in out


@pytest.mark.unit
def test_check_dir_permission_not_writable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    read_only = tmp_path / "readonly"
    read_only.mkdir()
    read_only.chmod(0o555)
    try:
        settings.check_dir_permission(read_only)

        out = capsys.readouterr().out
        assert f"Error: {read_only} is not writable" in out
        assert "1000:1000" in out
    finally:
        read_only.chmod(0o755)


@pytest.mark.unit
def test_load_config_permission_error_exits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    monkeypatch.setenv("TEST_CONFIG_DIR", str(config_dir))

    def raise_permission_error(_src: Path, _dst: Path) -> None:
        raise PermissionError("Permission denied")

    monkeypatch.setattr(settings.shutil, "copy2", raise_permission_error)

    def fake_exit(code: int) -> None:
        raise SystemExit(code)

    monkeypatch.setattr(settings.sys, "exit", fake_exit)

    with pytest.raises(SystemExit) as exc_info:
        settings.load_config()

    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Error copying example settings: Permission denied" in out
    assert "Please check the permissions of the config directory" in out
    assert f"Error: {config_dir} is not writable" not in out
