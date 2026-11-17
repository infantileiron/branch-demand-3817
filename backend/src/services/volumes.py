from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models.entities import DailyVolume,Fulfilment
from src.services.business import bump


def fulfilled_total(s,branch,day):
    return sum(r.quantity for r in s.query(Fulfilment).filter_by(branch=branch,day=day).all())


def check_daily_total(s,branch,day,volume):
    used=fulfilled_total(s,branch,day)
    if used>volume:
        raise HTTPException(422,f'{day} 已登记兑现 {used} 单，日结总量不能低于该值（预约已含在日结中）')


def save_volume(s,data,id=None,user=None):
    row=s.get(DailyVolume,id) if id else DailyVolume()
    if not row:raise HTTPException(404,'日量不存在')
    check_daily_total(s,data['branch'],data['day'],data['volume'])
    for k,v in data.items():setattr(row,k,v)
    s.add(row)
    try:s.flush()
    except IntegrityError:
        s.rollback();raise HTTPException(409,'该网点日期已有日量，请修订原记录')
    bump(s,data['branch'])
    s.commit()
    return row


def scatter_rows(s,branch):
    """散客日量 = 日结总量 - 当日各批兑现量；预约已经包含在日结中，不能再重复叠加。"""
    fulfil={}
    for r in s.query(Fulfilment).filter_by(branch=branch).all():
        fulfil[r.day]=fulfil.get(r.day,0)+r.quantity
    rows=[]
    for r in s.query(DailyVolume).filter_by(branch=branch).order_by(DailyVolume.day).all():
        used=fulfil.get(r.day,0);scatter=r.volume-used
        if scatter<0:raise HTTPException(409,f'{r.day} 兑现量超过日结总量，请先核对')
        rows.append({'branch':r.branch,'day':r.day,'volume':scatter,'daily_total':r.volume,'fulfilled':used})
    return rows
