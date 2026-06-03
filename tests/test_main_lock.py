"""main.py のロック機構テスト（多重起動防止・stale奪取・解放）。

orchestration 全体は実サイトが必要なため、ここでは純粋なロックロジックを検証する。
"""

import logging
import os
import time
from pathlib import Path

import pytest

from src.main import acquire_lock, release_lock
from src.models import LockError

_LOG = logging.getLogger("test")


def test_acquire_creates_lock_file(tmp_path):
    lock = str(tmp_path / "data" / ".lock")
    acquire_lock(lock, stale_minutes=60, logger=_LOG)
    assert Path(lock).exists()
    release_lock(lock)
    assert not Path(lock).exists()


def test_second_acquire_raises_when_fresh(tmp_path):
    lock = str(tmp_path / ".lock")
    acquire_lock(lock, stale_minutes=60, logger=_LOG)
    with pytest.raises(LockError):
        acquire_lock(lock, stale_minutes=60, logger=_LOG)
    release_lock(lock)


def test_stale_lock_is_taken_over(tmp_path):
    lock = Path(tmp_path / ".lock")
    lock.write_text("9999 old", encoding="utf-8")
    # mtime を2時間前に設定 → stale_minutes=60 で奪取される
    old = time.time() - 2 * 3600
    os.utime(lock, (old, old))
    acquire_lock(str(lock), stale_minutes=60, logger=_LOG)
    # 自プロセスのロックに置き換わっている
    assert str(os.getpid()) in lock.read_text(encoding="utf-8")
    release_lock(str(lock))


def test_release_is_idempotent(tmp_path):
    lock = str(tmp_path / ".lock")
    # 存在しなくても例外を投げない
    release_lock(lock)
    acquire_lock(lock, stale_minutes=60, logger=_LOG)
    release_lock(lock)
    release_lock(lock)
