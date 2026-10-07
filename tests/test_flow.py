import os,json,importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def env(tmp_path,monkeypatch):
    monkeypatch.setenv('MATHTUTOR_ROOT',str(tmp_path));monkeypatch.setenv('EMBEDDING_PROVIDER','hash');monkeypatch.setenv('LLM_PROVIDER','offline')
    for name in ['app.config','app.database.store','app.rag.service','app.main']:
        importlib.reload(importlib.import_module(name))
    from app.main import app
    (tmp_path/'books/analysis').mkdir(parents=True);(tmp_path/'books/algebra').mkdir()
    return tmp_path,TestClient(app)

def pdf_bytes():
    # 含真实文字层的最小 PDF；不依赖字体或网络。
    parts=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    stream=b'BT /F1 12 Tf 50 700 Td (Uniform convergence: supremum norm tends to zero.) Tj ET'
    parts.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
    data=b'%PDF-1.4\n';offset=[0]
    for i,p in enumerate(parts,1):offset.append(len(data));data+=str(i).encode()+b' 0 obj\n'+p+b'\nendobj\n'
    start=len(data);data+=b'xref\n0 6\n0000000000 65535 f \n'
    for n in offset[1:]:data+=f'{n:010d} 00000 n \n'.encode()
    return data+b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n'+str(start).encode()+b'\n%%EOF'

def test_end_to_end(env,monkeypatch):
    root,c=env
    assert c.get('/').status_code==200
    r=c.post('/api/upload',data={'subject':'analysis'},files={'file':('test.pdf',pdf_bytes(),'application/pdf')})
    assert r.status_code==200,r.text
    did=r.json()['id'];assert '已索引' in r.json()['status']
    captured=[]
    class Fake:
        def answer(self,msg):captured.extend(msg);return r'推导：\(x^2\) [S1]'
    import app.main
    monkeypatch.setattr(app.main,'chat_model',lambda:Fake())
    a=c.post('/api/chat',json={'question':'Uniform convergence','documents':[did]}).json()
    assert a['sources'][0]['page']==1
    assert 'supremum norm' in a['sources'][0]['text']
    assert '[S1]' in captured[-1]['content'] and 'supremum norm' in captured[-1]['content']
    assert len(c.get('/api/chats/'+a['chatid']).json())==2
    assert c.get('/api/documents/'+did+'/file').content==pdf_bytes()
    assert c.post('/api/upload',data={'subject':'analysis'},files={'file':('test.pdf',pdf_bytes())}).status_code==400
    assert c.delete('/api/documents/'+did).status_code==200
    assert (root/'books/analysis/test.pdf').exists()
    from app.rag.service import retrieve
    assert retrieve('Uniform convergence')==[]

def test_modes_and_chunk(env):
    from app.prompts.tutor import messages
    for mode in ['detail','hint','review','summary']:
        assert len(messages('题目',mode,[],[]))==2
    assert '只有用户明确' in messages('再提示一点','hint',[],[])[0]['content']
    from app.rag.chunk import chunks
    text='定义 一致收敛\n\n'+'证明内容。'*500
    parts=chunks({'text':text,'page':2,'title':'测试'})
    assert len(parts)>1 and all(p['page']==2 for p in parts)

def test_subject_and_compare(env):
    root,c=env
    for subject in ['analysis','algebra']:
        (root/'books'/subject/'sample.md').write_text('一致收敛：上确界范数趋于零。不同资料对比。',encoding='utf8')
    rows=c.post('/api/index').json();ids=[r['id'] for r in rows]
    from app.rag.service import retrieve
    assert all(s['subject']=='analysis' for s in retrieve('一致收敛','analysis'))
    r=c.post('/api/chat',json={'question':'一致收敛的资料对比','documents':ids}).json()
    assert len({s['doc'] for s in r['sources']})==2
    assert all(s['page'] is None for s in r['sources'])

def test_embedding_adapter(monkeypatch):
    import app.llm.providers as p
    monkeypatch.setattr(p,'request',lambda *args:{'data':[{'index':1,'embedding':[0,2]},{'index':0,'embedding':[2,0]}]})
    assert p.APIEmbedding().embed(['a','b'])==[[1,0],[0,1]]

def test_vision_confirmation(monkeypatch):
    import app.vision.service as v
    monkeypatch.setenv('LLM_PROVIDER','api');monkeypatch.setenv('VISION_MODEL','test')
    monkeypatch.setattr(v,'request',lambda *a:{'choices':[{'message':{'content':json.dumps({'question':'x [?] 2','uncertain':['运算符']})}}]})
    assert v.recognize(b'test','image/png')['requires_confirmation'] is True

def test_scan_only_pdf(env):
    root,c=env
    from pypdf import PdfWriter
    path=root/'books/analysis/scan.pdf';w=PdfWriter();w.add_blank_page(width=100,height=100);w.write(path)
    rows=c.post('/api/index').json()
    assert '需要 OCR' in rows[0]['status']

def test_failed_reindex_preserves_existing_chunks(env,monkeypatch):
    root,c=env
    path=root/'books/analysis/notes.md';path.write_text('一致收敛 上确界趋于零',encoding='utf8')
    rows=c.post('/api/index').json();did=rows[0]['id']
    path.write_text('更新后的正文',encoding='utf8')
    import app.rag.service as service
    class Broken:
        identity='broken'
        def embed(self,texts): raise ValueError('模拟服务故障')
    with monkeypatch.context() as m:
        m.setattr(service,'embedder',lambda:Broken())
        assert '索引失败' in c.post('/api/index').json()[0]['status']
    assert service.retrieve('一致收敛')[0]['doc']==did

def test_switch_vector_space_requires_reindex(env,monkeypatch):
    root,c=env
    (root/'books/analysis/notes.md').write_text('一致收敛 上确界',encoding='utf8')
    c.post('/api/index')
    import app.rag.service as service
    from app.llm.providers import HashEmbedding
    emb=HashEmbedding();emb.identity='other-space'
    monkeypatch.setattr(service,'embedder',lambda:emb)
    with pytest.raises(ValueError,match='配置已改变'):service.retrieve('一致收敛')
