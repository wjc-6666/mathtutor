import os, math, hashlib, re
from typing import Protocol
import httpx

class Embedder(Protocol):
    identity: str
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class HashEmbedding:
    identity='hash-char-bigram-v1-512'
    def embed(self,texts):
        result=[]
        for text in texts:
            text=re.sub(r'\s+','',text.lower()); v=[0.0]*512
            for token in [text[i:i+2] for i in range(max(0,len(text)-1))]:
                v[int.from_bytes(hashlib.sha256(token.encode()).digest()[:4],'big')%512]+=1
            n=math.sqrt(sum(x*x for x in v)) or 1
            result.append([x/n for x in v])
        return result

def request(kind,endpoint,payload):
    key=os.getenv(kind+'_API_KEY','')
    if not key: raise ValueError('请先在 .env 配置 '+kind+'_API_KEY')
    url=os.getenv(kind+'_BASE_URL','https://api.openai.com/v1').rstrip('/')
    try:
        with httpx.Client(timeout=120) as c:
            r=c.post(url+'/'+endpoint,json=payload,headers={'Authorization':'Bearer '+key})
            if r.status_code>=400: raise ValueError(f'{kind} 服务返回 HTTP {r.status_code}，请检查模型、额度和地址')
            return r.json()
    except httpx.HTTPError:
        raise ValueError(kind+' 服务连接失败或超时') from None

class APIEmbedding:
    def __init__(self):
        self.model=os.getenv('EMBEDDING_MODEL','text-embedding-3-small')
        self.identity='api:'+os.getenv('EMBEDDING_BASE_URL','https://api.openai.com/v1')+':'+self.model
    def embed(self,texts):
        out=[]
        for i in range(0,len(texts),32):
            batch=texts[i:i+32]
            rows=sorted(request('EMBEDDING','embeddings',{'model':self.model,'input':batch})['data'],key=lambda x:x['index'])
            if len(rows)!=len(batch): raise ValueError('Embedding 返回数量错误')
            for row in rows:
                v=row['embedding']; n=math.sqrt(sum(x*x for x in v))
                if not n: raise ValueError('Embedding 返回零向量')
                out.append([x/n for x in v])
        return out

class LocalEmbedding:
    """Free offline semantic embeddings; load only an explicitly downloaded model."""
    _models={}
    def __init__(self):
        from pathlib import Path
        path=Path(os.getenv('LOCAL_EMBEDDING_PATH','data/models/multilingual-e5-small')).resolve()
        if not path.is_dir():raise ValueError('本地语义模型尚未下载；请按 README 准备 LOCAL_EMBEDDING_PATH')
        self.path=str(path);self.identity='local-e5-v1:'+self.path
    def _model(self):
        if self.path not in self._models:
            try:from sentence_transformers import SentenceTransformer
            except ImportError:raise ValueError('请安装 requirements-semantic.txt 中的免费本地模型依赖') from None
            self._models[self.path]=SentenceTransformer(self.path,local_files_only=True,device='cpu')
        return self._models[self.path]
    def embed(self,texts):return self._model().encode(['passage: '+t for t in texts],normalize_embeddings=True,batch_size=16).tolist()
    def embed_query(self,text):return self._model().encode(['query: '+text],normalize_embeddings=True).tolist()[0]

def embedder():
    provider=os.getenv('EMBEDDING_PROVIDER','hash')
    if provider=='hash': return HashEmbedding()
    if provider=='api': return APIEmbedding()
    if provider=='local':return LocalEmbedding()
    raise ValueError('未知 Embedding provider')

class ChatModel(Protocol):
    def answer(self,messages: list[dict]) -> str: ...

class APIChat:
    def answer(self,messages):
        model=os.getenv('LLM_MODEL','')
        if not model: raise ValueError('请配置 LLM_MODEL')
        return request('LLM','chat/completions',{'model':model,'messages':messages})['choices'][0]['message']['content']

class OfflineChat:
    def answer(self,messages):
        return '【离线检索测试】已完成检索流程；如有命中，实际片段已传入 Tutor 上下文并显示在右侧。此模式不生成数学解答。请配置 .env 中 LLM_PROVIDER=api、LLM_API_KEY 与 LLM_MODEL，然后重启。'

def chat_model():
    provider=os.getenv('LLM_PROVIDER','offline')
    if provider=='api': return APIChat()
    if provider=='offline': return OfflineChat()
    raise ValueError('未知 LLM provider')
