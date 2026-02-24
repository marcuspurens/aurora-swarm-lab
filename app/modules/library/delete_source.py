"""Delete a source and all its associated data."""

from __future__ import annotations

import shutil

from app.core.ids import safe_source_id
from app.core.storage import artifact_root
from app.queue.db import get_conn


def delete_source(source_id: str) -> dict[str, int | bool]:
    """Delete all data for a given source_id and return counts of deleted items."""
    with get_conn() as conn:
        cur = conn.cursor()
        ph = "?" if conn.is_sqlite else "%s"

        # Count and delete embeddings
        cur.execute(f"SELECT COUNT(*) FROM embeddings WHERE source_id = {ph}", (source_id,))
        embeddings_deleted: int = cur.fetchone()[0]
        cur.execute(f"DELETE FROM embeddings WHERE source_id = {ph}", (source_id,))

        # Count and delete jobs
        cur.execute(f"SELECT COUNT(*) FROM jobs WHERE source_id = {ph}", (source_id,))
        jobs_deleted: int = cur.fetchone()[0]
        cur.execute(f"DELETE FROM jobs WHERE source_id = {ph}", (source_id,))

        # Count and delete manifests
        cur.execute(f"SELECT COUNT(*) FROM manifests WHERE source_id = {ph}", (source_id,))
        manifests_deleted: int = cur.fetchone()[0]
        cur.execute(f"DELETE FROM manifests WHERE source_id = {ph}", (source_id,))

        conn.commit()

    # Remove artifact directory
    art_path = artifact_root() / safe_source_id(source_id)
    artifacts_removed = art_path.exists()
    shutil.rmtree(art_path, ignore_errors=True)

    return {
        "embeddings_deleted": embeddings_deleted,
        "jobs_deleted": jobs_deleted,
        "manifests_deleted": manifests_deleted,
        "artifacts_removed": artifacts_removed,
    }
