import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_TEST_CONFIG_DIR = Path(tempfile.gettempdir()) / "atp-test-config"
_TEST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_EXAMPLE_SETTINGS = _PROJECT_ROOT / "example.settings.conf"
_TEST_SETTINGS = _TEST_CONFIG_DIR / "settings.conf"
if not _TEST_SETTINGS.exists() and _EXAMPLE_SETTINGS.exists():
    shutil.copy2(_EXAMPLE_SETTINGS, _TEST_SETTINGS)
os.environ.setdefault("TEST_CONFIG_DIR", str(_TEST_CONFIG_DIR))

from atp.database import Base  # noqa: E402


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def downloads_dir(tmp_workspace: Path) -> Path:
    path = tmp_workspace / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture
def sqlite_session(tmp_workspace: Path) -> Generator[Session, None, None]:
    db_file = tmp_workspace / "test.db"
    engine = create_engine(f"sqlite:///{db_file}")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
