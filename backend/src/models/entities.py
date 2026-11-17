from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,UniqueConstraint
from src.config.database import Base


class User(Base):
    __tablename__='users'
    id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))


class DailyVolume(Base):
    """网点日结总量。预约到店量已含在这个总量内，散客量=总量-当日各批兑现量。"""
    __tablename__='daily_volumes';__table_args__=(UniqueConstraint('branch','day',name='uq_branch_day'),)
    id=Column(Integer,primary_key=True);branch=Column(String(30),nullable=False);day=Column(String(10),nullable=False);volume=Column(Integer,nullable=False);note=Column(Text,default='')


class BranchState(Base):
    """每个网点一行：revision 随日结/预约变动递增，用于冻结与失效判断；行锁用于串行签核。"""
    __tablename__='branch_states'
    branch=Column(String(30),primary_key=True)
    revision=Column(Integer,nullable=False,default=0)


class AppointmentBatch(Base):
    """网点在一个服务日登记的一批预约。quantity 为当前有效数量（部分改期会调减）。"""
    __tablename__='appointment_batches'
    id=Column(Integer,primary_key=True)
    branch=Column(String(30),nullable=False,index=True)
    service_day=Column(String(10),nullable=False,index=True)
    quantity=Column(Integer,nullable=False)
    cancelled=Column(Integer,nullable=False,default=0)
    fulfilled=Column(Integer,nullable=False,default=0)
    moved_out=Column(Integer,nullable=False,default=0)
    note=Column(Text,default='')
    rescheduled_from=Column(Integer,default=None)
    created=Column(String(40),default='')
    updated=Column(String(40),default='')


class Fulfilment(Base):
    """日结登记的各批兑现量；同一批次同一兑现日只允许一条，重试不会重复计量。"""
    __tablename__='fulfilments';__table_args__=(UniqueConstraint('batch_id','day',name='uq_fulfilment_batch_day'),)
    id=Column(Integer,primary_key=True)
    batch_id=Column(Integer,ForeignKey('appointment_batches.id'),nullable=False,index=True)
    branch=Column(String(30),nullable=False,index=True)
    day=Column(String(10),nullable=False,index=True)
    quantity=Column(Integer,nullable=False)
    note=Column(Text,default='')
    created=Column(String(40),default='')


class AppointmentOp(Base):
    """带 request_id 的预约写操作回执，重试直接返回原结果，不重复增减。"""
    __tablename__='appointment_ops'
    id=Column(Integer,primary_key=True)
    request_id=Column(String(80),unique=True,nullable=False)
    branch=Column(String(30),nullable=False)
    kind=Column(String(20),nullable=False)
    result=Column(JSON)
    created=Column(String(40),default='')


class ApprovedDay(Base):
    """已签核排班覆盖的网点日期；唯一约束保证并发签核只有一方成功。"""
    __tablename__='approved_days';__table_args__=(UniqueConstraint('branch','day',name='uq_approved_branch_day'),)
    id=Column(Integer,primary_key=True)
    branch=Column(String(30),nullable=False)
    day=Column(String(10),nullable=False)
    staffing_id=Column(Integer,ForeignKey('staffings.id'),nullable=False)
    actor=Column(String(100),default='')
    created=Column(String(40),default='')


class ForecastRun(Base):
    __tablename__='forecast_runs'
    id=Column(Integer,primary_key=True);name=Column(String(100));branch=Column(String(30));revision=Column(Integer,default=0)
    backtest_days=Column(Integer);alpha=Column(Float);beta=Column(Float);state=Column(String(20),default='queued');result=Column(JSON);error=Column(Text,default='')


class Staffing(Base):
    __tablename__='staffings'
    id=Column(Integer,primary_key=True);run_id=Column(Integer,ForeignKey('forecast_runs.id'));branch=Column(String(30));revision=Column(Integer,default=0)
    capacity=Column(Integer);model=Column(String(30));schedule=Column(JSON);note=Column(Text);status=Column(String(20),default='draft')
    basis=Column(JSON)
    approved_by=Column(String(100),default='')
    approved_at=Column(String(40),default='')
    invalid_reason=Column(Text,default='')


class Audit(Base):
    __tablename__='audits'
    id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
