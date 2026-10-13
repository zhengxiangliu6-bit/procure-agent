import asyncio
import json
import os
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from langgraph.types import Command
from .models import CreateTask, ResumeTask, Quote, SourcingTask
from .storage import Repository
from .retrieval import KnowledgeBase
from .graph import ProcurementGraph
from .parsing import parse_quotes, parse_knowledge
from .model_config import has_key, provider
from .sourcing import SourcingGraph, validate_answers

ROOT=Path(__file__).resolve().parents[1]
repo=Repository(os.environ.get('PROCURE_DATA_DIR',ROOT/'data'))
kb=KnowledgeBase(repo); engine=ProcurementGraph(repo,kb)
sourcing_engine=SourcingGraph(repo,kb)
pool=ThreadPoolExecutor(max_workers=1)
lock=threading.Lock()
app=FastAPI(title='Procure Agent',version='0.2.0')

def task_engine(task_id):
    return sourcing_engine if repo.get(task_id).get('kind')=='sourcing' else engine

def config(task_id): return {'configurable':{'thread_id':task_id},'recursion_limit':40}

def snapshot(task_id):
    # SqliteSaver serializes each cursor internally. A model request must not hold
    # historical readers behind the whole-task worker lock.
    return task_engine(task_id).graph.get_state(config(task_id))

def checkpoint_id(snap):
    return (snap.config or {}).get('configurable',{}).get('checkpoint_id','')

def run(task_id,input):
    try:
        with lock:
            graph=task_engine(task_id).graph
            graph.invoke(input,config(task_id))
            snap=graph.get_state(config(task_id))
        if snap.interrupts:
            status='awaiting_review' if snap.interrupts[0].value['type']=='review' else 'awaiting_clarification'
        else: status='completed' if snap.values.get('approved') else 'rejected'
        repo.update(task_id,status)
    except Exception as e:
        # Never expose provider exception bodies, which may include credentials or document content.
        message=str(e) if isinstance(e,ValueError) else f'执行失败（{type(e).__name__}），可从检查点重试。'
        repo.update(task_id,'failed',message);repo.event(task_id,'error','执行失败',{'message':message})

def require_task(task_id):
    t=repo.get(task_id)
    if not t: raise HTTPException(404,'任务不存在')
    return t

def submit(payload):
    ids=[q.id for q in payload.quotes]
    if len(ids)!=len(set(ids)): raise HTTPException(422,'报价 ID 不可重复')
    tid=repo.create(payload.name)
    pool.submit(run,tid,{'task_id':tid,'requirement':payload.requirement.model_dump(mode='json'),'quotes':[q.model_dump(mode='json') for q in payload.quotes]})
    return {'id':tid}

@app.get('/api/health')
def health(): return {'ok':True,'mode':os.environ.get('AGENT_MODE','demo'),'provider':provider(),'model':os.environ.get('AGENT_MODEL'),'live_configured':has_key(),'storage':'SQLite durable checkpoints','retrieval':'exact model + BM25 + TF-IDF'}

@app.get('/api/tasks')
def list_tasks(): return repo.list()

@app.post('/api/tasks')
def create_task(payload:CreateTask): return submit(payload)

@app.post('/api/sourcing')
def create_sourcing(payload:SourcingTask):
    tid=repo.create('自主寻源 · '+payload.goal[:60],kind='sourcing')
    pool.submit(run,tid,{'task_id':tid,'kind':'sourcing','goal':payload.goal,'scenario':payload.scenario})
    return {'id':tid}

@app.post('/api/demo')
def demo():
    return submit(CreateTask(name='演示 · 500 个 MCU 采购核验',quotes=[
        Quote(id='q1',supplier='青禾电子（模拟）',model='DEMO-MCU-A',price='2.35',lead_days=10,shipping='20',source='模拟报价 A，第 2 行'),
        Quote(id='q2',supplier='远川科技（模拟）',model='DEMO-MCU-A',price='210',price_unit=100,lead_days=12,tax_included=False,tax_rate='.13',shipping=None,source='模拟报价 B，第 2 行'),
        Quote(id='q3',supplier='星野元件（模拟）',model='DEMO-MCU-B',price='1.80',lead_days=7,shipping='0',source='模拟报价 C，第 2 行')]))

@app.get('/api/tasks/{task_id}')
def detail(task_id):
    t=require_task(task_id)
    if t['status']=='running': return {**t,'state':{},'events':repo.events(task_id),'checkpoint':'','interrupt':None}
    snap=snapshot(task_id)
    return {**t,'state':snap.values,'events':repo.events(task_id),'checkpoint':checkpoint_id(snap),'interrupt':snap.interrupts[0].value if snap.interrupts else None}

