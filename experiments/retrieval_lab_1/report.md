# MathTutor Retrieval Lab 1 实测报告

**建议：No Upgrade，继续正式V1.2，不promote V1.2.1，不进入V1.2.2实现。**

本轮最支持的主瓶颈是数学查询与教材文本的表示/语义对齐；OCR关键公式丢失是直接观察到的部分，排序是可量化的第二个问题。没有干净转录或query rewrite反事实，不能将全部失败排他归到OCR、模型或查询中的单项。

关键证据：排除编号题后，38道公式题E5-small与Qwen D2的Top50都找回23题，32道文字题则从20题提升到27题。所有raw方案的改写R@10只有10%–20%。更强embedding改善文字和关系排序，尚未广泛改善隐式数学改写。

固定E5 Top50上，当前规则R@10=48.75%，BGE neural=53.75%（净增4题），后者P95=17.27秒。Qwen D1+BGE对其同池规则的R@10净增0。Quality Winner：raw召回Qwen D2、固定池排序E5-small+BGE；Efficiency Winner：E5-small；Balanced Winner：现有正式V1.2。

正式V1.2完整hybrid的上下文对照R@10=60%、Exact=100%、P95≈0.447秒；候选池不同，不能混入同池模型比较。冻结C为80题/25原页，由单一助手核对编写、未经独立人工复核，相关页非穷尽；结论限于这份内部测试和384-token第三方INT8 CPU条件。

原80项及12项实验测试全部通过：**92 passed, 1 warning**。1,862个原有文件哈希无变化；没有重新OCR、修改教材/缓存/数据库/聊天/旧索引或正式规则，没有调用付费API。

正式 active 保持 V1.2，V1.2.1 仍是候选。实验代码、模型、索引和结果均位于 experiments/retrieval_lab_1；普通聊天没有接入实验。

## 数据纪律与可复现性

Test C：80题，8类各10题；高代45/分析35；25个源PDF页，覆盖三本教材，源页与开发集A/B不重叠。SHA256 `359f8d4220cd6a9bd83560e91df67389f776068d13a8b7b8cbffdb8aec8c5667`。冻结时间 `1790948777.512495`（Unix秒）。Test C 原文 author_policy 写26主题，是计数笔误，实际 source_pages 为25；为保留冻结字节未修订该元数据。

A为原35题开发集，B为已查看结果的旧70题holdout，均只标 development。新C在模型推理前由本任务助手依据原PDF图像核对后编写、标注和冻结，未经独立人工复核。80道问题共享25页，有相关性；单一助手内部标注，相关页非穷尽，尤其类似题/方法题可能有其它未标注正确页。指标是找回指定正确源页的指标，不能等同于所有答案的数学正确率。Exact 另检查例题编号；其它题按 book/PDF page 判相关，同页其它习题也可能被计入，因此页级指标可能高估题目级相关性。

所有模型使用相同3,800条V1.2 records、相同 semantic_text passage、相同raw query和TopK；第一阶段不用词典/组合规则/扩展/精确旁路，不按学科过滤，搜索全部三本教材。384 tokens 是本机实验预算，不是BGE/Qwen原生上下文上限；各模型tokenizer不同，实际可见字符数量不同。索引统计 truncated_passages 按达到384-token上限计数，包含刚好到上限的记录，是近似截断统计。E5-small直接复用原E5CPU类，完整独立重建向量与旧向量逐项相等。

Qwen D1无instruction；D2和Qwen reranker全题使用唯一固定instruction：`Retrieve textbook passages that solve, define, prove, or use the same mathematical concept, theorem, relation, or method as the query.`。冻结后未调整任何数学规则、权重、alias或ground truth。

## 第一阶段：纯 dense candidate recall

| Retriever | R@5 | R@10 | R@20 | R@50 | MRR@50 | mean/median/P95 ms | 峰值RAM MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | 37.50% | 46.25% | 52.50% | 61.25% | 0.3243 | 23.3/23.4/31.2 | 1035.5 |
| e5-base | 33.75% | 41.25% | 48.75% | 55.00% | 0.2302 | 9.0/9.1/10.9 | 799.2 |
| e5-small | 33.75% | 36.25% | 45.00% | 60.00% | 0.2633 | 4.3/4.4/5.4 | 1058.9 |
| qwen-D1 | 37.50% | 45.00% | 51.25% | 65.00% | 0.2888 | 50.9/49.2/76.7 | 1105.9 |
| qwen-D2 | 46.25% | 50.00% | 56.25% | 65.00% | 0.3333 | 122.0/120.7/150.6 | 1105.9 |

这里MRR截断50；第二阶段另列MRR@10。查询延迟包含tokenize、ONNX、向量点积和全库排序，不含冷加载；本机不同进程串行跑CPU，固定4个推理线程。CPU百分比是进程CPU秒/墙钟秒，可超过100%（占多核），不是全机平均CPU利用率。原V1.2的CPU arena开启，baseline保持不变；其它模型关闭arena以控制内存，资源差异需结合这一设置解读。

## 资源与索引成本

| 模型 | 维度 | 模型disk MiB | 索引 MiB | 索引秒 | 冷加载秒 | 达到token上限的passages | CPU% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | 1024 | 559.6 | 14.84 | 1210.8 | 1.78 | 830 | 394.7 |
| e5-base | 768 | 282.0 | 11.13 | 401.0 | 0.99 | 833 | 394.9 |
| e5-small | 384 | 129.1 | 5.57 | 133.4 | 1.17 | 833 | 396.4 |
| qwen-D1 | 1024 | 596.0 | 14.84 | 3156.9 | 1.75 | 891 | 394.9 |
| qwen-D2 | 1024 | 596.0 | 14.84 | 3156.9 | 1.75 | 891 | 394.9 |

