import json,hashlib
from pathlib import Path
import pytest
from test_v12 import indexed
from test_flow import env
from app.rag.math_understanding import represent,normalize_math,RULES

def test_normalization():
    assert normalize_math('  ＡＡ^Ｔ  Cauchy- B inet ')=='aa^Tcauchy-binet'
def test_compositional_chain():
    m=represent('向量空间间保加法保数乘的双射叫什么')
    assert {'linear_structure','bijective_linear'}<=set(m.triggered_rules)
    assert '线性同构' in m.concepts and len(m.relations)>=4
    assert all(e['basis']=='system_inference' for e in m.evidence)
def test_rules_can_be_disabled():
    assert '线性同构' not in represent('向量空间间保加法保数乘的双射',disabled_rules=['bijective_linear']).concepts
def test_contextual_invertibility():
    assert '线性同构' in represent('可逆线性映射').concepts
    assert '线性同构' not in represent('这个数可逆吗').concepts
def test_negative_bijection():
    assert 'bijective_linear' not in represent('保加法保数乘的映射不是双射').triggered_rules
def test_positive_semidefinite_distinct():
    m=represent('半正定矩阵')
    assert '半正定' in m.concepts and '正定' not in m.concepts
def test_lagrange_identity_not_mean_value():
    assert 'Lagrange中值定理' not in represent('Lagrange 恒等式').theorem_candidates
def test_symbolic_and_question_relations():
    m=represent('矩阵A秩为1，是否迹为零时可对角化？')
    assert 'rank(A)=1' in m.symbolic_forms and 'tr(A)=0' in m.symbolic_forms
    assert m.conditions[0]['status']=='question'
    assert any(r['relation']=='QUESTION_PROPERTY' and r['property']=='diagonalizable' for r in m.relations)
def test_principal_minor_paraphrase():
    m=represent('实矩阵乘上自身转置，相同行列选出的子行列式不会为负')
    assert '主子式' in m.concepts and 'AA^T' in m.symbolic_forms and 'apply_cauchy_binet' in m.method_signature
def test_method_signature_independent():
    m=represent('不使用Rolle，利用Cauchy-Binet展开')
    assert 'apply_cauchy_binet' in m.method_signature and 'apply_rolle' not in m.method_signature
def test_five_views():
    assert set(represent('可逆线性映射').views)=={'Raw','Canonical','Concepts','Relations','Method'}

@pytest.fixture
def candidate(indexed):
    from app.rag import v121
    root,client,_=indexed
    before=(root/'data/index/v12/active.json').read_bytes()
    manifest=v121.build()
    assert (root/'data/index/v12/active.json').read_bytes()==before
    assert not (root/'data/index/v121/active.json').exists()
    return root,client,manifest
def test_candidate_generation_never_publishes(candidate):
    from app.rag import v121
    root,_,manifest=candidate;second=v121.build()
    assert second['generation']!=manifest['generation'] and v121.status()['active_version']=='v12'
def test_exact_regression_bypass(candidate):
    from app.rag import v121,v12
    expected=v12.search('例1.1')['results'];got=v121.search('例1.1')['results']
    assert [r['id'] for r in got]==[r['id'] for r in expected]
def test_multiview_and_trace(candidate):
    _,c,_=candidate;r=c.post('/api/retrieval-debug-v21',json={'question':'向量空间间保加法保数乘的双射'}).json()
    assert r['INDEX_VERSION']=='math-v121.1' and r['routing']=='multi_view'
    stages={s['stage'] for s in r['query_trace']}
    assert {'Raw Query','Normalization','Relations','Generated Views','Exact','BM25','Semantic per view','RRF','Metadata / Knowledge Map','Rerank','Final Results'}<=stages
    bm=next(s['details'] for s in r['query_trace'] if s['stage']=='BM25')
    assert len(bm)>=3
def test_invalid_experiment_api(candidate):
    _,c,_=candidate
    assert c.post('/api/retrieval-debug-v21',json={'question':'test','experiment':'bad'}).status_code==422
def test_failed_acceptance_no_publish(candidate,tmp_path):
    from app.rag import v121
    report=tmp_path/'acceptance.json';report.write_text(json.dumps({'gates':{'exact':True}}))
    with pytest.raises(ValueError,match='验收'):v121.promote(report)
    assert not (candidate[0]/'data/index/v121/active.json').exists()
def test_failed_build_keeps_stable(candidate,monkeypatch):
    from app.rag import v121
    before=(candidate[0]/'data/index/v121/candidate.json').read_bytes()
    monkeypatch.setattr(v121,'represent',lambda *a,**kw:(_ for _ in ()).throw(ValueError('failed')))
    with pytest.raises(ValueError):v121.build()
    assert (candidate[0]/'data/index/v121/candidate.json').read_bytes()==before
def test_corrupt_candidate_fallback(candidate):
    from app.rag import v121
    (candidate[0]/'data/index/v121/candidate.json').write_text('{')
    r=v121.search('Rolle')
    assert r['v121_fallback_reason'] and r['INDEX_VERSION']==v121.v12.INDEX_VERSION
