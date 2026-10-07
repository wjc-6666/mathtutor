import importlib,json
from pathlib import Path
import pytest
from test_flow import env

@pytest.mark.parametrize('query,intent',[
 ('例2.59','find_exact_example'),('证明存在 ξ∈(a,b)，使 f\'(ξ)=0','solve_problem'),
 ('什么是线性同构','explain_concept'),('为什么想到构造辅助函数','explain_method'),
 ('找类似题：存在一点导数为零','find_similar_problem'),('构造辅助函数有哪些相关方法','find_related_method'),
 ('比较反证法与数学归纳法','compare_methods'),('复习一致收敛','review_topic')])
def test_query_intents(query,intent):
    from app.rag.math_profile import parse_query
    assert parse_query(query)['query_intent']==intent

def test_query_hypotheses_and_math_expressions():
    from app.rag.math_profile import parse_query,expand
    p=parse_query('证明存在 ξ∈(a,b)，使 f\'(ξ)=0')
    assert p['mathematical_expressions'] and 'Rolle定理' in p['possible_theorems']
    assert all(h['basis']=='系统推断' and h['confidence']=='medium' for h in p['hypotheses'])
    assert expand(p)[0]['query']==p['raw_query']
    assert any(e['perspective']=='Method' for e in expand(p))

def test_identifier_normalization_and_boundary():
    from app.rag.math_profile import parse_query
    assert parse_query('例题 2．59')['exact_identifiers']==['例2.59']
    assert parse_query('习题1.3.20')['exact_identifiers']==['习题1.3.20']

def test_principal_minor_query_profile():
    from app.rag.math_profile import parse_query
    p=parse_query('设A为m×n实矩阵，证明AA^T的任一主子式都非负')
    assert p['subject']=='algebra' and '行列式' in p['concepts'] and '不等式证明' in p['problem_type']
    assert p['mathematical_expressions'] and 'Cauchy-Binet展开' in p['possible_methods']

@pytest.fixture
def indexed(env):
    root,client=env
    path=root/'books/analysis/sample.md'
    path.write_text('§ 1.1 微分中值定理\n定义1.1 Rolle定理需要连续和可导。\n\n例1.1 证明存在一点导数为零。\n证明：构造辅助函数，利用Rolle定理。\n\n例1.10 由Rolle定理，构造辅助函数证明另一存在性结论。',encoding='utf8')
    response=client.post('/api/index');assert response.status_code==200
    from app.rag.v12 import build
    manifest=build(semantic=False)
    return root,client,manifest

def test_versioned_build_preserves_legacy(indexed):
    root,_,manifest=indexed
    from app.rag.v12 import build,legacy_rows,signature
    before=signature(legacy_rows());pointer=(root/'data/index/v12/active.json').read_text()
    second=build(semantic=False)
    assert before==signature(legacy_rows())
    assert second['generation']!=manifest['generation'] and pointer!=(root/'data/index/v12/active.json').read_text()
    assert (root/'data/index/v12/generations'/manifest['generation']/'knowledge.json').exists()

def test_exact_not_identifier_prefix(indexed):
    from app.rag.v12 import search
    r=search('例1.1')
    assert r['results'][0]['label']=='例1.1' and r['results'][0]['exact_score']==1
    assert all(s['exact_score']!=1 for s in r['results'] if s['label']=='例1.10')
    assert r['semantic_available'] is False

def test_debug_scores_and_evidence(indexed):
    _,client,_=indexed
    r=client.post('/api/retrieval-debug-v2',json={'question':'如何构造辅助函数证明存在一点'}).json()
    assert r['candidate_count']<=50 and r['expansion'] and r['query_profile']['hypotheses']
    assert set(['exact_match','core_theory','similar_problems','method_related','parent_context','source_pages'])==set(r['evidence_bundle'])
    for s in r['results']:
        assert all(key in s for key in ['candidate_score','exact_score','keyword_score','semantic_score','metadata_score','graph_score','final_score','relationship'])