D1/D2共享同一passage index，只改变query instruction，不将同一建库成本计作两次。模型disk含权重、tokenizer/config/card；冷加载包括文件校验、tokenizer、ORT session，操作系统文件缓存未清空，非整机冷启动。RAM为测量进程PeakWorkingSetSize，含解释器、模型、索引和runtime工作内存。未安装GPU/PyTorch栈，没有新依赖安装。

## 首次相关排名与四类失败

| Retriever | Success 1–5 | Near 6–10 | Opportunity 11–50 | Recall Failure >50 |
| --- | --- | --- | --- | --- |
| bge-m3 | 30 | 7 | 12 | 31 |
| e5-base | 27 | 6 | 11 | 36 |
| e5-small | 27 | 2 | 19 | 32 |
| qwen-D1 | 30 | 6 | 16 | 28 |
| qwen-D2 | 37 | 3 | 12 | 28 |

逐题排名和分类见 first_relevant_ranks.json；百分比为计数/80。Recall@50之外的目标，任意fixed-pool reranker都不能救回。

## 第二阶段：固定Top50重排

门槛预先固定为Test C Recall@50≥60%。未达门槛的E5-base等条件不进入神经重排。各retriever的Top50预先落盘，各reranker在同一个retriever pool上比较，不能增加候选。current适配器保留V1.2原有评分公式/词典/规则/权重，仅将候选入口固定为纯dense Top50、使用缓存原query向量；它不是普通聊天的完整混合检索结果。不同retriever的pool不同，横向neural差异需按各自pool解释。

| Retriever | Reranker | Hit@1 | R@5 | R@10 | MRR@10 | nDCG@10 | total mean/median/P95 ms | 峰值RAM MiB |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | current | 27.50% | 42.50% | 52.50% | 0.3436 | 0.3861 | 425.9/415.2/503.8 | 138.4 |
| e5-small | bge-reranker | 35.00% | 46.25% | 53.75% | 0.4014 | 0.4335 | 15326.5/15713.9/17270.3 | 1101.7 |
| e5-small | current | 32.50% | 45.00% | 48.75% | 0.3751 | 0.4023 | 391.1/373.6/459.4 | 761.7 |
| qwen-D1 | bge-reranker | 31.25% | 46.25% | 53.75% | 0.3799 | 0.4174 | 14169.6/15377.3/16718.3 | 1100.6 |
| qwen-D1 | current | 31.25% | 42.50% | 53.75% | 0.3674 | 0.4069 | 444.1/426.0/526.6 | 138.7 |
| qwen-D2 | current | 31.25% | 43.75% | 51.25% | 0.3687 | 0.4025 | 506.9/494.6/582.6 | 138.9 |

Total latency为该次dense查询时间+重排时间；神经模型冷加载不计入交互延迟，另在结果performance给出。BGE使用query-document cross encoder logit；Qwen使用完整固定chat前后缀及yes-no末token logit差，等价于二分类softmax排序。384token预算内保留Qwen答案后缀，只裁剪document部分。nDCG为grade3正目标、grade0已标注hard negatives，重复chunk不会重复得分，cutoff仍按raw records。

## 分学科与问题类型（Test C）

### 学科

| 方案 | 分组 | n | Hit@1 | R@5 | R@10 | R@20 | R@50 | MRR@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | algebra | 45 | 35.56% | 48.89% | 57.78% | 68.89% | 77.78% | 0.4149 |
| bge-m3 | analysis | 35 | 14.29% | 22.86% | 31.43% | 31.43% | 40.00% | 0.1917 |
| e5-base | algebra | 45 | 13.33% | 42.22% | 51.11% | 62.22% | 68.89% | 0.2554 |
| e5-base | analysis | 35 | 14.29% | 22.86% | 28.57% | 31.43% | 37.14% | 0.1821 |
| e5-small | algebra | 45 | 22.22% | 42.22% | 46.67% | 60.00% | 75.56% | 0.3037 |
| e5-small | analysis | 35 | 14.29% | 22.86% | 22.86% | 25.71% | 40.00% | 0.1857 |
| qwen-D1 | algebra | 45 | 26.67% | 51.11% | 60.00% | 66.67% | 75.56% | 0.3638 |
| qwen-D1 | analysis | 35 | 14.29% | 20.00% | 25.71% | 31.43% | 51.43% | 0.1719 |
| qwen-D2 | algebra | 45 | 26.67% | 60.00% | 62.22% | 68.89% | 75.56% | 0.4002 |
| qwen-D2 | analysis | 35 | 17.14% | 28.57% | 34.29% | 40.00% | 51.43% | 0.2306 |
| bge-m3-current | algebra | 45 | 33.33% | 53.33% | 64.44% | 68.89% | 77.78% | 0.4243 |
| bge-m3-current | analysis | 35 | 20.00% | 28.57% | 37.14% | 37.14% | 40.00% | 0.2398 |
| e5-small-bge-reranker | algebra | 45 | 40.00% | 57.78% | 66.67% | 71.11% | 75.56% | 0.4741 |
| e5-small-bge-reranker | analysis | 35 | 28.57% | 31.43% | 37.14% | 40.00% | 40.00% | 0.3079 |
| e5-small-current | algebra | 45 | 35.56% | 51.11% | 55.56% | 66.67% | 75.56% | 0.4185 |
| e5-small-current | analysis | 35 | 28.57% | 37.14% | 40.00% | 40.00% | 40.00% | 0.3193 |
| qwen-D1-bge-reranker | algebra | 45 | 37.78% | 60.00% | 71.11% | 75.56% | 75.56% | 0.4769 |
| qwen-D1-bge-reranker | analysis | 35 | 22.86% | 28.57% | 31.43% | 40.00% | 51.43% | 0.2552 |
| qwen-D1-current | algebra | 45 | 37.78% | 51.11% | 64.44% | 71.11% | 75.56% | 0.4432 |
| qwen-D1-current | analysis | 35 | 22.86% | 31.43% | 40.00% | 40.00% | 51.43% | 0.2700 |
| qwen-D2-current | algebra | 45 | 35.56% | 48.89% | 60.00% | 66.67% | 75.56% | 0.4256 |
| qwen-D2-current | analysis | 35 | 25.71% | 37.14% | 40.00% | 40.00% | 51.43% | 0.2956 |

