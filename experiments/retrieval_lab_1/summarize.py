"""Audit raw runs and write reproducible tables. Never tune/relabel/promote."""
import json,time,hashlib,statistics,collections,math,sys
from pathlib import Path
import numpy as np
from inference import LAB,ROOT,verify_freeze,sha
from metrics import aggregate
from run_recall import dump
def load(p):return json.loads(p.read_text(encoding='utf8'))
def pct(v):return f'{100*v:.2f}%'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def cluster_ci(a,b,questions,key='Recall@10',draws=4000):
 groups=collections.defaultdict(list)
 for i,q in enumerate(questions):
  t=next(t for t in q['relevant'] if t.get('grade',3)>0);groups[(t['book'],t['pdf_page'])].append(b[i][key]-a[i][key])
 rng=np.random.default_rng(731);vals=list(groups.values());est=[]
 for j in range(draws):
  selected=rng.integers(0,len(vals),len(vals));sample=[v for i in selected for v in vals[i]];est.append(statistics.mean(sample))
 return {'paired_mean_delta':statistics.mean(b[i][key]-a[i][key] for i in range(len(questions))),'bootstrap_95CI':[float(x) for x in np.percentile(est,[2.5,97.5])],'resampling_unit':'positive book/PDF page cluster','clusters':len(vals),'seed':731,'draws':draws}