def test_parent_continuation_and_neighbours():
    from app.rag.v12 import structure
    def row(i,p,label,text):return dict(id=i,doc='doc',title='book',name='test.pdf',subject='analysis',page=p,page_end=p,chapter='bad inherited chapter',section='§1',subsection=None,text=text,label=label,method=None,content_type='example' if label else 'text',digest='x')
    data=structure([row('a',1,'例1.1','例1.1 题目'),row('b',2,None,'证明续页，不重新 OCR'),row('c',2,'例1.2','例1.2 下一题')])
    a,b,c=data['records'];assert a['parent_chunk']==b['parent_chunk']!=c['parent_chunk']
    parent=data['parents'][a['parent_chunk']]
    assert '题目' in parent['text'] and '证明续页' in parent['text']
    assert (parent['pdf_page_start'],parent['pdf_page_end'])==(1,2)
    assert b['neighboring_chunks']==['a','c'] and a['chapter'] is None

def test_same_number_fragments_have_one_parent():
    from app.rag.v12 import structure
    def row(i,text):return dict(id=i,doc='d',title='b',name='b.pdf',subject='analysis',page=1,page_end=1,chapter=None,section=None,subsection=None,text=text,label='例1.1',method=None,content_type='example',digest='x')
    data=structure([row('a','例1.1 长题目的开头'),row('b','长题目的证明后半段')])
    assert len(data['parents'])==1
    assert data['records'][0]['parent_chunk']==data['records'][1]['parent_chunk']

def test_semantic_prose_preserves_original():
    from app.rag.v12 import semantic_text
    raw='例1.1 证明存在零点\n1 2 3 + ???\n微信公众号广告\n由Rolle定理得结论'
    row={'subject':'analysis','section':None,'label':'例1.1','concepts':[],'theorems':['Rolle定理'],'methods':[],'problem_types':[],'text':raw}
    text=semantic_text(row)
    assert 'Rolle定理' in text and '证明存在零点' in text and '微信公众号' not in text
    assert row['text']==raw

def test_mathematical_single_character_terms():
    from app.rag.v12 import BM25
    bm=BM25([{'text':'矩阵的迹的性质与秩为一。'},{'text':'无关的文字'}])
    assert bm.score('迹为零，秩是一')[0]>bm.score('迹为零，秩是一')[1]

def test_exercise_structuring_and_provenance():
    from app.rag.v12 import structure
    row=dict(id='original',doc='doc',title='solutions',name='习题解答.pdf',subject='analysis',page=14,page_end=14,chapter=None,section=None,subsection=None,text='广告\n1.3.20 求极限\n解：利用Rolle定理\n1.3.21 证明存在一点\n解：构造辅助函数',label=None,method=None,content_type='text',digest='x')
    data=structure([row]);exercises=[r for r in data['records'] if r['content_type']=='exercise']
    assert len(exercises)==2 and {r['exercise_number'] for r in exercises}=={'1.3.20','1.3.21'}
    assert all(r['source_chunk_id']=='original' and r['page']==14 for r in exercises)
    assert sum(e['type']=='Exercise' for e in data['entities'].values())==2

def test_similarity_groups_only_real_examples(indexed):
    _,client,_=indexed
    r=client.post('/api/similar-problems',json={'question':'Rolle定理 构造辅助函数 类似题'}).json()
    assert set(r['groups'])=={'surface','concept','method'}
    assert r['groups']['method'] and r['groups']['concept']
    for group in r['groups'].values():
        assert all(x['relation']=='SIMILAR_TO' and x['source']['content_type'] in {'example','exercise'} and x['basis']=='系统推断' for x in group)

def test_graph_uses_requires_and_confidence(indexed):
    from app.rag.v12 import load,map_summary
    data=load();edges=data['edges']
    assert any(e['relation']=='USES_METHOD' and e['target']=='构造辅助函数' and e['evidence']['chunk'] for e in edges)
    assert any(e['relation']=='REQUIRES' and e['source']=='Rolle定理' for e in edges)
    assert any(e['relation']=='APPLIES_TO' for e in edges)
    assert all(e['confidence'] in {'explicit','high'} for e in edges)
    assert 'SIMILAR_TO' in map_summary()['supported_relations']

def test_method_topic_sources(indexed):
    _,client,_=indexed
    r=client.get('/api/topics/构造辅助函数').json()
    assert r['catalogue']['triggers'] and r['examples'] and all(s['doc'] for s in r['sources'])
    assert r['catalogue']['basis'].startswith('系统整理')

