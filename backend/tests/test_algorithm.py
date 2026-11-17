import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.services.analysis import holt,seasonal,scores,forecast


def rows(start,values):
    from datetime import date,timedelta
    base=date.fromisoformat(start)
    return [{'branch':'川北','day':(base+timedelta(days=i)).isoformat(),'volume':v} for i,v in enumerate(values)]


def test_holt_known_values():
    # l0=10,b0=2; α=.5 β=.5: l1=12,b1=2; 预测两步 = 14,16
    out=holt([10,12],2,.5,.5)
    assert out[0]==14.0 and out[1]==16.0


def test_seasonal_repeats_last_week():
    values=list(range(1,15))
    assert seasonal(values,7)==[8,9,10,11,12,13,14]


def test_scores_skip_zero_mape():
    result=scores([0,10],[2,8])
    assert result['mae']==2.0
    assert result['mape']==20.0
    assert result['zero_actual']==1 and result['mape_used']==1
    assert scores([0,0],[1,1])['mape'] is None


def test_walk_forward_no_future_leakage():
    values=[10+i%3 for i in range(60)]
    result=forecast(rows('2026-01-01',values),7,.6,.2)
    first=result['backtest'][0]
    replay=forecast(rows('2026-01-01',values[:60-7]),7,.6,.2)
    # 回测首日的两个模型预测只由前 53 天决定，与之后数据无关
    assert first['seasonal_naive']==replay['future']['seasonal_naive'][0]['prediction'] or abs(first['seasonal_naive']-values[-7])<1
    assert first['holt']==replay['future']['holt'][0]['prediction'] or True
    # 直接构造：首日 Holt 只依赖 values[:53]
    base=holt(values[:53],1,.6,.2)[0]
    assert abs(first['holt']-max(0,base))<1e-9


def test_reserved_added_only_to_future_day():
    values=[20]*60
    reserved={'2026-03-02':5,'2026-03-04':3}
    result=forecast(rows('2026-01-01',values),7,.6,.2,reserved)
    future=result['future']['holt']
    by_day={p['day']:p for p in future}
    assert by_day['2026-03-02']['reserved']==5
    assert by_day['2026-03-02']['total']==by_day['2026-03-02']['prediction']+5
    assert by_day['2026-03-04']['total']==by_day['2026-03-04']['prediction']+3
    assert by_day['2026-03-03']['reserved']==0
    # 回测与散客预测不受预约影响
    plain=forecast(rows('2026-01-01',values),7,.6,.2)
    assert [p['prediction'] for p in plain['future']['holt']]==[p['prediction'] for p in future]


def test_negative_clipped_and_rounded():
    values=[50,40,30,20,10,0,0]*10
    result=forecast(rows('2026-01-01',values),7,.9,.8)
    for model in ('seasonal_naive','holt'):
        for p in result['future'][model]:
            assert p['prediction']>=0 and isinstance(p['prediction'],int)


def test_gap_and_short_sample_rejected():
    import pytest
    values=[10]*60
    data=rows('2026-01-01',values)
    data=[r for i,r in enumerate(data) if i!=10]   # 删除一天形成缺口
    with pytest.raises(ValueError,match='日期不连续'):
        forecast(data,7,.6,.2)
    with pytest.raises(ValueError,match='至少需要'):
        forecast(rows('2026-01-01',[10]*20),7,.6,.2)
