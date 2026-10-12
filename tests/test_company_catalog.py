from bot_loker_wfh.company import (
    DIVISIONS,
    EMPLOYEES,
    JOB_SCOUTS as CATALOG_JOB_SCOUTS,
    LEAD_SCOUTS as CATALOG_LEAD_SCOUTS,
    MANAGERS,
    MAX_FLOORS,
    ROLES,
    division_for_employee,
)
from bot_loker_wfh.office_desk import JOB_SCOUTS, LEAD_SCOUTS


def test_company_catalog_has_one_manager_for_each_operational_division():
    assert MAX_FLOORS == 7
    assert len(DIVISIONS) == 7
    assert len({division["id"] for division in DIVISIONS}) == len(DIVISIONS)
    assert {division["manager"] for division in DIVISIONS} == {
        "tegar", "reno", "sari", "cora", "subi", "tara", "mira"
    }
    assert len(MANAGERS) == len(DIVISIONS)
    assert [division["floor"] for division in DIVISIONS] == list(range(7))


def test_each_employee_has_one_valid_division_and_manager_metadata():
    assert len(EMPLOYEES) == 20
    assert len({employee["id"] for employee in EMPLOYEES}) == len(EMPLOYEES)
    assert set(ROLES) == {employee["id"] for employee in EMPLOYEES}

    for employee in EMPLOYEES:
        division = division_for_employee(employee["id"])
        assert division is not None
        assert employee["division"] == division["id"]
        assert employee["is_manager"] is (division["manager"] == employee["id"])


def test_manager_mapping_matches_the_approved_teams():
    assert MANAGERS == {
        "lobi": "tegar",
        "cari": "reno",
        "seleksi": "sari",
        "tulis": "cora",
        "lamar": "subi",
        "pantau": "tara",
        "freelance": "mira",
    }


def test_scout_sources_come_from_the_canonical_employee_catalog():
    expected_jobs = {
        "reno": "remoteok",
        "rima": "remotive",
        "gery": "greenhouse",
        "leva": "lever",
        "kalia": "kalibrr",
        "dela": "dealls",
    }
    expected_leads = {
        "lido": "freelancer",
        "nara": "projects.co.id",
        "tama": "telegram",
    }
    assert CATALOG_JOB_SCOUTS == JOB_SCOUTS == expected_jobs
    assert CATALOG_LEAD_SCOUTS == LEAD_SCOUTS == expected_leads
