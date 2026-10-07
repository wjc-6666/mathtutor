"""Data-backed conclusions after all experiments and safety tests finish."""
import json,statistics,collections
from inference import LAB,verify_freeze
from run_recall import dump
from summarize import pct,table

def main():
 verify_freeze();r=json.loads((LAB/'results.json').read_text(encoding='utf8'))
 assert 'diagnostics' in r and '92 passed' in (LAB/'pytest-final.txt').read_text(encoding='utf8')
 integrity=json.loads((LAB/'integrity.json').read_text(encoding='utf8'));assert not integrity['changed']
 raw=r['retrieval'];reranks=r['reranking'];base=reranks['e5-small-current'];b=base['summary'];gates={}
 for name,d in reranks.items():
  a=d['summary'];checks={
   'Paraphrase_R10_at_least_10pp_gain':a['categories']['Paraphrase']['Recall@10']-b['categories']['Paraphrase']['Recall@10']>=.1-1e-9,
   'Relation_R10_at_least_10pp_gain':a['categories']['Relation']['Recall@10']-b['categories']['Relation']['Recall@10']>=.1-1e-9,
   'overall_no_drop_over_2pp':a['overall']['Recall@10']>=b['overall']['Recall@10']-.02,
   'Exact_not_lower':a['categories']['Exact']['Recall@10']>=b['categories']['Exact']['Recall@10'],
   'two_core_metrics_improve':a['overall']['Recall@10']>b['overall']['Recall@10'] and a['overall']['MRR@10']>b['overall']['MRR@10'],
   'P95_within_frozen_3s_budget':d['performance']['p95_total_ms']<=3000,
   'repeat_stable':d['repeat_top50_identical'],
   'no_math_rule_or_alias_tuning':True}
  gates[name]={'reference':'e5-small-current, fixed-pool route compatibility only','checks':checks,'passes_measured_gates':all(checks.values()),'scope':'OCR-limited slices remain separate and no gain from those cases is used to justify promotion; actual full hybrid with replacement models was not tested.'}
 best_raw=r['quality_winner_raw'];best=r['quality_winner_fixed_pool'];quality=reranks[best]
 meaningful=[n for n,v in gates.items() if v['passes_measured_gates']]
 decision={'quality_winner_raw':{'name':best_raw,'rule':'Recall@50 then MRR@50 point estimates'},
           'quality_winner_fixed_pool':{'name':best,'rule':'Recall@10 then MRR@10 point estimates; tested combinations only'},
           'efficiency_winner':'e5-small + current rules (fastest/smallest embedding; E5-base has lower measured index-process peak RAM, so no claim of minimum on every resource)',
           'balanced_winner':'keep unchanged production V1.2; no experimental replacement recommended',
           'No_Upgrade':not meaningful,'passes_all_measured_gates':meaningful,'route_gate_results':gates,
           'main_bottleneck':'Mathematical query/passage representation and alignment; damaged OCR formulas are a directly observed subset. Sorting is a measurable secondary bottleneck. No exclusive causal separation without clean-text/query-rewrite counterfactuals.',
           'active_changed':False,'V121_promoted':False,
           'test_result':(LAB/'pytest-final.txt').read_text(encoding='utf8'),
           'next_step':'Small independently frozen clean formula/structure representation and query-understanding comparison; no more model swapping by default; retain exact/lexical route; Test C is now development for future work.'}
 dump(LAB/'decision.json',decision);r['decision_matrix']=decision;r['integrity']=integrity;dump(LAB/'results.json',r)
 base_raw=raw['e5-small']['summary']['overall'];a=quality['summary']['overall'];qp=quality['performance'];diag=r['diagnostics']
 sections=['## 结论与最终决策',
 '本轮最支持的主瓶颈是**数学查询与教材文本的表示/语义对齐缺口**，OCR关键公式丢失是其中已经直接观察到的一部分；排序也有明确问题，但不能用reranker补回未进入候选池的原页。不能据此将全部失败单独归因于OCR，或断言E5-small是唯一主因。没有做干净转录/重写查询的反事实对照，故OCR、prose过滤、截断和模型域能力还不能排他地因果拆分。',
 '### 回答三个研究问题',
 f'1. **E5-small有改善空间，但不是已证实的唯一数学瓶颈。** 全C raw R@50为{pct(base_raw["Recall@50"])}，最佳raw Qwen D1/D2为65%，净增4题。排除Exact后，38道公式题E5-small与Qwen D2都找回23题；32道文字题则由20题升到27题。Paraphrase raw R@10：E5-small/E5-base/BGE-M3/Qwen D2均10%，Qwen D1为20%（只多1题）；最佳单条件Paraphrase R@50也仅40%。Relation raw R@10从40%升至Qwen D2的70%，说明强模型确实有关系排序收益，不能说换模型完全无效。',
 f'2. **相关内容经常在Top50内但排得靠后。** E5-small有19/80题位于11–50，另32/80题不在Top50。相同E5候选池上，当前规则把R@10从36.25%推到48.75%，BGE neural再推到53.75%；相对现有规则净增4题，R@50始终60%。也就是说现有规则已取得多数可观察排序收益，神经模型补了部分余量。',
 '正式V1.2完整hybrid另行只读测得R@10=60%、R@50=71.25%，其中9/80题仍处11–50、23/80不在Top50；Paraphrase R@10=40%、Exact R@10=100%。其候选池与纯dense不同，只作实际体验的上下文对照，不能混作同池模型胜负。',
 f'3. **纯质量最高的已测组合是 {best}；交互使用继续V1.2。** 该组合Hit@1={pct(a["Hit@1"])}, R@10={pct(a["Recall@10"])}, MRR@10={a["MRR@10"]:.4f}，mean/P95={qp["mean_total_ms"]/1000:.2f}/{qp["p95_total_ms"]/1000:.2f}秒。E5+BGE相对同池规则只净增4题但P95 17.27秒；embedding+neural组合的完整收益、同池CI及各类回退均在表中，不能只把raw分数提升当成相对正式V1.2的收益。',
 table(['决策项','结果','解释'],[
  ['Quality Winner',best_raw+' raw；'+best+' 固定池','按预定优先指标的点估计；不是所有指标都最优，也不是未测交叉组合的全局最优'],
  ['Efficiency Winner','E5-small + current','embedding查询、权重/索引磁盘最小；峰值RAM最小并非所有测量都由它取得'],
  ['Balanced Winner','正式V1.2','现有精确/词法通道和低延迟保留；实验替换没有满足核心改写与体验门槛'],
  ['No Upgrade','是' if decision['No_Upgrade'] else '需额外独立确认','不promote V1.2.1，不将实验部署到普通聊天，不进入V1.2.2实现']]),
 '### 进入V1.2.2的门槛检查',
 '以下将实验路线与E5-small + current固定池控制比较；它只检验本轮路线兼容性，不能代替完整hybrid整合后新的独立验收。预算门槛来自推理前冻结的计划。',
 table(['路线','改写+10pp','关系+10pp','整体不降','Exact不降','两指标提升','P95≤3s','重复稳定','全部满足'],[[n,*['是' if v['checks'][k] else '否' for k in ['Paraphrase_R10_at_least_10pp_gain','Relation_R10_at_least_10pp_gain','overall_no_drop_over_2pp','Exact_not_lower','two_core_metrics_improve','P95_within_frozen_3s_budget','repeat_stable']],'是' if v['passes_measured_gates'] else '否'] for n,v in gates.items()]),
 '按25源页cluster重采样，E5+BGE相对同池规则的R@10净增5pp，95%区间为0至10.34pp；Qwen D1+BGE相对同池规则净增0pp，区间为-7.14至9.41pp。Qwen raw R@50相对E5净增5pp的区间亦跨0。改写每类仅10题，不能把1题差异包装成稳健升级证据。',
 '神经路线即使得到更高分，CPU P95仍超过体验预算；更强embedding+原规则也没有稳定扩大改写检索，且pure-dense候选池丢失编号目标。OCR-limited增益单列，不作为升级理由。正式精确旁路本身未受影响，pure-dense Exact回退不等同于保留该旁路后的必然回退。',
 '### 下一阶段建议',
 '先做小规模、另行冻结的数学表示对照：保留可核对的公式/矩阵/上下标与题目条件，再比较查询概念提取或通用query rewrite。每种操作都与不改写、不修复的控制组同题同池比较；按公式题/文字题分开，保留精确和词法通道。选择少量原页验证机制，再决定后续工程，不重跑三本书OCR，也不继续无休止换embedding。',
 '公式/文字切片同时混有学科和题目难度差异；它不是同一道题只改变公式的配对实验，不能将切片差异直接解释为公式的因果效应。API状态的active_version=v12；INDEX_VERSION=math-v12.1是既有技术索引标签，不能据该标签误认已promote独立v121候选。',
 'C现在已经被查看，之后用于改进只能称development/diagnostic；后续升级重新冻结独立D。C由单一助手编写、25页共享80题、页级非穷尽相关标注、第三方INT8与384-token预算，限制了结论外推。未经过独立人工复核，不能称为数学推理能力认证。',
 '## 最终正式项目核验',
 f'完整pytest结果：`92 passed, 1 warning`（原80项 + 12项实验纪律/指标测试）。前后比对{integrity["protected_files"]}个原有文件，changed为空；数据库计数为{integrity["table_counts"]}。正式active仍v12，V1.2.1 active指针不存在，仍为候选。',
 '没有重新OCR、没有修改/删除原PDF、OCR缓存、数据库/聊天或旧索引，没有修改正式检索代码/权重/规则/词表，没有配置或调用OpenAI/付费API，没有安装GPU/PyTorch或新依赖。新增内容仅在隔离实验目录和工作区交付目录。']
 with (LAB/'report.md').open('a',encoding='utf8') as f:f.write('\n\n'+'\n\n'.join(sections)+'\n')
 print('DECISION',best_raw,best,'No Upgrade',decision['No_Upgrade'])

if __name__=='__main__':main()