@app.post('/api/tasks/{task_id}/resume')
def resume(task_id,payload:ResumeTask):
    t=require_task(task_id)
    if t['status'] not in ['awaiting_clarification','awaiting_review']: raise HTTPException(409,'任务当前不等待人工输入')
    snap=snapshot(task_id)
    if payload.expected_checkpoint!=checkpoint_id(snap): raise HTTPException(409,'页面版本过期，请刷新任务')
    it=snap.interrupts[0].value
    if it['type']=='clarification':
        allowed={(q['quote_id'],q['field']) for q in it['questions']}
        missing=[(i,f) for i,f in allowed if f not in payload.patches.get(i,{})]
        if missing: raise HTTPException(422,'请补充所有待澄清字段')
        if any((i,f) not in allowed for i,p in payload.patches.items() for f in p): raise HTTPException(422,'只能修改待澄清字段')
        try:
            for q in snap.values['quotes']: Quote.model_validate({**q,**payload.patches.get(q['id'],{})})
        except ValueError: raise HTTPException(422,'补充值不合法，请检查交期、运费与税率')
    elif it['type'] in ['goal_clarification','sourcing_decision']:
        try: validate_answers(snap.values,payload.answers)
        except (ValueError,TypeError):raise HTTPException(422,'决策输入不合法，请完整填写当前问题；不得修改其他条件')
    elif payload.approved is None: raise HTTPException(422,'请明确审核结论')
    # Server-side status claim closes concurrent resume races.
    with repo.connect() as c:
        cursor=c.execute('UPDATE tasks SET status=? WHERE id=? AND status=?',('running',task_id,t['status']))
        if not cursor.rowcount: raise HTTPException(409,'任务已被其他操作恢复')
    pool.submit(run,task_id,Command(resume=payload.model_dump(exclude={'expected_checkpoint'})))
    return {'id':task_id}

@app.post('/api/tasks/{task_id}/retry')
def retry(task_id):
    t=require_task(task_id)
    if t['status'] not in ['failed','interrupted']: raise HTTPException(409,'只有失败或重启中断的任务可重试')
    with repo.connect() as c:
        result=c.execute("UPDATE tasks SET status='running',error=NULL WHERE id=? AND status=?",(task_id,t['status']))
        if not result.rowcount: raise HTTPException(409,'任务已恢复')
    pool.submit(run,task_id,None);return {'id':task_id}

@app.get('/api/tasks/{task_id}/events')
async def events(task_id,after:int=0):
    require_task(task_id)
    async def generate():
        cursor=after
        while True:
            for e in repo.events(task_id,cursor):
                cursor=e['id'];yield f"id: {cursor}\ndata: {json.dumps(e,ensure_ascii=False)}\n\n"
            t=repo.get(task_id)
            if t['status']!='running':
                yield 'event: done\ndata: {}\n\n';break
            yield ': heartbeat\n\n';await asyncio.sleep(1)
    return StreamingResponse(generate(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})

async def read_upload(file):
    content=await file.read(5*1024*1024+1)
    if len(content)>5*1024*1024: raise HTTPException(413,'单个文件限制 5 MB')
    return content

@app.post('/api/quotes/import')
async def import_quotes(file:UploadFile=File(...)):
    try: return {'quotes':parse_quotes(Path(file.filename or '').name,await read_upload(file))}
    except (ValueError,UnicodeError) as e: raise HTTPException(422,str(e))

@app.get('/api/knowledge')
def documents(): return repo.documents()

@app.post('/api/knowledge')
async def knowledge(file:UploadFile=File(...),models:str=Form('')):
    try: docs=parse_knowledge(Path(file.filename or '').name,await read_upload(file),[x.strip() for x in models.split(',') if x.strip()])
    except (ValueError,UnicodeError) as e: raise HTTPException(422,str(e))
    for doc in docs: repo.add_document(doc)
    return {'chunks':len(docs)}

@app.get('/api/knowledge/search')
def search(q:str,model:str|None=None): return kb.search(q,model)

@app.get('/api/tasks/{task_id}/report')
def export(task_id):
    t=require_task(task_id);snap=snapshot(task_id);r=snap.values.get('report')
    if not r: raise HTTPException(409,'报告尚未生成')
    lines=[f"# {t['name']}",f"状态：{t['status']}",f"模式：{snap.values.get('mode')}",r['recommendation'],r['scope'],'']
    if r.get('kind')=='sourcing':
        lines += ['## 确认的目标',json.dumps(r['constraints'],ensure_ascii=False),'## Agent 说明',r['analysis'],'## 分配方案',json.dumps(r['plan'],ensure_ascii=False,indent=2),'## 已评估方案',json.dumps(r['evaluations'],ensure_ascii=False,indent=2),'## 工具行动']
        for event in repo.events(task_id):
            if event['kind'] in ['action','human','plan']:lines += [event['title'],json.dumps(event['detail'],ensure_ascii=False,indent=2)]
    for row in r['rows']:
        lines += [f"## {row['supplier']}",f"型号：{row['model']}；状态：{row['status']}",f"总成本：{row['cost'].get('total')} CNY",f"报价来源：{row['source']}",row['spec_note']]
        for h in row['evidence']: lines.append(f"- {h['title']}，第 {h['page']} 页：{h['text']}")
    return PlainTextResponse('\n\n'.join(lines),headers={'Content-Disposition':f'attachment; filename="report-{task_id}.md"'})

dist=ROOT/'frontend'/'dist'
if dist.exists(): app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