### 类别

| 方案 | 分组 | n | Hit@1 | R@5 | R@10 | R@20 | R@50 | MRR@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | Concept | 10 | 70.00% | 90.00% | 100.00% | 100.00% | 100.00% | 0.7917 |
| bge-m3 | Exact | 10 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.0000 |
| bge-m3 | HardNegative | 10 | 10.00% | 40.00% | 50.00% | 70.00% | 70.00% | 0.2250 |
| bge-m3 | MethodSimilarity | 10 | 20.00% | 20.00% | 30.00% | 40.00% | 70.00% | 0.2100 |
| bge-m3 | Paraphrase | 10 | 10.00% | 10.00% | 10.00% | 10.00% | 30.00% | 0.1000 |
| bge-m3 | Relation | 10 | 20.00% | 40.00% | 60.00% | 80.00% | 80.00% | 0.2878 |
| bge-m3 | SimilarProblem | 10 | 40.00% | 50.00% | 50.00% | 50.00% | 70.00% | 0.4500 |
| bge-m3 | Theorem | 10 | 40.00% | 50.00% | 70.00% | 70.00% | 70.00% | 0.4736 |
| e5-base | Concept | 10 | 30.00% | 50.00% | 60.00% | 60.00% | 70.00% | 0.3917 |
| e5-base | Exact | 10 | 10.00% | 10.00% | 20.00% | 20.00% | 20.00% | 0.1125 |
| e5-base | HardNegative | 10 | 0.00% | 30.00% | 40.00% | 50.00% | 60.00% | 0.1250 |
| e5-base | MethodSimilarity | 10 | 10.00% | 20.00% | 40.00% | 50.00% | 50.00% | 0.1583 |
| e5-base | Paraphrase | 10 | 0.00% | 10.00% | 10.00% | 10.00% | 10.00% | 0.0500 |
| e5-base | Relation | 10 | 10.00% | 50.00% | 50.00% | 70.00% | 80.00% | 0.2450 |
| e5-base | SimilarProblem | 10 | 30.00% | 50.00% | 50.00% | 60.00% | 70.00% | 0.3833 |
| e5-base | Theorem | 10 | 20.00% | 50.00% | 60.00% | 70.00% | 80.00% | 0.3208 |
| e5-small | Concept | 10 | 40.00% | 70.00% | 70.00% | 70.00% | 90.00% | 0.5333 |
| e5-small | Exact | 10 | 20.00% | 20.00% | 20.00% | 30.00% | 50.00% | 0.2000 |
| e5-small | HardNegative | 10 | 10.00% | 20.00% | 30.00% | 40.00% | 50.00% | 0.1343 |
| e5-small | MethodSimilarity | 10 | 20.00% | 20.00% | 20.00% | 30.00% | 50.00% | 0.2000 |
| e5-small | Paraphrase | 10 | 0.00% | 10.00% | 10.00% | 20.00% | 30.00% | 0.0500 |
| e5-small | Relation | 10 | 20.00% | 40.00% | 40.00% | 60.00% | 70.00% | 0.2833 |
| e5-small | SimilarProblem | 10 | 20.00% | 30.00% | 40.00% | 40.00% | 70.00% | 0.2458 |
| e5-small | Theorem | 10 | 20.00% | 60.00% | 60.00% | 70.00% | 70.00% | 0.3700 |
| qwen-D1 | Concept | 10 | 60.00% | 80.00% | 80.00% | 80.00% | 80.00% | 0.6750 |
| qwen-D1 | Exact | 10 | 0.00% | 0.00% | 0.00% | 0.00% | 20.00% | 0.0000 |
| qwen-D1 | HardNegative | 10 | 20.00% | 50.00% | 60.00% | 60.00% | 80.00% | 0.3226 |
| qwen-D1 | MethodSimilarity | 10 | 0.00% | 10.00% | 40.00% | 50.00% | 60.00% | 0.0667 |
| qwen-D1 | Paraphrase | 10 | 10.00% | 10.00% | 20.00% | 20.00% | 40.00% | 0.1111 |
| qwen-D1 | Relation | 10 | 40.00% | 60.00% | 60.00% | 70.00% | 70.00% | 0.4700 |
| qwen-D1 | SimilarProblem | 10 | 20.00% | 40.00% | 50.00% | 50.00% | 80.00% | 0.2933 |
| qwen-D1 | Theorem | 10 | 20.00% | 50.00% | 50.00% | 80.00% | 90.00% | 0.3000 |
| qwen-D2 | Concept | 10 | 60.00% | 80.00% | 80.00% | 90.00% | 90.00% | 0.6833 |
| qwen-D2 | Exact | 10 | 0.00% | 20.00% | 20.00% | 20.00% | 20.00% | 0.0833 |
| qwen-D2 | HardNegative | 10 | 40.00% | 60.00% | 60.00% | 60.00% | 70.00% | 0.5000 |
| qwen-D2 | MethodSimilarity | 10 | 10.00% | 20.00% | 30.00% | 50.00% | 60.00% | 0.1393 |
| qwen-D2 | Paraphrase | 10 | 10.00% | 10.00% | 10.00% | 30.00% | 40.00% | 0.1000 |
| qwen-D2 | Relation | 10 | 40.00% | 70.00% | 70.00% | 70.00% | 80.00% | 0.5033 |
| qwen-D2 | SimilarProblem | 10 | 10.00% | 50.00% | 60.00% | 60.00% | 70.00% | 0.2944 |
| qwen-D2 | Theorem | 10 | 10.00% | 60.00% | 70.00% | 70.00% | 90.00% | 0.3042 |
| bge-m3-current | Concept | 10 | 80.00% | 100.00% | 100.00% | 100.00% | 100.00% | 0.8750 |
| bge-m3-current | Exact | 10 | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.0000 |
| bge-m3-current | HardNegative | 10 | 30.00% | 50.00% | 70.00% | 70.00% | 70.00% | 0.4060 |
| bge-m3-current | MethodSimilarity | 10 | 20.00% | 40.00% | 40.00% | 50.00% | 70.00% | 0.2750 |
| bge-m3-current | Paraphrase | 10 | 10.00% | 10.00% | 20.00% | 20.00% | 30.00% | 0.1111 |
| bge-m3-current | Relation | 10 | 20.00% | 50.00% | 60.00% | 60.00% | 80.00% | 0.2992 |
| bge-m3-current | SimilarProblem | 10 | 20.00% | 40.00% | 60.00% | 70.00% | 70.00% | 0.3033 |
| bge-m3-current | Theorem | 10 | 40.00% | 50.00% | 70.00% | 70.00% | 70.00% | 0.4792 |
| e5-small-bge-reranker | Concept | 10 | 70.00% | 80.00% | 90.00% | 90.00% | 90.00% | 0.7500 |
| e5-small-bge-reranker | Exact | 10 | 50.00% | 50.00% | 50.00% | 50.00% | 50.00% | 0.5000 |
| e5-small-bge-reranker | HardNegative | 10 | 20.00% | 40.00% | 50.00% | 50.00% | 50.00% | 0.2867 |
| e5-small-bge-reranker | MethodSimilarity | 10 | 10.00% | 10.00% | 20.00% | 40.00% | 50.00% | 0.1125 |
| e5-small-bge-reranker | Paraphrase | 10 | 10.00% | 20.00% | 30.00% | 30.00% | 30.00% | 0.1393 |
| e5-small-bge-reranker | Relation | 10 | 30.00% | 60.00% | 70.00% | 70.00% | 70.00% | 0.4417 |
| e5-small-bge-reranker | SimilarProblem | 10 | 40.00% | 50.00% | 50.00% | 60.00% | 70.00% | 0.4200 |
| e5-small-bge-reranker | Theorem | 10 | 50.00% | 60.00% | 70.00% | 70.00% | 70.00% | 0.5611 |
| e5-small-current | Concept | 10 | 70.00% | 90.00% | 90.00% | 90.00% | 90.00% | 0.7667 |
| e5-small-current | Exact | 10 | 50.00% | 50.00% | 50.00% | 50.00% | 50.00% | 0.5000 |
| e5-small-current | HardNegative | 10 | 30.00% | 40.00% | 50.00% | 50.00% | 50.00% | 0.3667 |
| e5-small-current | MethodSimilarity | 10 | 20.00% | 20.00% | 20.00% | 30.00% | 50.00% | 0.2000 |
| e5-small-current | Paraphrase | 10 | 10.00% | 20.00% | 20.00% | 30.00% | 30.00% | 0.1250 |
| e5-small-current | Relation | 10 | 20.00% | 50.00% | 50.00% | 70.00% | 70.00% | 0.3083 |
| e5-small-current | SimilarProblem | 10 | 20.00% | 30.00% | 40.00% | 50.00% | 70.00% | 0.2476 |
| e5-small-current | Theorem | 10 | 40.00% | 60.00% | 70.00% | 70.00% | 70.00% | 0.4867 |
| qwen-D1-bge-reranker | Concept | 10 | 60.00% | 80.00% | 80.00% | 80.00% | 80.00% | 0.6833 |
| qwen-D1-bge-reranker | Exact | 10 | 20.00% | 20.00% | 20.00% | 20.00% | 20.00% | 0.2000 |
| qwen-D1-bge-reranker | HardNegative | 10 | 20.00% | 40.00% | 60.00% | 70.00% | 80.00% | 0.2952 |
| qwen-D1-bge-reranker | MethodSimilarity | 10 | 20.00% | 30.00% | 50.00% | 60.00% | 60.00% | 0.2600 |
| qwen-D1-bge-reranker | Paraphrase | 10 | 10.00% | 20.00% | 20.00% | 30.00% | 40.00% | 0.1333 |
| qwen-D1-bge-reranker | Relation | 10 | 30.00% | 70.00% | 70.00% | 70.00% | 70.00% | 0.4700 |
| qwen-D1-bge-reranker | SimilarProblem | 10 | 40.00% | 50.00% | 60.00% | 70.00% | 80.00% | 0.4375 |
| qwen-D1-bge-reranker | Theorem | 10 | 50.00% | 60.00% | 70.00% | 80.00% | 90.00% | 0.5600 |
| qwen-D1-current | Concept | 10 | 70.00% | 80.00% | 80.00% | 80.00% | 80.00% | 0.7500 |
| qwen-D1-current | Exact | 10 | 20.00% | 20.00% | 20.00% | 20.00% | 20.00% | 0.2000 |
| qwen-D1-current | HardNegative | 10 | 30.00% | 50.00% | 70.00% | 70.00% | 80.00% | 0.3967 |
| qwen-D1-current | MethodSimilarity | 10 | 30.00% | 40.00% | 40.00% | 50.00% | 60.00% | 0.3333 |
| qwen-D1-current | Paraphrase | 10 | 10.00% | 10.00% | 20.00% | 30.00% | 40.00% | 0.1111 |
| qwen-D1-current | Relation | 10 | 20.00% | 40.00% | 60.00% | 60.00% | 70.00% | 0.3000 |
| qwen-D1-current | SimilarProblem | 10 | 30.00% | 50.00% | 60.00% | 70.00% | 80.00% | 0.3550 |
| qwen-D1-current | Theorem | 10 | 40.00% | 50.00% | 80.00% | 80.00% | 90.00% | 0.4935 |
| qwen-D2-current | Concept | 10 | 80.00% | 90.00% | 90.00% | 90.00% | 90.00% | 0.8500 |
| qwen-D2-current | Exact | 10 | 20.00% | 20.00% | 20.00% | 20.00% | 20.00% | 0.2000 |
| qwen-D2-current | HardNegative | 10 | 30.00% | 50.00% | 70.00% | 70.00% | 70.00% | 0.4028 |
| qwen-D2-current | MethodSimilarity | 10 | 30.00% | 40.00% | 40.00% | 40.00% | 60.00% | 0.3333 |
| qwen-D2-current | Paraphrase | 10 | 10.00% | 10.00% | 10.00% | 30.00% | 40.00% | 0.1000 |
| qwen-D2-current | Relation | 10 | 20.00% | 40.00% | 60.00% | 60.00% | 80.00% | 0.2992 |
| qwen-D2-current | SimilarProblem | 10 | 20.00% | 40.00% | 50.00% | 60.00% | 70.00% | 0.2800 |
| qwen-D2-current | Theorem | 10 | 40.00% | 60.00% | 70.00% | 70.00% | 90.00% | 0.4843 |

