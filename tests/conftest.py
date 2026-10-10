import pytest

from bot_loker_wfh import config


@pytest.fixture(autouse=True)
def _no_real_supabase(monkeypatch):
    """Keep unit tests off the real Supabase project, even when a local .env has a key."""
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY"):
        monkeypatch.delenv(name, raising=False)
