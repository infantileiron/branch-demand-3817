from datetime import datetime,timezone
from threading import RLock
from fastapi import HTTPException
from src.models.entities import Audit,BranchState,Staffing

_LOCKS={}
_LOCKS_GUARD=RLock()


def audit(s,u,action):
    s.add(Audit(actor=u.email,action=action,created=now()))


def now():
    return datetime.now(timezone.utc).isoformat()


def dump(obj):
    return {c.name:getattr(obj,c.name) for c in obj.__table__.columns if c.name!='password'}


def branch_lock(branch):
    """同一进程内按网点串行化写操作；数据库唯一约束与行锁兜底多进程。"""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(branch,RLock())


def branch_state(s,branch,lock=False):
    state=s.get(BranchState,branch)
    if not state:
        try:
            with s.begin_nested():
                state=BranchState(branch=branch,revision=0);s.add(state);s.flush()
        except Exception:
            state=s.get(BranchState,branch)
            if not state:raise
    if lock and state is not None:
        try:s.refresh(state,with_for_update=True)
        except Exception:pass
    return state


def bump(s,branch):
    """任何日结/预约变动递增依据版本，并让草稿排班失效。加行锁保证跨进程也不丢计数。"""
    state=branch_state(s,branch,lock=True)
    state.revision=(state.revision or 0)+1
    invalidate_drafts(s,branch,state.revision)
    return state.revision


def invalidate_drafts(s,branch,revision):
    for row in s.query(Staffing).filter_by(branch=branch,status='draft').all():
        if (row.revision or 0)<revision:
            row.status='invalid'
            row.invalid_reason='预约或日结依据已变动，需要按新依据重算排班'


def require_not_approved(s,branch,day,action='变动'):
    from src.models.entities import ApprovedDay
    if s.query(ApprovedDay).filter_by(branch=branch,day=day).first():
        raise HTTPException(409,f'{day} 已签核排班，禁止{action}')