### 公式/文字

| 方案 | 分组 | n | Hit@1 | R@5 | R@10 | R@20 | R@50 | MRR@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3 | formula-heavy | 48 | 20.83% | 31.25% | 37.50% | 43.75% | 50.00% | 0.2602 |
| bge-m3 | text-heavy | 32 | 34.38% | 46.88% | 59.38% | 65.62% | 78.12% | 0.4028 |
| e5-base | formula-heavy | 48 | 10.42% | 29.17% | 37.50% | 43.75% | 50.00% | 0.1908 |
| e5-base | text-heavy | 32 | 18.75% | 40.62% | 46.88% | 56.25% | 62.50% | 0.2721 |
| e5-small | formula-heavy | 48 | 14.58% | 27.08% | 31.25% | 39.58% | 58.33% | 0.2070 |
| e5-small | text-heavy | 32 | 25.00% | 43.75% | 43.75% | 53.12% | 62.50% | 0.3198 |
| qwen-D1 | formula-heavy | 48 | 10.42% | 31.25% | 35.42% | 39.58% | 54.17% | 0.1903 |
| qwen-D1 | text-heavy | 32 | 37.50% | 46.88% | 59.38% | 68.75% | 81.25% | 0.4142 |
| qwen-D2 | formula-heavy | 48 | 12.50% | 39.58% | 43.75% | 45.83% | 52.08% | 0.2369 |
| qwen-D2 | text-heavy | 32 | 37.50% | 56.25% | 59.38% | 71.88% | 84.38% | 0.4596 |
| bge-m3-current | formula-heavy | 48 | 20.83% | 31.25% | 39.58% | 43.75% | 50.00% | 0.2637 |
| bge-m3-current | text-heavy | 32 | 37.50% | 59.38% | 71.88% | 71.88% | 78.12% | 0.4634 |
| e5-small-bge-reranker | formula-heavy | 48 | 31.25% | 45.83% | 50.00% | 54.17% | 58.33% | 0.3702 |
| e5-small-bge-reranker | text-heavy | 32 | 40.62% | 46.88% | 59.38% | 62.50% | 62.50% | 0.4482 |
| e5-small-current | formula-heavy | 48 | 31.25% | 41.67% | 45.83% | 50.00% | 58.33% | 0.3526 |
| e5-small-current | text-heavy | 32 | 34.38% | 50.00% | 53.12% | 62.50% | 62.50% | 0.4089 |
| qwen-D1-bge-reranker | formula-heavy | 48 | 25.00% | 39.58% | 45.83% | 50.00% | 54.17% | 0.3155 |
| qwen-D1-bge-reranker | text-heavy | 32 | 40.62% | 56.25% | 65.62% | 75.00% | 81.25% | 0.4766 |
| qwen-D1-current | formula-heavy | 48 | 29.17% | 35.42% | 41.67% | 43.75% | 54.17% | 0.3205 |
| qwen-D1-current | text-heavy | 32 | 34.38% | 53.12% | 71.88% | 78.12% | 81.25% | 0.4379 |
| qwen-D2-current | formula-heavy | 48 | 27.08% | 33.33% | 39.58% | 41.67% | 52.08% | 0.3044 |
| qwen-D2-current | text-heavy | 32 | 37.50% | 59.38% | 68.75% | 75.00% | 84.38% | 0.4652 |

