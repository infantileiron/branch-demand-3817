import random
from datetime import date,timedelta
from src.config.database import Base,engine,Session
from src.models.entities import User,DailyVolume,AppointmentBatch,Fulfilment,BranchState
from src.constants.enums import BRANCHES
from src.utils.security import hash_password


def _appointment_demo(s):
    """演示预约批次：含部分取消、已兑现、未来未兑现与跨日改期来源。重复执行不新增。"""
    if s.query(AppointmentBatch).count():return
    demo=[
        dict(branch='川北',day='2026-11-13',qty=20,cancelled=0,fulfilled=8,moved=0,note='日结内已兑现8单，剩余12单仍在待兑现'),
        dict(branch='川北',day='2026-11-16',qty=14,cancelled=4,fulfilled=0,moved=0,note='部分取消4单，剩余10单'),
        dict(branch='川北',day='2026-11-18',qty=16,cancelled=0,fulfilled=0,moved=0,note='下周服务日预约'),
        dict(branch='川北',day='2026-11-19',qty=9,cancelled=0,fulfilled=0,moved=0,note='下周服务日预约'),
        dict(branch='川南',day='2026-11-18',qty=12,cancelled=0,fulfilled=0,moved=0,note='下周服务日预约'),
        dict(branch='川南',day='2026-11-20',qty=7,cancelled=0,fulfilled=0,moved=0,note='下周服务日预约'),
        dict(branch='东河',day='2026-11-17',qty=10,cancelled=0,fulfilled=0,moved=0,note='下周服务日预约'),
    ]
    for item in demo:
        row=AppointmentBatch(branch=item['branch'],service_day=item['day'],quantity=item['qty'],
            cancelled=item['cancelled'],fulfilled=item['fulfilled'],moved_out=item['moved'],note=item['note'],
            created='2026-11-14T09:00:00+00:00',updated='2026-11-14T09:00:00+00:00')
        s.add(row);s.flush()
        if item['fulfilled']:
            s.add(Fulfilment(batch_id=row.id,branch=item['branch'],day=item['day'],quantity=item['fulfilled'],
                note='日结登记兑现',created='2026-11-14T09:00:00+00:00'))
    for branch in {item['branch'] for item in demo}:
        state=s.get(BranchState,branch) or BranchState(branch=branch,revision=0)
        state.revision=(state.revision or 0)+1;s.add(state)


def seed():
    Base.metadata.create_all(engine);rng=random.Random(3109)
    with Session() as s:
        for role in ('admin','analyst','viewer'):
            email=role+'@demo.local'
            if not s.query(User).filter_by(email=email).first():s.add(User(email=email,role=role,password=hash_password('Demo123!')))
        for b,branch in enumerate(BRANCHES):
            for i in range(70):
                day=(date(2026,9,6)+timedelta(days=i)).isoformat();weekday=date.fromisoformat(day).weekday();volume=max(0,round(24+b*4+i*.12+(10 if weekday<5 else -8)+rng.gauss(0,3)))
                if not s.query(DailyVolume).filter_by(branch=branch,day=day).first():s.add(DailyVolume(branch=branch,day=day,volume=volume,note='栖川网点日结工单到达量'))
        _appointment_demo(s)
        s.commit()
        print({'users':s.query(User).count(),'volumes':s.query(DailyVolume).count(),'appointments':s.query(AppointmentBatch).count()})


if __name__=='__main__':seed()
