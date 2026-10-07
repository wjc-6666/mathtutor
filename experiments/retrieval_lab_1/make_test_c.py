"""One-time authorship BEFORE model inference. Never relabel after scoring."""
import json,time,hashlib,collections
from pathlib import Path
LAB=Path(__file__).resolve().parent
corpus=json.loads((LAB/'corpus.json').read_text(encoding='utf8'))
books={b:next(r['name'] for r in corpus['records'] if r['name'].startswith(prefix)) for b,prefix in [('A','高等'),('P','数学分析中的'),('S','裴礼文')]}
questions=[]
def add(cat,q,b,p,note,formula=False,label=None,negative=None):
 target={'book':books[b],'pdf_page':p,'grade':3}
 if label:target['label']=label
 rel=[target]
 if negative:
  nb,np=negative;rel.append({'book':books[nb],'pdf_page':np,'grade':0})
 questions.append({'id':f'C-{cat}-{1+sum(x["category"]==cat for x in questions):02d}','category':cat,'query':q,'subject':'algebra' if b=='A' else 'analysis','relevant':rel,'annotation':note,'source_style':'formula-heavy' if formula else 'text-heavy','verified':'original PDF page image, before model scoring; PDF pages are 1-based'})
for q,b,p,label in [('例3.37','A',154,'例3.37'),('例3.66','A',169,'例3.66'),('例3.82','A',175,'例3.82'),('例4.39','A',225,'例4.39'),('例5.39','A',266,'例5.39'),('例6.62','A',332,'例6.62'),('例2.1.13','P',133,'例2.1.13'),('例3.3.8','P',222,'例3.3.8'),('习题3.2.32','S',64,'习题3.2.32'),('习题3.4.15','S',73,'习题3.4.15')]:add('Exact',q,b,p,'原页编号核对',True,label)
for q,b,p,n,f in [
 ('投影变换与幂等变换的定义有什么联系？','A',231,'幂等变换是投影变换',False),
 ('多项式的零点和一次因式是什么关系？','A',248,'余数定理及零点定义',False),
 ('Frobenius标准型的块如何定义？','A',366,'Frobenius块及有理标准型',True),
 ('Gram行列式的几何意义是什么？','A',508,'平行多面体体积平方',True),
 ('Cantor怎样用有理数基本序列定义实数？','P',115,'基本序列等价类',False),
 ('用上下极限如何判别数列收敛？','P',102,'上下极限相等且有限',False),
 ('一致连续可以用两数列距离趋零来刻画吗？','P',146,'例2.2.3序列判别',False),
 ('二阶对称导数与普通二阶导数有何区别？','P',208,'二阶广义导数定义及反例',True),
 ('没有初等原函数时怎样用Darboux和估计积分？','P',302,'上、下和夹估',True),
 ('逐项求导的充分条件为何不一定是必要条件？','P',483,'例5.2.28不能用逐项求导定理',False)]:add('Concept',q,b,p,n,f)
for q,b,p,n,f in [
 ('Sylvester矩阵乘积秩不等式及其证明','A',169,'r(AB)>=r(A)+r(B)-n',True),
 ('严格对角占优矩阵为什么非奇异？','A',175,'例3.83',True),
 ('无重因式多项式与形式导数互素的充要条件','A',248,'无重因式定理',False),
 ('奇数次实系数多项式必有实根的证明','A',266,'例5.40',False),
 ('可交换且都可对角化的线性变换可同时对角化吗？','A',320,'例6.41',False),
 ('闭区间到自身的连续函数存在不动点的证明','P',133,'例2.1.13',False),
 ('有限区间上一致连续等价于保持Cauchy序列的证明','P',146,'例2.2.4有限区间条件',False),
 ('连续函数绝对值可导能推出函数可导吗？','P',182,'练习3.1.12',False),
 ('函数和二阶导数有界时一阶导数的界如何估计？','P',222,'例3.3.9 Landau型不等式',True),
 ('二阶导数存在能否推出中心二阶差商收敛？','S',64,'习题3.2.32',True)]:add('Theorem',q,b,p,n,f)
