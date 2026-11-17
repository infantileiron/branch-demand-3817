import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient


def _client():
    from src.main import app
    from src.config.database import Base,engine,Session
    from src.models.entities import User
    from src.utils.security import hash_password
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as s:
        for role in ('admin','analyst'):
            s.add(User(email=role+'@demo.local',role=role,password=hash_password('Demo123!')))
        s.commit()
    return TestClient(app)


def test_branch_state_serialises_cross_process_like_conflicts():
    """并发签核的数据库兜底：两个排班覆盖同一网点日期时，第二条因唯一约束失败。"""
    from src.config.database import Session
    from src.models.entities import ApprovedDay,ForecastRun,Staffing
    c=_client()
    with c:
        with Session() as s:
            run=ForecastRun(name='锁定验证',branch='川北',state='done',result={});s.add(run);s.flush()
            one=Staffing(run_id=run.id,branch='川北',capacity=10,model='holt',note='a',schedule=[],status='draft')
            two=Staffing(run_id=run.id,branch='川北',capacity=10,model='holt',note='b',schedule=[],status='draft')
            s.add_all([one,two]);s.flush()
            s.add(ApprovedDay(branch='川北',day='2026-11-18',staffing_id=one.id,actor='a',created='x'));s.commit()
            s.add(ApprovedDay(branch='川北',day='2026-11-18',staffing_id=two.id,actor='b',created='x'))
            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):s.commit()
