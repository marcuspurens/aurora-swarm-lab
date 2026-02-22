"""Obsidian client for watching vault and parsing command notes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

import yaml
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.core.config import load_settings


@dataclass
class ObsidianCommand:
    command: str
    params: Dict[str, object]
    note_path: Path


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_text = parts[1]
    body = parts[2]
    data = yaml.safe_load(fm_text) or {}
    return data, body.lstrip("\n")


def parse_command(note_path: Path) -> Optional[ObsidianCommand]:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    fm, _body = parse_frontmatter(text)
    command = fm.get("aurora_command")
    if not command:
        return None
    params = {k: v for k, v in fm.items() if k != "aurora_command"}
    return ObsidianCommand(command=str(command), params=params, note_path=note_path)


def write_output(note_path: Path, content: str, output_root: Optional[Path] = None) -> Path:
    root = output_root or (note_path.parent / "_outputs")
    root.mkdir(parents=True, exist_ok=True)
    out_path = root / f"{note_path.stem}.output.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


class _NoteHandler(FileSystemEventHandler):
    def __init__(self, vault: Path, on_note):
        super().__init__()
        self.vault = vault
        self.on_note = on_note

    def on_modified(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".md":
            return
        if path.name.endswith(".output.md"):
            return
        if "_outputs" in path.parts:
            return
        self.on_note(path)


class ObsidianWatcher:
    def __init__(self, vault_path: Optional[Path] = None):
        settings = load_settings()
        self.vault_path = vault_path or settings.obsidian_vault_path
        if not self.vault_path:
            raise RuntimeError("OBSIDIAN_VAULT_PATH not set")
        self._observer = Observer()

    def start(self, on_note) -> None:
        handler = _NoteHandler(self.vault_path, on_note)
        self._observer.schedule(handler, str(self.vault_path), recursive=True)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()
