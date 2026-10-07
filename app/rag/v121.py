"""Candidate generations and local multi-view retrieval. Promotion is explicit."""
import json,time,uuid,hashlib,re,os,collections,threading
from pathlib import Path
from app.rag import v12
from app.rag.math_understanding import represent,normalize_math,RULES,LEXICON,METHOD_SIGNATURES

VERSION='math-v121.1'
WEIGHTS={'rrf':.45,'concept':.45,'property':.65,'method':.30,'definition':.24,'example':.12,'rrf_k':60,'channel_depth':50,'candidate_cap':150}
_cache={};_lock=threading.RLock()
def folder():return v12.locations()[0].parent/'v121'
def policy_hash():
    files=[Path(__file__),Path(__file__).with_name('math_understanding.py')]
    return hashlib.sha256(b''.join(p.read_bytes() for p in files)+json.dumps(WEIGHTS,sort_keys=True).encode()).hexdigest()
def _atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');tmp.replace(path)
def build():
    data=v12.load();generation=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    path=folder()/'generations'/generation;path.mkdir(parents=True)
    annotations=[]
    for r in data['records']:
        m=represent(r['text'],r['subject'],source='ocr_record').to_dict()
        annotations.append({'id':r['id'],'representation':m,'basis':'system_inference','provenance':{'doc':r['doc'],'pdf_page':r['page'],'source_chunk_id':r.get('source_chunk_id',r['id'])}})
    manifest={'INDEX_VERSION':VERSION,'generation':generation,'source_signature':data['manifest']['source_signature'],'baseline_generation':data['manifest']['generation'],
        'records':len(annotations),'created_at':time.time(),'policy_hash':policy_hash(),'embedding':data['manifest']['embedding'],'semantic_available':data['manifest']['semantic_available'],
        'vector_policy':'reuse unchanged V1.2 E5 passage vectors; query views embedded separately','state':'candidate'}
    _atomic(path/'annotations.json',annotations);_atomic(path/'manifest.json',manifest)
    # Never publish during a build. Stable V1.2 active pointer is untouched.
    _atomic(folder()/'candidate.json',{'generation':generation,'INDEX_VERSION':VERSION});_cache.clear();return manifest
def load(pointer='candidate'):
    if pointer not in {'candidate','active'}:raise ValueError('未知指针')
    ref=json.loads((folder()/(pointer+'.json')).read_text(encoding='utf8'));gen=ref['generation']
    if not re.fullmatch(r'[\w-]+',gen):raise ValueError('generation 无效')
    data=v12.load();key=(str(folder()),gen)
    with _lock:
        if key not in _cache:
            path=folder()/'generations'/gen;manifest=json.loads((path/'manifest.json').read_text(encoding='utf8'))
            if manifest['INDEX_VERSION']!=VERSION or manifest['policy_hash']!=policy_hash():raise ValueError('候选代码/索引策略不一致，请重新构建候选')
            if manifest['source_signature']!=data['manifest']['source_signature'] or manifest['baseline_generation']!=data['manifest']['generation']:raise ValueError('基础教材或V1.2 generation已变化')
            annotations=json.loads((path/'annotations.json').read_text(encoding='utf8'))
            if [a['id'] for a in annotations]!=[r['id'] for r in data['records']]:raise ValueError('候选元数据不完整')
            annotated=[dict(r,text=normalize_math(r['text'])+' '+a['representation']['canonical_text']) for r,a in zip(data['records'],annotations)]
            _cache[key]={'manifest':manifest,'annotations':annotations,'bm25':v12.BM25(annotated)}
        return dict(_cache[key],base=data)
def status():
    if os.getenv('RETRIEVAL_VERSION') in {'v11','v12'}:return v12.status()
    try:
        data=load('active');return dict(data['manifest'],active_version='v121',fallback_reason=None)
    except Exception as e:
        result=v12.status();result['v121_fallback_reason']=str(e);return result
