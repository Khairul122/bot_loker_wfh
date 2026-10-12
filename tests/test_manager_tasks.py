import pytest

from bot_loker_wfh import database
from bot_loker_wfh.database import apply_schema
from bot_loker_wfh.manager_tasks import create_task, list_tasks, update_task


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
