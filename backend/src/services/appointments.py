from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.models.entities import AppointmentBatch,Fulfilment,AppointmentOp,DailyVolume,Staffing
from src.services.business import bump,now,require_not_approved,dump


def remaining(row):
    """未兑现、未取消、未改期走的有效预约量。兑现部分不因取消回减。"""
    return max(0,(row.quantity or 0)-(row.cancelled or 0)-(row.fulfilled or 0)-(row.moved_out or 0))


def status(row):
    left=remaining(row)
    if left>0:return 'open'
    if (row.fulfilled or 0)>0:return 'fulfilled'
    if (row.cancelled or 0)>0:return 'cancelled'
    if (row.moved_out or 0)>0:return 'rescheduled'
    return 'open'


def view(row):
    return {**dump(row),'remaining':remaining(row),'status':status(row)}


def get_batch(s,i):
    row=s.get(AppointmentBatch,i)
    if not row:raise HTTPException(404,'预约批次不存在')
    return row


def replay(s,request_id,kind=None,branch=None):
    if not request_id:return None
    op=s.query(AppointmentOp).filter_by(request_id=request_id).first()
    if not op:return None
    if kind and op.kind!=kind:raise HTTPException(409,'请求编号已用于其他操作，请换一个编号')
    if branch and op.branch!=branch:raise HTTPException(409,'请求编号属于其他网点，请换一个编号')
    return op.result


def record_op(s,request_id,branch,kind,result):
    if not request_id:return
    s.add(AppointmentOp(request_id=request_id,branch=branch,kind=kind,result=result,created=now()))


def _commit_with_replay(s,request_id,branch,kind,result):
    """提交包括幂等回执；并发同号请求撞唯一约束时回滚并返回已存回执。"""
    record_op(s,request_id,branch,kind,result)
    try:s.commit()
    except IntegrityError:
        s.rollback()
        existing=replay(s,request_id,kind,branch)
        if existing is not None:return existing
        raise HTTPException(409,'请求与已有记录冲突，请刷新后重试')
    return result


def create(s,data):
    branch=data.branch;day=data.service_day.isoformat();qty=data.quantity
    prior=replay(s,data.request_id,'create',branch)
    if prior is not None:return prior
    require_not_approved(s,branch,day,'新增预约')
    row=AppointmentBatch(branch=branch,service_day=day,quantity=qty,note=data.note,created=now(),updated=now())
    s.add(row);s.flush()
    result=view(row)
    bump(s,branch)
    return _commit_with_replay(s,data.request_id,branch,'create',result)


def cancel(s,i,data):
    row=get_batch(s,i)
    prior=replay(s,data.request_id,'cancel',row.branch)
    if prior is not None:return prior
    require_not_approved(s,row.branch,row.service_day,'取消预约')
    left=remaining(row)
    if data.quantity>left:raise HTTPException(422,f'最多可取消未兑现的 {left} 单，已兑现部分不随取消回减')
    row.cancelled=(row.cancelled or 0)+data.quantity
    if data.note:row.note=((row.note or '')+' | 取消：'+data.note).strip(' |')
    row.updated=now();s.flush()
    result=view(row)
    bump(s,row.branch)
    return _commit_with_replay(s,data.request_id,row.branch,'cancel',result)


def reschedule(s,i,data):
    row=get_batch(s,i)
    prior=replay(s,data.request_id,'reschedule',row.branch)
    if prior is not None:return prior
    target=data.service_day.isoformat();source_day=row.service_day
    if target==source_day:raise HTTPException(422,'改期目标日不能与原服务日相同')
    left=remaining(row)
    if left<=0:raise HTTPException(409,'该批次已无可改期的预约')
    qty=data.quantity if data.quantity is not None else left
    if qty>left:raise HTTPException(422,f'最多可改期未兑现的 {left} 单')
    # 先完成全部校验，再动原批次；任何失败都不改变原批次
    require_not_approved(s,row.branch,source_day,'改期')
    require_not_approved(s,row.branch,target,'改期')
    row.moved_out=(row.moved_out or 0)+qty
    if data.note:row.note=((row.note or '')+' | 改期：'+data.note).strip(' |')
    row.updated=now()
    moved=AppointmentBatch(branch=row.branch,service_day=target,quantity=qty,note=data.note or ('由批次 %s 改期'%row.id),rescheduled_from=row.id,created=now(),updated=now())
    s.add(moved);s.flush()
    result={'source':view(row),'target':view(moved)}
    bump(s,row.branch)
    return _commit_with_replay(s,data.request_id,row.branch,'reschedule',result)