def promote(acceptance_path):
    # Acceptance must bind rules, both datasets, the index and all guard outcomes.
    report=json.loads(Path(acceptance_path).read_text(encoding='utf8'));d=load()
    required=['development_paraphrase','holdout_paraphrase','exact','concept','theorem','method','similar_problem','no_benchmark_hardcode','tests','integrity','holdout_isolation']
    if not all(report.get('gates',{}).get(k) is True for k in required):raise ValueError('验收门禁未全部通过，保留 V1.2 active')
    if report.get('policy_hash')!=policy_hash() or report.get('generation')!=d['manifest']['generation']:raise ValueError('验收与当前候选不匹配')
    from app import config
    for name,relative in [('development','tests/retrieval_benchmark.json'),('holdout','tests/retrieval_holdout_v121.json')]:
        if report.get('dataset_hashes',{}).get(name)!=hashlib.sha256((config.ROOT/relative).read_bytes()).hexdigest():raise ValueError('验收数据集已变化')
    _atomic(folder()/'active.json',{'generation':d['manifest']['generation'],'INDEX_VERSION':VERSION,'acceptance_sha256':hashlib.sha256(Path(acceptance_path).read_bytes()).hexdigest()})
    return status()

def search(query,subject='all',docids=None,k=10,experiment='E',pointer='candidate',disabled_rules=(),strict=False):
    if experiment not in {'A','B','C','D','E'}:raise ValueError('未知消融变体')
    start=time.perf_counter();m=represent(query,subject,disabled_rules);rep=m.to_dict()
    try:d=load(pointer)
    except Exception as e:
        if strict:raise
        old=v12.search(query,subject,docids,k);old.update(v121_fallback_reason=str(e),query_representation=rep,query_trace=[{'stage':'fallback','details':str(e)}]);return old
    base=d['base'];records=base['records'];allowed=[i for i,r in enumerate(records) if (subject=='all' or r['subject']==subject) and (not docids or r['doc'] in docids)]
    trace=[{'stage':name,'details':value} for name,value in [('Raw Query',query),('Normalization',m.normalized_text),('Canonical Concepts',{'canonical':m.canonical_text,'concepts':m.concepts,'evidence':m.evidence,'disabled_rules':list(disabled_rules)}),('Relations',m.relations),('Generated Views',m.views)]]
    # Exact identifiers bypass every semantic rewrite and keep stable ordering.
    if m.exact_identifiers:
        response=v12.search(query,subject,docids,k);response.update(INDEX_VERSION=VERSION,query_representation=rep,query_trace=trace+[{'stage':'Exact','details':{'bypass':True,'identifiers':m.exact_identifiers}},{'stage':'Final Results','details':[r['id'] for r in response['results']]}],routing='exact_bypass',experiment=experiment)
        return response
    viewtexts={'A':{'Raw':query},'B':{'Canonical':m.canonical_text},'C':{'Raw+Canonical':query+' '+m.canonical_text}}.get(experiment,{key:value for key,value in m.views.items() if value.strip()})
    channels={};semantics={};lexical={};fusion=collections.defaultdict(float)
    def channel(name,values):
        ranking=sorted(allowed,key=lambda i:values[i],reverse=True)[:WEIGHTS['channel_depth']]
        ranking=[i for i in ranking if values[i]>0]
        channels[name]=[{'id':records[i]['id'],'doc':records[i]['doc'],'pdf_page':records[i]['page'],'label':records[i]['label'],'rank':rank,'score':round(float(values[i]),6)} for rank,i in enumerate(ranking,1)]
        for rank,i in enumerate(ranking,1):fusion[i]+=1/(WEIGHTS['rrf_k']+rank)
    for name,text in viewtexts.items():
        values=d['bm25'].score(text);lexical[name]=values;channel('BM25/'+name,values)
    if base['engine'] and allowed:
        vectors=base['engine'].embed(list(viewtexts.values()),query=True)
        for (name,_),vector in zip(viewtexts.items(),vectors):
            values=(base['vectors']@vector).tolist();semantics[name]=values;channel('E5/'+name,values)
    trace.extend([{'stage':'Exact','details':{'bypass':False,'identifiers':[]}},{'stage':'BM25','details':{k:v for k,v in channels.items() if k.startswith('BM25/')}},{'stage':'Semantic per view','details':{k:v for k,v in channels.items() if k.startswith('E5/')}}])
    # A separate canonical/property channel can recall sparse formula-heavy OCR.
    scores={};queryconcepts=set(m.concepts+m.theorem_candidates);queryprops=set(m.properties);querysigs=set(m.method_signature)
    for i in allowed:
        r=records[i];a=d['annotations'][i]['representation'];n=normalize_math(r['text'])
        shared=sorted(queryconcepts&set(a['concepts']+a['theorem_candidates']));props=sorted(queryprops&set(a['properties']));sigs=sorted(querysigs&set(a['method_signature']))
        coverage=len(shared)/max(1,len(queryconcepts));propcoverage=len(props)/max(1,len(queryprops));methodcoverage=len(sigs)/max(1,len(querysigs))
        definition=WEIGHTS['definition'] if m.target=='explain_concept' and r['content_type'] not in {'example','exercise'} and re.search(r'定义|所谓|则称|充要条件',n) and shared else 0
        example=WEIGHTS['example'] if m.target=='find_similar_problem' and r['content_type'] in {'example','exercise'} else 0
        meta=WEIGHTS['concept']*coverage+WEIGHTS['property']*propcoverage+WEIGHTS['method']*methodcoverage+definition+example
        scores[i]={'shared_concepts':shared,'shared_properties':props,'shared_method_signature':sigs,'concept_coverage':coverage,'property_coverage':propcoverage,'method_coverage':methodcoverage,'metadata_score':round(meta,6),'definition_bonus':definition,'example_bonus':example}
    if experiment=='E':channel('Canonical metadata',[scores[i]['metadata_score'] if i in scores else 0 for i in range(len(records))])
    recalled=sorted(fusion,key=lambda i:fusion[i],reverse=True)[:WEIGHTS['candidate_cap']];maxfusion=max(fusion.values(),default=1)
    trace.append({'stage':'RRF','details':[{'id':records[i]['id'],'score':fusion[i]} for i in recalled]})
    final={i:WEIGHTS['rrf']*fusion[i]/maxfusion+(scores[i]['metadata_score'] if experiment=='E' else 0) for i in recalled}
    ranked=sorted(recalled,key=lambda i:final[i],reverse=True)
    rows=[]
    for i in ranked:
        r=dict(records[i]);r.update(scores[i],score=round(final[i],6),final_score=round(final[i],6),candidate_score=round(fusion[i],8),candidate_rrf=round(fusion[i],8),exact_score=0,
            keyword_score=round(max((v[i] for v in lexical.values()),default=0),6),semantic_score=round(max((v[i] for v in semantics.values()),default=0),6) if semantics else None,
            semantic_per_view={name:round(values[i],6) for name,values in semantics.items()},semantic_available=bool(semantics),graph_score=0,confidence='medium',basis='system_inference：对象/性质/多视图检索；请核查原页',
            relationship=[])
        r['relationship']=[{'relation':rel,'entities':scores[i][field],'basis':'system_inference','confidence':'medium'} for rel,field in [('same_concept','shared_concepts'),('same_property','shared_properties'),('same_method','shared_method_signature')] if scores[i][field]]
        rows.append(r)
    routing='multi_view'
    # Conservative production guard: explicit/recognised requests with no new
    # compositional evidence retain proven V1.2 ranking, still show view trace.
    if experiment=='E' and not m.triggered_rules:
        old=v12.search(query,subject,docids,k);rows=old['results'];routing='stable_v12_guard'
    profile=v12.parse_query(query,subject)
    profile['concepts']=list(dict.fromkeys(profile['concepts']+m.concepts));profile['possible_theorems']=list(dict.fromkeys(profile['possible_theorems']+m.theorem_candidates));profile['possible_methods']=list(dict.fromkeys(profile['possible_methods']+m.method_candidates))
    trace.extend([{'stage':'Metadata / Knowledge Map','details':{'basis':'system_inference','weights':WEIGHTS,'matches':[dict(id=records[i]['id'],**scores[i]) for i in ranked[:50]]}},{'stage':'Rerank','details':{'routing':routing,'candidate_cap':WEIGHTS['candidate_cap'],'results':[{'id':r['id'],'score':r['score'],'reasons':r['relationship']} for r in rows[:k]]}},{'stage':'Final Results','details':[r['id'] for r in rows[:k]]}])
    return {'INDEX_VERSION':VERSION,'generation':d['manifest']['generation'],'semantic_available':bool(semantics),'fallback_reason':None,'query_profile':profile,'query_representation':rep,'query_trace':trace,'routing':routing,'experiment':experiment,
        'results':rows[:k],'candidates':rows,'candidate_count':len(recalled),'evidence_bundle':v12.bundle(rows[:k],base,profile),'elapsed_ms':round((time.perf_counter()-start)*1000,2),'reranker':'local-object-property-method-v1'}

