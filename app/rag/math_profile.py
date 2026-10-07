"""Local, deliberately bounded mathematical query hypotheses (no LLM calls)."""
import re
from app.rag.keyword import normalize

# Canonical names and OCR/English variants. Matching is evidence of a mention,
# never evidence that the theorem's assumptions have been satisfied.
LEXICON = {
 'Concept': {
  '极限':['极限','limit'], '连续':['连续','continuous'], '一致连续':['一致连续','uniformly continuous'],
  '导数':['导数','可导','derivative'], '定积分':['定积分','integral'], '一致收敛':['一致收敛','uniform convergence'],
  '逐点收敛':['逐点收敛','点态收敛','pointwise'], '函数项级数':['函数项级数'], '数项级数':['数项级数'],
  '等度连续':['等度连续'], '线性空间':['线性空间','向量空间'], '线性相关':['线性相关','线性无关'],
  '矩阵的秩':['矩阵的秩','秩','rank'], '迹':['迹','trace','tr('], '特征值':['特征值','eigenvalue'], '特征向量':['特征向量'],
  '线性变换':['线性变换','线性映射'], '同构':['同构','isomorphism'], '行列式':['行列式','determinant'],
  '正定':['正定','半正定'], '可对角化':['对角化','diagonaliz'], 'Jordan标准形':['jordan','约当'],
  '对偶空间':['对偶空间','对偶基'], '内积':['内积','正交'], '交空间与和空间':['交空间','和空间','维数公式']},
 'Theorem': {
  'Rolle定理':['rolle','罗尔','罗耳'], 'Lagrange中值定理':['lagrange','拉格朗日'],
  'Cauchy中值定理':['cauchy中值','柯西中值'], '微分中值定理':['微分中值定理','中值定理'],
  'Taylor定理':['taylor','泰勒'], 'Cauchy收敛准则':['cauchy准则','cauchy收敛','柯西准则','柯西收敛'],
  'Cauchy-Binet公式':['cauchy-binet','cauchybinet','柯西比内','cauchy-binct'],
  'Cayley-Hamilton定理':['cayley-hamilton','cayleyhamilton','哈密顿'],
  'Bolzano-Weierstrass定理':['bolzano','weierstrass','有界数列必有收敛子列'],
  '维数公式':['维数公式','dim(w','dimv'], '均值不等式':['均值不等式'],
  'LHopital法则':["l'hopital",'lhopital','洛必达'], '积分中值定理':['积分中值定理']},
 'Method': {
  '构造辅助函数':['辅助函数','辅助函','构造函数'], '以果寻因':['以果寻因','从结论倒推','从目标倒推'],
  '反证法':['反证法','用反证','反证'], '数学归纳法':['数学归纳法','归纳法','归纳假设'],
  '放缩':['放缩','估计法'], '分部积分':['分部积分'], '换元':['换元','变量代换'],
  '构造递推关系':['递推关系','递推公式'], '特征多项式':['特征多项式','特征方程'],
  '相似变换':['相似变换'], '不变量法':['不变量'], '行列变换':['行变换','列变换','初等变换'],
  '上确界估计':['上确界','sup'], 'Cauchy-Binet展开':['cauchy-binet','cauchybinet','cauchy-binct'],
  '定义法':['利用定义','根据定义','由定义','按定义'], '构造反例':['反例'], '配方法':['配方法','配方']},
 'ProblemType': {
  '存在性证明':['证明存在','存在一点','存在ξ','存在一个'], '极限计算':['求极限','计算极限'],
  '不等式证明':['证明不等式','不等式'], '中值定理证明':['中值定理'],
  '函数方程':['函数方程'], '积分估计':['积分估计'], '矩阵可对角化判断':['可对角化','能对角化'],
  '特征值计算':['求特征值','计算特征值'], '收敛性判断':['是否收敛','证明一致收敛','收敛性'],
  '行列式计算':['求行列式','计算行列式']}
}

def mentions(text):
    n=normalize(text).replace('－','-')
    found={kind:[name for name,aliases in values.items() if any(normalize(a) in n for a in aliases)] for kind,values in LEXICON.items()}
    if '一致连续' in found['Concept'] and '连续' in found['Concept'] and '连续' not in n.replace('一致连续',''):found['Concept'].remove('连续')
    return found

