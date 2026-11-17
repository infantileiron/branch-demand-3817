import math
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from src.models.entities import Staffing,ApprovedDay,ForecastRun
from src.services.business import branch_state,now


def schedule_from(run,model,capacity):
    """合计需求（散客预测+未兑现预约）换算人数；逐日保留分量便于追溯。"""
    out=[]
    for p in run.result['future'][model]:
        total=p.get('total',p['prediction'])
        out.append({'day':p['day'],'prediction':p['prediction'],'scatter':p.get('prediction',0),
                    'reserved':p.get('reserved',0),'total':total,'staff':math.ceil(total/capacity)})
    return out


def draft(s,run,data):
    if run.state!='done':raise HTTPException(409,'预测完成后才能生成排班建议')
    if not run.branch:raise HTTPException(409,'预测缺少网点信息')
    state=branch_state(s,run.branch,lock=True)
    revision=state.revision or 0
    if (run.revision or 0)!=revision:
        raise HTTPException(409,'预约或日结依据已变动，请按最新依据重新提交预测')
    schedule=schedule_from(run,data.model,data.capacity)
    days=[x['day'] for x in schedule]
    taken=[d for (d,) in s.query(ApprovedDay.day).filter(ApprovedDay.branch==run.branch,ApprovedDay.day.in_(days)).all()]
    if taken:raise HTTPException(409,'以下日期已签核排班，不能再起草：'+', '.join(sorted(taken)))
    basis={'run_id':run.id,'run_revision':run.revision,'branch_revision':revision,'checksum':run.result.get('checksum'),
           'appointment_basis':run.result.get('appointment_basis'),'model':data.model,'capacity':data.capacity,
           'daily':[{'day':x['day'],'scatter':x['scatter'],'reserved':x['reserved'],'total':x['total'],'staff':x['staff']} for x in schedule]}
    row=Staffing(**data.model_dump(),branch=run.branch,revision=revision,schedule=schedule,basis=basis,status='draft')
    s.add(row);s.commit();return row


def approve(s,row,user):
    if row.status=='approved':raise HTTPException(409,'不可重复签核')
    if row.status=='invalid':raise HTTPException(409,row.invalid_reason or '依据已变动，请重算后再签核')
    state=branch_state(s,row.branch,lock=True)
    revision=state.revision or 0
    run=s.get(ForecastRun,row.run_id)
    if (row.revision or 0)!=revision or not run or (run.revision or 0)!=revision or run.state!='done':
        row.status='invalid';row.invalid_reason='预测依据已被预约或日结变动取代，请重新预测后签核';s.commit()
        raise HTTPException(409,row.invalid_reason)
    try:
        for item in row.schedule:
            s.add(ApprovedDay(branch=row.branch,day=item['day'],staffing_id=row.id,actor=user.email,created=now()))
        row.status='approved';row.approved_by=user.email;row.approved_at=now()
        s.commit()
    except IntegrityError:
        s.rollback()
        row=s.get(Staffing,row.id);row.status='invalid';row.invalid_reason='该网点日期已被其他签核覆盖';s.commit()
        raise HTTPException(409,'该网点部分日期已被其他排班签核，不能重复签核')
    return row
