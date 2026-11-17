import sys,json
from datetime import date,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from fastapi.testclient import TestClient


def _prepare(client,admin):
    pass


@pytest.fixture()
def app_client():
    from src.main import app
    from src.config.database import Base,engine,Session
    from src.models.entities import User,DailyVolume,AppointmentBatch,BranchState
    from src.utils.security import hash_password
    Base.metadata.drop_all(engine);Base.metadata.create_all(engine)
    with Session() as s:
        for role in ('admin','analyst','viewer'):
            s.add(User(email=role+'@demo.local',role=role,password=hash_password('Demo123!')))
        for day in range(72):
            d=(date(2026,9,6)+timedelta(days=day)).isoformat()
            s.add(DailyVolume(branch='川北',day=d,volume=40+day%3,note='夹具'))
        s.commit()
    with TestClient(app) as c:
        yield c


def login(c,role):
    r=c.post('/auth/login',json={'email':f'{role}@demo.local','password':'Demo123!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}


def add_reserved(c,headers,branch='川北',days=(1,3),quantity=5,tag='r'):
    from datetime import date,timedelta
    last=max(v['day'] for v in c.get('/volumes',headers=headers).json() if v['branch']==branch)
    ids=[]
    for offset in days:
        d=(date.fromisoformat(last)+timedelta(days=offset)).isoformat()
        r=c.post('/appointments',json={'branch':branch,'service_day':d,'quantity':quantity,'request_id':f'{tag}-{offset}'},headers=headers)
        assert r.status_code==200,r.text
        ids.append((r.json()['id'],d))
    return ids


def run_job(c,headers,backtest_days=14,tag=None):
    """直接调用 runner 处理队列（无 Redis 环境下驱动真实计算路径）。"""
    from src.services.runner import process
    r=c.post('/runs',json={'name':'测试预测','branch':'川北','backtest_days':backtest_days,'alpha':.6,'beta':.2},headers=headers)
    assert r.status_code==200,r.text
    run_id=r.json()['id'];process(run_id)
    return c.get(f'/runs/{run_id}',headers=headers).json()


def test_roles_enforced(app_client):
    c=app_client;viewer=login(c,'viewer');analyst=login(c,'analyst')
    assert c.post('/appointments',json={'branch':'川北','service_day':'2026-11-18','quantity':5},headers=viewer).status_code==403
    assert c.post('/runs',json={'name':'x1','branch':'川北'},headers=viewer).status_code==403
    assert c.post('/runs',json={'name':'x2','branch':'川北'},headers=analyst).status_code==200


def test_partial_cancel_and_fulfil_rules(app_client):
    c=app_client;h=login(c,'analyst')
    created=c.post('/appointments',json={'branch':'川北','service_day':'2026-11-15','quantity':20,'request_id':'t-cancel-1'},headers=h).json()
    bid=created['id']
    # 超额兑现被拒
    assert c.post(f'/appointments/{bid}/fulfil',json={'day':'2026-11-15','quantity':25},headers=h).status_code==422
    ok=c.post(f'/appointments/{bid}/fulfil',json={'day':'2026-11-15','quantity':6,'request_id':'t-fulfil-1'},headers=h)
    assert ok.status_code==200,ok.text
    # 部分取消：只能取消未兑现的 14 单
    over=c.post(f'/appointments/{bid}/cancel',json={'quantity':15},headers=h)
    assert over.status_code==422 and '已兑现部分' in over.json()['detail']
    part=c.post(f'/appointments/{bid}/cancel',json={'quantity':10,'request_id':'t-cancel-2'},headers=h)
    assert part.status_code==200,part.text
    body=part.json()
    assert body['cancelled']==10 and body['fulfilled']==6 and body['remaining']==4
    # 重试同一 request_id 不重复计量
    again=c.post(f'/appointments/{bid}/cancel',json={'quantity':10,'request_id':'t-cancel-2'},headers=h)
    assert again.status_code==200 and again.json()['cancelled']==10
    # 重复兑现被拒
    dup=c.post(f'/appointments/{bid}/fulfil',json={'day':'2026-11-15','quantity':1},headers=h)
    assert dup.status_code==409
    detail=c.get(f'/appointments/{bid}',headers=h).json()
    assert len(detail['fulfilments'])==1


def test_cross_day_reschedule_adjusts_both_days(app_client):
    c=app_client;h=login(c,'analyst')
    created=c.post('/appointments',json={'branch':'川北','service_day':'2026-11-16','quantity':8,'request_id':'t-resched-0'},headers=h).json()
    bid=created['id']
    before=c.get('/appointments/basis/川北',params={'day':'2026-11-14'},headers=h).json()
    moved=c.post(f'/appointments/{bid}/reschedule',json={'service_day':'2026-11-18','quantity':3,'request_id':'t-resched-1'},headers=h)
    assert moved.status_code==200,moved.text
    body=moved.json()
    assert body['source']['remaining']==5 and body['source']['moved_out']==3
    assert body['target']['service_day']=='2026-11-18' and body['target']['remaining']==3
    after=c.get('/appointments/basis/川北',params={'day':'2026-11-14'},headers=h).json()
    # 源日减少 3、目标日增加 3，同日生效
    assert after['reserved_by_day']['2026-11-18']-before['reserved_by_day']['2026-11-18']==3
    assert after['reserved_by_day']['2026-11-16']-before['reserved_by_day']['2026-11-16']==-3
    # 同一 request_id 幂等
    retry=c.post(f'/appointments/{bid}/reschedule',json={'service_day':'2026-11-18','quantity':3,'request_id':'t-resched-1'},headers=h)
    assert retry.status_code==200 and retry.json()['target']['quantity']==3
    basis=c.get('/appointments/basis/川北',params={'day':'2026-11-14'},headers=h).json()
    assert basis['reserved_by_day']['2026-11-18']==after['reserved_by_day']['2026-11-18']


def test_forecast_uses_scatter_and_adds_reserved(app_client):
    c=app_client;h=login(c,'analyst')
    add_reserved(c,h,days=(1,3),quantity=7,tag='scatter')
    run=run_job(c,h)
    assert run['state']=='done',run.get('error')
    result=run['result']
    # 散客日量 = 日结 - 兑现
    history={r['day']:r for r in result['history']}
    vols={r['day']:r for r in c.get('/volumes',headers=h).json() if r['branch']=='川北'}
    day='2026-11-15'
    assert history[day]['volume']==vols[day]['volume']-vols[day]['fulfilled']
    # 回测只基于散客量
    assert all(set(d)>= {'day','actual','holt','seasonal_naive'} for d in result['backtest'])
    reserved={d['day']:d['reserved'] for d in result['future']['holt']}
    assert sorted(v for v in reserved.values() if v)==[7,7]
    for item in result['future']['holt']:
        assert item['total']==item['prediction']+item['reserved']
    assert result['appointment_basis']['branch']=='川北'


def test_staffing_invalidated_by_appointment_change_and_approve_blocks_edits(app_client):
    c=app_client;admin=login(c,'admin');analyst=login(c,'analyst')
    run=run_job(c,analyst)
    staff=c.post('/staffings',json={'run_id':run['id'],'capacity':12,'model':'holt','note':'现场休息与技能已核对，先出草案'},headers=analyst)
    assert staff.status_code==200,staff.text
    sid=staff.json()['id']
    # 预约变动使草稿依据失效
    c.post('/appointments',json={'branch':'川北','service_day':'2026-11-21','quantity':4,'request_id':'t-invalidate'},headers=analyst)
    stale=c.get('/staffings',headers=analyst).json()
    assert [s for s in stale if s['id']==sid][0]['status']=='invalid'
    assert c.post(f'/staffings/{sid}/approve',json={},headers=admin).status_code==409
    # 用变动后的依据重新预测再签核
    run2=run_job(c,analyst)
    staff2=c.post('/staffings',json={'run_id':run2['id'],'capacity':12,'model':'holt','note':'按最新预约依据重算，准备签核'},headers=analyst).json()
    ok=c.post(f"/staffings/{staff2['id']}/approve",json={},headers=admin)
    assert ok.status_code==200,ok.text
    assert ok.json()['status']=='approved'
    assert c.post(f"/staffings/{staff2['id']}/approve",json={},headers=admin).status_code==409
    # 已签核日期禁止改期/取消/新增
    target=staff2['schedule'][0]['day']
    batch=c.post('/appointments',json={'branch':'川北','service_day':target,'quantity':2},headers=analyst)
    assert batch.status_code==409 and '已签核' in batch.json()['detail']


def test_volume_cannot_drop_below_fulfilled(app_client):
    c=app_client;h=login(c,'analyst')
    batch=c.post('/appointments',json={'branch':'川北','service_day':'2026-09-07','quantity':9,'request_id':'t-vol-1'},headers=h).json()
    assert c.post(f"/appointments/{batch['id']}/fulfil",json={'day':'2026-09-07','quantity':7,'request_id':'t-vol-2'},headers=h).status_code==200
    row=[v for v in c.get('/volumes',headers=h).json() if v['branch']=='川北' and v['day']=='2026-09-07'][0]
    r=c.put(f"/volumes/{row['id']}",json={'branch':'川北','day':'2026-09-07','volume':3},headers=h)
    assert r.status_code==422 and '兑现' in r.json()['detail']
    assert c.put(f"/volumes/{row['id']}",json={'branch':'川北','day':'2026-09-07','volume':9},headers=h).status_code==200


def test_failed_reschedule_keeps_original_batch(app_client):
    c=app_client;h=login(c,'analyst')
    batch=c.post('/appointments',json={'branch':'东河','service_day':'2026-11-20','quantity':6,'request_id':'t-keep-1'},headers=h).json()
    before=c.get(f"/appointments/{batch['id']}",headers=h).json()
    over=c.post(f"/appointments/{batch['id']}/reschedule",json={'service_day':'2026-11-22','quantity':99},headers=h)
    assert over.status_code==422
    same=c.post(f"/appointments/{batch['id']}/reschedule",json={'service_day':'2026-11-20','quantity':2},headers=h)
    assert same.status_code==422
    after=c.get(f"/appointments/{batch['id']}",headers=h).json()
    assert (after['remaining'],after['moved_out'],after['service_day'])==(before['remaining'],before['moved_out'],before['service_day'])
    # 失败尝试也不能消耗 request_id
    retry=c.post(f"/appointments/{batch['id']}/reschedule",json={'service_day':'2026-11-22','quantity':2,'request_id':'t-keep-2'},headers=h)
    assert retry.status_code==200 and retry.json()['target']['quantity']==2


def test_forecast_frozen_snapshot_unchanged_by_later_appointment(app_client):
    c=app_client;h=login(c,'analyst')
    run=run_job(c,h)
    frozen=json.dumps(run['result']['appointment_basis'],sort_keys=True)
    c.post('/appointments',json={'branch':'川北','service_day':'2026-11-19','quantity':5,'request_id':'t-freeze'},headers=h)
    again=c.get(f"/runs/{run['id']}",headers=h).json()
    assert json.dumps(again['result']['appointment_basis'],sort_keys=True)==frozen
    basis_now=c.get('/appointments/basis/川北',headers=h).json()
    assert basis_now['reserved_by_day']['2026-11-19']>=5
    # 新提交的预测使用新依据，并能据此起草排班
    run2=run_job(c,h)
    assert run2['revision']>run['revision']
    staff=c.post('/staffings',json={'run_id':run2['id'],'capacity':10,'model':'seasonal_naive','note':'按新冻结依据重算并核对'},headers=h)
    assert staff.status_code==200,staff.text
    # 旧依据的排班已失效
    old=c.get('/staffings',headers=h).json()
    assert all(s['status']!='draft' or s['run_id']!=run['id'] for s in old)


def test_concurrent_approval_only_one_wins(app_client):
    import threading
    c=app_client;admin=login(c,'admin');analyst=login(c,'analyst')
    run=run_job(c,analyst)
    ids=[]
    for _ in range(2):
        r=c.post('/staffings',json={'run_id':run['id'],'capacity':11,'model':'holt','note':'并发签核验证用排班草案'},headers=analyst)
        assert r.status_code==200,r.text
        ids.append(r.json()['id'])
    results=[]
    barrier=threading.Barrier(2)
    def sign(sid):
        barrier.wait()
        try:
            resp=c.post(f'/staffings/{sid}/approve',json={},headers=admin)
            results.append(resp.status_code)
            if resp.status_code!=200:results.append(resp.json().get('detail'))
        except Exception as e:results.append(type(e).__name__)
    threads=[threading.Thread(target=sign,args=(i,)) for i in ids]
    [t.start() for t in threads];[t.join() for t in threads]
    assert results.count(200)==1,results
    assert 409 in results


def test_worker_duplicate_delivery_counts_once(app_client):
    from src.services.runner import process
    c=app_client;h=login(c,'analyst')
    r=c.post('/runs',json={'name':'重复投递验证','branch':'川北','backtest_days':7,'alpha':.6,'beta':.2},headers=h)
    run_id=r.json()['id']
    assert process(run_id) is True
    assert process(run_id) is False
    stored=c.get(f'/runs/{run_id}',headers=h).json()
    assert stored['state']=='done' and stored['result']['n']==72


def test_stale_run_flag_and_reapproval_after_change(app_client):
    c=app_client;analyst=login(c,'analyst');admin=login(c,'admin')
    run=run_job(c,analyst)
    assert run['stale'] is False
    add_reserved(c,analyst,days=(2,),quantity=3,tag='stale')
    stale=c.get(f"/runs/{run['id']}",headers=analyst).json()
    assert stale['stale'] is True and stale['current_revision']>stale['revision']
    blocked=c.post('/staffings',json={'run_id':run['id'],'capacity':10,'model':'holt','note':'应按最新依据重算排班'},headers=analyst)
    assert blocked.status_code==409 and '依据已变动' in blocked.json()['detail']


def test_draft_rejected_when_days_already_approved(app_client):
    c=app_client;analyst=login(c,'analyst');admin=login(c,'admin')
    run=run_job(c,analyst)
    first=c.post('/staffings',json={'run_id':run['id'],'capacity':12,'model':'holt','note':'首份草案，准备签核确认'},headers=analyst).json()
    assert c.post(f"/staffings/{first['id']}/approve",json={},headers=admin).status_code==200
    again=c.post('/staffings',json={'run_id':run['id'],'capacity':12,'model':'holt','note':'同依据重复起草应被拒绝'},headers=analyst)
    assert again.status_code==409 and '已签核' in again.json()['detail']