def parse_query(query,subject='all'):
    if subject not in {'all','analysis','algebra'}:raise ValueError('未知学科')
    explicit=mentions(query); found={k:list(v) for k,v in explicit.items()};hypotheses=[]
    def propose(kind,name,reason):
        if name not in found[kind]:
            found[kind].append(name);hypotheses.append({'kind':kind,'name':name,'basis':'系统推断','confidence':'medium','reason':reason})
    n=normalize(query)
    if re.search(r'存在.*(?:ξ|\bxi\b|一点|c∈|一点c)',query.lower()) or ('使' in query and '存在' in query):
        for t in ['Rolle定理','Lagrange中值定理','Cauchy中值定理']:propose('Theorem',t,'存在性结论可能与中值定理有关，尚需检查条件')
        propose('Method','构造辅助函数','从目标表达式倒推导数；候选思路')
        propose('ProblemType','存在性证明','问题含存在性表述')
    if any(x in query for x in ['每一点都收敛','所有点共用','同一个N','不依赖x','收敛速度一样','整个区间同时']):
        propose('Concept','一致收敛','误差界/指标对自变量独立的改写')
        propose('Method','上确界估计','检查误差上确界是否趋于零')
    if any(x in query for x in ['端点取值相同','两端取值相同','两端函数值相等','两端一样']):
        propose('Theorem','Rolle定理','端点等值是 Rolle 条件之一，另需连续与可导')
        propose('Method','构造辅助函数','制造端点等值，尚需教材证据')
    if any(x in query for x in ['对角矩阵','一组由特征向量构成的基','足够多的特征向量']):propose('Concept','可对角化','线性无关特征向量与对角化判断')
    if ('双射' in query or '一一对应' in query) and any(x in query for x in ['数乘','加法','线性']):propose('Concept','同构','保线性结构的双射是线性同构的候选表述')
    if any(x in query for x in ['乘积的子式','乘积矩阵的子式','主子式非负']) or ('主子式' in query and '非负' in query) or ('转置' in query and any(x in query for x in ['子式','子行列式'])):
        propose('Theorem','Cauchy-Binet公式','矩阵乘积子式展开的候选理论')
        propose('Method','Cauchy-Binet展开','把子式化为乘积/平方和的候选方法')
    if '主子式' in query or '子行列式' in query:propose('Concept','行列式','子式是行列式相关知识，不是已证结论')
    if any(x in query for x in ['证明','求证']) and any(x in query for x in ['非负','非正','不等式','≥','≤']):propose('ProblemType','不等式证明','证明符号/非负性条件')
    if any(x in query for x in ['为什么想到','怎么想到','从目标倒推']):propose('Method','以果寻因','用户询问方法动机')
    from app.rag.knowledge import CATALOGUE
    for method in list(found['Method']):
        for theorem in CATALOGUE.get(method,{}).get('theorems',[]):
            propose('Theorem',theorem,'通用方法地图的关联定理；仅扩展检索，不能证明当前题满足条件')
    ids=re.findall(r'(?:例题|例|习题|练习|定义|定理|引理|推论|公式)\s*\d+(?:[.．]\d+)+',query)
    ids=[normalize(x).replace('例题','例').replace('练习','习题') for x in ids]
    intent='solve_problem'
    if ids and not any(x in query for x in ['类似','相似','同类']):intent='find_exact_example'
    elif any(x in query for x in ['比较','区别','对比']) and len(found['Method'])>=2:intent='compare_methods'
    elif any(x in query for x in ['类似','相似','同类']):intent='find_similar_problem'
    elif any(x in query for x in ['相关方法','方法联系']):intent='find_related_method'
    elif any(x in query for x in ['复习','总结','知识地图']):intent='review_topic'
    elif found['Method'] and any(x in query for x in ['如何','为什么','怎么','方法']):intent='explain_method'
    elif any(x in query for x in ['什么是','定义','条件是什么','解释','叫什么','有何区别','为何']):intent='explain_concept'
    inferred_subject=subject
    if subject=='all':
        algebra=set(LEXICON['Concept'])-{'极限','连续','一致连续','导数','定积分','一致收敛','逐点收敛','函数项级数','数项级数','等度连续'}
        if set(found['Concept'])&algebra:inferred_subject='algebra'
        elif any(t in found['Theorem'] for t in ['Cauchy-Binet公式','Cayley-Hamilton定理']):inferred_subject='algebra'
        elif found['Concept'] or any('中值' in t or 'Rolle' in t for t in found['Theorem']):inferred_subject='analysis'
    return {'raw_query':query,'subject':inferred_subject,'subject_basis':'用户指定' if subject!='all' else '系统推断，仅加分不排除另一学科',
            'concepts':found['Concept'],'possible_theorems':found['Theorem'],'possible_methods':found['Method'],
            'problem_type':found['ProblemType'] or None,'exact_identifiers':ids,
            'mathematical_expressions':re.findall(r'\$[^$]+\$|\\\([^\n]+?\\\)|[^\s，。；]*(?:[=<>≤≥∈ξ^×_]|\\frac)[^\s，。；]*',query),
            'query_intent':intent,'explicit_mentions':explicit,'hypotheses':hypotheses}

def expand(profile):
    result=[{'query':profile['raw_query'],'perspective':'原题','basis':'用户原文','confidence':'explicit'}]
    for kind,key in [('Concept','concepts'),('Method','possible_methods'),('Theorem','possible_theorems'),('ProblemType','problem_type')]:
        for name in profile[key] or []:
            inferred=name not in profile['explicit_mentions'][kind]
            result.append({'query':name,'perspective':kind,'basis':'系统推断' if inferred else '用户提及术语','confidence':'medium' if inferred else 'explicit'})
    return result
