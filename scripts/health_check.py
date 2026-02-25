#!/usr/bin/env python3
"""Aurora health check — writes data/health.json with system status."""

import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check_components() -> dict[str, dict]:
    """Check availability of each required component."""
    components: dict[str, dict] = {}

    # sqlite3 (stdlib)
    try:
        import sqlite3 as _sq  # noqa: F401
        components["sqlite3"] = {"ok": True}
    except ImportError:
        components["sqlite3"] = {"ok": False, "reason": "not installed"}

    # ollama + snowflake-arctic-embed model
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and "snowflake-arctic-embed" in result.stdout:
            components["ollama"] = {
                "ok": True,
                "model": "snowflake-arctic-embed:latest",
            }
        elif result.returncode == 0:
            components["ollama"] = {
                "ok": False,
                "reason": "snowflake-arctic-embed model not found",
            }
        else:
            components["ollama"] = {"ok": False, "reason": result.stderr.strip() or "non-zero exit"}
    except FileNotFoundError:
        components["ollama"] = {"ok": False, "reason": "ollama not found on PATH"}
    except subprocess.TimeoutExpired:
        components["ollama"] = {"ok": False, "reason": "ollama list timed out"}
    except Exception as exc:
        components["ollama"] = {"ok": False, "reason": str(exc)}

    # faster_whisper
    try:
        import faster_whisper  # noqa: F401
        components["faster_whisper"] = {"ok": True}
    except ImportError:
        components["faster_whisper"] = {"ok": False, "reason": "not installed"}

    # paddleocr
    try:
        import paddleocr  # noqa: F401
        components["paddleocr"] = {"ok": True}
    except ImportError:
        components["paddleocr"] = {"ok": False, "reason": "not installed"}

    # yt_dlp
    try:
        import yt_dlp  # noqa: F401
        components["yt_dlp"] = {"ok": True}
    except ImportError:
        components["yt_dlp"] = {"ok": False, "reason": "not installed"}

    # playwright
    try:
        import playwright  # noqa: F401
        components["playwright"] = {"ok": True}
    except ImportError:
        components["playwright"] = {"ok": False, "reason": "not installed"}

    return components


def run_tests() -> dict:
    """Run the pytest suite and return pass/fail counts."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "--ignore=tests/test_health_check.py"],
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(PROJECT_ROOT),
        )
        stdout = result.stdout
        # Match patterns like "204 passed", "3 failed, 201 passed", "204 passed, 1 warning"
        passed_m = re.search(r"(\d+) passed", stdout)
        failed_m = re.search(r"(\d+) failed", stdout)
        passed = int(passed_m.group(1)) if passed_m else 0
        failed = int(failed_m.group(1)) if failed_m else 0
        return {"passed": passed, "failed": failed, "total": passed + failed}
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 0, "total": 0, "error": "pytest timed out"}
    except Exception as exc:
        return {"passed": 0, "failed": 0, "total": 0, "error": str(exc)}


def get_data_dir_stats() -> dict:
    """Count rows in manifests and embeddings tables."""
    db_path = PROJECT_ROOT / "data" / "aurora_queue.db"
    stats: dict = {"manifests_count": 0, "embeddings_count": 0}
    if not db_path.exists():
        return stats
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM manifests")
            stats["manifests_count"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass
        try:
            cur.execute("SELECT COUNT(*) FROM embeddings")
            stats["embeddings_count"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass
        conn.close()
    except Exception:
        pass
    return stats


def determine_status(tests: dict) -> str:
    """Derive overall status from test results."""
    if "error" in tests:
        return "error"
    if tests["failed"] == 0 and tests["passed"] > 0:
        return "ok"
    if tests["passed"] > 0 and tests["failed"] > 0:
        return "degraded"
    return "error"


def main() -> None:
    """Run all checks and write data/health.json."""
    components = check_components()
    tests = run_tests()
    data_dir = get_data_dir_stats()
    status = determine_status(tests)

    health = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "tests": tests,
        "components": components,
        "data_dir": data_dir,
    }

    out_dir = PROJECT_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "health.json"
    out_path.write_text(json.dumps(health, indent=2) + "\n")

    total = tests.get("total", 0)
    passed = tests.get("passed", 0)
    print(f"Health check complete: status={status}, tests={passed}/{total}")


if __name__ == "__main__":
    main()
