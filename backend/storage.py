import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat()

class Repository:
    def __init__(self, root):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'business.sqlite'
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, name TEXT, status TEXT, created TEXT, updated TEXT, error TEXT);
            CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT, title TEXT, detail TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, payload TEXT);''')
            if 'kind' not in [r['name'] for r in c.execute('PRAGMA table_info(tasks)')]:
                c.execute("ALTER TABLE tasks ADD COLUMN kind TEXT NOT NULL DEFAULT 'verification'")
            c.execute("UPDATE tasks SET status='interrupted',error='服务重启，点击恢复执行从检查点继续' WHERE status='running'")
        self.seed()

    def connect(self):
        c=sqlite3.connect(self.path,timeout=20); c.row_factory=sqlite3.Row
        c.execute('PRAGMA journal_mode=WAL'); return c

    def seed(self):
        docs=[
            {'id':'demo-a','title':'DEMO-MCU-A 模拟规格书','models':['DEMO-MCU-A'],'page':1,'chunk':0,'demo':True,'text':'DEMO-MCU-A 模拟元器件。封装 LQFP-48。工作温度 -40 至 85 摄氏度。仅为评估用模拟资料，不代表真实产品。','specs':{'package':'LQFP-48','min_temp':-40,'max_temp':85}},
            {'id':'demo-b','title':'DEMO-MCU-B 模拟规格书','models':['DEMO-MCU-B'],'page':1,'chunk':0,'demo':True,'text':'DEMO-MCU-B 模拟元器件。封装 QFN-32。工作温度 0 至 70 摄氏度。不满足 DEMO-MCU-A 的 LQFP-48 封装和 -40 至 85 摄氏度要求。','specs':{'package':'QFN-32','min_temp':0,'max_temp':70}},
            {'id':'policy','title':'演示采购核验规则','models':[],'page':1,'chunk':0,'demo':True,'text':'报价须明确税费、运费与交期。型号不同不能按字符串相似度认定可替代。资料不足时应暂停澄清，不应按零运费或零税率计算。','specs':{}}
        ]
        docs.append({'id':'demo-a2','title':'DEMO-MCU-A2 模拟候选规格书','models':['DEMO-MCU-A2'],'page':1,'chunk':0,'demo':True,'text':'DEMO-MCU-A2 模拟候选。LQFP-48，-40 至 85 摄氏度；模拟数据声明引脚与电气条件可替代 DEMO-MCU-A，仅用于演示。仍须由采购人员取得工程确认，不能用于真实器件。','specs':{'package':'LQFP-48','min_temp':-40,'max_temp':85,'equivalent_to':['DEMO-MCU-A']}})
        with self.connect() as c:
            for d in docs: c.execute('INSERT OR IGNORE INTO documents VALUES (?,?)',(d['id'],json.dumps(d,ensure_ascii=False)))

    def add_document(self,payload):
        with self.connect() as c: c.execute('INSERT INTO documents VALUES (?,?)',(payload['id'],json.dumps(payload,ensure_ascii=False)))

    def documents(self):
        with self.connect() as c: return [json.loads(r['payload']) for r in c.execute('SELECT payload FROM documents')]

    def create(self,name,kind='verification'):
        task_id=uuid.uuid4().hex
        with self.connect() as c: c.execute('INSERT INTO tasks(id,name,status,created,updated,error,kind) VALUES (?,?,?,?,?,?,?)',(task_id,name,'running',now(),now(),None,kind))
        return task_id

    def update(self,task_id,status,error=None):
        with self.connect() as c: c.execute('UPDATE tasks SET status=?,updated=?,error=? WHERE id=?',(status,now(),error,task_id))

    def get(self,task_id):
        with self.connect() as c:
            r=c.execute('SELECT * FROM tasks WHERE id=?',(task_id,)).fetchone()
            return dict(r) if r else None

    def list(self):
        with self.connect() as c: return [dict(r) for r in c.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]

    def event(self,task_id,kind,title,detail):
        with self.connect() as c: c.execute('INSERT INTO events(task_id,kind,title,detail,created) VALUES (?,?,?,?,?)',(task_id,kind,title,json.dumps(detail,ensure_ascii=False,default=str),now()))

    def events(self,task_id,after=0):
        with self.connect() as c:
            return [{**dict(r),'detail':json.loads(r['detail'])} for r in c.execute('SELECT * FROM events WHERE task_id=? AND id>? ORDER BY id',(task_id,after))]

