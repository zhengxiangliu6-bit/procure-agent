from decimal import Decimal
from langgraph.types import Command
from backend.storage import Repository
from backend.retrieval import KnowledgeBase
from backend.graph import ProcurementGraph
from backend.models import Quote, Requirement
from backend.rules import calculate, report, validate
from backend.parsing import parse_quotes, parse_knowledge

def quote(**kw):
    return Quote(id='a',supplier='模拟 A',model='DEMO-MCU-A',price='2.35',shipping='20',lead_days=10,**kw).model_dump(mode='json')

def test_decimal_and_price_unit():
    req=Requirement().model_dump()
    assert calculate(req,quote())['total']=='1195.00'
    q=Quote(id='b',supplier='B',model='DEMO-MCU-A',price='210',price_unit=100,shipping='15',tax_included=False,tax_rate='.13',lead_days=12).model_dump(mode='json')
    assert calculate(req,q)['total']=='1201.50'

def test_unknown_shipping_is_not_zero():
    q=quote(); q['shipping']=None
    assert calculate(Requirement().model_dump(),q)['total'] is None
    assert validate(Requirement().model_dump(),[q])[0]['field']=='shipping'

def test_restart_and_review(tmp_path,monkeypatch):
    monkeypatch.setenv('AGENT_MODE','demo')
    repo=Repository(tmp_path);kb=KnowledgeBase(repo);runner=ProcurementGraph(repo,kb)
    tid=repo.create('restart');cfg={'configurable':{'thread_id':tid}}
    q=quote();q['shipping']=None
    runner.graph.invoke({'task_id':tid,'requirement':Requirement().model_dump(),'quotes':[q]},cfg)
    assert runner.graph.get_state(cfg).interrupts[0].value['type']=='clarification'
    runner.connection.close()
    runner=ProcurementGraph(repo,kb)
    runner.graph.invoke(Command(resume={'patches':{'a':{'shipping':'20'}}}),cfg)
    state=runner.graph.get_state(cfg)
    assert state.interrupts[0].value['type']=='review'
    assert state.values['report']['recommended_id']=='a'
    runner.graph.invoke(Command(resume={'approved':True,'note':'已核验'}),cfg)
    assert not runner.graph.get_state(cfg).interrupts
    assert runner.graph.get_state(cfg).values['approved'] is True

def test_wrong_model_retrieval_and_exclusion(tmp_path):
    repo=Repository(tmp_path); kb=KnowledgeBase(repo);runner=ProcurementGraph(repo,kb)
    q=quote();q.update(model='DEMO-MCU-B',price='1.80')
    req=Requirement().model_dump()
    evidence=runner.spec_check({'requirement':req},q)
    assert evidence['compatible'] is False
    assert all('DEMO-MCU-B' in h['models'] for h in evidence['hits'])
    r=report(req,[q],validate(req,[q]),{'a':evidence})
    assert r['recommended_id'] is None
    assert r['rows'][0]['status']=='不满足'

def test_matching_model_without_evidence_not_recommended(tmp_path):
    repo=Repository(tmp_path);runner=ProcurementGraph(repo,KnowledgeBase(repo))
    req=Requirement(model='UNKNOWN').model_dump();q=quote();q['model']='UNKNOWN'
    evidence=runner.spec_check({'requirement':req},q)
    assert evidence['compatible'] is None
    assert report(req,[q],[],{'a':evidence})['recommended_id'] is None

def test_import_and_source():
    data='供应商,型号,单价,交期,含税,运费\nA,DEMO-MCU-A,2.35,10,是,20\n'.encode()
    rows=parse_quotes('sample.csv',data)
    assert rows[0]['source']=='sample.csv 第2行'
    assert rows[0]['tax_included'] is True

def test_knowledge_upload_provenance():
    docs=parse_knowledge('spec.txt','温度条件 -40 至 85'.encode(),['PART-X'])
    assert docs[0]['models']==['PART-X']
    assert docs[0]['page']==1 and docs[0]['demo'] is False

def test_hard_deadline_not_overridden_by_low_cost():
    q=quote();q['lead_days']=30
    req=Requirement().model_dump(); issues=validate(req,[q])
    r=report(req,[q],issues,{'a':{'compatible':True,'hits':[]}})
    assert r['rows'][0]['status']=='不满足' and r['recommended_id'] is None

