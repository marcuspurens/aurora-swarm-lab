"""Intake Obsidian note: parse frontmatter commands and enqueue jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from app.clients.obsidian_client import ObsidianCommand, ObsidianWatcher, parse_command, parse_frontmatter, write_output
from app.core.ids import make_source_id, sha256_file
from app.queue.jobs import enqueue_job
from app.queue.logs import log_run
from app.modules.intake.ingest_auto import extract_items, enqueue_items
from app.modules.intake.intake_url import compute_source_version as compute_url_version
from app.modules.intake.intake_youtube import compute_source_version as compute_youtube_version


def _enqueue_command(cmd: ObsidianCommand) -> Dict[str, object]:
    command = cmd.command
    params = cmd.params

    if command == "ingest_url":
        url = str(params.get("url"))
        source_id = make_source_id("url", url)
        source_version = compute_url_version(url)
        job_id = enqueue_job("ingest_url", "io", source_id, source_version)
        return {"job_id": job_id, "job_type": "ingest_url", "source_id": source_id}

    if command == "ingest_doc":
        raw_path = Path(str(params.get("path")))
        if not raw_path.is_absolute():
            raw_path = (cmd.note_path.parent / raw_path).resolve()
        path = raw_path
        return _enqueue_doc_path(path)

    if command == "ingest_youtube":
        url = str(params.get("url"))
        from app.clients.youtube_client import get_video_info
        info = get_video_info(url)
        video_id = str(info.get("id") or "unknown")
        source_id = make_source_id("youtube", video_id)
        source_version = compute_youtube_version(url)
        job_id = enqueue_job("ingest_youtube", "io", source_id, source_version)
        return {"job_id": job_id, "job_type": "ingest_youtube", "source_id": source_id}

    if command == "ask":
        question = str(params.get("question"))
        source_id = make_source_id("obsidian", str(cmd.note_path))
        from app.core.ids import sha256_text
        source_version = sha256_text(question)
        job_id = enqueue_job("ask", "oss20b", source_id, source_version)
        return {"job_id": job_id, "job_type": "ask", "source_id": source_id, "question": question}

    return {"error": f"Unknown command: {command}"}


def _enqueue_doc_path(path: Path) -> Dict[str, object]:
    source_id = make_source_id("file", str(path))
    source_version = sha256_file(path)
    job_id = enqueue_job("ingest_doc", "io", source_id, source_version)
    return {"job_id": job_id, "job_type": "ingest_doc", "source_id": source_id}


def _note_is_auto(note_path: Path, frontmatter: Dict[str, object]) -> bool:
    if frontmatter.get("aurora_auto") is True:
        return True
    for part in note_path.parents:
        if part.name.lower() == "aurora inbox":
            return True
    return False


def _enqueue_auto(note_path: Path) -> Dict[str, object] | None:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    frontmatter, body = parse_frontmatter(text)
    if not _note_is_auto(note_path, frontmatter):
        return None
    items = extract_items(
        text=body,
        items=frontmatter.get("aurora_items"),
        base_dir=note_path.parent,
        dedupe=True,
    )
    if items:
        return {"job_type": "auto", "items": enqueue_items(items, base_dir=note_path.parent)}
    if body.strip():
        return _enqueue_doc_path(note_path)
    return {"error": "No intake items found"}


def handle_command(cmd: ObsidianCommand) -> None:
    run_id = log_run(
        lane="io",
        component="intake_obsidian",
        input_json={"command": cmd.command, "params": cmd.params, "note_path": str(cmd.note_path)},
    )
    result = _enqueue_command(cmd)
    content = (
        "# Aurora output\n\n"
        f"Command: `{cmd.command}`\n\n"
        "Result:\n```\n"
        f"{result}\n"
        "```\n"
    )
    write_output(cmd.note_path, content)
    log_run(lane="io", component="intake_obsidian", input_json={"run_id": run_id}, output_json=result)


def enqueue(note_path: str) -> Dict[str, object]:
    path = Path(note_path)
    cmd = parse_command(path)
    if cmd:
        return _enqueue_command(cmd)
    auto = _enqueue_auto(path)
    if auto is not None:
        return auto
    return {"error": "No aurora_command or aurora_auto found"}


def watch_vault() -> None:
    def _handle_note(note_path: Path) -> None:
        cmd = parse_command(note_path)
        if cmd:
            handle_command(cmd)
            return
        result = _enqueue_auto(note_path)
        if result is None:
            return
        content = (
            "# Aurora output\n\n"
            f"Command: `auto`\n\n"
            "Result:\n```\n"
            f"{result}\n"
            "```\n"
        )
        write_output(note_path, content)
        log_run(lane="io", component="intake_obsidian", input_json={"note_path": str(note_path)}, output_json=result)

    watcher = ObsidianWatcher()
    watcher.start(_handle_note)
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()
