"""Versioned, offline retrieval. Original V1.1 database is only read here."""
import collections, hashlib, json, math, os, re, sqlite3, time, uuid, threading
from pathlib import Path
from app.rag.keyword import tokens,normalize
from app.rag.math_profile import mentions,parse_query,expand,LEXICON
from app.rag.knowledge import CATALOGUE,PREREQUISITES,CONFUSIONS,catalogue_edges

INDEX_VERSION='math-v12.1'
SEMANTIC_REPRESENTATION='ocr-prose-and-explicit-metadata-v2'
_cache={};_lock=threading.RLock()

def locations():
    from app import config
    return config.DATA/'index/v12', config.DATA/'models/e5-small-int8', config.DATA/'mathtutor.sqlite3'

def legacy_rows():
    _,_,db=locations()
    if not db.exists():return []
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as c:
        c.row_factory=sqlite3.Row
        return [dict(r) for r in c.execute('SELECT chunks.*,documents.name,documents.subject,documents.digest,documents.path FROM chunks JOIN documents ON chunks.doc=documents.id ORDER BY chunks.doc,chunks.page,chunks.rowid')]

def signature(rows):
    return hashlib.sha256(json.dumps([(r['id'],r['doc'],r['digest'],r['text']) for r in rows],ensure_ascii=False).encode()).hexdigest()

def structure(rows):
    records=[];parents={};sections={};entities={};edges=[];bydoc=collections.defaultdict(list)
    for kind,items in LEXICON.items():
        for name in items:entities[name]={'id':name,'name':name,'type':kind,'basis':'系统词表','confidence':'high'}
    current={}
    expanded_rows=[]
    for raw in rows:
        # Split identifiable exercise starts in the existing OCR text only.
        # Keep the source chunk ID for navigation to the unchanged V1.1 record.
        starts=list(re.finditer(r'(?m)^\s*(\d+\s*[.．]\s*\d+\s*[.．]\s*\d+)\s*(?=设|求|证明|试|若|对|当|已|作|取|令|说明|计算)',raw['text'])) if '习题解答' in raw['name'] else []
        if starts:
            if starts[0].start()>100:
                prefix=dict(raw,text=raw['text'][:starts[0].start()],label=None);expanded_rows.append(prefix)
            for i,match in enumerate(starts):
                number=normalize(match.group(1));child=dict(raw,id=raw['id']+':exercise:'+number,
                    source_chunk_id=raw['id'],text=raw['text'][match.start():starts[i+1].start() if i+1<len(starts) else len(raw['text'])],
                    label='习题'+number,content_type='exercise')
                expanded_rows.append(child)
        else:expanded_rows.append(raw)
    for raw in expanded_rows:
        r={k:v for k,v in raw.items() if k not in {'vector','path','digest'}}
        r.update(book=r['name'],book_name=r['title'],source_file=r['name'],pdf_page=r['page'],pdf_page_start=r['page'],pdf_page_end=r['page_end'] or r['page'],difficulty=None)
        # Do not trust chapter inherited from a table of contents in V1.1 OCR.
        heading=re.search(r'(?m)^\s*(第[一二三四五六七八九十\d]+章[^\n]*)',r['text'])
        r['chapter']=heading.group(1)[:100] if heading else None
        m=mentions(r['text']);r.update(concepts=m['Concept'],theorems=m['Theorem'],methods=m['Method'],problem_types=m['ProblemType'])
        label=normalize(r.get('label') or '')
        r['example_number']=label[1:] if label.startswith('例') else None
        exercise=re.match(r'(?:习题|练习)(\d+(?:\.\d+)+)',label)
        r['exercise_number']=normalize(exercise.group(1)) if exercise else None
        if exercise:r['content_type']='exercise';r['label']='习题'+r['exercise_number']
        did=r['doc'];previous=current.get(did)
        continuation=(previous and (not r.get('label') or r.get('label')==previous['label']) and r['page'] is not None and previous['page'] is not None
                      and 0<=r['page']-previous['page']<=1 and (not r['section'] or r['section']==previous['section'])
                      and sum(len(x['text']) for x in parents[previous['parent']]['children'])<8000)
        pid=previous['parent'] if continuation else 'parent:'+r['id']
        r['parent_chunk']=pid
        parents.setdefault(pid,{'id':pid,'doc':did,'label':r.get('label'),'content_type':r.get('content_type'),'children':[]})['children'].append(r)
        current[did]={'parent':pid,'page':r['page'],'section':r['section'],'label':r.get('label') or (previous['label'] if continuation else None)}
        if r['section']:
            sid=did+':section:'+r['section'];sections.setdefault(sid,[]).append(r['id']);r['section_parent']=sid
        else:r['section_parent']=None
        records.append(r);bydoc[did].append(r)
        if r['example_number'] or r['exercise_number']:
            typ='Example' if r['example_number'] else 'Exercise'
            entities[r['id']]={'id':r['id'],'name':r['label'],'type':typ,'doc':did,'pdf_page':r['page'],'basis':'教材 OCR 编号','confidence':'explicit'}
            for kind,relation in [('Concept','TESTS'),('Theorem','USES_THEOREM'),('Method','USES_METHOD')]:
                for name in m[kind]:
                    aliases=LEXICON[kind][name];snippet=next((line.strip() for line in r['text'].splitlines() if any(normalize(a) in normalize(line) for a in aliases)), '')[:250]
                    # TESTS is a conservative inferred annotation. USES requires
                    # a proof-use cue, rather than merely a theorem mention.
                    cue=bool(re.search(r'由|利用|应用|根据|运用|取|构造|令|设',snippet))
                    if kind!='Concept' and not cue:continue
                    edges.append({'source':r['id'],'target':name,'relation':relation,'basis':'系统推断：教材术语'+('及使用语句' if cue else '提及'),
                                  'confidence':'high','evidence':{'chunk':r['id'],'doc':did,'pdf_page':r['page'],'excerpt':snippet}})
    for group in bydoc.values():
        for i,r in enumerate(group):r['neighboring_chunks']=[x['id'] for x in group[max(0,i-1):i]+group[i+1:i+2]]
    for p in parents.values():
        children=p.pop('children');p.update(child_ids=[r['id'] for r in children],text='\n'.join(r['text'] for r in children),
                                           pdf_page_start=children[0]['page'],pdf_page_end=children[-1]['page'])
    edges.extend(catalogue_edges(entities))
    return {'records':records,'parents':parents,'sections':sections,'entities':entities,'edges':edges}

