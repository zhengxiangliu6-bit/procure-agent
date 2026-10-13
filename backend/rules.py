from decimal import Decimal, ROUND_HALF_UP
from .models import Quote, Requirement

def validate(requirement, quotes):
    req=Requirement.model_validate(requirement); issues=[]
    for raw in quotes:
        q=Quote.model_validate(raw)
        for field,label in [('lead_days','交期'),('shipping','运费')]:
            if getattr(q,field) is None:
                issues.append({'quote_id':q.id,'supplier':q.supplier,'field':field,'kind':'missing','message':f'{label}未明确，请补充。','source':q.source})
        if not q.tax_included and q.tax_rate is None:
            issues.append({'quote_id':q.id,'supplier':q.supplier,'field':'tax_rate','kind':'missing','message':'未税报价缺少税率，请补充小数形式税率。','source':q.source})
        if q.moq>req.quantity:
            issues.append({'quote_id':q.id,'supplier':q.supplier,'field':'moq','kind':'constraint','message':f'起订量 {q.moq} 超过需求 {req.quantity}。','source':q.source})
        if q.lead_days is not None and q.lead_days>req.max_lead_days:
            issues.append({'quote_id':q.id,'supplier':q.supplier,'field':'lead_days','kind':'constraint','message':f'交期 {q.lead_days} 天超过要求 {req.max_lead_days} 天。','source':q.source})
        if q.model.upper()!=req.model.upper():
            issues.append({'quote_id':q.id,'supplier':q.supplier,'field':'model','kind':'model','message':'型号与采购需求不同，需要规格依据，不能默认可替代。','source':q.source})
    return issues

def calculate(requirement, raw):
    req=Requirement.model_validate(requirement); q=Quote.model_validate(raw)
    if q.shipping is None or (not q.tax_included and q.tax_rate is None): return {'total':None,'reason':'税费或运费未明确'}
    subtotal=q.price*Decimal(req.quantity)/Decimal(q.price_unit)
    tax=Decimal(0) if q.tax_included else subtotal*q.tax_rate
    money=lambda x: str(x.quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
    return {'subtotal':money(subtotal),'tax':money(tax),'shipping':money(q.shipping),'total':money(subtotal+tax+q.shipping),'currency':'CNY','formula':f'{q.price} × {req.quantity} / {q.price_unit} + 税费 {money(tax)} + 运费 {money(q.shipping)}','tax_note':'单价已含税' if q.tax_included else f'未税单价，税率 {q.tax_rate}'}

def report(requirement, quotes, issues, evidence):
    rows=[]; req=Requirement.model_validate(requirement)
    for q in quotes:
        costs=calculate(requirement,q); qi=[i for i in issues if i['quote_id']==q['id']]
        spec=evidence.get(q['id'],{}); reasons=[i['message'] for i in qi if i['kind']=='constraint']
        if spec.get('compatible') is False: reasons.append('规格证据不满足需求，禁止作为等价型号推荐。')
        unknown=any(i['kind']=='missing' for i in qi) or spec.get('compatible') is None
        status='不满足' if reasons else ('待确认' if unknown else '满足')
        rows.append({**q,'cost':costs,'status':status,'reasons':reasons,'evidence':spec.get('hits',[]),'spec_note':spec.get('note','')})
    eligible=sorted([r for r in rows if r['status']=='满足' and r['cost']['total'] is not None],key=lambda r:Decimal(r['cost']['total']))
    return {'rows':rows,'recommended_id':eligible[0]['id'] if eligible else None,'recommendation':f"在已核验且满足条件的报价中，{eligible[0]['supplier']}总成本最低。" if eligible else '暂无可推荐报价，需要补充资料或重新询价。','scope':'仅比较报价成本与当前明确要求；未评估供应商信用、真伪与完整电气替代性。','demo':any(h.get('demo') for e in evidence.values() for h in e.get('hits',[]))}
