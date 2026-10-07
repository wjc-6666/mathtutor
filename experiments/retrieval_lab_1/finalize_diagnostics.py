"""Post-run diagnostic slices only; never mutate frozen inputs or app state."""
import json,collections,statistics
from inference import LAB,verify_freeze
from metrics import aggregate
from run_recall import dump
from summarize import cluster_ci,table,pct

def main():
 verify_freeze()
 result=json.loads((LAB/'results.json').read_text(encoding='utf8'))
 questions=json.loads((LAB/'test_c.json').read_text(encoding='utf8'))['questions']
 raw=result['retrieval'];ranked=result['reranking'];baseline=raw['e5-small']
 reviews=json.loads((LAB/'ocr_review.json').read_text(encoding='utf8'))['case_reviews']
 excluded={k for k,v in reviews.items() if v['tag']=='OCR-limited'}
 routes={**raw,**ranked};slices={};deltas={};tiers={};negative={}
 for name,d in routes.items():
  cases=d['cases'];assert [c['id'] for c in cases]==[q['id'] for q in questions]
  slices[name]={'non_Exact':aggregate([c for c in cases if c['category']!='Exact']),
               'exclude_reviewed_OCR_limited':aggregate([c for c in cases if c['id'] not in excluded]),
               'non_Exact_by_style':{style:aggregate([c for c in cases if c['category']!='Exact' and c['source_style']==style]) for style in ['formula-heavy','text-heavy']}}
  ref=baseline if name in raw else ranked.get(d['retriever']+'-current',raw[d['retriever']])
  deltas[name]={}
  for key in ['Recall@10','Recall@50']:
   deltas[name][key]={'reference':ref.get('retriever','')+(' + '+ref['reranker'] if 'reranker' in ref else ' raw'),
                    'gained':[c['id'] for a,c in zip(ref['cases'],cases) if not a[key] and c[key]],
                    'lost':[c['id'] for a,c in zip(ref['cases'],cases) if a[key] and not c[key]]}
  if name in ranked and d['reranker']!='current':
   deltas[name]['paired_R10_CI_vs_same_pool_current']=cluster_ci(ref['cases'],cases,questions)
  perf=d['performance'];p95=perf.get('p95_total_ms',perf.get('p95_ms'))
  tiers[name]={'p95_ms':p95,'experience':'Excellent' if p95<1000 else 'Acceptable' if p95<=3000 else 'Slow'}
  cases_negative=[c for c in cases if c['category']=='HardNegative']
  negative[name]={'n':len(cases_negative),'annotated_negative_in_Top5':sum(c['hard_negative_in_top5'] or 0 for c in cases_negative)}
 common=[q['id'] for i,q in enumerate(questions) if all(d['cases'][i]['first_relevant_rank'] is None for d in raw.values())]
 assert all(k in reviews for k in common),'review every common miss'
 repeats={p.stem:json.loads(p.read_text(encoding='utf8')) for p in (LAB/'repeat').glob('*.json')}
 stable=all(d['repeat_top50_identical'] for d in routes.values()) and len(repeats)==4 and all(v['identical_top50']==80 for r in repeats.values() for v in r['results'].values())
 diagnostics={'scope':'Post-run diagnostic slices, same frozen relevance. Not additional independent tests. OCR-limited exclusions are evidence tags, not exclusive causal assignments.',
              'excluded_OCR_limited_ids':sorted(excluded),'slices':slices,'gains_losses':deltas,'latency_tiers':tiers,'hard_negative_exposure':negative,
              'common_misses':common,'common_review_tags':dict(collections.Counter(reviews[k]['tag'] for k in common)),
              'same_process_and_fresh_dense_rankings_stable':stable,'fresh_dense_replays':repeats,
              'reranker_resource_probes':json.loads((LAB/'reranker-resource-probes.json').read_text(encoding='utf8')),
              'rerank_plan':json.loads((LAB/'rerank_plan.json').read_text(encoding='utf8')),
              'resource_stops':{p.name:json.loads(p.read_text(encoding='utf8')) for p in LAB.glob('*resource-stop.json')},
              'co_resident_startup':{p.stem:json.loads(p.read_text(encoding='utf8')) for p in (LAB/'startup').glob('*.json')}}
 dump(LAB/'diagnostics.json',diagnostics);result['diagnostics']=diagnostics;dump(LAB/'results.json',result)
 sections=['## 补充诊断：排除编号检索的公式/文字对照',
 '以下是冻结C的事后诊断切片，不是新的独立测试。排除10道Exact，可避免模型对例题数字编号的回退混入公式能力比较。',
 table(['方案','非Exact样式','n','R@10','R@50'],[[n,style,a['n'],pct(a['Recall@10']),pct(a['Recall@50'])] for n in raw for style,a in slices[n]['non_Exact_by_style'].items()]),
 '## 神经重排相对同池现有规则的增益',
 table(['组合','ΔR@10','95%页cluster CI','新增正确题','丢失正确题'],[[n,pct(d['paired_R10_CI_vs_same_pool_current']['paired_mean_delta']),'/'.join(pct(x) for x in d['paired_R10_CI_vs_same_pool_current']['bootstrap_95CI']),len(d['Recall@10']['gained']),len(d['Recall@10']['lost'])] for n,d in deltas.items() if 'paired_R10_CI_vs_same_pool_current' in d]),
 'current的权重直接沿用E5配置，没有校准新embedding的cosine分布；这是固定原规则的兼容性实验，不代表新模型的最优融合能力。编号检索需保留正式精确通道。新embedding在完整hybrid中的效果未测试，本轮pure-dense固定池的Exact回退不能等同于保留精确旁路后的必然回退。',
 '## CPU资源缩减与体验等级',
 table(['方案','P95 ms','等级'],[[n,f"{a['p95_ms']:.1f}",a['experience']] for n,a in tiers.items()]),
 'Qwen reranker先通过通用短/384-token长文本CPU探针，没有做Test C评分。长文本每对1.743秒，80×50×2估算13,945秒，超过预设单组合90分钟预算，故停止；不能据此评价其Test C质量。BGE长文本探针估算单完整重复组合约35分钟，按资源计划只做E5-small和Qwen D1两池。D1/D2的R@50相同，脚本按预定候选顺序在最高召回并列中选择D1，未根据单题选择池。BGE-M3+BGE、Qwen D2+BGE及所有Qwen神经重排交叉组均未测。',
 '完整资源探针、缩减计划和停止记录见diagnostics.json。Excellent <1秒、Acceptable 1–3秒、Slow >3秒，按P95分类；体验等级不代表硬性质量验收。',
 '## 共同漏召回来源审计',
 table(['来源审计标签','共同漏召回题数'],list(diagnostics['common_review_tags'].items())),
 '共同漏召回18题中5题为dense-only编号匹配失败，剩余13题属于数学语义目标；其中8题有关键原公式在输入中缺失的直接证据。题数共享源页，不能当成8个独立数学主题，更不能把8/13解释为已证明的因果占比。其它问题保留混合/未确定归因。',
 f'标为OCR-limited的诊断排除题共{len(excluded)}题；完整切片和新增/丢失题ID见diagnostics.json。该切片不修改GT、不用于调规则；这类增益不作为模型能力升级证据。',
 '## 重复运行与协议核验',
 f'原进程全题重跑、神经/规则重排实际重复、独立进程dense全C重放的Top50排名一致：{stable}。独立进程每条件80/80；D1/D2共享passage索引，但query单独重放。',
 '## 正式V1.2上下文对照',
 '另行只读运行正式V1.2完整hybrid，保留学科过滤、词法/精确旁路/扩展和融合。因此此表仅展示正式体验，不能混入纯dense或固定pool的公平对照。']
 active_intro=sections[-2:];sections=sections[:-2]
 sections.extend(['## 组合加载与共同驻留RAM',table(['方案','进程内冷组件加载秒','共同驻留generic峰值RAM MiB'],[[n,f"{v['cold_components_after_import_seconds']:.2f}",f"{v['after_generic_warmup']['peak_rss_bytes']/2**20:.1f}"] for n,v in diagnostics['co_resident_startup'].items()]),'这是各方案另起独立进程、import完成后加载模型/索引/corpus/重排组件的测量，OS缓存未清空；以固定384-token通用文本预热，记录组件共同驻留峰值。不是整机冷启动或网页启动，也不是Test C延迟。固定pool质量实验使用缓存query，不需要embedding模型与neural模型共同驻留，故其单进程峰值不可当作完整交互组合峰值。两种资源测量分别保留。'])
 sections.extend(active_intro)
 active=result['active_v12_context'];a=active['summary']['overall']
 sections.append(table(['控制','Hit@1','R@5','R@10','R@50','MRR@10','P95 ms'],[['正式V1.2',*[pct(a[k]) for k in ['Hit@1','Recall@5','Recall@10','Recall@50']],f"{a['MRR@10']:.4f}",f"{active['performance']['p95_ms']:.1f}"]]))
 sections.append(table(['正式V1.2类别','n','R@10','R@50'],[[k,v['n'],pct(v['Recall@10']),pct(v['Recall@50'])] for k,v in active['summary']['categories'].items()]))
 with (LAB/'report.md').open('a',encoding='utf8') as f:f.write('\n\n'+'\n\n'.join(sections)+'\n')
 print('DIAGNOSTICS COMPLETE; stable',stable)

if __name__=='__main__':main()
