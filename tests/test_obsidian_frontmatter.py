from pathlib import Path

from app.clients.obsidian_client import parse_frontmatter, parse_command


def test_parse_frontmatter():
    text = """---
aurora_command: ask
question: Hello
---
Body text
"""
    fm, body = parse_frontmatter(text)
    assert fm["aurora_command"] == "ask"
    assert body.strip() == "Body text"


def test_parse_command(tmp_path):
    note = tmp_path / "note.md"
    note.write_text(
        """---
aurora_command: ingest_url
url: https://example.com
---
Hello
""",
        encoding="utf-8",
    )
    cmd = parse_command(note)
    assert cmd is not None
    assert cmd.command == "ingest_url"
