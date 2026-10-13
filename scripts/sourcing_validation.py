"""Exercise the running live Agent with synthetic supplier scenarios, no secrets."""
import json
import sys
import time
from pathlib import Path
import httpx
import argparse
from decimal import Decimal

sys.stdout.reconfigure(encoding='utf-8')
ROOT=Path(__file__).resolve().parents[1]

def run_case(client,name,goal,scenario,accept_alt=True,missing=None):
    start=time.monotonic();tid=client.post('/api/sourcing',json={'goal':goal,'scenario':scenario}).raise_for_status().json()['id']
    decisions=[];end=start+420
    while time.monotonic()<end:
        task=client.get('/api/tasks/'+tid).raise_for_status().json()
        if task['status']=='running':time.sleep(.5);continue
        if task['status']=='awaiting_clarification':
            request=task['interrupt'];answers={}
            for q in request['questions']:
                key=q['field']
                if key=='allow_alternatives':answers[key]=accept_alt
                else:answers[key]=(missing or {}).get(key,task['state']['requirement'].get(key))
            decisions.append({'request':request,'answers':answers})
            if len(decisions)>4:raise AssertionError('Repeated human decision loop')
            client.post(f'/api/tasks/{tid}/resume',json={'expected_checkpoint':task['checkpoint'],'answers':answers}).raise_for_status()
            continue
        assert task['status']=='awaiting_review',task.get('error') or task['status']
        r=task['state']['report'];plan=r['plan'];actions=[e['detail']['tool'] for e in task['events'] if e['kind']=='action']
        assert task['state']['mode']=='live'
        assert actions and any(e['kind']=='model' for e in task['events'])
        if name in ['normal','stock_split','budget_alternative','missing_goal']:
            assert plan and plan['quantity']==500 and plan['feasible'],r['analysis']
        if name=='normal':assert plan['total']=='1195.00',plan
        if name=='stock_split':assert len(plan['allocations'])==2 and plan['total']=='1162.00',plan
        if name=='budget_alternative':
            assert any(d['answers'].get('allow_alternatives') is True for d in decisions)
            assert any(a['model']=='DEMO-MCU-A2' for a in plan['allocations'])
        if name in ['reject_alternative','impossible']:
            assert plan is None
            assert Decimal(task['state']['requirement']['budget']) in [Decimal('1200'),Decimal('1300')]
            assert task['state']['requirement']['max_lead_days']==14
        client.post(f'/api/tasks/{tid}/resume',json={'expected_checkpoint':task['checkpoint'],'approved':True,'note':'自动化测试确认，仅为模拟报告。'}).raise_for_status()
        return {'name':name,'status':'passed','task_id':tid,'seconds':round(time.monotonic()-start,2),'tools':actions,'decisions':decisions,'report':r,'model_usage':[e['detail'].get('usage',{}) for e in task['events'] if e['kind']=='model']}
    raise TimeoutError('Live sourcing task timed out')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--only',nargs='*');options=parser.parse_args()
    target=ROOT/'SOURCING_TEST_RESULTS.json'
    checks=json.loads(target.read_text(encoding='utf-8')) if options.only and target.exists() else []
    with httpx.Client(base_url='http://127.0.0.1:8011',timeout=15) as client:
        assert client.get('/api/health').json()['live_configured']
        cases=[
            ('normal','采购 500 个 DEMO-MCU-A，预算 1300 元，14 天内到货。请优先核验原型号，不满足时再调整策略。','balanced',True,None),
            ('stock_split','采购 500 个 DEMO-MCU-A，预算 1300 元，14 天内到货。优先原型号，单家缺货时可拆单，不优先使用替代。','stockout',True,None),
            ('budget_alternative','采购 500 个 DEMO-MCU-A，固定预算 1200 元，14 天内到货。超预算时先议价，再寻找候选替代并让我确认。','budget',True,None),
            ('reject_alternative','采购 500 个 DEMO-MCU-A，固定预算 1200 元，14 天内到货。先议价，再寻找候选替代并让我确认；不能满足就报告障碍。','budget',False,None),
            ('impossible','采购 500 个 DEMO-MCU-A，固定预算 1300 元，14 天内到货。不能满足就说明障碍，不可自行改变条件。','impossible',False,None),
            ('missing_goal','采购 500 个 DEMO-MCU-A，14 天内到货。请寻找满足目标的方案。','balanced',True,{'budget':'1300'}),
        ]
        for args in cases:
            if options.only and args[0] not in options.only:continue
            try:result=run_case(client,*args)
            except Exception as exc:result={'name':args[0],'status':'failed','error':type(exc).__name__,'message':str(exc)[:1000]}
            checks=[c for c in checks if c['name']!=args[0]]+[result]
            (ROOT/'SOURCING_TEST_RESULTS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k not in ['report','model_usage']},ensure_ascii=False),flush=True)
    if any(c['status']!='passed' for c in checks):raise SystemExit(1)

if __name__=='__main__':main()