def test_bundle_pdf_page_one_based():
    from app.rag.v12 import bundle
    r=bundle([{'id':'chunk','doc':'doc','name':'test.pdf','page':1,'content_type':'example'}],None,{})
    assert r['source_pages'][0]['pdf_url']=='/api/documents/doc/pdf#page=1'
    assert r['source_pages'][0]['page_url']=='/api/documents/doc/page/1'

def test_failed_build_keeps_active(indexed,monkeypatch):
    root,_,_=indexed
    from app.rag.v12 import build
    import app.rag.local_dense as dense
    before=(root/'data/index/v12/active.json').read_bytes()
    def broken(*a):raise OSError('model unavailable')
    monkeypatch.setattr(dense,'E5CPU',broken)
    with pytest.raises(OSError):build(semantic=True)
    assert (root/'data/index/v12/active.json').read_bytes()==before

def test_corrupt_index_fallback(indexed):
    root,_,_=indexed
    from app.rag.v12 import search
    (root/'data/index/v12/active.json').write_text('broken',encoding='utf8')
    r=search('Rolle')
    assert r['INDEX_VERSION']=='v11' and not r['semantic_available'] and r['fallback_reason'] and r['results']

def test_manual_fallback(indexed,monkeypatch):
    from app.rag.v12 import search
    monkeypatch.setenv('RETRIEVAL_VERSION','v11')
    r=search('Rolle');assert r['INDEX_VERSION']=='v11' and '手动' in r['fallback_reason']

def test_changed_source_fallback(indexed):
    root,client,_=indexed
    from app.rag.v12 import search
    (root/'books/analysis/sample.md').write_text('新文档 Rolle 定理',encoding='utf8');client.post('/api/index')
    assert search('Rolle')['INDEX_VERSION']=='v11'

def test_benchmark_metrics_and_dataset():
    from app.rag.benchmark import metrics
    targets=[{'book':'A.pdf','pdf_page':1},{'book':'A.pdf','pdf_page':2}]
    rows=[{'name':'B.pdf','page':1},{'name':'A.pdf','page':1}]
    m=metrics(rows,targets);assert m['Recall@5']==.5 and m['Recall@10']==.5 and m['MRR']==.5
    rows=[{'name':'A.pdf','page':1,'label':'例1.10'}]
    assert metrics(rows,[{'book':'A.pdf','pdf_page':1,'label':'例1.1'}])['MRR']==0
    data=json.loads((Path(__file__).parent/'retrieval_benchmark.json').read_text(encoding='utf8'))
    assert 30<=len(data['questions'])<=50 and len({q['id'] for q in data['questions']})==len(data['questions'])
    assert len({q['category'] for q in data['questions']})==7
    assert all(t['pdf_page']>=1 for q in data['questions'] for t in q['relevant'])

def test_tutor_bundle_and_four_modes(indexed):
    from app.rag.v12 import search
    from app.prompts.tutor import messages
    r=search('例1.1')
    for mode in ['detail','hint','review','summary']:
        prompt=messages('q',mode,r['results'],[],r['evidence_bundle'])
        assert 'EvidenceBundle' in prompt[-1]['content'] and '[S1]' in prompt[-1]['content']
    _,client,_=indexed
    response=client.post('/api/chat',json={'question':'如何构造辅助函数','mode':'hint'}).json()
    assert response['evidence_bundle'] and '一层提示' in response['answer'] and '离线' in response['answer']

def test_dense_masked_pooling(monkeypatch,tmp_path):
    import numpy as np
    from app.rag.local_dense import E5CPU
    engine=object.__new__(E5CPU);engine.np=np
    import threading
    engine.lock=threading.Lock()
    class Encoded:
        ids=[1,2];attention_mask=[1,0];type_ids=[0,0]
    class Tokenizer:
        def encode_batch(self,texts):
            assert texts==['query: x'];return [Encoded()]
    class Session:
        def get_inputs(self):return [type('Input',(),{'name':'input_ids'})(),type('Input',(),{'name':'attention_mask'})()]
        def run(self,*args):return [np.array([[[3.,4.],[999.,999.]]])]
    engine.tokenizer=Tokenizer();engine.session=Session()
    assert np.allclose(engine.embed(['x'],query=True),[[.6,.8]])
