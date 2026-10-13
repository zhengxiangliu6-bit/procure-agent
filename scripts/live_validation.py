"""Authorized API validation with a credential read only from hidden stdin.
Run from the repository: python -m scripts.live_validation [--serve]
Reports contain synthetic data, provider errors redacted, and no secrets.
"""
import argparse
import getpass
import json
import os
import re
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
def safe_error(exc,key):
    body=getattr(exc,'body',None)
    text=json.dumps(body,ensure_ascii=False,default=str) if body else str(exc)
    text=text.replace(key,'[REDACTED]')
    text=re.sub(r'sk-[a-zA-Z0-9_-]+','[REDACTED]',text)
    return {'class':type(exc).__name__,'http_status':getattr(exc,'status_code',None),'message':text[:1500]}

def wait_task(client,tid,seconds=360):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        result=client.get('/api/tasks/'+tid).json()
        if result['status']!='running': return result
        time.sleep(.2)
    raise TimeoutError('Agent task exceeded test deadline')

def main():
    args=argparse.ArgumentParser();args.add_argument('--serve',action='store_true'); options=args.parse_args()
    key=getpass.getpass('Test API key (hidden): ')
    os.environ.update(AGENT_MODE='live',AGENT_PROVIDER='openai',AGENT_MODEL='glm-5.2',MODEL_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1',MODEL_API_KEY=key,LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',PROCURE_DATA_DIR=str(ROOT/'data-live-validation'))
    from backend.model_config import build_model
    result={'started':datetime.now(timezone.utc).isoformat(),'model':'glm-5.2','base_url':os.environ['MODEL_BASE_URL'],'dataset':'explicitly synthetic DEMO-MCU parts, not market quotes','checks':[],'issues':[]}
    live_ok=False
    # First request uses exactly the caller's requested model/provider/base URL.
    try:
        started=time.monotonic(); response=build_model().invoke('仅回复：连接成功')
        result['checks'].append({'name':'basic_model_call','status':'passed','seconds':round(time.monotonic()-started,2),'content':str(response.content)[:300],'usage':response.usage_metadata})
        live_ok=True
    except Exception as exc:
        result['checks'].append({'name':'basic_model_call','status':'failed',**safe_error(exc,key)})
        result['issues'].append('指定模型接口基础调用失败，跳过需要真实模型的 Agent 测试；未擅自更换模型或接入地址。')
    print(json.dumps(result['checks'][-1],ensure_ascii=False),flush=True)
    from fastapi.testclient import TestClient
    from backend import main as server
    client=TestClient(server.app)
    if live_ok:
        scenarios=[
          {'name':'complete_quote_tool_loop','quotes':[
            {'id':'q1','supplier':'模拟供应商 A','model':'DEMO-MCU-A','price':'2.35','shipping':'20','lead_days':10},
            {'id':'q2','supplier':'模拟供应商 B','model':'DEMO-MCU-A','price':'210','price_unit':100,'tax_included':False,'tax_rate':'.13','shipping':'15','lead_days':12},
            {'id':'q3','supplier':'模拟供应商 C','model':'DEMO-MCU-B','price':'1.80','shipping':'0','lead_days':7}], 'expected':'q1'},
          {'name':'unknown_specs_no_recommendation','quotes':[{'id':'q1','supplier':'模拟供应商 D','model':'UNKNOWN-PART','price':'1.0','shipping':'0','lead_days':5}], 'requirement':{'model':'UNKNOWN-PART'},'expected':None},
        ]
        for scenario in scenarios:
            started=time.monotonic()
            try:
                r=client.post('/api/tasks',json={'name':scenario['name'],'requirement':scenario.get('requirement',{}),'quotes':scenario['quotes']})
                r.raise_for_status();tid=r.json()['id']; task=wait_task(client,tid)
                if task['status']!='awaiting_review': raise RuntimeError(task.get('error') or task['status'])
                assert task['state']['report']['recommended_id']==scenario['expected']
                events=task['events'];model_steps=[e['detail'] for e in events if e['kind']=='model']
                agent_events=[e['detail'] for e in events if e['title']=='分析完成']
                assert model_steps and agent_events[0]['tool_calls'], 'No genuine model tool calls occurred'
                approval=client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':task['checkpoint'],'approved':True});approval.raise_for_status()
                final=wait_task(client,tid);assert final['status']=='completed'
                result['checks'].append({'name':scenario['name'],'status':'passed','task_id':tid,'seconds':round(time.monotonic()-started,2),'model_steps':model_steps,'tools':agent_events[0]['tool_calls'],'analysis':task['state']['analysis'],'report':task['state']['report']})
            except Exception as exc:
                result['checks'].append({'name':scenario['name'],'status':'failed',**safe_error(exc,key)})
            print(json.dumps({k:v for k,v in result['checks'][-1].items() if k not in ['report','analysis']},ensure_ascii=False),flush=True)
        try:
            tid=client.post('/api/demo').json()['id']; task=wait_task(client,tid)
            assert task['status']=='awaiting_clarification'
            r=client.post('/api/tasks/'+tid+'/resume',json={'expected_checkpoint':task['checkpoint'],'patches':{'q2':{'shipping':'15'}}});r.raise_for_status()
            task=wait_task(client,tid);assert task['status']=='awaiting_review'
            assert task['state']['report']['rows'][2]['status']=='不满足'
            result['checks'].append({'name':'clarification_resume_real_model','status':'passed','task_id':tid,'analysis':task['state']['analysis']})
        except Exception as exc: result['checks'].append({'name':'clarification_resume_real_model','status':'failed',**safe_error(exc,key)})
        print(json.dumps(result['checks'][-1],ensure_ascii=False),flush=True)
    else:
        for name in ['complete_quote_tool_loop','unknown_specs_no_recommendation','clarification_resume_real_model']:
            result['checks'].append({'name':name,'status':'skipped','reason':'基础 API 调用失败'})
    result['finished']=datetime.now(timezone.utc).isoformat()
    target=ROOT/'LIVE_TEST_RESULTS.json';target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Sanitized report: '+str(target),flush=True)
    if options.serve and live_ok:
        import uvicorn
        print('Live UI: http://127.0.0.1:8011',flush=True)
        uvicorn.run(server.app,host='127.0.0.1',port=8011)

if __name__=='__main__': main()
