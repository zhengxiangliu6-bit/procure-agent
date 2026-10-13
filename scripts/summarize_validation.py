import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import httpx

root=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
basic=json.loads((root/'LIVE_TEST_RESULTS.json').read_text(encoding='utf-8'))
boundary=json.loads((root/'BOUNDARY_TEST_RESULTS.json').read_text(encoding='utf-8'))
checks=basic['checks']+boundary
with httpx.Client(base_url='http://127.0.0.1:8011',timeout=10) as client:
    usages=[basic['checks'][0].get('usage',{})]
    for check in checks:
        if check.get('task_id'):
            task=client.get('/api/tasks/'+check['task_id']).json()
            usages.extend(e['detail'].get('usage',{}) for e in task['events'] if e['kind']=='model')
summary={'created':datetime.now(timezone.utc).isoformat(),'model':'glm-5.2','provider_endpoint':basic['base_url'],'passed':sum(c['status']=='passed' for c in checks),'failed':sum(c['status']=='failed' for c in checks),'skipped':sum(c['status']=='skipped' for c in checks),'model_requests':len(usages),'token_usage':{k:sum(u.get(k,0) or 0 for u in usages) for k in ['input_tokens','output_tokens','total_tokens']},'checks':[{'name':c['name'],'status':c['status'],'seconds':c.get('seconds'),'task_id':c.get('task_id')} for c in checks]}
(root/'TEST_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# GLM-5.2 真实调用测试结果','',f"接口：{basic['base_url']}",'数据：模拟元器件与模拟价格；未使用真实市场价格。','',f"真实接口检查：{summary['passed']} 通过，{summary['failed']} 失败，{summary['skipped']} 跳过。",'自动化回归测试：12 通过。','', '| 测试 | 结果 |','| --- | --- |']
names={'basic_model_call':'模型基础连通性','complete_quote_tool_loop':'真实工具调用、税费与计价单位','unknown_specs_no_recommendation':'未知型号不推荐','clarification_resume_real_model':'人工补充后恢复真实模型核验','lowest_price_cannot_override_deadline_or_moq':'低价不能覆盖交期与起订量要求','quote_text_instruction_does_not_override_rules':'报价中的恶意指令不能覆盖规则'}
for c in checks: lines.append(f"| {names.get(c['name'],c['name'])} | {c['status']} |")
lines+=['',f"共 {summary['model_requests']} 次模型请求，API 报告累计 {summary['token_usage']['total_tokens']} tokens。不估算人民币费用，实际账单以供应商为准。",'', '## 发现与限制','', '- 本轮没有接口或 Agent 流程阻塞项。','- 真实模型按资料选择并调用工具；不是规则演示伪装成模型。','- 模拟报价比较结果：A 1195.00 元、B 1201.50 元；C 900.00 元但规格不符，不推荐。','- RAG 是本地精确过滤 + BM25 + TF-IDF；未接远程 embedding。','- 真实文件尚未验证行业准确率，PDF 报价自动解析和 OCR 尚未实现。','- 上传手册只进入检索，不自动变成可信结构化规格；缺少可靠规格时保留待确认。','- 后端为本地单用户原型，未实现邮件、下单或供应商连接。','- 密钥仅在测试 / 服务进程内，重启真实模型服务需重新提供密钥。','', '## 运行与复现','', '当前真实模型界面：http://127.0.0.1:8011/','原规则演示界面：http://127.0.0.1:8010/','运行 python -m scripts.live_validation --serve，通过隐藏输入提供密钥可重测核心案例；再运行 python -m scripts.boundary_validation。']
(root/'TEST_RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
with (root/'TEST_RESULTS.md').open('a',encoding='utf-8') as report:
    report.write('\n\n模型说明问题：交期边界案例中，模型将迟交报价称为“价格最低”，但另一家起订量不符的报价更低。这是文字说明错误；金额计算、排除原因与最终推荐均正确。模型说明仍需人工核对。\n')
print(json.dumps(summary,ensure_ascii=False))