def fulfil(s,i,data):
    row=get_batch(s,i)
    prior=replay(s,data.request_id,'fulfil',row.branch)
    if prior is not None:return prior
    day=data.day.isoformat()
    if day!=row.service_day:raise HTTPException(422,'兑现日必须等于预约服务日，便于与当日日结对账')
    daily=s.query(DailyVolume).filter_by(branch=row.branch,day=day).first()
    if not daily:raise HTTPException(422,'请先登记该日网点日结，再登记兑现量')
    left=remaining(row)
    if data.quantity>left:raise HTTPException(422,f'超额兑现：该批仅剩未兑现 {left} 单')
    used=sum(f.quantity for f in s.query(Fulfilment).filter_by(branch=row.branch,day=day).all())
    if used+data.quantity>daily.volume:
        raise HTTPException(422,f'超额兑现：{day} 日结总量 {daily.volume} 单，已登记兑现 {used} 单，最多还能登记 {daily.volume-used} 单')
    existing=s.query(Fulfilment).filter_by(batch_id=row.id,day=day).first()
    if existing:raise HTTPException(409,'该批次该服务日已登记兑现，重试不会重复计量；如需修订请核对原记录')
    entry=Fulfilment(batch_id=row.id,branch=row.branch,day=day,quantity=data.quantity,note=data.note,created=now())
    s.add(entry)
    row.fulfilled=(row.fulfilled or 0)+data.quantity
    row.updated=now();s.flush()
    result={'batch':view(row),'fulfilment':dump(entry)}
    bump(s,row.branch)
    return _commit_with_replay(s,data.request_id,row.branch,'fulfil',result)


def list_batches(s,branch=None):
    q=s.query(AppointmentBatch)
    if branch:q=q.filter_by(branch=branch)
    return [view(r) for r in q.order_by(AppointmentBatch.service_day,AppointmentBatch.id).all()]


def detail(s,i):
    row=get_batch(s,i)
    return {**view(row),'fulfilments':[dump(f) for f in s.query(Fulfilment).filter_by(batch_id=row.id).order_by(Fulfilment.id).all()]}


def appointment_basis(s,branch,last_day,horizon=7):
    """提交预测时冻结的预约依据：未来7日逐日未兑现预约，以及窗口外与历史未到店部分。"""
    from datetime import date,timedelta
    start=date.fromisoformat(last_day)+timedelta(days=1);window=[(start+timedelta(days=i)).isoformat() for i in range(horizon)]
    by_day={d:[] for d in window};outside=[];past={'quantity':0,'batches':0}
    for row in s.query(AppointmentBatch).filter_by(branch=branch).order_by(AppointmentBatch.service_day,AppointmentBatch.id).all():
        left=remaining(row)
        if left<=0:continue
        item={'batch_id':row.id,'service_day':row.service_day,'quantity':row.quantity,'remaining':left}
        if row.service_day in by_day:by_day[row.service_day].append(item)
        elif row.service_day>window[-1]:outside.append(item)
        else:past['quantity']+=left;past['batches']+=1
    return {'branch':branch,'as_of':last_day,'window':window,
            'reserved_by_day':{d:sum(x['remaining'] for x in items) for d,items in by_day.items()},
            'by_day':by_day,'beyond_window':outside,'past_unfulfilled':past}
