from langgraph.types import Command
from langchain_core.messages import AIMessage
from backend.models import SourcingGoal
from backend.storage import Repository
from backend.retrieval import KnowledgeBase
from backend.sourcing import SourcingGraph, validate_answers
from backend.supplier_market import SimulatedMarket

GOAL='采购 500 个 DEMO-MCU-A，预算 1300 元，14 天内到货。'

def setup(tmp_path,scenario='stockout'):
    repo=Repository(tmp_path);runner=SourcingGraph(repo,KnowledgeBase(repo))
    req={'model':'DEMO-MCU-A','quantity':500,'budget':'1300','max_lead_days':14,'package':'LQFP-48','min_temp':-40,'max_temp':85}
    state={'task_id':repo.create('sourcing',kind='sourcing'),'requirement':req,'scenario':scenario,'allow_alternatives':False,'approved_models':[]}
    market=SimulatedMarket(scenario)
    offers={o['id']:market.quote(o['supplier_id'],o['model'],500) for o in market.offers}
    evidence={oid:runner.inspect(state,o) for oid,o in offers.items()}
    return runner,state,offers,evidence

def test_split_stock_and_independent_shipping(tmp_path):
    r,s,o,e=setup(tmp_path)
    single=r.evaluate(s,[{'offer_id':'green-a','quantity':500}],o,e)
    assert not single['feasible'] and any('库存' in x for x in single['reasons'])
    split=r.evaluate(s,[{'offer_id':'green-a','quantity':280},{'offer_id':'river-a','quantity':220}],o,e)
    assert split['feasible'] and split['total']=='1162.00'
    assert [a['cost']['shipping'] for a in split['allocations']]==['20.00','20.00']
    duplicate=r.evaluate(s,[{'offer_id':'green-a','quantity':250},{'offer_id':'green-a','quantity':250}],o,e)
    assert not duplicate['feasible']

def test_constraints_and_explicit_alternative_approval(tmp_path):
    r,s,o,e=setup(tmp_path,'budget');s['requirement']['budget']='1200'
    direct=r.evaluate(s,[{'offer_id':'green-a','quantity':500}],o,e)
    assert not direct['feasible'] and any('预算' in x for x in direct['reasons'])
    alt=r.evaluate(s,[{'offer_id':'substitute-a2','quantity':500}],o,e)
    assert not alt['feasible'] and any('工程确认' in x for x in alt['reasons'])
    s.update(allow_alternatives=True,approved_models=['DEMO-MCU-A2'])
    assert r.evaluate(s,[{'offer_id':'substitute-a2','quantity':500}],o,e)['feasible']
    assert not r.evaluate(s,[{'offer_id':'substitute-a2','quantity':500}],o,{})['feasible']

