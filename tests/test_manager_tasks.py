from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest

from bot_loker_wfh import database
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.company import DIVISIONS, EMPLOYEES
from bot_loker_wfh.manager_tasks import (
    assign_recommendations, create_task, division_brief, list_tasks, update_task,
)


@pytest.fixture
def connection():
    conn = database.connect()
    apply_schema(conn)
    yield conn
    conn.close()


def test_manager_assigns_and_reviews_internal_division_task(connection):
    task = create_task(connection, "mira", "bimo", "Rapikan ringkasan operasional", "high")
    assert task["status"] == "assigned"
    assert list_tasks(connection, "mira")[0]["assignee_name"] == "Bimo"

    update_task(connection, "mira", task["id"], "in_progress")
    reviewed = update_task(connection, "mira", task["id"], "reviewed", "Sudah dicek bersama tim")
    assert reviewed["status"] == "reviewed"
    assert reviewed["review_note"] == "Sudah dicek bersama tim"


@pytest.mark.parametrize("manager", ["bimo", "owner", "unknown"])
def test_only_registered_division_manager_can_access_tasks(connection, manager):
    with pytest.raises(KeyError):
        list_tasks(connection, manager)


def test_manager_cannot_assign_outside_their_division(connection):
    with pytest.raises(ValueError, match="managed_division"):
        create_task(connection, "tegar", "reno", "Review pencarian hari ini")


@pytest.mark.parametrize("title", ["", "ab", "x" * 161])
def test_task_title_is_bounded(connection, title):
    with pytest.raises(ValueError, match="title"):
        create_task(connection, "tegar", "tegar", title)


def test_each_division_has_one_manager_who_belongs_to_that_division():
    by_id = {employee["id"]: employee for employee in EMPLOYEES}
    assert len(DIVISIONS) == 7
    for division in DIVISIONS:
        manager = by_id[division["manager"]]
        assert manager["division"] == division["id"]
        assert manager["is_manager"] is True


def test_hermes_manager_brief_uses_manager_memory_and_only_recommends_own_team(connection):
    response = '{"summary":"Antrean proyek perlu dirapikan.","priorities":[' \
        '{"title":"Periksa draf proyek baru","assignee":"lido","priority":"high",' \
        '"reason":"Ada proyek baru yang belum ditinjau."}]}'
    runner = MagicMock(return_value=response)
    router = MagicMock(spec=["for_task"])
    router.for_task.return_value = runner
    llm = SimpleNamespace(router=router)

    result = division_brief(connection, "mira", llm)

    assert result["division"] == {"id": "freelance", "name": "Proyek Freelance", "manager": "mira"}
    assert result["priorities"][0]["assignee_name"] == "Lido"
    context = router.for_task.call_args.kwargs
    assert router.for_task.call_args.args == ("manager",)
    assert context["persona"] == "mira"
    assert context["session_key"] == "bot-loker-wfh:v3:employee:mira"
    assert "accountable manager" in context["system_prompt"]
    prompt = runner.call_args.args[0]
    assert '"division": "Proyek Freelance"' in prompt
    assert '"id": "bimo"' in prompt
    assert '"id": "sari"' not in prompt
    assert "Never submit applications or bids" in context["system_prompt"]

    assigned = assign_recommendations(connection, "mira", result["priorities"])
    assert assigned[0]["status"] == "assigned"
    assert assigned[0]["manager"] == "mira"
    assert list_tasks(connection, "mira")[0]["assignee"] == "lido"
    assert assign_recommendations(connection, "mira", result["priorities"]) == []


def test_hermes_manager_brief_rejects_assignment_outside_managed_division(connection):
    llm = MagicMock(spec=["with_context"])
    llm.with_context.return_value = MagicMock(return_value=(
        '{"summary":"Perlu tindak lanjut.","priorities":['
        '{"title":"Review pencarian","assignee":"reno","priority":"high","reason":"Cek antrean."}]}'
    ))
    with pytest.raises(ValueError, match="invalid_manager_brief"):
        division_brief(connection, "tegar", llm)


def test_hermes_manager_brief_fails_closed_when_runtime_toolsets_are_unsafe(connection):
    provider = MagicMock()
    provider.check_readiness.return_value = {"ok": False, "unexpected_toolsets": ["terminal"]}
    router = SimpleNamespace(
        chain=[(provider, "draft")],
        task_models={"manager": "loker-answer"},
        for_task=MagicMock(),
    )
    with pytest.raises(RuntimeError, match="hermes_not_ready"):
        division_brief(connection, "mira", SimpleNamespace(router=router))
    provider.check_readiness.assert_called_once_with(required_models=("loker-answer",))
    router.for_task.assert_not_called()