def generate():
 f=verify_freeze();questions=load(LAB/'test_c.json')['questions'];raw={p.name.removesuffix('-test_c.json'):load(p) for p in (LAB/'results_recall').glob('*-test_c.json')};reranks={p.stem:load(p) for p in (LAB/'results_rerank').glob('*.json') if 'summary' in load(p)}
 assert len(raw)==5,'all five dense conditions required'
 model_manifest=load(LAB/'model_manifest.json');small=load(ROOT/'data/models/e5-small-int8/manifest.json');model_manifest['baseline']={**small,'name':'e5-small','source_url':'https://huggingface.co/'+small['repository'],'directory':'existing baseline read-only'};dump(LAB/'model_manifest.json',model_manifest)
 baseline=raw['e5-small'];best=max(raw,key=lambda n:(raw[n]['summary']['overall']['Recall@50'],raw[n]['summary']['overall']['MRR@50']));bestR=max(reranks,key=lambda n:(reranks[n]['summary']['overall']['Recall@10'],reranks[n]['summary']['overall']['MRR@10'])) if reranks else None
 first_rank_matrix=[];failures=[];ocr=load(LAB/'ocr_review.json')['case_reviews']
 for i,q in enumerate(questions):
  ranks={n:d['cases'][i]['first_relevant_rank'] for n,d in raw.items()};classes={n:d['cases'][i]['failure_class'] for n,d in raw.items()};common=all(v is None for v in ranks.values());review=ocr.get(q['id'])
  first_rank_matrix.append({'id':q['id'],'query':q['query'],'category':q['category'],'subject':q['subject'],'source_style':q['source_style'],'first_relevant_rank':ranks,'classes':classes})
  if any(v is None or v>5 for v in ranks.values()):
   failures.append({'id':q['id'],'query':q['query'],'targets':q['relevant'],'first_ranks':ranks,'failure_classes':classes,'all_models_miss_top50':common,'source_review':review or {'tag':'undetermined' if common else 'no exclusive source-cause attribution','evidence':'See read-only source_representation_audit.json. Missing annotated target is not proof that every returned passage is irrelevant.'},'formula_heavy':q['source_style']=='formula-heavy'})
 dump(LAB/'failure_analysis.json',{'test_sha256':sha(LAB/'test_c.json'),'cases':failures,'common_failures':[x['id'] for x in failures if x['all_models_miss_top50']],'common_OCR_limited':[x['id'] for x in failures if x['all_models_miss_top50'] and x['source_review']['tag']=='OCR-limited'],'policy':'Do not count OCR-limited semantic gains toward model upgrade; cases can have multiple causes; no label changes'})
 dump(LAB/'first_relevant_ranks.json',first_rank_matrix)
 ci={n:{key:cluster_ci(baseline['cases'],raw[n]['cases'],questions,key) for key in ['Recall@10','Recall@50']} for n in raw if n!='e5-small'}
 for n,d in reranks.items():
  d['performance']['median_total_ms']=statistics.median(c['total_search_ms'] for c in d['cases'])
  source=raw[d['retriever']];assert all(set(c['candidate_ids'])=={r['id'] for r in c['top50']} for c in d['cases']);assert d['summary']['overall']['Recall@50']==source['summary']['overall']['Recall@50']
  ci[n]={'Recall@10':cluster_ci(source['cases'],d['cases'],questions)}
 result={'created_at':time.time(),'test':f,'retrieval':raw,'reranking':reranks,'first_relevant_ranks':first_rank_matrix,'confidence_intervals':ci,'active_v12_context':load(LAB/'active_v12_context.json') if (LAB/'active_v12_context.json').exists() else None,'quality_winner_raw':best,'quality_winner_fixed_pool':bestR,'active_changed':False,'scope':'CPU INT8 conversions at 384 tokens; partial source-page relevance; single-assistant annotated 80 queries on 25 source pages; not full-precision family capability proof','experiments_only':True}
 dump(LAB/'results.json',result)
 # The full interpretive conclusion is added after inspecting all results;
 # tables here are generated exclusively from measured raw runs.
 sections=['# MathTutor Retrieval Lab 1 实测报告','正式 active 保持 V1.2，V1.2.1 仍是候选。实验代码、模型、索引和结果均位于 experiments/retrieval_lab_1；普通聊天没有接入实验。','## 数据纪律与可复现性',
 f'Test C：80题，8类各10题；高代45/分析35；25个源PDF页，覆盖三本教材，源页与开发集A/B不重叠。SHA256 `{f["test_sha256"]}`。冻结时间 `{f["frozen_at"]}`（Unix秒）。Test C 原文 author_policy 写26主题，是计数笔误，实际 source_pages 为25；为保留冻结字节未修订该元数据。',
 'A为原35题开发集，B为已查看结果的旧70题holdout，均只标 development。新C在模型推理前由本任务助手依据原PDF图像核对后编写、标注和冻结，未经独立人工复核。80道问题共享25页，有相关性；单一助手内部标注，相关页非穷尽，尤其类似题/方法题可能有其它未标注正确页。指标是找回指定正确源页的指标，不能等同于所有答案的数学正确率。Exact 另检查例题编号；其它题按 book/PDF page 判相关，同页其它习题也可能被计入，因此页级指标可能高估题目级相关性。',
 '所有模型使用相同3,800条V1.2 records、相同 semantic_text passage、相同raw query和TopK；第一阶段不用词典/组合规则/扩展/精确旁路，不按学科过滤，搜索全部三本教材。384 tokens 是本机实验预算，不是BGE/Qwen原生上下文上限；各模型tokenizer不同，实际可见字符数量不同。索引统计 truncated_passages 按达到384-token上限计数，包含刚好到上限的记录，是近似截断统计。E5-small直接复用原E5CPU类，完整独立重建向量与旧向量逐项相等。',
 f'Qwen D1无instruction；D2和Qwen reranker全题使用唯一固定instruction：`{f["qwen_instruction"]}`。冻结后未调整任何数学规则、权重、alias或ground truth。',
 '## 第一阶段：纯 dense candidate recall',
 table(['Retriever','R@5','R@10','R@20','R@50','MRR@50','mean/median/P95 ms','峰值RAM MiB'],[[n,*[pct(d['summary']['overall'][k]) for k in ['Recall@5','Recall@10','Recall@20','Recall@50']],f"{d['summary']['overall']['MRR@50']:.4f}",'/'.join(f"{d['performance'][k]:.1f}" for k in ['mean_ms','median_ms','p95_ms']),f"{d['performance']['peak_rss_bytes']/2**20:.1f}"] for n,d in raw.items()]),
 '这里MRR截断50；第二阶段另列MRR@10。查询延迟包含tokenize、ONNX、向量点积和全库排序，不含冷加载；本机不同进程串行跑CPU，固定4个推理线程。CPU百分比是进程CPU秒/墙钟秒，可超过100%（占多核），不是全机平均CPU利用率。原V1.2的CPU arena开启，baseline保持不变；其它模型关闭arena以控制内存，资源差异需结合这一设置解读。',
 '## 资源与索引成本',
 table(['模型','维度','模型disk MiB','索引 MiB','索引秒','冷加载秒','达到token上限的passages','CPU%'],[[n,d['index']['dimensions'],f"{sum(x['bytes'] for x in (small if n=='e5-small' else next(m for m in model_manifest['models'] if m['name']==d['model']))['files'].values())/2**20:.1f}",f"{d['index']['disk_bytes']/2**20:.2f}",f"{d['index']['index_seconds']:.1f}",f"{d['performance']['cold_start_seconds']:.2f}",d['index']['truncated_passages'],f"{d['index']['index_process_cpu_percent']:.1f}"] for n,d in raw.items()]),
 'D1/D2共享同一passage index，只改变query instruction，不将同一建库成本计作两次。模型disk含权重、tokenizer/config/card；冷加载包括文件校验、tokenizer、ORT session，操作系统文件缓存未清空，非整机冷启动。RAM为测量进程PeakWorkingSetSize，含解释器、模型、索引和runtime工作内存。未安装GPU/PyTorch栈，没有新依赖安装。',
 '## 首次相关排名与四类失败',
 table(['Retriever','Success 1–5','Near 6–10','Opportunity 11–50','Recall Failure >50'],[[n,*[d['summary']['overall']['failure_classes'].get(k,0) for k in ['Success','Near Success','Ranking Opportunity','Recall Failure']]] for n,d in raw.items()]),
 '逐题排名和分类见 first_relevant_ranks.json；百分比为计数/80。Recall@50之外的目标，任意fixed-pool reranker都不能救回。',
 '## 第二阶段：固定Top50重排',
 '门槛预先固定为Test C Recall@50≥60%。未达门槛的E5-base等条件不进入神经重排。各retriever的Top50预先落盘，各reranker在同一个retriever pool上比较，不能增加候选。current适配器保留V1.2原有评分公式/词典/规则/权重，仅将候选入口固定为纯dense Top50、使用缓存原query向量；它不是普通聊天的完整混合检索结果。不同retriever的pool不同，横向neural差异需按各自pool解释。',
 table(['Retriever','Reranker','Hit@1','R@5','R@10','MRR@10','nDCG@10','total mean/median/P95 ms','峰值RAM MiB'],[[d['retriever'],d['reranker'],*[pct(d['summary']['overall'][k]) for k in ['Hit@1','Recall@5','Recall@10']],f"{d['summary']['overall']['MRR@10']:.4f}",f"{d['summary']['overall']['nDCG@10']:.4f}",f"{d['performance']['mean_total_ms']:.1f}/{d['performance']['median_total_ms']:.1f}/{d['performance']['p95_total_ms']:.1f}",f"{d['performance']['peak_rss_bytes']/2**20:.1f}"] for d in reranks.values()]),
 'Total latency为该次dense查询时间+重排时间；神经模型冷加载不计入交互延迟，另在结果performance给出。BGE使用query-document cross encoder logit；Qwen使用完整固定chat前后缀及yes-no末token logit差，等价于二分类softmax排序。384token预算内保留Qwen答案后缀，只裁剪document部分。nDCG为grade3正目标、grade0已标注hard negatives，重复chunk不会重复得分，cutoff仍按raw records。',
 '## 分学科与问题类型（Test C）']
 for grouping,label in [('subjects','学科'),('categories','类别'),('source_styles','公式/文字')]:
  sections.append('### '+label)
  sections.append(table(['方案','分组','n','Hit@1','R@5','R@10','R@20','R@50','MRR@10'],[[n,g,a['n'],*[pct(a[k]) for k in ['Hit@1','Recall@5','Recall@10','Recall@20','Recall@50']],f"{a['MRR@10']:.4f}"] for n,d in {**raw,**reranks}.items() for g,a in d['summary'][grouping].items()]))
 sections.extend(['## 开发集A/B（不能称独立测试）',table(['数据集','Retriever','R@5','R@10','R@20','R@50','MRR@50'],[[setname,n,*[pct(load(LAB/'results_recall'/f'{n}-{setname}.json')['summary']['overall'][k]) for k in ['Recall@5','Recall@10','Recall@20','Recall@50']],f"{load(LAB/'results_recall'/f'{n}-{setname}.json')['summary']['overall']['MRR@50']:.4f}"] for setname in ['development_a','development_b'] for n in raw]),
 '## 不确定性与重复测量','采用固定seed731的4000次按正目标book/PDF页cluster重采样，避免把相关的80问题当80独立主题。95% CI仅描述这份内部测试样本，未覆盖单一助手标注偏差。详细区间见results.json。',table(['方案 vs raw E5-small','ΔR@10','95% cluster CI'],[[n,pct(ci[n]['Recall@10']['paired_mean_delta']),'/'.join(pct(x) for x in ci[n]['Recall@10']['bootstrap_95CI'])] for n in raw if n!='e5-small']),
 '每个Test C query原进程重复一次，另独立进程重放纯dense所有C题；排名一致性见repeat/*.json。神经重排每题重复推理一次，记录repeat_top50_identical；没有重新建库做统计鲁棒性实验。',
 '## OCR与passage表示审计',f'所有dense条件都没召回的C题：{", ".join(x["id"] for x in failures if x["all_models_miss_top50"]) or "无"}。',
 '单独比对原PDF、raw OCR、实际encoded passage。明确标为OCR-limited的题见ocr_review.json；formula-heavy是冻结前标注，不能自动等同OCR-limited。没有对原教材做OCR或修复公式。',
 '例如习题解答PDF64的二阶中心差商原公式清晰，但OCR与prose过滤后的passage丢失导数阶数和分母；PDF81的归一化积分核和分部积分关键等式也严重损坏。高代PDF366的不变因子与特征/极小多项式公式部分被截掉。这里只判断存在representation限制，不声称它唯一导致模型漏召回。',
 '未确定归因的共同失败保留undetermined，不能仅因所有模型失败就断言OCR-limited，或断言所有embedding模型都无能力。未做干净转录/更长passage对照，无法因果分离OCR损坏、prose过滤、token截断和模型本身。',
 '## 模型来源与许可',table(['名称','转换来源','revision','上游许可'],[[m['name'],f"[{m['source']}]({m['source_url']})",m['revision'],m['license']] for m in model_manifest['models']]),
 '以上是第三方ONNX INT8转换，不能冒充官方原始权重。全部实际下载文件大小、SHA256及Hub LFS校验值见model_manifest.json。原模型说明：[E5-base](https://huggingface.co/intfloat/multilingual-e5-base)、[BGE-M3](https://huggingface.co/BAAI/bge-m3)、[Qwen Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)、[BGE Reranker](https://huggingface.co/BAAI/bge-reranker-v2-m3)、[Qwen Reranker](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)。部分转换repo缺少明确license元数据；清单license指上游许可，license_basis明确区分。',
 'BGE-M3只测dense；未测sparse和multi-vector，现有dense ONNX文件没有提供完整sparse/ColBERT heads。本轮只隔离dense召回与重排；Jina v3未列入第一批，也未下载。没有付费API和远程inference，网络仅用于读取公开模型资料、下载权重。',
 '## 安全与复现','运行顺序：make_test_c.py（一次性，存在冻结C即拒绝覆盖）→download_models.py（公开模型下载）→run_stage1.py→run_stage2.py→measure_active.py→audit_sources.py→summarize.py。本次下载早于冻结开始、模型推理晚于冻结；下载不涉及query或passage上传。重放建议直接使用run_recall.py模型名及verify_repeat.py，不再运行数据集生成脚本。',
 '正式代码/数据前后SHA256见integrity.json；pytest原80项与12项实验纪律测试见pytest-final.txt。实验仅新增独立目录；V1.2权重、V1.2.1词表/组合规则、PDF/OCR、数据库、聊天与全部旧索引均应保持不变。'])
 (LAB/'report.md').write_text('\n\n'.join(sections)+'\n',encoding='utf8')
 print('raw quality',best,'rerank quality',bestR,'common misses',sum(x['all_models_miss_top50'] for x in failures),flush=True)
if __name__=='__main__':generate()