def test_demo_missing_goal_and_restart(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT_MODE','demo');r,s,_,_=setup(tmp_path)
    cfg={'configurable':{'thread_id':s['task_id']},'recursion_limit':40}
    r.graph.invoke({'task_id':s['task_id'],'goal':'采购 500 个 DEMO-MCU-A，14 天内到货。','scenario':'stockout'},cfg)
    snap=r.graph.get_state(cfg);assert snap.interrupts[0].value['type']=='goal_clarification'
    assert snap.interrupts[0].value['questions'][0]['field']=='budget'
    r.connection.close();r=SourcingGraph(r.repo,r.knowledge)
    r.graph.invoke(Command(resume={'answers':{'budget':'1300'}}),cfg)
    snap=r.graph.get_state(cfg);assert snap.interrupts[0].value['type']=='review'
    assert snap.values['report']['plan']['total']=='1162.00'
    r.graph.invoke(Command(resume={'approved':True}),cfg)
    assert r.graph.get_state(cfg).values['approved'] is True

def test_model_adapts_after_stock_failure_and_checkpoint(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT_MODE','live');r,s,_,_=setup(tmp_path)
    import backend.model_config
    class Fake:
        def with_structured_output(self,*a,**kw):return self
        def bind_tools(self,tools):return self
        def invoke(self,messages):
            if '从用户采购目标' in messages[0].content:return SourcingGoal.model_validate(s['requirement'])
            tool_messages=[m for m in messages if m.type=='tool']
            def response(calls):return AIMessage(content='',tool_calls=[{'name':n,'args':a,'id':f'{len(tool_messages)}-{i}','type':'tool_call'} for i,(n,a) in enumerate(calls)])
            if not tool_messages:return response([('search_suppliers',{'model':'DEMO-MCU-A'})])
            if len(tool_messages)==1:return response([('request_quote',{'supplier_id':sid,'model':'DEMO-MCU-A','quantity':500}) for sid in ['green','river']])
            if len(tool_messages)==3:return response([('inspect_offer',{'offer_id':oid}) for oid in ['green-a','river-a']])
            if len(tool_messages)==5:return response([('evaluate_plan',{'allocations':[{'offer_id':'green-a','quantity':500}]})])
            if len(tool_messages)==6:
                assert '库存' in tool_messages[-1].content
                return response([('evaluate_plan',{'allocations':[{'offer_id':'green-a','quantity':280},{'offer_id':'river-a','quantity':220}]})])
            assert '"feasible": true' in tool_messages[-1].content
            return response([('finish_sourcing',{'plan_id':'plan-2','summary':'单家缺货，改为拆单。'})])
    monkeypatch.setattr(backend.model_config,'build_model',lambda:Fake())
    cfg={'configurable':{'thread_id':s['task_id']},'recursion_limit':40}
    r.graph.invoke({'task_id':s['task_id'],'goal':GOAL,'scenario':'stockout'},cfg)
    snap=r.graph.get_state(cfg)
    assert snap.values['report']['plan']['total']=='1162.00'
    assert len(snap.values['evaluations'])==2 and not snap.values['evaluations'][0]['feasible']
    assert len([e for e in r.repo.events(s['task_id']) if e['kind']=='model'])==6

def test_human_cannot_patch_unrequested_constraints(tmp_path):
    _,s,_,_=setup(tmp_path)
    s['pending']={'questions':[{'field':'budget'}]}
    import pytest
    with pytest.raises(ValueError):validate_answers(s,{'budget':'2000','max_lead_days':99})
    with pytest.raises(ValueError):validate_answers(s,{'budget':'-1'})

def test_negotiated_price_requires_order_threshold(tmp_path):
    r,s,o,e=setup(tmp_path,'balanced')
    negotiated=SimulatedMarket('balanced').negotiate('green-a',500)['quote']
    assert negotiated['moq']==500
    o['green-a']=negotiated
    s['requirement']['quantity']=100
    result=r.evaluate(s,[{'offer_id':'green-a','quantity':100}],o,e)
    assert not result['feasible'] and any('起订量' in x for x in result['reasons'])

def test_sourcing_api_resume_and_export(monkeypatch):
    import time
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setenv('AGENT_MODE','demo')
    with TestClient(app) as client:
        response=client.post('/api/sourcing',json={'goal':'采购 500 个 DEMO-MCU-A，14 天内到货。','scenario':'stockout'})
        assert response.status_code==200
        tid=response.json()['id']
        def wait():
            end=time.monotonic()+8
            while time.monotonic()<end:
                d=client.get('/api/tasks/'+tid).json()
                if d['status']!='running':return d
                time.sleep(.02)
            raise AssertionError('task timeout')
        task=wait();assert task['kind']=='sourcing' and task['status']=='awaiting_clarification'
        url=f'/api/tasks/{tid}/resume'
        assert client.post(url,json={'expected_checkpoint':'old','answers':{'budget':1300}}).status_code==409
        assert client.post(url,json={'expected_checkpoint':task['checkpoint'],'answers':{'budget':1300,'max_lead_days':50}}).status_code==422
        assert client.post(url,json={'expected_checkpoint':task['checkpoint'],'answers':{'budget':1300}}).status_code==200
        task=wait();assert task['state']['report']['plan']['total']=='1162.00'
        exported=client.get(f'/api/tasks/{tid}/report');assert exported.status_code==200
        assert '1162.00' in exported.text and '工具行动' in exported.text

def test_locked_budget_cannot_be_relaxed_by_model(tmp_path,monkeypatch):
    r,s,o,e=setup(tmp_path,'budget')
    s.update(goal=GOAL,mode='live',round=0,offers=o,evidence=e,evaluations=[],messages=[],locked_fields=['budget'])
    class Fake:
        def bind_tools(self,tools):return self
        def invoke(self,messages):return AIMessage(content='',tool_calls=[{'name':'ask_user','args':{'field':'budget','reason':'提高预算'},'id':'lock','type':'tool_call'}])
    import backend.model_config
    monkeypatch.setattr(backend.model_config,'build_model',lambda:Fake())
    result=r.decide(s)
    assert not result.get('pending') and '固定' in r.repo.events(s['task_id'])[-1]['detail']['result']['error']

def test_history_snapshot_does_not_wait_for_model_request(tmp_path,monkeypatch):
    import threading
    from types import SimpleNamespace
    from backend import main
    repo=Repository(tmp_path);tid=repo.create('slow-model')
    started=threading.Event();release=threading.Event();read_done=threading.Event()
    class SlowGraph:
        def invoke(self,*args):started.set();release.wait(3)
        def get_state(self,*args):return SimpleNamespace(interrupts=(),values={'approved':False})
    monkeypatch.setattr(main,'repo',repo);monkeypatch.setattr(main,'engine',SimpleNamespace(graph=SlowGraph()))
    worker=threading.Thread(target=main.run,args=(tid,{}));worker.start()
    assert started.wait(1)
    reader=threading.Thread(target=lambda:(main.snapshot(tid),read_done.set()));reader.start()
    try:assert read_done.wait(1),'历史读取被模型请求的整任务锁阻塞'
    finally:release.set();worker.join();reader.join()
