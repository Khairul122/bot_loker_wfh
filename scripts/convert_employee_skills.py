"""Convert packaged employee persona notes to Hermes Agent skills."""

from __future__ import annotations

from pathlib import Path

from bot_loker_wfh.office_desk import ROLES

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "bot_loker_wfh" / "skills" / "employees"
TARGET = ROOT / "src" / "bot_loker_wfh" / "hermes_skills"


def main() -> None:
    for employee, role in sorted(ROLES.items()):
        source_dir = SOURCE / employee
        if not source_dir.is_dir():
            source_file = SOURCE / f"{employee}.md"
            if not source_file.is_file():
                raise FileNotFoundError(f"Missing persona source for {employee}")
            source_files = [source_file]
        else:
            source_files = sorted(source_dir.glob("*.md"), key=lambda path: (path.name != "main.md", path.name))
        if not source_files:
            raise FileNotFoundError(f"No persona sources for {employee}")

        sections = []
        for path in source_files:
            title = "Persona" if path.stem == "main" else path.stem.replace("-", " ").title()
            sections.append(f"## {title}\n\n{path.read_text(encoding='utf-8-sig').strip()}")
        skill_name = f"loker-employee-{employee}"
        description = f"Persona dan konteks kerja untuk {employee.title()}, {role}."
        content = (
            "---\n"
            f"name: {skill_name}\n"
            f"description: {description}\n"
            "version: 1.0.0\n"
            "metadata:\n"
            "  hermes:\n"
            f"    tags: [loker-wfh, employee, {employee}]\n"
            "---\n\n"
            f"# {employee.title()} — {role}\n\n"
            "Gunakan fakta dan instruksi dalam konteks tugas aplikasi. Jangan mengarang data owner, "
            "jangan mengubah status record, jangan mengirim bid/lamaran, dan jangan melewati CAPTCHA. "
            "Tool Hermes hanya untuk reasoning, skill, memory, serta handoff antar-karyawan.\n\n"
            + "\n\n".join(sections)
            + "\n"
        )
        output = TARGET / skill_name / "SKILL.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
