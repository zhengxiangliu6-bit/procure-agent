import React,{useEffect,useState,useRef} from 'react';

const examples=[
 {id:'balanced',title:'正常采购',text:'原型号有货，同时存在低价迟交与高起订量报价。',goal:'采购 500 个 DEMO-MCU-A，预算 1300 元，14 天内到货。请自主寻找并核验供应商，给我一个满足目标的采购方案。'},
 {id:'stockout',title:'库存不足 · 尝试拆单',text:'原型号分散在两家供应商，单家库存都不足。',goal:'采购 500 个 DEMO-MCU-A，预算 1300 元，14 天内到货。优先使用原型号，单家缺货时可以拆单，请自主寻找满足目标的方案。'},
 {id:'budget',title:'预算紧张 · 调整策略',text:'原型号超预算，模拟议价与候选替代可尝试。',goal:'采购 500 个 DEMO-MCU-A，预算 1200 元，14 天内到货。超预算时请尝试议价或寻找候选替代，涉及替代型号时先让我确认。'},
 {id:'impossible',title:'约束冲突 · 如实报告',text:'便宜的交期不符，按期的超预算；可能需要你的决定。',goal:'采购 500 个 DEMO-MCU-A，预算 1300 元，14 天内到货。请寻找满足条件的方案；不满足就说明障碍，未经确认不要放宽条件。'},
];
const labels={running:'正在自主寻源',awaiting_clarification:'等待你的决定',awaiting_review:'等待报告审核',completed:'审核完成',rejected:'已退回',failed:'执行失败',interrupted:'可恢复'};

function actionText(event){
 const d=event.detail,r=d.result||{},a=d.input||{};
 switch(d.tool){
 case 'search_suppliers':return `搜索 ${a.model}，发现 ${r.suppliers?.length||0} 家供应商。`;
 case 'request_quote':return r.error||`${r.supplier}：库存 ${r.stock}，单价 ¥${r.price}，交期 ${r.lead_days} 天。`;
 case 'inspect_offer':return r.error||(!r.known?'没有可靠规格依据。':!r.basic_match?'封装或温度不满足要求。':r.exact_model?'原型号规格匹配。':r.documented_equivalence?'找到模拟等价依据，仍需该型号的工程确认。':'未找到明确等价依据。');
 case 'evaluate_plan':return r.feasible?`${r.id} 核验通过：总计 ¥${r.total}，${r.quantity} 个，最长 ${r.max_lead_days} 天。`:(r.reasons||[]).join('；');
 case 'negotiate_quote':return r.error||(r.accepted?`模拟议价成功，单价调整为 ¥${r.quote.price}。`:r.reason);
 case 'find_alternatives':return r.candidates?.length?`发现候选：${r.candidates.map(x=>x.model).join('、')}，继续核验。`:'未找到候选型号。';
 case 'ask_user':return r.error||r.request?.reason;
 case 'finish_sourcing':return r.error||(r.accepted?'已提交结论，等待你审核。':(r.reasons||[]).join('；'));
 default:return d.reason||'';
 }
}

