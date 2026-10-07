"""Bounded local mathematics hypotheses; never a proof or textbook quotation."""
import re,unicodedata
from dataclasses import dataclass,asdict,field
from app.rag.math_profile import parse_query

# Aliases are matched within mathematical context, not substituted into OCR.
LEXICON={
 '线性映射':['线性映射','线性变换','linear map'],
 '线性同构':['线性同构','同构','isomorphism'],
 '向量空间':['向量空间','线性空间','vector space'],
 '双射':['双射','一一对应','一一且到上','bijective'],
 '可对角化':['可对角化','对角化','diagonalizable'],
 '主子式':['主子式','principal minor'], '子式':['子式','子行列式','minor'],
 '矩阵的秩':['矩阵的秩','秩','rank'], '迹':['迹','trace','tr('],
 '核':['零空间','核','kernel','null space'],
 '正定':['正定','positive definite'], '半正定':['半正定','positive semidefinite'],
 '内积':['内积','inner product'], '特征值':['特征值','eigenvalue'],
 '特征向量':['特征向量','eigenvector'], '相似变换':['相似变换','similarity transform'],
 'Cauchy-Binet公式':['cauchy-binet','cauchybinet','cauchy-binct','柯西比内'],
 'Cauchy-Schwarz不等式':['cauchy-schwarz','cauchy-schwarz不等式','柯西施瓦茨'],
 'Lagrange恒等式':['lagrange恒等式','拉格朗日恒等式'],
 'Rolle定理':['rolle','罗尔','罗耳'], '一致收敛':['一致收敛','uniform convergence'],
 '逐点收敛':['逐点收敛','点态收敛'], '等度连续':['等度连续'],
 '一致连续':['一致连续'], '连续':['连续'],
 '积分中值定理':['积分中值定理'], '微分中值定理':['微分中值定理'],
 '导数':['导数','可导','derivative'], '行列式':['行列式','determinant'],
 '极小多项式':['极小多项式','minimal polynomial'], '幂零矩阵':['幂零矩阵','nilpotent'],
}
RULES={
 'linear_structure':'保加法 + 保数乘 + 映射/空间 → 线性映射',
 'bijective_linear':'线性映射 + 双射 → 线性同构',
 'invertible_linear':'可逆 + 线性映射 → 线性同构',
 'basis_diagonal':'基/相似 + 对角矩阵 → 可对角化',
 'principal_selection':'相同行列选取子行列式 → 主子式',
 'transpose_product':'矩阵乘自身转置 → AA^T',
 'product_minors':'矩阵乘积 + 子式展开 → Cauchy-Binet候选',
 'principal_nonnegative':'主子式 + 非负 + 实矩阵/转置 → Cauchy-Binet候选',
 'squared_inner_product':'平方和乘积 - 内积平方 → Lagrange恒等式/Cauchy-Schwarz候选',
 'rank_value':'秩/ rank / r 的数值 → rank(A)=n',
 'trace_value':'迹/ trace / tr 的数值 → tr(A)=n（询问不当作已知）',
 'uniform_index':'所有点共享误差指标 → 一致收敛候选',
 'equal_endpoints':'连续可导且端点等值 → Rolle候选',
 'derivative_bound':'函数族 + 导数一致界 → 等度连续候选',
 'auxiliary_derivative':'辅助函数构造 + 求导 → 构造辅助函数签名',
}
METHOD_SIGNATURES={
 'construct_auxiliary_function':r'辅助函数|辅助函|构造函数',
 'apply_rolle':r'rolle|罗尔|罗耳',
 'apply_cauchy_binet':r'cauchy-?bin(?:et|ct)|柯西比内',
 'induction':r'归纳法|数学归纳|归纳假设', 'contradiction':r'反证',
 'invariant':r'不变量', 'substitution':r'换元|变量代换',
 'integration_by_parts':r'分部积分', 'row_column_operations':r'行变换|列变换|初等变换',
 'supremum_bound':r'上确界|sup', 'apply_cauchy_mean_value':r'cauchy中值|柯西中值',
}
def normalize_math(text):
    n=unicodedata.normalize('NFKC',text).lower().replace('−','-').replace('－','-')
    n=re.sub(r'\s+','',n).replace('^t','^T')
    # Normalise the name only, never repair a scanned mathematical formula.
    n=re.sub(r'cauchy-?b(?:in|inet|inct)(?:et)?',lambda m:'cauchy-binet' if m.group() in ['cauchy-binet','cauchybinet','cauchy-binct'] else m.group(),n)
    return n

