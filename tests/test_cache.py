"""Tests for the incremental-build cache predicate (NTH-001)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from rst_to_md.core import is_up_to_date


def test_missing_target_not_up_to_date(tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    tgt = tmp_path / "b.txt"  # never created
    assert is_up_to_date(src, tgt) is False


def test_newer_target_up_to_date(tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    tgt = tmp_path / "b.txt"
    tgt.write_text("y", encoding="utf-8")
    time.sleep(0.01)
    tgt.write_text("y2", encoding="utf-8")  # bump mtime
    assert is_up_to_date(src, tgt) is True


def test_older_target_not_up_to_date(tmp_path: Path):
    tgt = tmp_path / "b.txt"
    tgt.write_text("y", encoding="utf-8")
    time.sleep(0.01)
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    assert is_up_to_date(src, tgt) is False


def test_equal_mtime_up_to_date(tmp_path: Path):
    src = tmp_path / "a.txt"
    src.write_text("x", encoding="utf-8")
    tgt = tmp_path / "b.txt"
    tgt.write_text("y", encoding="utf-8")
    # Force identical mtimes so the check is deterministic.
    mtime = src.stat().st_mtime
    os.utime(tgt, (mtime, mtime))
    assert is_up_to_date(src, tgt) is True