## 开发集A/B（不能称独立测试）

| 数据集 | Retriever | R@5 | R@10 | R@20 | R@50 | MRR@50 |
| --- | --- | --- | --- | --- | --- | --- |
| development_a | bge-m3 | 40.00% | 47.14% | 65.71% | 75.71% | 0.3221 |
| development_a | e5-base | 35.71% | 41.43% | 48.57% | 61.43% | 0.2500 |
| development_a | e5-small | 47.14% | 50.00% | 60.00% | 68.57% | 0.3785 |
| development_a | qwen-D1 | 51.43% | 57.14% | 68.57% | 81.43% | 0.3774 |
| development_a | qwen-D2 | 54.29% | 57.14% | 62.86% | 84.29% | 0.4414 |
| development_b | bge-m3 | 23.57% | 30.71% | 34.29% | 44.29% | 0.2118 |
| development_b | e5-base | 27.14% | 28.57% | 33.57% | 42.86% | 0.2074 |
| development_b | e5-small | 27.86% | 34.29% | 43.57% | 60.00% | 0.2159 |
| development_b | qwen-D1 | 32.14% | 45.00% | 51.43% | 65.00% | 0.2712 |
| development_b | qwen-D2 | 45.71% | 52.14% | 60.71% | 66.43% | 0.3163 |

## 不确定性与重复测量

采用固定seed731的4000次按正目标book/PDF页cluster重采样，避免把相关的80问题当80独立主题。95% CI仅描述这份内部测试样本，未覆盖单一助手标注偏差。详细区间见results.json。

