import math,json,hashlib
from datetime import date,timedelta


def holt(values,horizon,alpha,beta):
    if len(values)<2:raise ValueError('Holt至少需要2天数据')
    level=float(values[0]);trend=float(values[1]-values[0])
    for value in values[1:]:
        previous=level;level=alpha*value+(1-alpha)*(level+trend);trend=beta*(level-previous)+(1-beta)*trend
    return [level+h*trend for h in range(1,horizon+1)]


def seasonal(values,horizon):return [float(values[-7+i%7]) for i in range(horizon)]


def scores(actual,predicted):
    errors=[abs(a-p) for a,p in zip(actual,predicted)];pairs=[(a,p) for a,p in zip(actual,predicted) if a!=0]
    return {'mae':sum(errors)/len(errors),'mape':sum(abs(a-p)/a for a,p in pairs)/len(pairs)*100 if pairs else None,'mape_used':len(pairs),'zero_actual':len(actual)-len(pairs)}


def validated(rows,backtest_days):
    rows=sorted(rows,key=lambda r:r['day']);days=[date.fromisoformat(r['day']) for r in rows]
    if len(rows)<backtest_days+28:raise ValueError(f'至少需要{backtest_days+28}个连续日量，保证回测前28天训练窗口')
    if len(set(days))!=len(days):raise ValueError('同网点存在重复日期，请先核对')
    gaps=[(a.isoformat(),b.isoformat()) for a,b in zip(days,days[1:]) if b-a!=timedelta(days=1)]
    if gaps:raise ValueError('日期不连续，缺口：'+str(gaps[:3])+'；不可将缺日当作零量')
    return rows,days


def walk_forward(rows,backtest_days,alpha,beta):
    """滚动一步回测：末 backtest_days 日逐日重拟合，每个预测只用此前历史。"""
    rows,days=validated(rows,backtest_days)
    values=[r['volume'] for r in rows];start=len(values)-backtest_days
    predictions={'seasonal_naive':[],'holt':[]};clipped={'seasonal_naive':0,'holt':0}
    for i in range(start,len(values)):
        train=values[:i]
        for model,raw in [('seasonal_naive',seasonal(train,1)[0]),('holt',holt(train,1,alpha,beta)[0])]:
            if raw<0:clipped[model]+=1
            predictions[model].append(max(0,raw))
    metrics={m:scores(values[start:],ps) for m,ps in predictions.items()}
    selected=min(metrics,key=lambda m:(metrics[m]['mae'],m!='seasonal_naive'))
    return dict(rows=rows,days=days,values=values,start=start,predictions=predictions,clipped=clipped,metrics=metrics,selected_model=selected)


def forecast(rows,backtest_days,alpha,beta,unfulfilled=None):
    """rows 为扣除各批兑现量后的散客日量；unfulfilled 为未来服务日的未兑现预约量。
    回测与散客预测只使用散客日量，预约只作为未来逐日加项，避免重复计算。"""
    unfulfilled=unfulfilled or {}
    base=walk_forward(rows,backtest_days,alpha,beta)
    rows,days,values=base['rows'],base['days'],base['values']
    future={}
    for model,raws in [('seasonal_naive',seasonal(values,7)),('holt',holt(values,7,alpha,beta))]:
        items=[]
        for h,raw in enumerate(raws,1):
            day=(days[-1]+timedelta(days=h)).isoformat()
            scatter=max(0,int(math.floor(raw+.5)))
            reserved=int(unfulfilled.get(day,0))
            items.append({'day':day,'raw':raw,'prediction':scatter,'clipped':raw<0,'reserved':reserved,'total':scatter+reserved})
        future[model]=items
    future_daily={model:[{'day':i['day'],'scatter_raw':i['raw'],'scatter':i['prediction'],'reserved':i['reserved'],'total':i['total']} for i in future[model]] for model in future}
    backtest=[]
    for i in range(base['start'],len(values)):
        row=rows[i]
        detail={'day':row['day'],'actual':values[i],**{m:base['predictions'][m][i-base['start']] for m in base['predictions']}}
        if 'daily_total' in row:detail['daily_total']=row['daily_total']
        if 'fulfilled' in row:detail['fulfilled']=row['fulfilled']
        backtest.append(detail)
    return dict(branch=rows[0]['branch'],n=len(rows),train_initial=base['start'],backtest_days=backtest_days,alpha=alpha,beta=beta,
        metrics=base['metrics'],selected_model=base['selected_model'],backtest=backtest,future=future,future_daily=future_daily,
        history=[{'day':r['day'],'volume':r['volume'],**({'daily_total':r['daily_total'],'fulfilled':r['fulfilled']} if 'daily_total' in r else {})} for r in rows],
        backtest_clipped=base['clipped'],
        checksum=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
        warning='回测只用扣除各批兑现量后的散客日量，按时间顺序滚动一步，每个预测只用此前数据；α/β为提交前指定，不用回测真值调参。未来合计=散客预测+该服务日未兑现预约；预约只叠加到对应日期，不进入训练与回测。回测MAE用于选模，不是独立最终泛化估计。MAPE跳过实际值0并报告数量；全部为0时MAPE未定义。负预测先截为0，未来值四舍五入为非负整数。')
