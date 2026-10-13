"""Deterministic simulated supplier adapters; no external RFQs or transactions."""
from decimal import Decimal

SCENARIOS = {
    'balanced': [('green','青禾电子', '2.35',600,10,1,'20','2.20'),('fast','迅达元件','2.70',800,3,1,'25',None),('late','低价慢交供应商','0.80',900,30,1,'0',None),('bulk','大批量供应商','1.50',2000,8,1000,'20',None)],
    'stockout': [('green','青禾电子','2.20',280,8,50,'20',None),('river','远川科技','2.30',260,10,50,'20',None),('late','延期到货供应商','1.60',1000,30,1,'15',None)],
    'budget': [('green','青禾电子','2.80',800,10,1,'20','2.60'),('fast','迅达元件','3.10',800,5,1,'25',None)],
    'impossible': [('green','青禾电子','3.50',700,10,1,'20',None),('late','延期到货供应商','1.50',1000,35,1,'20',None)],
}

class SimulatedMarket:
    def __init__(self,scenario):
        self.scenario=scenario
        self.offers=[]
        for sid,name,price,stock,days,moq,shipping,floor in SCENARIOS[scenario]:
            self.offers.append(dict(id=sid+'-a',supplier_id=sid,supplier=name+'（模拟）',model='DEMO-MCU-A',price=price,stock=stock,lead_days=days,moq=moq,shipping=shipping,floor=floor,price_unit=1,tax_included=True,currency='CNY',source=f'模拟供应商接口 / {scenario} / {sid}-a'))
        if scenario!='impossible':
            self.offers.append(dict(id='substitute-a2',supplier_id='substitute',supplier='替代元件供应商（模拟）',model='DEMO-MCU-A2',price='2.05',stock=700,lead_days=7,moq=1,shipping='25',floor=None,price_unit=1,tax_included=True,currency='CNY',source=f'模拟供应商接口 / {scenario} / substitute-a2'))

    def search(self,model):
        return [{'supplier_id':o['supplier_id'],'supplier':o['supplier'],'model':o['model'],'stock':o['stock'],'lead_days':o['lead_days'],'moq':o['moq']} for o in self.offers if o['model'].upper()==model.upper()]

    def quote(self,supplier_id,model,quantity):
        offer=next((o for o in self.offers if o['supplier_id']==supplier_id and o['model'].upper()==model.upper()),None)
        if not offer: return {'error':'供应商没有该型号；请先搜索供应商'}
        return {**{k:v for k,v in offer.items() if k!='floor'},'requested_quantity':quantity,'quote_notice':'库存为有限数量；本报价不会预留库存，不是实际采购承诺。'}

    def negotiate(self,offer_id,quantity):
        offer=next((o for o in self.offers if o['id']==offer_id),None)
        if not offer:return {'error':'报价不存在'}
        if not offer['floor'] or quantity<500:return {'accepted':False,'reason':'模拟供应商拒绝降价，当前没有可用阶梯折扣。'}
        if quantity>offer['stock']:return {'accepted':False,'reason':'库存不足以满足议价订单数量。'}
        return {'accepted':True,'quote':{**{k:v for k,v in offer.items() if k!='floor'},'price':offer['floor'],'moq':max(500,offer['moq']),'source':offer['source']+' / 模拟议价回复 / 阶梯价至少500个'},'notice':'至少500个的订单适用阶梯价。仅生成模拟回复，未联系真实供应商。'}

    def alternatives(self,model):
        if model.upper()=='DEMO-MCU-A':
            return [{'model':'DEMO-MCU-A2','relationship':'模拟手册定义的同系列候选；须检索规格并取得工程确认','source':'demo-a2'}] if self.scenario!='impossible' else [{'model':'DEMO-MCU-B','relationship':'候选型号，封装不一致，必须核验','source':'demo-b'}]
        return []