def explain_similarity(rep,record,annotation,semantic=None):
    qconcept=set(rep['concepts']+rep['theorem_candidates']);rconcept=set(annotation['concepts']+annotation['theorem_candidates'])
    shared=sorted(qconcept&rconcept);sigs=sorted(set(rep['method_signature'])&set(annotation['method_signature']))
    qt=set(v12.BM25.math_tokens(rep['raw_query']));rt=set(v12.BM25.math_tokens(record['text']))
    surface=len(qt&rt)/max(1,len(qt));concept=len(shared)/max(1,len(qconcept));method=len(sigs)/max(1,len(rep['method_signature']))
    evidence=[]
    for sig in sigs:
        snippet=next((line for line in record['text'].splitlines() if re.search(METHOD_SIGNATURES[sig],normalize_math(line))),None)
        if snippet:evidence.append({'signature':sig,'excerpt':snippet[:300],'doc':record['doc'],'pdf_page':record['page'],'basis':'system_inference'})
    return {'surface_similarity':round(surface,4),'concept_similarity':round(concept,4),'method_similarity':round(method,4),'shared_concepts':shared,'shared_method_signature':sigs,'method_evidence':evidence,
            'reason':('共享方法签名：'+', '.join(sigs)+'。' if sigs else '')+'系统推测，建议查看原题确认。','basis':'system_inference','confidence':'medium','source':record}
