import json
from pathlib import Path
import pytest
from test_flow import env,pdf_bytes
from app.pdf.pipeline import quality,clean,process_pdf,cached_pages,file_hash

def test_quality_and_formula_cleaning():
    assert not quality('目录 100-200')['usable']
    assert quality('一致收敛的定义是函数列在整个定义域上一致地趋近极限函数。'*5)['usable']
    text='定 理 3 ． 2 ． 1\n∫₀¹ x² dx = 1/3\nA = (a₁₁ a₁₂)\nlim fₙ(x)\n'
    result=clean(text)
    for symbol in ['∫₀¹','x²','a₁₁','fₙ']:assert symbol in result
    assert '定理3.2.1' in result.replace(' ','')

def test_ocr_cache_resume_and_hash(env,monkeypatch):
    root,c=env
    from pypdf import PdfWriter
    path=root/'books/analysis/scan.pdf';w=PdfWriter()
    for _ in range(3):w.add_blank_page(width=100,height=100)
    w.write(path)
    import app.pdf.pipeline as p
    monkeypatch.setattr(p,'render_page',lambda doc,n,path:path.write_bytes(b'image'))
    calls=[];fail=[True]
    class Fake:
        identity='fake'
        def recognize(self,path):
            calls.append(1)
            if len(calls)==2 and fail[0]:raise RuntimeError('page failure')
            return {'text':'定义1.1 一致收敛。\n证明 这是测试文本。','version':'test'}
        def close(self):pass
    folder,state=process_pdf(path,root/'cache',engine_factory=Fake)
    assert state['failed_pages']==[2]
    fail[0]=False;folder,state=process_pdf(path,root/'cache',engine_factory=Fake)
    assert state['status']=='completed' and len(calls)==4
    assert state['cache_reused']==2
    folder,state=process_pdf(path,root/'cache',engine_factory=lambda:pytest.fail('cache must not OCR again'))
    assert [r['pdf_page'] for r in cached_pages(folder)]==[1,2,3]
    old_hash=file_hash(path);path.write_bytes(path.read_bytes()+b'\n')
    assert file_hash(path)!=old_hash

def test_structure_metadata():
    from app.rag.chunk import chunks
    page={'text':'第三章 一元微分学\n定理3.2.1 中值定理\n证明：过程。\n例3.2.26 构造辅助函数\n解：改写目标式。','page':200,'title':'教材'}
    parts=chunks(page)
    assert any(p['content_type']=='theorem' and '证明' in p['text'] for p in parts)
    assert any(p['label']=='例3.2.26' and '解：' in p['text'] for p in parts)
    assert all(p['pdf_page_start']==200 and p['pdf_page_end']==200 for p in parts)
    assert all(p['chapter']=='第三章 一元微分学' for p in parts)
    assert chunks({'text':'3.2 这是练习编号而非节标题','page':1})[0]['section'] is None

def test_exact_keyword_priority_and_debug(env):
    root,c=env
    (root/'books/analysis/notes.md').write_text('例12.4.5 构造辅助函数的方法。\n解：从结论倒推。\n例12.4.50 其他例题。',encoding='utf8')
    rows=c.post('/api/index').json();assert 'id' in rows[0]
    r=c.post('/api/retrieval-debug',json={'question':'例12.4.5','mode':'keyword'}).json()
    assert r[0]['label']=='例12.4.5'
    assert r[0]['keyword_score']>40
    assert c.get('/api/chunks/'+r[0]['id']).json()['text']==r[0]['text']
    r=c.post('/api/retrieval-debug',json={'question':'例12.4.5','mode':'hybrid'}).json()
    assert r[0]['label']=='例12.4.5'
    assert r[0]['retrieval_backend']=='keyword-fallback'
    assert c.post('/api/retrieval-debug',json={'question':'辅助函数','mode':'semantic'}).status_code==400

def test_migration_preserves_history(env):
    root,c=env
    import sqlite3
    # Start with an actual V1 schema and pre-existing history, before V1.1 connects.
    with sqlite3.connect(root/'data/mathtutor.sqlite3') as old:
        old.executescript('''
        CREATE TABLE documents(id TEXT PRIMARY KEY,path TEXT UNIQUE,name TEXT,subject TEXT,digest TEXT,embedding TEXT,status TEXT);
        CREATE TABLE chunks(id TEXT PRIMARY KEY,doc TEXT REFERENCES documents(id) ON DELETE CASCADE,title TEXT,page INTEGER,section TEXT,subsection TEXT,text TEXT,vector TEXT);
        CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT);
        CREATE TABLE messages(id INTEGER PRIMARY KEY AUTOINCREMENT,chat TEXT REFERENCES chats(id) ON DELETE CASCADE,role TEXT,content TEXT,sources TEXT);
        INSERT INTO chats VALUES('v1-history','existing V1 conversation');
        INSERT INTO messages(chat,role,content,sources) VALUES('v1-history','user','原有问题','[]');
        INSERT INTO messages(chat,role,content,sources) VALUES('v1-history','assistant','原有回答','[]');
        ''')
    assert [m['content'] for m in c.get('/api/chats/v1-history').json()]==['原有问题','原有回答']
    from app.database.store import connect
    with connect() as db:
        assert 'chapter' in {r[1] for r in db.execute('PRAGMA table_info(chunks)')}
        assert 'index_revision' in {r[1] for r in db.execute('PRAGMA table_info(documents)')}
    assert len(c.get('/api/chats/v1-history').json())==2
