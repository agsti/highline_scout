"""Content contracts for issue-driven country-ETL coordination skills."""

from pathlib import Path


SKILLS_DIR = Path(__file__).parent.parent / ".claude" / "skills"


def _skill(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text()


def test_country_etl_skills_use_issue_based_progress_contracts() -> None:
    adding = _skill("adding-country-etls")
    dispatching = _skill("dispatching-country-etls")

    for skill in (adding, dispatching):
        assert "at least every 30 minutes" in skill
        assert "COUNTRIES.md" not in skill
        assert "sync_country_etl_issues" not in skill

    assert "Closes #<issue-number>" in dispatching