for q,b,p,n,f in [
 ('一组坐标方向依次改成前几个方向的总和，这些新方向还能唯一表示每个向量吗？','A',154,'前缀和基例3.38',False),
 ('实方阵里互换两个指标会把元素变号，再加上对角位置全为正的阵，为什么不会丢掉逆？','A',175,'反对称加正对角例3.82',True),
 ('把方阵对角线上所有数加起来，这个操作把哪些矩阵压到零，它们有多少自由度？','A',225,'迹映射核n^2-1例4.39',True),
 ('一个线性操作做第二遍与做第一遍完全一样，整个空间怎样拆成被留下和被抹掉两部分？','A',231,'幂等的像与核直和',False),
 ('一个复数系数的多项式在每个实输入都给实输出，为什么各个系数其实也是实数？','A',266,'例5.39插值Vandermonde',False),
 ('两个实数只要距离很近，函数值就一起接近；怎样用两列点的距离消失来检验这种共同控制？','P',146,'一致连续序列标准',False),
 ('连续曲线把一段闭区间里的点都送回这段里，为什么总有一个点送完没有动？','P',133,'不动点',False),
 ('曲线上某点的左右两点一起贴近它，左右两点连线的斜率会到哪里去？','P',171,'例3.1.6跨点差商极限',True),
 ('把图像离横轴的距离当作新函数，这个新函数在某点能求斜率且原函数连续，为何原图像也能求斜率？','P',182,'绝对值可导推出可导',False),
 ('不直接求出面积原函数，只拿越来越细的长方条从上下夹住曲线面积，怎样得到带误差界的数值？','P',302,'Darboux积分估计',True)]:add('Paraphrase',q,b,p,n,f)
for q,b,p,n,f in [
 ('m个向量的秩为r时，全部线性依赖关系的系数空间为何有m-r维？','A',154,'例3.37关系空间',True),
 ('AB为零时A和B的秩之和与中间维数有什么关系？','A',169,'Sylvester推论',True),
 ('定义域维数大于值域维数的线性映射为何必有非零核？','A',225,'例4.40',False),
 ('满线性映射能否在核的补空间上变成到值域的同构？','A',225,'例4.41',False),
 ('矩阵的不变因子怎样同时决定特征多项式和极小多项式？','A',366,'不变因子乘积与最大因子',True),
 ('若A有互异特征值且AB=BA，A的特征子空间对B有什么性质？','A',332,'例6.62一维不变子空间',True),
 ('A转置乘B等于BA且B正定，怎样联系自伴随算子与A可对角化？','A',552,'例9.72',True),
 ('正数列相邻项之比趋向l时，n次方根是否也趋向l？','P',102,'例1.6.6比值与根极限',True),
 ('函数二阶导数与中心二阶差商极限是什么关系？','S',64,'习题3.2.32',True),
 ('所有内积两两为负的非零向量，个数怎样受欧氏空间维数限制？','A',508,'例9.6至多n+1',False)]:add('Relation',q,b,p,n,f)
for q,b,p,n,f in [
 ('找讨论一组基的循环相邻和是否线性无关的例题','A',154,'例3.39奇偶性',True),
 ('找以矩阵乘积为零并结合奇偶阶数证明另一矩阵奇异的例题','A',169,'例3.67',True),
 ('找反对称矩阵加正对角阵的可逆性证明题','A',175,'例3.82',True),
 ('找计算迹为零矩阵空间的维数和基的题','A',225,'例4.39',True),
 ('找将多项式所有非零根换成倒数后求新多项式的题','A',266,'例5.37',True),
 ('找利用共同特征向量证明可交换矩阵可对角化的题','A',332,'例6.62',True),
 ('找圆周上连续函数在某条直径两端取相同值的题','P',133,'例2.1.14',False),
 ('找函数值和二阶导数有界从而控制一阶导数的题','P',222,'例3.3.9',True),
 ('找用三角函数的高阶导数证明三角不等式的题','S',73,'习题3.4.13',True),
 ('找用积分核近似连续函数端点值的题','S',81,'P254两道练习',True)]:add('SimilarProblem',q,b,p,n,f)
for q,b,p,n,f in [
 ('哪里用构造分块矩阵并做初等变换来证明矩阵秩的下界？','A',169,'例3.66分块变换',True),
 ('哪里把零解唯一性和二次型正性结合起来证明可逆？','A',175,'例3.82第一部分',True),
 ('哪里先把核的一组基扩张成全空间基，再限制映射得到同构？','A',225,'例4.41证法1',False),
 ('哪里用Vandermonde矩阵和插值把函数值的信息转成多项式系数的信息？','A',266,'例5.39',True),
 ('哪里通过不变子空间上的归纳同时化简两个可交换算子？','A',320,'例6.40结尾归纳',False),
 ('哪里通过正定矩阵开平方把算子转成实对称矩阵来证明对角化？','A',552,'例9.72证法1',True),
 ('哪里构造对径点函数值的差，再用正负号变化找到零点？','P',133,'例2.1.14',False),
 ('哪里用反证法制造靠近的两列点和不靠近的两列函数值？','P',146,'例2.2.3充分性',False),
 ('哪里反复应用求导极限法计算中心高阶差商？','S',64,'习题3.2.32/33 lHopital',True),
 ('哪里先给零均值周期函数构造有界原函数，再分部积分处理振荡积分极限？','S',81,'P259练习Riemann引理',True)]:add('MethodSimilarity',q,b,p,n,f)
