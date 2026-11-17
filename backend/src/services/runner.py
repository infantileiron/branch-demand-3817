import json
from pathlib import Path
from src.config.database import Session
from src.models.entities import ForecastRun
from src.services.analysis import forecast


def _artifact_dir():
    path=Path('/artifacts')
    try:path.mkdir(parents=True,exist_ok=True)
    except OSError:pass
    return path


def process(run_id):
    """执行一条排队预测；重复投递时状态已不是 queued，直接跳过，保证不重复计量。"""
    with Session() as s:
        row=s.get(ForecastRun,int(run_id))
        if not row or row.state!='queued':return False
        snapshot=row.result or {}
        row.state='running';s.commit()
        try:
            if 'appointment_basis' not in snapshot:
                raise ValueError('该预测依据为旧格式（未冻结预约），请按当前日结与预约重新提交')
            rows=snapshot.get('rows') or []
            basis=snapshot.get('appointment_basis') or {}
            for item in rows:item.setdefault('branch',row.branch)
            reserved=basis.get('reserved_by_day') or {}
            result=forecast(rows,row.backtest_days,row.alpha,row.beta,reserved)
            result={**result,'revision':row.revision,'appointment_basis':basis,'snapshot':{'rows':rows,'appointment_basis':basis}}
            row.result=result;row.error='';row.state='done'
            try:_artifact_dir().joinpath(f'{row.id}.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            except OSError:pass
        except Exception as e:
            s.rollback();row=s.get(ForecastRun,int(run_id))
            row.state='failed';row.error=str(e)
        s.commit()
        return True
