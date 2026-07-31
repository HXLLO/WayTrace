"""The manual quick start must work out of the box.

The README flow (``cp ../.env.example ../.env`` then ``uvicorn main:app`` from
``backend/``) used to load no .env at all (env_file was CWD-relative) and fall
back to ``/data/waytrace.db``, which is not creatable outside Docker. The
runtime settings must reach the repo-root .env from any CWD, and the default
DB path must be writable on a bare clone. Docker images are unaffected: every
image/compose file pins ``DATABASE_URL=/data/waytrace.db`` explicitly.
"""
from pathlib import Path

from config import ENV_FILES, Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_db_path_is_repo_root_not_docker(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    s = Settings(_env_file=None)
    p = Path(s.database_url)
    assert s.database_url != "/data/waytrace.db"
    assert p.is_absolute()
    assert p.name == "waytrace.db"
    assert p.parent == REPO_ROOT


def test_runtime_env_files_reach_repo_root_from_any_cwd():
    first = Path(ENV_FILES[0])
    assert first.is_absolute()
    assert first == REPO_ROOT / ".env"
    # A CWD-local .env still takes priority for whoever relies on it on purpose.
    assert str(ENV_FILES[1]) == ".env"