def similar(query,subject='all',docids=None,k=5,exclude=None,pointer='candidate'):
    response=search(query,subject,docids,30,pointer=pointer)
    if response['INDEX_VERSION']!=VERSION:
        return dict(v12.similar(query,subject,docids,k,exclude),v121_fallback_reason=response.get('v121_fallback_reason'))
    d=load(pointer);annotations={a['id']:a['representation'] for a in d['annotations']};rep=response['query_representation']
    if not exclude:exclude=next((r['id'] for r in response['results'] if r.get('exact_score')==1),None)
    if rep['exact_identifiers'] and exclude in annotations:
        anchor=annotations[exclude]
        rep=dict(rep,concepts=anchor['concepts'],theorem_candidates=anchor['theorem_candidates'],method_signature=anchor['method_signature'])
    explanations=[explain_similarity(rep,r,annotations[r['id']]) for r in response['candidates'] if r['id']!=exclude and r['content_type'] in {'example','exercise'}]
    groups={kind:sorted([e for e in explanations if e[kind+'_similarity']>0],key=lambda e:e[kind+'_similarity'],reverse=True)[:k] for kind in ['surface','concept','method']}
    return {'query_profile':response['query_profile'],'query_representation':rep,'semantic_available':response['semantic_available'],'fallback_reason':None,'groups':groups,'candidate_explanations':explanations}
