"""Tests for run_worker max_idle_polls (drain mode)."""

from __future__ import annotations

from unittest.mock import patch

from app.queue.worker import run_worker


def test_run_worker_drains_after_max_idle_polls() -> None:
    """Worker should return after max_idle_polls consecutive empty polls."""
    with patch("app.queue.worker.claim_job", return_value=None) as mock_claim, \
         patch("app.queue.worker.time.sleep") as mock_sleep:
        run_worker("test", {}, idle_sleep=0.1, max_idle_polls=3)

    assert mock_claim.call_count == 3
    assert mock_sleep.call_count == 2  # sleeps on polls 1 and 2, exits on poll 3


def test_run_worker_resets_idle_count_on_job() -> None:
    """Idle count resets to 0 after processing a job."""
    job = {"job_type": "ping", "job_id": "j1"}
    side_effects = [None, None, job, None, None, None]

    with patch("app.queue.worker.claim_job", side_effect=side_effects) as mock_claim, \
         patch("app.queue.worker.time.sleep"), \
         patch("app.queue.worker.mark_done") as mock_done:
        run_worker("test", {"ping": lambda j: None}, idle_sleep=0, max_idle_polls=3)

    # 6 total calls: 2 idle, 1 job, 3 idle (exits on 3rd idle)
    assert mock_claim.call_count == 6
    mock_done.assert_called_once_with("j1")


def test_run_worker_max_idle_zero_exits_immediately() -> None:
    """max_idle_polls=0 should exit on the very first empty poll."""
    with patch("app.queue.worker.claim_job", return_value=None) as mock_claim, \
         patch("app.queue.worker.time.sleep") as mock_sleep:
        run_worker("test", {}, max_idle_polls=0)

    assert mock_claim.call_count == 1
    assert mock_sleep.call_count == 0  # never sleeps, exits immediately