def test_changed_policy_candidate_rejected(candidate,monkeypatch):
    from app.rag import v121
    monkeypatch.setattr(v121,'policy_hash',lambda:'changed')
    v121._cache.clear()
    with pytest.raises(ValueError):v121.load()
def test_similarity_separate_scores_and_method_evidence():
    from app.rag.v121 import explain_similarity
    q=represent('用Rolle定理构造辅助函数处理零点').to_dict()
    text='证明：构造辅助函数，利用Rolle定理处理导数。'
    r={'text':text,'doc':'d','page':1};a=represent(text,source='ocr_record').to_dict()
    e=explain_similarity(q,r,a)
    assert e['method_similarity']==1 and len(e['method_evidence'])==2 and e['reason'].endswith('系统推测，建议查看原题确认。')
def test_hard_negative_not_method_similarity():
    from app.rag.v121 import explain_similarity
    q=represent('使用Cauchy-Binet的矩阵子式方法').to_dict();r={'text':'线性映射与可逆矩阵','doc':'d','page':1}
    e=explain_similarity(q,r,represent(r['text']).to_dict())
    assert e['method_similarity']==0
def test_graded_metrics_no_duplicate_gain():
    from app.rag.evaluation_v121 import metrics
    target=[{'book':'b','pdf_page':1,'grade':3},{'book':'b','pdf_page':2,'grade':1}]
    r=metrics([{'name':'b','page':1}]*10,target)
    assert r['Hit@1']==1 and r['Recall@10']==.5 and 0<r['nDCG@10']<1
def test_holdout_rejects_changed_rules(candidate,tmp_path):
    from app.rag.evaluation_v121 import freeze,run
    f=tmp_path/'freeze.json';freeze(f)
    h=tmp_path/'holdout.json';h.write_text(json.dumps({'split':'holdout','frozen_policy_hash':'wrong','created_at':1,'questions':[]}))
    with pytest.raises(ValueError,match='独立性'):run(h,f)
def test_stable_routing_guard(candidate):
    from app.rag import v121,v12
    q='Rolle定理的定义是什么'
    assert v121.search(q)['routing']=='stable_v12_guard'
    assert [r['id'] for r in v121.search(q)['results']]==[r['id'] for r in v12.search(q)['results']]
def test_missing_active_fallback(candidate):
    from app.rag import v121
    assert v121.status()['active_version']=='v12'

def test_paraphrase_retrieval_with_related_hard_negative(indexed):
    from app.rag import v12,v121
    root,c,_=indexed
    (root/'books/algebra/understanding.md').write_text('定义1.2 向量空间间的线性同构是保加法、保持数乘的一一对应。\n\n例1.3 线性映射保持加法和数乘，但不要求双射。\n\n定义1.4 可逆矩阵的行列式不等于零。',encoding='utf8')
    assert c.post('/api/index').status_code==200
    v12.build(semantic=False);v121.build()
    r=v121.search('向量空间间既保持加法又保持数乘的双射叫什么',subject='algebra')
    assert r['results'][0]['label']=='定义1.2'
    assert r['query_representation']['triggered_rules'] and r['results'][0]['shared_properties']
def test_filter_and_candidate_cap(candidate):
    from app.rag import v121
    r=v121.search('向量空间间保加法保数乘的双射',subject='algebra')
    assert not r['results'] and r['candidate_count']==0
def test_candidate_pointer_traversal_rejected(candidate):
    from app.rag import v121
    (candidate[0]/'data/index/v121/candidate.json').write_text(json.dumps({'generation':'../../other'}))
    with pytest.raises(ValueError,match='generation'):v121.load()
def test_no_benchmark_specific_hardcode():
    from app.rag import v121,math_understanding
    text=Path(v121.__file__).read_text(encoding='utf8')+Path(math_understanding.__file__).read_text(encoding='utf8')
    for forbidden in ['Paraphrase-02','MethodSimilarity-03','例2.59','例6.74','66be647d-b47c-47d6-a842-6bb347225176','pdf_page==103','pdf_page==129']:
        assert forbidden not in text
def test_holdout_protocol_and_page_disjointness():
    # Repository artifacts, independent of the fixture's temporary corpus.
    root=Path(__file__).parents[1]
    dev=json.loads((root/'tests/retrieval_benchmark.json').read_text(encoding='utf8'))
    holdout=json.loads((root/'tests/retrieval_holdout_v121.json').read_text(encoding='utf8'))
    assert len(dev['questions'])==35 and len(holdout['questions'])>=50
    assert holdout['development_sha256']==hashlib.sha256((root/'tests/retrieval_benchmark.json').read_bytes()).hexdigest()
    old={(t['book'],t['pdf_page']) for q in dev['questions'] for t in q['relevant']}
    new={(t['book'],t['pdf_page']) for q in holdout['questions'] for t in q['relevant']}
    assert not old&new
