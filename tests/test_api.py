import importlib
import time
from fastapi.testclient import TestClient
from backend.storage import Repository
from backend.retrieval import KnowledgeBase
from backend.graph import ProcurementGraph

def wait(client,tid):
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        d=client.get('/api/tasks/'+tid).json()
        if d['status']!='running': return d
        time.sleep(.02)
    raise AssertionError('task timeout')

def test_api_full_lifecycle_and_resume_validation(tmp_path,monkeypatch):
    monkeypatch.setenv('PROCURE_DATA_DIR',str(tmp_path));monkeypatch.setenv('AGENT_MODE','demo')
    main=importlib.import_module('backend.main')
    with TestClient(main.app) as client:
        assert client.get('/api/health').json()['mode']=='demo'
        tid=client.post('/api/demo').json()['id']
        d=wait(client,tid);assert d['status']=='awaiting_clarification'
        assert client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':'stale','patches':{'q2':{'shipping':'15'}}}).status_code==409
        assert client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':d['checkpoint'],'patches':{'q2':{'shipping':'-1'}}}).status_code==422
        assert client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':d['checkpoint'],'patches':{'q2':{'shipping':'15','price':'0'}}}).status_code==422
        r=client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':d['checkpoint'],'patches':{'q2':{'shipping':'15'}}})
        assert r.status_code==200
        d=wait(client,tid);assert d['status']=='awaiting_review'
        assert d['state']['report']['recommended_id']=='q1'
        assert d['state']['report']['rows'][2]['status']=='不满足'
        assert client.get('/api/tasks/'+tid+'/report').status_code==200
        assert client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':d['checkpoint'],'approved':True}).status_code==200
        d=wait(client,tid);assert d['status']=='completed'
        assert client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':d['checkpoint'],'approved':True}).status_code==409
        assert client.get('/api/tasks/'+tid+'/events').status_code==200

def test_live_tool_loop_without_external_credentials(tmp_path,monkeypatch):
    from langchain_core.messages import AIMessage
    import langchain_anthropic
    monkeypatch.setenv('AGENT_MODE','live');monkeypatch.setenv('ANTHROPIC_API_KEY','test-not-a-real-key')
    calls=[]
    class FakeModel:
        def __init__(self,**kw): self.step=0
        def bind_tools(self,tools): calls.extend(t.name for t in tools);return self
        def invoke(self,messages):
            self.step+=1
            if self.step==1: return AIMessage(content='',tool_calls=[{'name':'read_quotes','args':{},'id':'1','type':'tool_call'}])
            if self.step==2: return AIMessage(content='',tool_calls=[{'name':'search_specs','args':{'quote_id':'a'},'id':'2','type':'tool_call'},{'name':'calculate_cost','args':{'quote_id':'a'},'id':'3','type':'tool_call'}])
            assert any(getattr(m,'tool_call_id',None)=='2' for m in messages)
            return AIMessage(content='根据 demo-a，封装与温度符合；总价 1195 元。')
    monkeypatch.setattr(langchain_anthropic,'ChatAnthropic',FakeModel)
    repo=Repository(tmp_path);engine=ProcurementGraph(repo,KnowledgeBase(repo))
    from backend.models import Requirement,Quote
    result=engine.analyze({'task_id':repo.create('mock-live'),'requirement':Requirement().model_dump(),'quotes':[Quote(id='a',supplier='A',model='DEMO-MCU-A',price='2.35',lead_days=10,shipping='20').model_dump(mode='json')],'issues':[]})
    assert result['mode']=='live' and result['evidence']['a']['compatible'] is True
    assert 'calculate_cost' in calls