| 方案 vs raw E5-small | ΔR@10 | 95% cluster CI |
| --- | --- | --- |
| bge-m3 | 10.00% | 1.33%/19.45% |
| e5-base | 5.00% | -1.89%/12.86% |
| qwen-D1 | 8.75% | 0.00%/18.18% |
| qwen-D2 | 13.75% | 4.88%/24.05% |

每个Test C query原进程重复一次，另独立进程重放纯dense所有C题；排名一致性见repeat/*.json。神经重排每题重复推理一次，记录repeat_top50_identical；没有重新建库做统计鲁棒性实验。

## OCR与passage表示审计

所有dense条件都没召回的C题：C-Exact-01, C-Exact-03, C-Exact-04, C-Exact-05, C-Exact-06, C-Theorem-10, C-Paraphrase-03, C-Paraphrase-06, C-Paraphrase-08, C-Paraphrase-09, C-Relation-08, C-Relation-09, C-SimilarProblem-03, C-SimilarProblem-10, C-MethodSimilarity-08, C-MethodSimilarity-10, C-HardNegative-09, C-HardNegative-10。

单独比对原PDF、raw OCR、实际encoded passage。明确标为OCR-limited的题见ocr_review.json；formula-heavy是冻结前标注，不能自动等同OCR-limited。没有对原教材做OCR或修复公式。

例如习题解答PDF64的二阶中心差商原公式清晰，但OCR与prose过滤后的passage丢失导数阶数和分母；PDF81的归一化积分核和分部积分关键等式也严重损坏。高代PDF366的不变因子与特征/极小多项式公式部分被截掉。这里只判断存在representation限制，不声称它唯一导致模型漏召回。

未确定归因的共同失败保留undetermined，不能仅因所有模型失败就断言OCR-limited，或断言所有embedding模型都无能力。未做干净转录/更长passage对照，无法因果分离OCR损坏、prose过滤、token截断和模型本身。

## 模型来源与许可

| 名称 | 转换来源 | revision | 上游许可 |
| --- | --- | --- | --- |
| e5-base | [Xenova/multilingual-e5-base](https://huggingface.co/Xenova/multilingual-e5-base) | 1ec9243030a27d1a115d5c340572074c125b58b2 | mit |
| bge-m3 | [Xenova/bge-m3](https://huggingface.co/Xenova/bge-m3) | 4de13258303883538bd53b696b452bf8099f0858 | mit |
| qwen-embedding | [onnx-community/Qwen3-Embedding-0.6B-ONNX](https://huggingface.co/onnx-community/Qwen3-Embedding-0.6B-ONNX) | c25a394dd583836952667c12f008335071b3f43d | apache-2.0 |
| bge-reranker | [onnx-community/bge-reranker-v2-m3-ONNX](https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX) | 6f5ff65298512715a1e669753bc754d2bc8f367b | apache-2.0 |
| qwen-reranker | [onnx-community/Qwen3-Reranker-0.6B-ONNX](https://huggingface.co/onnx-community/Qwen3-Reranker-0.6B-ONNX) | 9995c50e2310679108a55f5ccd16ba8be9f17c20 | apache-2.0 |

以上是第三方ONNX INT8转换，不能冒充官方原始权重。全部实际下载文件大小、SHA256及Hub LFS校验值见model_manifest.json。原模型说明：[E5-base](https://huggingface.co/intfloat/multilingual-e5-base)、[BGE-M3](https://huggingface.co/BAAI/bge-m3)、[Qwen Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B)、[BGE Reranker](https://huggingface.co/BAAI/bge-reranker-v2-m3)、[Qwen Reranker](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B)。部分转换repo缺少明确license元数据；清单license指上游许可，license_basis明确区分。

BGE-M3只测dense；未测sparse和multi-vector，现有dense ONNX文件没有提供完整sparse/ColBERT heads。本轮只隔离dense召回与重排；Jina v3未列入第一批，也未下载。没有付费API和远程inference，网络仅用于读取公开模型资料、下载权重。

## 安全与复现

运行顺序：make_test_c.py（一次性，存在冻结C即拒绝覆盖）→download_models.py（公开模型下载）→run_stage1.py→run_stage2.py→measure_active.py→audit_sources.py→summarize.py。本次下载早于冻结开始、模型推理晚于冻结；下载不涉及query或passage上传。重放建议直接使用run_recall.py模型名及verify_repeat.py，不再运行数据集生成脚本。

正式代码/数据前后SHA256见integrity.json；pytest原80项与12项实验纪律测试见pytest-final.txt。实验仅新增独立目录；V1.2权重、V1.2.1词表/组合规则、PDF/OCR、数据库、聊天与全部旧索引均应保持不变。


## 补充诊断：排除编号检索的公式/文字对照

以下是冻结C的事后诊断切片，不是新的独立测试。排除10道Exact，可避免模型对例题数字编号的回退混入公式能力比较。

| 方案 | 非Exact样式 | n | R@10 | R@50 |
| --- | --- | --- | --- | --- |
| bge-m3 | formula-heavy | 38 | 47.37% | 63.16% |
| bge-m3 | text-heavy | 32 | 59.38% | 78.12% |
| e5-base | formula-heavy | 38 | 42.11% | 57.89% |
| e5-base | text-heavy | 32 | 46.88% | 62.50% |
| e5-small | formula-heavy | 38 | 34.21% | 60.53% |
| e5-small | text-heavy | 32 | 43.75% | 62.50% |
| qwen-D1 | formula-heavy | 38 | 44.74% | 63.16% |
| qwen-D1 | text-heavy | 32 | 59.38% | 81.25% |
| qwen-D2 | formula-heavy | 38 | 50.00% | 60.53% |
| qwen-D2 | text-heavy | 32 | 59.38% | 84.38% |

## 神经重排相对同池现有规则的增益

| 组合 | ΔR@10 | 95%页cluster CI | 新增正确题 | 丢失正确题 |
| --- | --- | --- | --- | --- |
| e5-small-bge-reranker | 5.00% | 0.00%/10.34% | 5 | 1 |
| qwen-D1-bge-reranker | 0.00% | -7.14%/9.41% | 3 | 3 |

current的权重直接沿用E5配置，没有校准新embedding的cosine分布；这是固定原规则的兼容性实验，不代表新模型的最优融合能力。编号检索需保留正式精确通道。新embedding在完整hybrid中的效果未测试，本轮pure-dense固定池的Exact回退不能等同于保留精确旁路后的必然回退。

## CPU资源缩减与体验等级

| 方案 | P95 ms | 等级 |
| --- | --- | --- |
| bge-m3 | 31.2 | Excellent |
| e5-base | 10.9 | Excellent |
| e5-small | 5.4 | Excellent |
| qwen-D1 | 76.7 | Excellent |
| qwen-D2 | 150.6 | Excellent |
| bge-m3-current | 503.8 | Excellent |
| e5-small-bge-reranker | 17270.3 | Slow |
| e5-small-current | 459.4 | Excellent |
| qwen-D1-bge-reranker | 16718.3 | Slow |
| qwen-D1-current | 526.6 | Excellent |
| qwen-D2-current | 582.6 | Excellent |

Qwen reranker先通过通用短/384-token长文本CPU探针，没有做Test C评分。长文本每对1.743秒，80×50×2估算13,945秒，超过预设单组合90分钟预算，故停止；不能据此评价其Test C质量。BGE长文本探针估算单完整重复组合约35分钟，按资源计划只做E5-small和Qwen D1两池。D1/D2的R@50相同，脚本按预定候选顺序在最高召回并列中选择D1，未根据单题选择池。BGE-M3+BGE、Qwen D2+BGE及所有Qwen神经重排交叉组均未测。

完整资源探针、缩减计划和停止记录见diagnostics.json。Excellent <1秒、Acceptable 1–3秒、Slow >3秒，按P95分类；体验等级不代表硬性质量验收。

## 共同漏召回来源审计

| 来源审计标签 | 共同漏召回题数 |
| --- | --- |
| dense-only identifier mismatch | 5 |
| OCR-limited | 8 |
| query/passage-alignment evidence | 2 |
| partially-readable | 1 |
| mixed source/query failure | 1 |
| readable-source retrieval failure | 1 |

共同漏召回18题中5题为dense-only编号匹配失败，剩余13题属于数学语义目标；其中8题有关键原公式在输入中缺失的直接证据。题数共享源页，不能当成8个独立数学主题，更不能把8/13解释为已证明的因果占比。其它问题保留混合/未确定归因。

标为OCR-limited的诊断排除题共9题；完整切片和新增/丢失题ID见diagnostics.json。该切片不修改GT、不用于调规则；这类增益不作为模型能力升级证据。

## 重复运行与协议核验

原进程全题重跑、神经/规则重排实际重复、独立进程dense全C重放的Top50排名一致：True。独立进程每条件80/80；D1/D2共享passage索引，但query单独重放。

## 组合加载与共同驻留RAM

| 方案 | 进程内冷组件加载秒 | 共同驻留generic峰值RAM MiB |
| --- | --- | --- |
| bge-m3-current | 2.37 | 990.5 |
| bge-m3 | 1.79 | 950.6 |
| e5-base | 1.29 | 658.2 |
| e5-small-bge-reranker | 3.33 | 1742.2 |
| e5-small-current | 1.80 | 795.1 |
| e5-small | 1.24 | 756.5 |
| qwen-D1-bge-reranker | 3.50 | 1739.0 |
| qwen-D1-current | 2.12 | 950.5 |
| qwen-D1 | 1.59 | 911.9 |
| qwen-D2-current | 2.13 | 950.2 |
| qwen-D2 | 1.63 | 912.6 |

这是各方案另起独立进程、import完成后加载模型/索引/corpus/重排组件的测量，OS缓存未清空；以固定384-token通用文本预热，记录组件共同驻留峰值。不是整机冷启动或网页启动，也不是Test C延迟。固定pool质量实验使用缓存query，不需要embedding模型与neural模型共同驻留，故其单进程峰值不可当作完整交互组合峰值。两种资源测量分别保留。

## 正式V1.2上下文对照

另行只读运行正式V1.2完整hybrid，保留学科过滤、词法/精确旁路/扩展和融合。因此此表仅展示正式体验，不能混入纯dense或固定pool的公平对照。

| 控制 | Hit@1 | R@5 | R@10 | R@50 | MRR@10 | P95 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 正式V1.2 | 38.75% | 53.75% | 60.00% | 71.25% | 0.4460 | 446.9 |

| 正式V1.2类别 | n | R@10 | R@50 |
| --- | --- | --- | --- |
| Concept | 10 | 100.00% | 100.00% |
| Exact | 10 | 100.00% | 100.00% |
| HardNegative | 10 | 50.00% | 70.00% |
| MethodSimilarity | 10 | 40.00% | 60.00% |
| Paraphrase | 10 | 40.00% | 40.00% |
| Relation | 10 | 50.00% | 70.00% |
| SimilarProblem | 10 | 40.00% | 60.00% |
| Theorem | 10 | 60.00% | 70.00% |


## 结论与最终决策

本轮最支持的主瓶颈是**数学查询与教材文本的表示/语义对齐缺口**，OCR关键公式丢失是其中已经直接观察到的一部分；排序也有明确问题，但不能用reranker补回未进入候选池的原页。不能据此将全部失败单独归因于OCR，或断言E5-small是唯一主因。没有做干净转录/重写查询的反事实对照，故OCR、prose过滤、截断和模型域能力还不能排他地因果拆分。

### 回答三个研究问题

1. **E5-small有改善空间，但不是已证实的唯一数学瓶颈。** 全C raw R@50为60.00%，最佳raw Qwen D1/D2为65%，净增4题。排除Exact后，38道公式题E5-small与Qwen D2都找回23题；32道文字题则由20题升到27题。Paraphrase raw R@10：E5-small/E5-base/BGE-M3/Qwen D2均10%，Qwen D1为20%（只多1题）；最佳单条件Paraphrase R@50也仅40%。Relation raw R@10从40%升至Qwen D2的70%，说明强模型确实有关系排序收益，不能说换模型完全无效。

2. **相关内容经常在Top50内但排得靠后。** E5-small有19/80题位于11–50，另32/80题不在Top50。相同E5候选池上，当前规则把R@10从36.25%推到48.75%，BGE neural再推到53.75%；相对现有规则净增4题，R@50始终60%。也就是说现有规则已取得多数可观察排序收益，神经模型补了部分余量。

正式V1.2完整hybrid另行只读测得R@10=60%、R@50=71.25%，其中9/80题仍处11–50、23/80不在Top50；Paraphrase R@10=40%、Exact R@10=100%。其候选池与纯dense不同，只作实际体验的上下文对照，不能混作同池模型胜负。

3. **纯质量最高的已测组合是 e5-small-bge-reranker；交互使用继续V1.2。** 该组合Hit@1=35.00%, R@10=53.75%, MRR@10=0.4014，mean/P95=15.33/17.27秒。E5+BGE相对同池规则只净增4题但P95 17.27秒；embedding+neural组合的完整收益、同池CI及各类回退均在表中，不能只把raw分数提升当成相对正式V1.2的收益。

| 决策项 | 结果 | 解释 |
| --- | --- | --- |
| Quality Winner | qwen-D2 raw；e5-small-bge-reranker 固定池 | 按预定优先指标的点估计；不是所有指标都最优，也不是未测交叉组合的全局最优 |
| Efficiency Winner | E5-small + current | embedding查询、权重/索引磁盘最小；峰值RAM最小并非所有测量都由它取得 |
| Balanced Winner | 正式V1.2 | 现有精确/词法通道和低延迟保留；实验替换没有满足核心改写与体验门槛 |
| No Upgrade | 是 | 不promote V1.2.1，不将实验部署到普通聊天，不进入V1.2.2实现 |

### 进入V1.2.2的门槛检查

以下将实验路线与E5-small + current固定池控制比较；它只检验本轮路线兼容性，不能代替完整hybrid整合后新的独立验收。预算门槛来自推理前冻结的计划。

| 路线 | 改写+10pp | 关系+10pp | 整体不降 | Exact不降 | 两指标提升 | P95≤3s | 重复稳定 | 全部满足 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bge-m3-current | 否 | 是 | 是 | 否 | 否 | 是 | 是 | 否 |
| e5-small-bge-reranker | 是 | 是 | 是 | 是 | 是 | 否 | 是 | 否 |
| e5-small-current | 否 | 否 | 是 | 是 | 否 | 是 | 是 | 否 |
| qwen-D1-bge-reranker | 否 | 是 | 是 | 否 | 是 | 否 | 是 | 否 |
| qwen-D1-current | 否 | 是 | 是 | 否 | 否 | 是 | 是 | 否 |
| qwen-D2-current | 否 | 是 | 是 | 否 | 否 | 是 | 是 | 否 |

按25源页cluster重采样，E5+BGE相对同池规则的R@10净增5pp，95%区间为0至10.34pp；Qwen D1+BGE相对同池规则净增0pp，区间为-7.14至9.41pp。Qwen raw R@50相对E5净增5pp的区间亦跨0。改写每类仅10题，不能把1题差异包装成稳健升级证据。

神经路线即使得到更高分，CPU P95仍超过体验预算；更强embedding+原规则也没有稳定扩大改写检索，且pure-dense候选池丢失编号目标。OCR-limited增益单列，不作为升级理由。正式精确旁路本身未受影响，pure-dense Exact回退不等同于保留该旁路后的必然回退。

### 下一阶段建议

先做小规模、另行冻结的数学表示对照：保留可核对的公式/矩阵/上下标与题目条件，再比较查询概念提取或通用query rewrite。每种操作都与不改写、不修复的控制组同题同池比较；按公式题/文字题分开，保留精确和词法通道。选择少量原页验证机制，再决定后续工程，不重跑三本书OCR，也不继续无休止换embedding。

公式/文字切片同时混有学科和题目难度差异；它不是同一道题只改变公式的配对实验，不能将切片差异直接解释为公式的因果效应。API状态的active_version=v12；INDEX_VERSION=math-v12.1是既有技术索引标签，不能据该标签误认已promote独立v121候选。

C现在已经被查看，之后用于改进只能称development/diagnostic；后续升级重新冻结独立D。C由单一助手编写、25页共享80题、页级非穷尽相关标注、第三方INT8与384-token预算，限制了结论外推。未经过独立人工复核，不能称为数学推理能力认证。

## 最终正式项目核验

完整pytest结果：`92 passed, 1 warning`（原80项 + 12项实验纪律/指标测试）。前后比对1862个原有文件，changed为空；数据库计数为{'documents': 3, 'chunks': 3471, 'chats': 6, 'messages': 16}。正式active仍v12，V1.2.1 active指针不存在，仍为候选。

没有重新OCR、没有修改/删除原PDF、OCR缓存、数据库/聊天或旧索引，没有修改正式检索代码/权重/规则/词表，没有配置或调用OpenAI/付费API，没有安装GPU/PyTorch或新依赖。新增内容仅在隔离实验目录和工作区交付目录。


冻结本地时间：`2026-10-02T21:46:17.512495+08:00`。全部dense started_at晚于冻结；全部rerank started_at晚于五条件dense完成。E5-small新旧向量逐项最大误差为0。
