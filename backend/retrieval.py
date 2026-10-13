"""Local hybrid retrieval: exact model filter + BM25 + character TF-IDF cosine.
No remote embeddings required. Every hit preserves its source/page/chunk identity.
"""
import math
import re
from collections import Counter
from langchain_core.documents import Document

def terms(text):
    tokens = re.findall(r'[a-zA-Z0-9_-]+|[\u4e00-\u9fff]', text.lower())
    return tokens

class KnowledgeBase:
    def __init__(self, repository):
        self.repository = repository

    def search(self, query, model=None, limit=4):
        rows = self.repository.documents()
        if model:
            rows = [x for x in rows if model.upper() in [m.upper() for m in x['models']]]
        if not rows:
            return []
        documents = [Document(page_content=x['text'], metadata={k:v for k,v in x.items() if k != 'text'}) for x in rows]
        counts = [Counter(terms(x.page_content)) for x in documents]
        q = Counter(terms(query))
        n = len(counts)
        df = Counter(t for c in counts for t in c)
        avg = sum(sum(c.values()) for c in counts) / max(1,n)
        def tfidf(c):
            return {t:(1+math.log(v))*(1+math.log((n+1)/(df[t]+1))) for t,v in c.items()}
        qv = tfidf(q)
        qnorm = math.sqrt(sum(v*v for v in qv.values()))
        hits=[]
        for doc,c in zip(documents, counts):
            length=sum(c.values())
            bm=sum(math.log(1+(n-df[t]+.5)/(df[t]+.5))*c[t]*2.2/(c[t]+1.2*(.25+.75*length/max(1,avg))) for t in q if c[t])
            dv=tfidf(c); norm=math.sqrt(sum(v*v for v in dv.values()))
            cosine=sum(v*dv.get(t,0) for t,v in qv.items()) / max(1e-9,qnorm*norm)
            score=cosine + bm/(1+bm)
            if score>0:
                hits.append({**doc.metadata,'text':doc.page_content,'score':round(score,4)})
        return sorted(hits,key=lambda x:x['score'],reverse=True)[:limit]