@dataclass
class MathQueryRepresentation:
    raw_query:str
    normalized_text:str
    concepts:list=field(default_factory=list)
    theorem_candidates:list=field(default_factory=list)
    method_candidates:list=field(default_factory=list)
    problem_type:list=field(default_factory=list)
    mathematical_objects:list=field(default_factory=list)
    properties:list=field(default_factory=list)
    relations:list=field(default_factory=list)
    conditions:list=field(default_factory=list)
    target:str=''
    symbolic_forms:list=field(default_factory=list)
    aliases:list=field(default_factory=list)
    confidence:str='medium'
    evidence:list=field(default_factory=list)
    canonical_text:str=''
    views:dict=field(default_factory=dict)
    method_signature:list=field(default_factory=list)
    exact_identifiers:list=field(default_factory=list)
    triggered_rules:list=field(default_factory=list)
    def to_dict(self):return asdict(self)

def represent(query,subject='all',disabled_rules=(),source='query'):
    n=normalize_math(query);p=parse_query(query,subject);m=MathQueryRepresentation(query,n)
    m.exact_identifiers=p['exact_identifiers'];m.target=p['query_intent'];m.problem_type=p['problem_type'] or []
    matrix=bool(re.search(r'矩阵|方阵|rank\(|tr\(|aa[\^\'tT]|r\(a\)',n))
    mapping=bool(re.search(r'映射|对应|空间|双射|数乘',n))
    if matrix:m.mathematical_objects.append('矩阵 A')
    if mapping:m.mathematical_objects.append('向量空间间映射')
    for name,aliases in LEXICON.items():
        for alias in aliases:
            if normalize_math(alias) not in n:continue
            if name in {'线性同构','核','双射','向量空间','线性映射'} and not mapping:continue
            if name in {'主子式','子式','正定','半正定','迹','矩阵的秩','幂零矩阵','极小多项式'} and not matrix:continue
            # Positive and semipositive; continuous and uniform continuous are distinct.
            if name=='正定' and '正定' not in n.replace('半正定',''):continue
            if name=='连续' and '连续' not in n.replace('一致连续','').replace('等度连续',''):continue
            m.concepts.append(name);m.aliases.append({'surface':alias,'canonical':name,'context':'matrix' if matrix else 'mapping' if mapping else 'analysis','basis':'system_inference'});break
    def rule(name,condition,concepts=(),theorems=(),methods=(),symbols=(),properties=()):
        if not condition or name in disabled_rules:return False
        m.triggered_rules.append(name);m.evidence.append({'rule':name,'reason':RULES[name],'basis':'system_inference','source':source,'confidence':'medium'})
        m.concepts.extend(concepts);m.theorem_candidates.extend(theorems);m.method_candidates.extend(methods);m.symbolic_forms.extend(symbols);m.properties.extend(properties);return True
    linear=rule('linear_structure',mapping and bool(re.search(r'保(?:持)?加法|加法保持|可加',n)) and bool(re.search(r'保(?:持)?数乘|数乘保持|标量乘法',n)),['线性映射'],properties=['additivity','scalar_compatibility','linear'])
    bijective=bool(re.search(r'双射|一一对应|一一且到上|bijective',n)) and not bool(re.search(r'(?:不是|非|不为|并非)双射|不是一一对应',n))
    rule('bijective_linear',mapping and bijective and (linear or '线性映射' in m.concepts or '线性' in n),['线性同构'],properties=['bijective','linear'])
    rule('invertible_linear',mapping and '可逆' in n and ('线性映射' in m.concepts or '线性变换' in n),['线性同构'],properties=['bijective','linear'])
    rule('basis_diagonal',bool(re.search(r'基|相似',n)) and bool(re.search(r'对角矩阵|对角阵',n)),['可对角化'])
    rule('principal_selection',matrix and bool(re.search(r'相同.*(?:行列|行.*列)|同一.*(?:行列|行.*列)',n)) and bool(re.search(r'子式|子行列式',n)),['主子式','行列式'])
    trans=rule('transpose_product',matrix and bool(re.search(r'乘.*转置|自身转置|aa\^?t|aa\x27',n)),symbols=['AA^T'],properties=['transpose_product'])
    rule('product_minors',bool(re.search(r'矩阵乘积|乘积矩阵',n)) and bool(re.search(r'子式|子行列式',n)),['子式','行列式'],['Cauchy-Binet公式'],['Cauchy-Binet展开'])
    principal='主子式' in m.concepts
    nonnegative=bool(re.search(r'非负|不会为负|不为负|不小于零|>=0|≥0',n))
    rule('principal_nonnegative',principal and nonnegative and (trans or '实矩阵' in n),['主子式'],['Cauchy-Binet公式'],['Cauchy-Binet展开'],properties=['principal_minor_nonnegative'])
    rule('squared_inner_product','平方和' in n and ('内积平方' in n or '内积的平方' in n),['内积','Lagrange恒等式','Cauchy-Schwarz不等式'],symbols=['||a||^2 ||b||^2 - <a,b>^2'])
    rank=re.search(r'(?:秩(?:是|为)?|rank\(a\)=|r\(a\)=)(\d+|一|二|三)',n)
    if not rank and '秩一' in n:rank=re.search(r'秩(一)',n)
    if rank and matrix:
        value={'一':'1','二':'2','三':'3'}.get(rank[1],rank[1]);rule('rank_value',True,['矩阵的秩'],symbols=['rank(A)='+value],properties=['rank='+value])
    trace=re.search(r'(?:迹(?:是|为)?|tr\(a\)=|trace\(a\)=)(\d+|零)',n)
    if trace and matrix:
        value='0' if trace[1]=='零' else trace[1];rule('trace_value',True,['迹'],symbols=['tr(A)='+value])
        m.conditions.append({'expression':'tr(A)='+value,'status':'question' if re.search(r'是否|什么时候|有关|吗',n) else 'asserted','basis':'system_inference'})
    rule('uniform_index',bool(re.search(r'所有点.*(?:同一个|共用)|不依赖x|n.*与x无关|共同.*n|整个区间同时',n)),['一致收敛'],methods=['上确界估计'])
    rule('equal_endpoints',bool(re.search(r'两端.*(?:相同|相等)|端点.*(?:相同|相等)|f\(a\)=f\(b\)',n)) and ('可导' in n or '导数' in n or '连续' in n),theorems=['Rolle定理'])
    rule('derivative_bound',bool(re.search(r'函数族|一族|这族',n)) and '导数' in n and bool(re.search(r'有界|一致界',n)),['等度连续'])
    rule('auxiliary_derivative','辅助函' in n and ('导数' in n or '求导' in n),methods=['构造辅助函数'])
    # Keep literal theorem/method mentions; disambiguate Lagrange identity from mean value theorem.
    m.theorem_candidates.extend(t for t in p['explicit_mentions']['Theorem'] if not (t=='Lagrange中值定理' and 'lagrange恒等式' in n) and not (t=='微分中值定理' and '积分中值' in n))
    m.method_candidates.extend(p['explicit_mentions']['Method'])
    for sig,pattern in METHOD_SIGNATURES.items():
        if re.search(r'(?:不用|不使用|不采用|而非)(?:'+pattern+')',n):continue
        if re.search(pattern,n) or (sig=='apply_cauchy_binet' and 'Cauchy-Binet展开' in m.method_candidates):m.method_signature.append(sig)
    for prop in m.properties:m.relations.append({'object':'AA^T' if prop in ['transpose_product','principal_minor_nonnegative'] else 'A' if matrix else '向量空间间映射','relation':'QUESTION_PROPERTY' if prop=='principal_minor_nonnegative' else 'HAS_PROPERTY','property':prop,'basis':'system_inference'})
    if '可对角化' in m.concepts:m.relations.append({'object':'A','relation':'QUESTION_PROPERTY' if source=='query' else 'RELATED_TO','property':'diagonalizable','basis':'system_inference'})
    if '迹' in m.concepts:m.relations.append({'object':'A','relation':'RELATED_TO','property':'trace(A)','basis':'system_inference'})
    for name in ['concepts','theorem_candidates','method_candidates','symbolic_forms','properties','triggered_rules','method_signature']:setattr(m,name,list(dict.fromkeys(getattr(m,name))))
    canonical=m.concepts+m.theorem_candidates+m.symbolic_forms
    if linear and bijective:canonical=['向量空间之间的双射线性映射','线性同构']+canonical
    m.canonical_text='；'.join(canonical) or query
    m.views={'Raw':query,'Canonical':m.canonical_text,'Concepts':' '.join(m.concepts+m.theorem_candidates),'Relations':' '.join(m.symbolic_forms+[r['property'] for r in m.relations]),'Method':' '.join(m.method_candidates+m.method_signature)}
    return m