hard=[
 ('不是仅仅找线性同构定义，我要满射在核的补空间上成为同构的证明。','A',225,'例4.41补空间限制，单纯定义非目标',False,('A',231)),
 ('找幂等投影的像与核分解，不是迹为零矩阵的空间。','A',231,'幂等直和分解',False,('A',225)),
 ('问没有重根的判别，不是奇数次实多项式至少有实根。','A',248,'导数互素判别',False,('A',266)),
 ('我要的是多项式在所有实输入取实值推出实系数，不是代数基本定理。','A',266,'例5.39',False,('A',248)),
 ('B只半正定时A转置B等于BA还保证A可对角化吗？找反例。','A',552,'例9.72后半正定反例',True,('A',332)),
 ('问一致连续和保持基本序列的等价，不是用基本序列定义实数。','P',146,'例2.2.4',False,('P',115)),
 ('要找有二阶对称导数却没有普通二阶导数的反例，不是普通导数存在的充分结论。','P',208,'x|x|反例',True,('S',64)),
 ('我问绝对值可导推出原函数可导，不是左右两点割线斜率的极限。','P',182,'练习3.1.12',False,('P',171)),
 ('要用上下和夹估积分而非三角函数高阶求导证明不等式。','P',302,'Darboux上下和',True,('S',73)),
 ('要积分核收缩到端点的极限，不是用连续自映射找固定点。','S',81,'P254练习',True,('P',133))]
for q,b,p,n,f,neg in hard:add('HardNegative',q,b,p,n,f,negative=neg)
assert len(questions)==80
used={(t['book'],t['pdf_page']) for name in ['development_a.json','development_b.json'] for q in json.loads((LAB/name).read_text(encoding='utf8'))['questions'] for t in q['relevant']}
assert not used&{(t['book'],t['pdf_page']) for q in questions for t in q['relevant']}
assert all(any(r['name']==t['book'] and r['page']==t['pdf_page'] and (not t.get('label') or r.get('label')==t['label']) for r in corpus['records']) for q in questions for t in q['relevant'])
dataset={'name':'Retrieval Lab Test C','split':'frozen_test','created_at':time.time(),'questions':questions,'source_pages':sorted({(t['book'],t['pdf_page']) for q in questions for t in q['relevant']}),'author_policy':'80 manually authored queries from original PDF page images; no retrieval predictions viewed; source pages disjoint A/B; related queries share 26 source pages, not 80 independent topics; relevance incomplete; single-author internal test'}
path=LAB/'test_c.json'
if path.exists():raise ValueError('Test C already frozen; refusing overwrite')
path.write_text(json.dumps(dataset,ensure_ascii=False,indent=2),encoding='utf8');digest=hashlib.sha256(path.read_bytes()).hexdigest();(LAB/'test_c.sha256').write_text(digest+'  test_c.json\n',encoding='utf8')
plan={'test_sha256':digest,'frozen_at':time.time(),'question_count':len(questions),'categories':dict(collections.Counter(q['category'] for q in questions)),'subjects':dict(collections.Counter(q['subject'] for q in questions)),'source_pages':dataset['source_pages'],'passages_sha256':hashlib.sha256((LAB/'corpus.json').read_bytes()).hexdigest(),'max_tokens':384,'threads':4,'topk':50,'subject_filter':False,'qwen_instruction':'Retrieve textbook passages that solve, define, prove, or use the same mathematical concept, theorem, relation, or method as the query.','rerank_pool':'each frozen retriever raw Top50, no additional candidates','rerank_gate':'Test C Recall@50 >= 0.60; exploratory only','repeat':2,'no_tuning':True,'promotion':False,'resource_policy':'CPU only INT8; <=8GB model RSS; max 2h per indexing; no full GPU/PyTorch install','upgrade_gate':'para/relation >= +10 percentage points; overall no drop>2pp; protected Exact no drop; two core metrics improved; p95<=3s; repeat stable; exclude OCR-limited gains'}
(LAB/'freeze.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(plan,ensure_ascii=False,indent=2))
