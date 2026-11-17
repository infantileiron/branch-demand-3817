import {state} from '../stores/session.js';import {esc} from '../utils/html.js';import {table} from '../components/common/table.js';import {badge} from '../components/common/status.js';import {MODELS} from '../constants/enums.js';
const fmt=x=>x===null||x===undefined?'未定义':Number(x).toFixed(2);
const n=v=>String(v??0).replace(/\B(?=(\d{3})+(?!\d))/g,',');
export function render(){
 let e=state.selected,r=e?.result;
 if(!e)return '<section class="panel"><h2>先建立预测版本</h2><p>在回测设置选择网点与固定参数，后台计算完成后查看对比。</p><button data-nav="1">前往回测设置</button></section>';
 let future=r?.future?.holt?r.future:null;
 let futureRows=future?future.holt.map((row,i)=>{
   let s=future.seasonal_naive[i];
   return [row.day,n(row.prediction),n(row.reserved),n(row.total),n(s.prediction),n(s.reserved),n(s.total)];
 }):[];
 let reservedTotal=future?future.holt.reduce((a,p)=>a+p.reserved,0):0;
 let scatterTotal=future?future.holt.reduce((a,p)=>a+p.prediction,0):0;
 let totalTotal=future?future.holt.reduce((a,p)=>a+p.total,0):0;
 let basis=r?.appointment_basis;
 let beyond=basis?.beyond_window||[];
 return `<section class="panel"><div class="result-head"><h2>${esc(e.name)} ${badge(e.state)}</h2><button id="refresh">刷新状态</button></div>${e.state==='done'?`${e.stale?'<p class="notice">该版本冻结的预约/日结依据已被后续变动取代：可查看与导出，但不能据此起草排班；请按最新依据重新提交预测。</p>':''}<p class="eyebrow">${esc(e.branch)} / ${r.n}日散客日量 / 末${r.backtest_days}日滚动一步回测 / 初始训练${r.train_initial}日 / 依据版本 #${e.revision??'—'}</p><div class="metrics">${Object.entries(r.metrics).map(([m,v])=>`<div><strong>${fmt(v.mae)}</strong>${MODELS[m]} · MAE / 单<p>MAPE ${fmt(v.mape)}% · 非零实际${v.mape_used}日</p></div>`).join('')}<div><strong>${MODELS[r.selected_model]}</strong>较低MAE参考选择</div><div><strong>${n(reservedTotal)}</strong>未来7日未兑现预约<p>散客 ${n(scatterTotal)} + 预约 ${n(reservedTotal)} = 合计 ${n(totalTotal)}</p></div></div><p class="notice">回测输入为扣除兑现量后的散客日量；预约只作为未来逐日加项，不再叠加已含预约的日结原值，避免高估需求。</p><h3>未来7日需求分量：散客预测 + 未兑现预约 = 合计</h3><div class="scroll">${table(['日期','季节朴素·散客','季节朴素·预约','季节朴素·合计','Holt·散客','Holt·预约','Holt·合计'],futureRows)}</div><div class="compare"><div><h3>滚动回测：实际散客量与两模型</h3><svg viewBox="0 0 660 230" role="img" aria-label="滚动回测预测对比"><path d="M30 25V200H640" fill="none" stroke="#a9afa1"/><text x="0" y="35" font-size="11">${(Math.max(1,...r.backtest.flatMap(d=>[d.actual,d.holt,d.seasonal_naive]))).toFixed(0)}</text><text x="8" y="200" font-size="11">0</text><text x="30" y="222" font-size="11">${r.backtest[0].day}</text><text x="520" y="222" font-size="11">${r.backtest.at(-1).day}</text>${['actual','seasonal_naive','holt'].map((m,i)=>`<polyline points="${r.backtest.map((d,j)=>`${30+j/(r.backtest.length-1)*600},${200-d[m]/Math.max(1,...r.backtest.flatMap(d=>[d.actual,d.holt,d.seasonal_naive]))*165}`).join(' ')}" fill="none" stroke="${['#253f32','#b17822','#718f7a'][i]}" stroke-width="${i===0?3:2}"/>`).join('')}</svg><p>深松：实际散客量 · 琥珀：季节朴素 · 灰绿：Holt</p></div><div><h3>冻结的预约依据</h3><p class="eyebrow">${esc(basis?.as_of||'—')} 冻结 / ${basis?.window?.length||0} 日窗口</p>${table(['服务日','未兑现预约'],Object.entries(basis?.reserved_by_day||{}).map(([d,v])=>[d,v]))}${beyond.length?`<p class="notice">窗口外未兑现 ${beyond.length} 批共 ${n(beyond.reduce((a,b)=>a+b.remaining,0))} 人，未计入本次7日合计。</p>`:''}</div></div><p class="notice">${esc(r.warning)}</p><button id="download">下载冻结预测 JSON</button><button data-nav="4">生成排班建议</button>`:`<p class="notice">${esc(e.error||'任务处理中，请刷新查看结果。')}</p>`}<h3>历史版本</h3>${state.runs.map(v=>`<button class="study" data-run="${v.id}">#${v.id} ${esc(v.name)} · ${esc(v.state)}</button>`).join('')}</section>`;
}
