"""Offline checks for evaluation discipline, not tests mirroring model scores."""
import json,hashlib
import numpy as np
from pathlib import Path
from metrics import score,relevant
LAB=Path(__file__).resolve().parent
def row(page,label=None):return {'id':str(page),'name':'book','page':page,'label':label}
def target(page,grade=3,label=None):
 t={'book':'book','pdf_page':page,'grade':grade}
 if label:t['label']=label
 return t
def test_recall_50_is_distinct_from_rank_10():
 rows=[row(i) for i in range(1,51)];m=score(rows,[target(34)])
 assert m['Recall@10']==0 and m['Recall@50']==1 and m['failure_class']=='Ranking Opportunity' and m['first_relevant_rank']==34
def test_absent_target_is_not_rerank_opportunity():
 m=score([row(i) for i in range(50)],[target(90)]);assert m['first_relevant_rank'] is None and m['failure_class']=='Recall Failure'
def test_raw_cutoff_keeps_duplicate_chunks():
 rows=[row(1)]*10+[row(2)];m=score(rows,[target(2)]);assert m['Recall@10']==0 and m['Recall@20']==1
def test_duplicate_page_does_not_inflate_ndcg():
 assert score([row(1)]*10,[target(1)])['nDCG@10']==1
def test_hard_negative_is_not_positive():
 m=score([row(1),row(2)],[target(1,0),target(2)]);assert m['Hit@1']==0 and m['MRR@10']==.5 and m['hard_negative_in_top5']==1
def test_exact_label_matters():
 assert not relevant(row(1,'例1.2'),target(1,label='例1.3'))
def test_c_is_frozen_and_large_enough():
 f=json.loads((LAB/'freeze.json').read_text(encoding='utf8'));d=json.loads((LAB/'test_c.json').read_text(encoding='utf8'))
 assert hashlib.sha256((LAB/'test_c.json').read_bytes()).hexdigest()==f['test_sha256'];assert len(d['questions'])>=70
def test_source_pages_disjoint_from_both_development_sets():
 c=json.loads((LAB/'test_c.json').read_text(encoding='utf8'))
 dev={(t['book'],t['pdf_page']) for name in ['development_a.json','development_b.json'] for q in json.loads((LAB/name).read_text(encoding='utf8'))['questions'] for t in q['relevant']}
 assert not dev&{(t['book'],t['pdf_page']) for q in c['questions'] for t in q['relevant']}
def test_all_targets_exist_in_unchanged_corpus():
 corpus=json.loads((LAB/'corpus.json').read_text(encoding='utf8'));c=json.loads((LAB/'test_c.json').read_text(encoding='utf8'))
 assert all(any(relevant(r,t) for r in corpus['records']) for q in c['questions'] for t in q['relevant'])
def test_reranking_never_adds_candidate_ids():
 for p in (LAB/'results_rerank').glob('*.json'):
  d=json.loads(p.read_text(encoding='utf8'))
  for c in d.get('cases',[]):assert set(c['candidate_ids'])=={r['id'] for r in c['top50']}
def test_dense_runs_use_frozen_datasets():
 for p in (LAB/'results_recall').glob('*.json'):
  d=json.loads(p.read_text(encoding='utf8'));assert d['dataset_sha256']==hashlib.sha256((LAB/(d['dataset']+'.json')).read_bytes()).hexdigest()
def test_model_file_manifest_is_true():
 for p in (LAB/'models').glob('*/manifest.json'):
  d=json.loads(p.read_text(encoding='utf8'))
  if d['status']!='downloaded_verified':continue
  for name,m in d['files'].items():assert (p.parent/name).stat().st_size==m['bytes']