export default function SourcingWorkbench({api,act,load,refreshList,current,busy,resume}){
 const [goal,setGoal]=useState(examples[0].goal),[scenario,setScenario]=useState('balanced'),[answers,setAnswers]=useState({}),[note,setNote]=useState('');
 const task=current?.kind==='sourcing'?current:null,state=task?.state||{},report=state.report,request=task?.interrupt;
 const hydrated=useRef(null);
 useEffect(()=>{if(task?.id&&state.goal&&hydrated.current!==task.id){hydrated.current=task.id;setGoal(state.goal);setScenario(state.scenario)}},[task?.id,state.goal,state.scenario]);
 useEffect(()=>{setAnswers({});setNote('')},[task?.id,task?.checkpoint]);
 async function start(){await act(async()=>{const r=await api('/sourcing',{method:'POST',body:JSON.stringify({goal,scenario})});await load(r.id);await refreshList()})}
 async function decide(){await act(async()=>{await api(`/tasks/${task.id}/resume`,{method:'POST',body:JSON.stringify({expected_checkpoint:task.checkpoint,answers})});await load(task.id);await refreshList()})}
 const events=task?.events||[],actions=events.filter(e=>e.kind==='action'),plans=events.filter(e=>e.kind==='plan'),goalEvent=events.find(e=>e.kind==='goal');
 const constraints=state.requirement||goalEvent?.detail?.constraints;
 return <>
 <section className="panel goal-panel"><div className="panel-title"><h2>给 Agent 一个采购目标</h2><span>GOAL → ACTION → OBSERVATION → ADAPT</span></div><label htmlFor="goal-input">型号、数量、全部预算与到货期限<textarea id="goal-input" value={goal} onChange={e=>setGoal(e.target.value)} maxLength={1500}/></label>
 <div className="scenario-grid">{examples.map(x=><button key={x.id} className={'scenario '+(scenario===x.id?'chosen':'')} onClick={()=>{setScenario(x.id);setGoal(x.goal)}}><b>{x.title}</b><span>{x.text}</span></button>)}</div>
 <div className="goal-footer"><p>接入固定的模拟供应商市场。每次运行由模型自主选择工具；不会联系真实供应商。</p><button className="primary" disabled={busy||goal.trim().length<5} onClick={start}>开始自主寻源 ↗</button></div></section>
 {!task&&<div className="empty sourcing-empty"><span>✳</span><h3>把目标交给它，观察它如何推进。</h3><p>从搜索供应商开始，遇到库存不足、预算超限时调整策略。<br/>替代型号和条件修改会先征求你的决定。</p></div>}
 {task&&<><div className="task-heading"><div><span className="eyebrow">SOURCING TASK · {task.id.slice(0,8)}</span><h2>{labels[task.status]}</h2></div><span className={'badge '+task.status}>{labels[task.status]}</span></div>
 {task.error&&<div className="error">{task.error}<button disabled={busy} onClick={()=>act(async()=>{await api(`/tasks/${task.id}/retry`,{method:'POST'});await load(task.id)})}>从检查点恢复</button></div>}
 {constraints&&<div className="constraint-strip"><span><small>型号 / 数量</small><b>{constraints.model||'待补充'} / {constraints.quantity??'待补充'} 个</b></span><span><small>全部预算</small><b>¥{constraints.budget??'待补充'}</b></span><span><small>最长交期</small><b>{constraints.max_lead_days??'待补充'} 天</b></span><span><small>数据环境</small><b>模拟报价与库存</b></span></div>}
 {request&&request.type!=='review'&&<section className="clarification agent-decision"><h3>{request.title}</h3><p>{request.reason}</p><div className="decision-fields">{request.questions.map(q=><label key={q.field}>{q.label}{q.input==='boolean'?<select aria-label={q.label} value={answers[q.field]===undefined?'':String(answers[q.field])} onChange={e=>setAnswers({...answers,[q.field]:e.target.value===''?undefined:e.target.value==='true'})}><option value="">请选择</option><option value="true">已取得该模拟型号的工程确认，允许使用</option><option value="false">不允许，继续寻找原型号方案</option></select>:<input aria-label={q.label} type={q.input} value={answers[q.field]??''} onChange={e=>setAnswers({...answers,[q.field]:q.input==='number'&&e.target.value!==''?Number(e.target.value):e.target.value})}/>}</label>)}</div><button className="primary" disabled={busy||request.questions.some(q=>answers[q.field]===undefined||answers[q.field]==='')} onClick={decide}>确认决定，继续行动 →</button><p className="muted">预算或交期输入原值表示保持条件；只会修改当前明确确认的字段。</p></section>}
 <div className="sourcing-layout"><section className="panel action-feed"><div className="panel-title"><h2>Agent 行动与结果</h2><span>{actions.length} 个工具动作</span></div>{!events.length&&<p className="muted">目标已提交，等待模型理解…</p>}{plans.map(p=><div className="agent-plan" key={p.id}><b>{p.title}</b><ol>{p.detail.steps.map(x=><li key={x}>{x}</li>)}</ol></div>)}{events.filter(e=>['action','human','goal'].includes(e.kind)).map((e,i)=><article key={e.id} className={'action-card '+(e.detail.result?.feasible===false?'blocked':'')}><div className="action-number">{e.kind==='human'?'你':String(i+1).padStart(2,'0')}</div><div><b>{e.title}</b><p>{e.kind==='action'?actionText(e):e.kind==='goal'?'已从目标提取约束；缺少必要信息时会暂停。':e.detail.notice||'收到明确确认，继续推进任务。'}</p><details><summary>查看工具输入与证据</summary><pre>{JSON.stringify(e.detail,null,2)}</pre></details></div></article>)}{task.status==='running'&&<div className="agent-working"><i/>正在观察工具结果并选择下一步…</div>}</section>
 <section className="panel agent-state"><div className="panel-title"><h2>当前进展</h2><span>可恢复执行</span></div><p>{task.status==='running'?'Agent 正在尝试满足你的采购目标。':labels[task.status]}</p><dl><dt>模型决策轮次</dt><dd>{events.filter(e=>e.kind==='model').length}</dd><dt>已获取报价</dt><dd>{Object.keys(state.offers||{}).length||actions.filter(e=>e.detail.tool==='request_quote'&&e.detail.result.id).length}</dd><dt>已评估方案</dt><dd>{state.evaluations?.length||actions.filter(e=>e.detail.tool==='evaluate_plan').length}</dd></dl><p className="muted">工具结果决定方案是否可用。模型文字不能覆盖库存、起订量、预算、交期和规格约束。</p></section></div>
 {report&&<section className="panel sourcing-report"><div className="panel-title"><h2>寻源结果</h2><a href={`/api/tasks/${task.id}/report`} download>↓ 导出方案与行动记录</a></div><div className="recommendation"><span>✳</span><div><b>{report.recommendation}</b><p>{report.scope}</p></div></div>{report.plan&&<><div className="plan-metrics"><span><small>含税含运费总成本</small><strong>¥{report.plan.total}</strong></span><span><small>预算剩余</small><strong>¥{report.plan.remaining_budget}</strong></span><span><small>最长交期</small><strong>{report.plan.max_lead_days} 天</strong></span></div><div className="table-wrap"><table><thead><tr><th>供应商 / 型号</th><th>分配数量 / 库存</th><th>含税含运费</th><th>交期</th><th>依据</th></tr></thead><tbody>{report.plan.allocations.map(a=><tr key={a.offer_id}><td><b>{a.supplier}</b><small>{a.model}</small></td><td>{a.quantity} / {a.stock}</td><td>¥{a.cost.total}<small>{a.cost.formula}</small></td><td>{a.lead_days} 天</td><td>{a.evidence.map(h=><details key={h.id}><summary>{h.title} · 第{h.page}页</summary><p>{h.text}</p></details>)}</td></tr>)}</tbody></table></div></>}
 {report.analysis&&<details className="final-analysis"><summary>Agent 的最终说明（需核对）</summary><pre>{report.analysis}</pre></details>}
 {report.evaluations.length>0&&<details className="evaluation-list"><summary>已尝试 {report.evaluations.length} 个方案，查看未通过原因</summary>{report.evaluations.map(p=><div key={p.id}><b>{p.id} · {p.feasible?'满足条件':'未通过'} · ¥{p.total}</b><p>{p.feasible?'数量、库存、预算、交期与规格均通过工具核验。':p.reasons.join('；')}</p></div>)}</details>}
 {request?.type==='review'&&<div className="review"><label>审核备注<input value={note} onChange={e=>setNote(e.target.value)} placeholder="核对方案与依据后确认"/></label><button className="outline" disabled={busy} onClick={()=>resume(false,note)}>退回报告</button><button className="primary" disabled={busy} onClick={()=>resume(true,note)}>确认报告 ✓</button><small>确认的是分析报告；不会发送询价、预留库存或下单。</small></div>}</section>}
 </>}
 </>;
}