def semantic_text(record):
    """Keep OCR formulas untouched for display/exact search; encode readable
    prose plus explicit term annotations to avoid truncating it behind a long
    formula or repeated scanned-page advertisements."""
    terms=record['concepts']+record['theorems']+record['methods']+record['problem_types']
    prefix='；'.join([record['subject'],record.get('section') or '',record.get('label') or '',*terms])
    prose=[]
    for line in record['text'].splitlines():
        if re.search(r'微信|公众号|mianbaoduo|manbaoduo|zhangzujin|pdf资料',normalize(line)):continue
        if len(re.findall(r'[\u4e00-\u9fff]',line))>=3:prose.append(line)
    return prefix+'\n'+('\n'.join(prose) if prose else record['text'])

def build(progress=print,semantic=True):
    folder,model_folder,_=locations();rows=legacy_rows()
    if not rows:raise ValueError('现有索引没有 chunks；未调用 OCR 或重建旧索引')
    data=structure(rows);generation=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
    target=folder/'generations'/generation;target.mkdir(parents=True)
    manifest={'INDEX_VERSION':INDEX_VERSION,'generation':generation,'source_signature':signature(rows),'created_at':time.time(),
              'source_chunks':len(rows),'records':len(data['records']),'semantic_available':False,'embedding':None,'semantic_representation':SEMANTIC_REPRESENTATION}
    if semantic:
        from app.rag.local_dense import E5CPU
        import numpy as np
        engine=E5CPU(model_folder);start=time.perf_counter();last=[0]
        def tick(n,total):
            if n-last[0]>=128 or n==total:progress(f'embeddings {n}/{total} ({time.perf_counter()-start:.1f}s)');last[0]=n
        # The numbered block is a child; full neighbouring/parent text is kept
        # independently and never truncated for provenance.
        vectors=engine.embed([semantic_text(r) for r in data['records']],progress=tick)
        if vectors.shape!=(len(data['records']),384) or not np.isfinite(vectors).all():raise ValueError('语义向量形状/数值无效')
        np.save(target/'vectors.npy',vectors)
        manifest.update(semantic_available=True,embedding=engine.identity,embedding_seconds=round(time.perf_counter()-start,3),dimensions=384)
    (target/'knowledge.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    # Publish only a complete generation; a failed build leaves active intact.
    pointer=folder/'active.json';temp=folder/('active-'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps({'generation':generation,'INDEX_VERSION':INDEX_VERSION}),encoding='utf8');temp.replace(pointer)
    _cache.clear();return manifest

class BM25:
    def __init__(self,records):
        self.counts=[collections.Counter(self.math_tokens(r['text'])) for r in records];self.lengths=[sum(x.values()) for x in self.counts]
        self.avg=sum(self.lengths)/max(1,len(records));self.df=collections.Counter(t for x in self.counts for t in x)
    def score(self,query):
        q=set(self.math_tokens(query));N=len(self.counts);idf={t:math.log(1+(N-self.df[t]+.5)/(self.df[t]+.5)) for t in q}
        return [sum(idf[t]*x[t]*2.2/(x[t]+1.2*(.25+.75*L/max(1,self.avg))) for t in q if x[t]) for x,L in zip(self.counts,self.lengths)]
    @staticmethod
    def math_tokens(text):
        # Pure bigrams lose essential one-character mathematical terms when
        # OCR removes spaces (e.g. "迹为" versus "迹的").
        return tokens(text)+re.findall(r'[秩迹根基核域]',normalize(text))

def load():
    folder,model_folder,_=locations();pointer=folder/'active.json'
    if not pointer.is_file():raise ValueError('V1.2 索引未建立')
    generation=json.loads(pointer.read_text(encoding='utf8'))['generation']
    if not re.fullmatch(r'[\w-]+',generation):raise ValueError('索引 generation 无效')
    key=(str(folder),generation)
    with _lock:
        if key not in _cache:
            for previous in list(_cache):
                if previous[0]==str(folder) and previous!=key:_cache.pop(previous)
            path=folder/'generations'/generation;manifest=json.loads((path/'manifest.json').read_text(encoding='utf8'))
            if manifest['INDEX_VERSION']!=INDEX_VERSION:raise ValueError('索引版本不匹配')
            if manifest.get('semantic_representation')!=SEMANTIC_REPRESENTATION:raise ValueError('语义文本表示已改变，请重建 V1.2 索引')
            if manifest['source_signature']!=signature(legacy_rows()):raise ValueError('原索引已更新，请重新执行 index-v12（不会 OCR）')
            data=json.loads((path/'knowledge.json').read_text(encoding='utf8'));data['manifest']=manifest;data['bm25']=BM25(data['records'])
            data['byid']={r['id']:r for r in data['records']};data['engine']=None;data['vectors']=None
            if manifest['semantic_available']:
                from app.rag.local_dense import E5CPU
                import numpy as np
                data['engine']=E5CPU(model_folder)
                if data['engine'].identity!=manifest['embedding']:raise ValueError('模型与索引向量空间不一致')
                data['vectors']=np.load(path/'vectors.npy',allow_pickle=False)
                if data['vectors'].shape!=(len(data['records']),384):raise ValueError('向量文件不完整')
            _cache[key]=data
        data=_cache[key]
        # Deletion / reindex must not return stale textbook records. Cheap docs
        # signature checked every request; full chunk signature only on loading.
        rows=legacy_rows()
        if signature(rows)!=data['manifest']['source_signature']:raise ValueError('教材索引有变动，回退 V1.1.1；需运行 index-v12')
        return data

def status():
    if os.getenv('RETRIEVAL_VERSION','v12')=='v11':return {'active_version':'v11','semantic_available':False,'fallback_reason':'手动选择 V1.1.1'}
    try:
        data=load();return dict(data['manifest'],active_version='v12',fallback_reason=None)
    except Exception as e:return {'active_version':'v11','semantic_available':False,'fallback_reason':str(e)}

def search(query,subject='all',docids=None,k=10,variant='full'):
    start=time.perf_counter();profile=parse_query(query,subject);expansion=expand(profile)
    if variant not in {'full','hybrid','keyword'}:raise ValueError('未知 V1.2 检索变体')
    try:
        if os.getenv('RETRIEVAL_VERSION','v12')=='v11':raise ValueError('手动选择 V1.1.1')
        data=load()
    except Exception as e:
        from app.rag.service import retrieve
        sources=retrieve(query,subject,docids,k)
        return {'INDEX_VERSION':'v11','semantic_available':False,'fallback_reason':str(e),'query_profile':profile,'expansion':[],
                'results':sources,'candidates':[],'evidence_bundle':bundle(sources,None,profile),'elapsed_ms':round((time.perf_counter()-start)*1000,2)}
    records=data['records'];allowed=[i for i,r in enumerate(records) if (subject=='all' or r['subject']==subject) and (not docids or r['doc'] in docids)]
    exact_records=[records[i] for i in allowed if normalize(records[i].get('label') or '') in profile['exact_identifiers']]
    if variant=='full' and exact_records:
        # A numerical identifier conveys little semantic information. Once it
        # resolves, use only the actual matching textbook block to hypothesise
        # related concepts/methods, with the provenance visible in Debug.
        for field,key,kind in [('concepts','concepts','Concept'),('theorems','possible_theorems','Theorem'),('methods','possible_methods','Method')]:
            for row in exact_records:
                for name in row[field]:
                    if name not in profile[key]:
                        profile[key].append(name);profile['hypotheses'].append({'kind':kind,'name':name,'basis':'系统注解：编号命中原文的术语','confidence':'high','reason':f"源 chunk {row['id']} / PDF {row['page']}；不自动确认数学适用条件"})
        expansion=expand(profile)
    if not allowed:return {'INDEX_VERSION':INDEX_VERSION,'semantic_available':bool(data['engine']),'fallback_reason':None,'query_profile':profile,'expansion':expansion,'results':[],'candidates':[],'evidence_bundle':bundle([],data,profile),'elapsed_ms':0}
    raw=data['bm25'].score(query);expanded=[0.]*len(records)
    if variant=='full':
        for item in expansion[1:]:
            scores=data['bm25'].score(item['query'])
            for i in allowed:expanded[i]=max(expanded[i],scores[i]*(.55 if item['confidence']=='medium' else .8))
    semantic=[0.]*len(records);semantic_on=bool(data['engine']) and variant!='keyword';semantic_query=None
    if semantic_on:
        # Keep original sentence central; candidate hypotheses contribute only
        # through lexical/metadata channels, not an unbounded vector expansion.
        semantic_query=semantic_text(exact_records[0]) if variant=='full' and exact_records else query
        vector=data['engine'].embed([semantic_query],query=True)[0];semantic=(data['vectors']@vector).tolist()
    maxraw=max([raw[i] for i in allowed]+[1]);maxexp=max([expanded[i] for i in allowed]+[1]);maxsem=max([semantic[i] for i in allowed]+[.001]);minsem=min(semantic[i] for i in allowed)
    candidates=[]
    for i in allowed:
        r=records[i];ids=profile['exact_identifiers'];label=normalize(r.get('label') or '')
        exact=1. if label and label in ids else (.15 if any(re.search(re.escape(x)+r'(?![\d.])',normalize(r['text'])) for x in ids) else 0.)
        reason=[];metadata=0.
        for field,key,tag in [('concepts','concepts','same_concept'),('methods','possible_methods','same_method'),('theorems','possible_theorems','same_theorem'),('problem_types','problem_type','same_problem_type')]:
            shared=sorted(set(r[field])&set(profile[key] or []))
            if shared:metadata+=min(.18,.09*len(shared));reason.append({'relation':tag,'entities':shared,'basis':'系统推断：术语/候选假设交集','confidence':'medium'})
        if exact:reason.append({'relation':'exact_identifier' if exact==1 else 'identifier_mention','entities':ids,'basis':'教材 OCR 编号','confidence':'explicit'})
        kw=raw[i]/maxraw;ex=expanded[i]/maxexp
        sem=(semantic[i]-minsem)/max(1e-6,maxsem-minsem) if semantic_on else 0.
        graph_edges=[e for e in data['edges'] if e['source']==r['id'] and e['target'] in profile['possible_methods']+profile['possible_theorems']]
        graph=min(.12,.04*len(graph_edges)) if variant=='full' else 0.
        base=.58*kw+.28*sem+(1000 if exact==1 else .08 if exact else 0)
        final=base;structural=0.
        if variant=='full':
            final+=.28*ex+metadata+graph
            if r['subject']==profile['subject'] and subject=='all':final+=.035
            if profile['query_intent']=='explain_concept' and r['content_type'] in {'definition','theorem'}:final+=.12
            if profile['query_intent']=='find_similar_problem' and r['content_type'] in {'example','exercise'}:final+=.08
            if profile['query_intent']=='explain_concept':
                # Prefer an explanation/definition that explicitly names the
                # requested concept, instead of an unrelated worked example.
                ntext=normalize(r['text'])
                if r['content_type'] not in {'example','exercise'} and any(normalize(t) in ntext for t in profile['concepts']):
                    if re.search(r'定义|所谓|充要条件|必要条件|利用定义',ntext):
                        final+=.24;structural=.24+metadata+ex*.2
        candidates.append((i,{'candidate_score':round(base,6),'exact_score':exact,'keyword_score':round(raw[i],6),'expansion_score':round(expanded[i],6),
                              'semantic_score':round(semantic[i],6) if semantic_on else None,'metadata_score':round(metadata,6) if variant=='full' else 0.,
                              'graph_score':graph,'structural_score':round(structural,6),'final_score':round(final,6),'relationship':reason,'graph_evidence':graph_edges}))
    # Stage 1: union of lexical/dense/expanded/exact candidates, capped at 50.
    pools=set();fusion=collections.defaultdict(float)
    for channel in ['keyword_score','semantic_score','expansion_score','exact_score','structural_score']:
        ranking=sorted(candidates,key=lambda x:x[1][channel] or 0,reverse=True)
        for rank,(i,scores) in enumerate(ranking[:30],1):
            if (scores[channel] or 0)>0:
                pools.add(i);fusion[i]+=(1. if channel!='exact_score' else 2.)/(60+rank)
    recalled=sorted([x for x in candidates if x[0] in pools],key=lambda x:(x[1]['exact_score']==1,fusion[x[0]]),reverse=True)[:50]
    for i,scores in recalled:scores['candidate_rrf']=round(fusion[i],8)
    reranked=sorted(recalled,key=lambda x:x[1]['final_score'],reverse=True)
    def result(item):
        i,sc=item;r=dict(records[i]);r.update(sc,score=sc['final_score'],semantic_available=semantic_on,retrieval_backend='local-e5-int8-hybrid' if semantic_on else 'v12-keyword',retrieval_mode=variant)
        r['confidence']='explicit' if sc['exact_score']==1 else 'medium';r['basis']='教材 OCR 直接编号' if sc['exact_score']==1 else '系统检索推断；请核查原页'
        return r
    results=[result(x) for x in reranked[:k]]
    candidates_result=[result(x) for x in reranked]
    evidence=bundle(results,data,profile)
    if variant=='full':
        relevant_terms=set(profile['concepts']+profile['possible_theorems'])
        # Auxiliary theory channel is separate from the ranked top-K benchmark.
        # It uses actual recalled text, never synthesized statements/page IDs.
        theories=[r for r in candidates_result if r['content_type'] not in {'example','exercise'} and relevant_terms&set(r['concepts']+r['theorems']) and re.search(r'定义|定理|准则|要点|公式',r['text'])]
        for r in theories[:3]:
            if not any(x['id']==r['id'] for x in evidence['core_theory']):evidence['core_theory'].append(r)
        for r in evidence['core_theory']:
            if r.get('page'):
                page=bundle([r],None,profile)['source_pages'][0]
                if page not in evidence['source_pages']:evidence['source_pages'].append(page)
    return {'INDEX_VERSION':INDEX_VERSION,'semantic_available':semantic_on,'fallback_reason':None,'query_profile':profile,'expansion':expansion if variant=='full' else expansion[:1],
            'results':results,'candidates':candidates_result,'candidate_count':len(recalled),'evidence_bundle':evidence,
            'semantic_query':semantic_query,'reranker':'local-explainable-metadata-v1' if variant=='full' else None,'elapsed_ms':round((time.perf_counter()-start)*1000,2)}

def similar(query,subject='all',docids=None,k=5,exclude=None):
    response=search(query,subject,docids,30);profile=response['query_profile'];rows=response['results']
    if not exclude and profile['exact_identifiers']:
        exclude=next((r['id'] for r in rows if r.get('exact_score')==1),None)
    groups={'surface':[],'concept':[],'method':[]}
    for r in rows:
        if r['id']==exclude or r.get('content_type') not in {'example','exercise'}:continue
        explanation={'basis':'系统推断','confidence':'medium','source':r,'relation':'SIMILAR_TO','source_entity':exclude,'target_entity':r['id']}
        if r.get('keyword_score',0)>0 or (r.get('semantic_score') or 0)>.5:
            groups['surface'].append(dict(explanation,reason='表达/关键词/语义接近，不能保证解法相同'))
        shared=sorted(set(r.get('concepts',[])+r.get('theorems',[]))&set(profile['concepts']+profile['possible_theorems']))
        if shared:groups['concept'].append(dict(explanation,reason='知识点或定理候选相同：'+', '.join(shared)))
        shared=sorted(set(r.get('methods',[]))&set(profile['possible_methods']))
        if shared:groups['method'].append(dict(explanation,reason='方法候选相同：'+', '.join(shared)+'；须核查使用条件'))
    return {'query_profile':profile,'semantic_available':response['semantic_available'],'fallback_reason':response['fallback_reason'],
            'groups':{kind:items[:k] for kind,items in groups.items()}}

def bundle(results,data,profile):
    groups={'exact_match':[],'core_theory':[],'similar_problems':[],'method_related':[],'parent_context':[],'source_pages':[]}
    for rank,r in enumerate(results):
        if r.get('exact_score')==1 or rank==0:groups['exact_match'].append(r)
        elif r.get('content_type') in {'definition','theorem','lemma','corollary'}:groups['core_theory'].append(r)
        elif any(x['relation']=='same_method' for x in r.get('relationship',[])):
            groups['method_related'].append(r)
            if r.get('content_type') in {'example','exercise'}:groups['similar_problems'].append(r)
        elif r.get('content_type') in {'example','exercise'}:groups['similar_problems'].append(r)
        else:groups['core_theory'].append(r)
        if data and r.get('parent_chunk') in data['parents']:
            p=dict(data['parents'][r['parent_chunk']]);p['neighboring_chunks']=[dict(data['byid'][x]) for x in r.get('neighboring_chunks',[]) if x in data['byid']]
            if len(groups['parent_context'])<4 and not any(x['id']==p['id'] for x in groups['parent_context']):groups['parent_context'].append(p)
        if r.get('page'):
            page={'doc':r['doc'],'book':r['name'],'pdf_page':r['page'],'pdf_url':f"/api/documents/{r['doc']}/pdf#page={r['page']}",'page_url':f"/api/documents/{r['doc']}/page/{r['page']}"}
            if page not in groups['source_pages']:groups['source_pages'].append(page)
    for key in ['core_theory','similar_problems','method_related']:groups[key]=groups[key][:5]
    return groups

def topic(name,subject='all'):
    data=load()
    if name not in data['entities']:raise ValueError('知识点或方法不存在')
    response=search(name,subject,k=20)
    rows=[r for r in response['results'] if name in r.get('concepts',[])+r.get('methods',[])+r.get('theorems',[])+r.get('problem_types',[])]
    return {'entity':data['entities'][name],'catalogue':dict(CATALOGUE.get(name,{}),basis='系统整理：通用方法说明，非教材引文',confidence='high'),
            'prerequisites':[{'name':p,'basis':'系统整理','confidence':'high'} for p in PREREQUISITES.get(name,[])],
            'confusions':{'text':CONFUSIONS.get(name),'basis':'系统整理'},'relations':[e for e in data['edges'] if e['source']==name or e['target']==name][:60],
            'theory':[r for r in rows if r['content_type'] in {'definition','theorem','lemma','corollary'}][:5],
            'examples':[r for r in rows if r['content_type'] in {'example','exercise'}][:10], 'sources':rows[:10],
            'related_methods':[m for m,c in CATALOGUE.items() if name in c['theorems'] or name in c['types']],
            'similar_problems':similar(name,subject,k=3)}

def map_summary():
    data=load();counts=collections.Counter(e['type'] for e in data['entities'].values());relations=collections.Counter(e['relation'] for e in data['edges'])
    return {'INDEX_VERSION':INDEX_VERSION,'entity_counts':dict(counts),'relation_counts':dict(relations),
            'supported_relations':['USES_METHOD','TESTS','USES_THEOREM','SIMILAR_TO','APPLIES_TO','REQUIRES','PREREQUISITE_OF'],
            'similar_to_policy':'查询时生成带解释的关系，不把低置信度相似关系写入永久图',
            'methods':[e for e in data['entities'].values() if e['type']=='Method'],
            'topics':[e for e in data['entities'].values() if e['type'] in {'Concept','Theorem'}]}

def offline_navigation(question,mode,profile,evidence,sources):
    """Useful local navigation, not an invented mathematical solution."""
    labels={s['id']:f'[S{i}]' for i,s in enumerate(sources,1)}
    lines=['离线知识导航：以下是本地检索与系统候选思路；完整数学推导尚未生成。',
           '知识点候选：'+('、'.join(profile['concepts']) or '未可靠识别'),
           '题型候选：'+('、'.join(profile['problem_type'] or []) or '未可靠识别'),
           '可能方法（系统推断）：'+('、'.join(profile['possible_methods']) or '未可靠识别')]
    if mode=='hint':
        method=next((CATALOGUE[m] for m in profile['possible_methods'] if m in CATALOGUE),None)
        lines.append('本次一层提示：'+(method['strategy'].split('，')[0] if method else '先打开直接命中的教材原页，找出已知条件与目标。'))
        return '\n\n'.join(lines)
    if mode=='review':lines.append('未启用讲解模型，不能自动判断你每一步的数学正确性；可先对照下列原页。')
    for m in profile['possible_methods']:
        if m in CATALOGUE:lines.append('方法迁移（系统整理）— '+m+'：看到 '+' / '.join(CATALOGUE[m]['triggers'])+' → 尝试 '+CATALOGUE[m]['strategy'])
    related=[];seen=set()
    for r in evidence['similar_problems']+evidence['method_related']:
        if r.get('content_type') not in {'example','exercise'} or r['id'] in seen:continue
        seen.add(r['id']);related.append(r)
    lines.append('类似题（系统检索推断，请核对原页）：')
    if len(related)<2:lines.append('可靠关联题不足两道，暂不补造。')
    for r in related[:5]:
        why='；'.join(x['relation']+': '+', '.join(x['entities']) for x in r.get('relationship',[]) if x['relation'].startswith('same_')) or '表达/语义接近，尚需确认方法'
        lines.append(f"{labels[r['id']]} {r.get('label') or '教材片段'} · {r['name']} · PDF 第 {r['page']} 页。原因：{why}")
    return '\n\n'.join(lines)
