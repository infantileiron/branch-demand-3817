import os,sys,tempfile
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


@pytest.fixture(scope='session',autouse=True)
def env(tmp_path_factory):
    db=str(tmp_path_factory.mktemp('db')/'test.db')
    os.environ['DATABASE_URL']='sqlite:///'+db
    os.environ['JWT_SECRET']='test-secret-3109'
    os.environ['REDIS_URL']='redis://127.0.0.1:6399/0'
    os.environ['SEED_DEMO']='false'
    yield


@pytest.fixture(autouse=True)
def fake_queue(monkeypatch):
    """测试不依赖 Redis：入队写入内存列表，runner 直接消费。"""
    pending=[]
    from src.services import queue
    monkeypatch.setattr(queue,'enqueue',lambda run_id:pending.append(int(run_id)))
    monkeypatch.setattr(queue,'take',lambda timeout=0:pending.pop(0) if pending else None)
    yield pending
