import os,json
from fastapi import APIRouter,Depends,HTTPException,Response
from src.config.database import db
from src.models.entities import User,DailyVolume,ForecastRun,Staffing,Audit,AppointmentBatch,Fulfilment,ApprovedDay,BranchState
from src.schemas.business import Login,DailyInput,ForecastInput,StaffingInput,AppointmentInput,CancelInput,RescheduleInput,FulfilInput
from src.middlewares.auth import current,editor,admin
from src.utils.security import verify,token
from src.services.business import audit,dump,branch_lock,branch_state
from src.services.volumes import save_volume,scatter_rows
from src.services import appointments as appts
from src.services.staffing import draft,approve
from src.services import queue
from src.controllers.business import ensure_run
router=APIRouter()


@router.post('/auth/login')
def login(data:Login,s=Depends(db)):
    u=s.query(User).filter_by(email=data.email).first()
    if not u or not verify(data.password,u.password):raise HTTPException(401,'账号或密码错误')
    return {'token':token(u),'user':dump(u)}


@router.get('/me')
def me(u=Depends(current)):return dump(u)


@router.get('/volumes')
def volumes(u=Depends(current),s=Depends(db)):
    fulfil={}
    for f in s.query(Fulfilment).all():fulfil[(f.branch,f.day)]=fulfil.get((f.branch,f.day),0)+f.quantity
    rows=[]
    for r in s.query(DailyVolume).order_by(DailyVolume.day,DailyVolume.branch).all():
        used=fulfil.get((r.branch,r.day),0)
        rows.append({**dump(r),'fulfilled':used,'scatter':r.volume-used})
    return rows


@router.post('/volumes')
def create_volume(data:DailyInput,u=Depends(editor),s=Depends(db)):
    with branch_lock(data.branch):
        r=save_volume(s,data.model_dump(mode='json'),user=u);audit(s,u,'录入日量 '+str(r.id));s.commit();return dump(r)


@router.put('/volumes/{i}')
def edit_volume(i:int,data:DailyInput,u=Depends(editor),s=Depends(db)):
    with branch_lock(data.branch):
        r=save_volume(s,data.model_dump(mode='json'),i,user=u);audit(s,u,'修订日量 '+str(r.id));s.commit();return dump(r)


@router.get('/appointments/basis/{branch}')
def appointment_basis(branch:str,day:str|None=None,u=Depends(current),s=Depends(db)):
    if day is None:
        last=s.query(DailyVolume).filter_by(branch=branch).order_by(DailyVolume.day.desc()).first()
        if not last:raise HTTPException(404,'该网点暂无日结')
        day=last.day
    return appts.appointment_basis(s,branch,day)


@router.get('/appointments')
def appointments(branch:str|None=None,u=Depends(current),s=Depends(db)):return appts.list_batches(s,branch)


@router.get('/appointments/{i}')
def appointment(i:int,u=Depends(current),s=Depends(db)):return appts.detail(s,i)


@router.post('/appointments')
def create_appointment(data:AppointmentInput,u=Depends(editor),s=Depends(db)):
    with branch_lock(data.branch):
        row=appts.create(s,data);audit(s,u,'登记预约批次 '+str(row['id']));s.commit();return row


@router.post('/appointments/{i}/cancel')
def cancel_appointment(i:int,data:CancelInput,u=Depends(editor),s=Depends(db)):
    row=appts.get_batch(s,i)
    with branch_lock(row.branch):
        result=appts.cancel(s,i,data);audit(s,u,'取消预约 '+str(i)+' '+str(data.quantity)+'单');s.commit();return result


@router.post('/appointments/{i}/reschedule')
def reschedule_appointment(i:int,data:RescheduleInput,u=Depends(editor),s=Depends(db)):
    row=appts.get_batch(s,i)
    with branch_lock(row.branch):
        result=appts.reschedule(s,i,data);audit(s,u,'改期预约 '+str(i)+' → '+data.service_day.isoformat());s.commit();return result


@router.post('/appointments/{i}/fulfil')
def fulfil_appointment(i:int,data:FulfilInput,u=Depends(editor),s=Depends(db)):
    row=appts.get_batch(s,i)
    with branch_lock(row.branch):
        result=appts.fulfil(s,i,data);audit(s,u,'登记兑现 批次'+str(i)+' '+str(data.quantity)+'单');s.commit();return result


def _run_view(s,row):
    data=dump(row)
    state=s.get(BranchState,row.branch) if row.branch else None
    current=state.revision if state else 0
    data['current_revision']=current
    data['stale']=(row.revision or 0)<current
    return data


@router.get('/runs')
def runs(u=Depends(current),s=Depends(db)):return [_run_view(s,r) for r in s.query(ForecastRun).order_by(ForecastRun.id.desc()).all()]


@router.post('/runs')
def create_run(data:ForecastInput,u=Depends(editor),s=Depends(db)):
    with branch_lock(data.branch):
        # 先锁网点状态行，再读日结与预约：任何并发变动要么已提交并被本预测看见，要么等本次提交后才递增版本
        revision=branch_state(s,data.branch,lock=True).revision or 0
        rows=scatter_rows(s,data.branch)
        if not rows:raise HTTPException(422,'该网点暂无日结，无法预测')
        basis=appts.appointment_basis(s,data.branch,rows[-1]['day'])
        snapshot={'rows':rows,'appointment_basis':basis}
        r=ForecastRun(**data.model_dump(),revision=revision,result=snapshot,state='queued')
        s.add(r);s.commit()
    try:queue.enqueue(r.id)
    except Exception:
        r.state='failed';r.error='队列暂不可用，请恢复后重试';s.commit();raise HTTPException(503,r.error)
    audit(s,u,'提交预测 '+str(r.id));s.commit();return _run_view(s,r)


@router.get('/runs/{i}')
def run_detail(i:int,u=Depends(current),s=Depends(db)):return _run_view(s,ensure_run(s,i))


@router.get('/runs/{i}/export')
def export(i:int,u=Depends(current),s=Depends(db)):
    r=ensure_run(s,i)
    if r.state!='done':raise HTTPException(409,'仅成功预测可导出')
    return Response(json.dumps(dump(r),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="branch-demand-{i}.json"'})


@router.get('/staffings')
def staffings(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Staffing).order_by(Staffing.id.desc()).all()]


@router.post('/staffings')
def create_staffing(data:StaffingInput,u=Depends(editor),s=Depends(db)):
    run=ensure_run(s,data.run_id)
    with branch_lock(run.branch or ''):
        row=draft(s,run,data)
    audit(s,u,'起草排班 '+str(row.id));s.commit();return dump(row)


@router.post('/staffings/{i}/approve')
def approve_staffing(i:int,u=Depends(admin),s=Depends(db)):
    row=s.get(Staffing,i)
    if not row:raise HTTPException(404,'排班建议不存在')
    with branch_lock(row.branch or ''):
        row=approve(s,row,u)
    audit(s,u,'签核排班 '+str(i));s.commit();return dump(row)


@router.get('/approved-days')
def approved_days(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(ApprovedDay).order_by(ApprovedDay.day).all()]


@router.get('/audits')
def audits(u=Depends(admin),s=Depends(db)):return [dump(r) for r in s.query(Audit).order_by(Audit.id.desc()).limit(100)]
