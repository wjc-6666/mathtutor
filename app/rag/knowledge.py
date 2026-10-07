"""Small mathematical catalogue. Pedagogical links are attributed, not textbook quotes."""
CATALOGUE = {
 '构造辅助函数':{'triggers':['目标要求某个导数表达式为零','端点关系需要转成等值','出现两个函数的导数关系'],
               'strategy':'从目标倒推 F 的导数，再检查端点等值、闭区间连续、开区间可导。',
               'theorems':['Rolle定理','Lagrange中值定理','Cauchy中值定理'],'types':['存在性证明','中值定理证明']},
 '以果寻因':{'triggers':['知道目标但不知道构造什么'],'strategy':'先写希望得到的结论，反推可用定理及所需条件，再选择构造。','theorems':['Rolle定理'],'types':['存在性证明','不等式证明']},
 '上确界估计':{'triggers':['误差控制要求对整个区间同时成立'],'strategy':'估计 sup_x |f_n(x)-f(x)|；不能仅检查固定 x。','theorems':['Cauchy收敛准则'],'types':['收敛性判断']},
 'Cauchy-Binet展开':{'triggers':['矩阵乘积的子式','A 与其转置乘积的主子式'],'strategy':'按行列索引集合展开子式，转置配对可得到平方和。','theorems':['Cauchy-Binet公式'],'types':['不等式证明','行列式计算']},
 '数学归纳法':{'triggers':['命题含正整数 n','递推关系'],'strategy':'检查起始情形，再从 n 推至 n+1。','theorems':[],'types':['不等式证明']},
 '分部积分':{'triggers':['积分中有函数乘积','可导部分与可积部分可分开'],'strategy':'选择 u 与 dv，再检查边界项和剩余积分。','theorems':[],'types':['积分估计']},
 '换元':{'triggers':['复合函数与其内函数导数同时出现'],'strategy':'明确变量替换、上下限和可逆性条件。','theorems':[],'types':['积分估计','极限计算']},
 '特征多项式':{'triggers':['特征值计算','矩阵可对角化判断'],'strategy':'先求 det(tI-A)，再检查各特征空间维数；代数重数不自动等于几何重数。','theorems':['Cayley-Hamilton定理'],'types':['特征值计算','矩阵可对角化判断']}
}
PREREQUISITES={
 'Rolle定理':['连续','导数'],'Lagrange中值定理':['连续','导数'], 'Cauchy中值定理':['连续','导数'],
 '一致收敛':['逐点收敛','极限'],'可对角化':['特征值','特征向量','线性相关'],
 '同构':['线性空间','线性变换'],'对偶空间':['线性空间','线性变换'],
 '特征值':['行列式','线性变换'],'定积分':['连续','极限']
}
CONFUSIONS={
 '一致收敛':'逐点收敛的 N 可依赖 x；一致收敛要求同一个 N 对全域有效。',
 'Rolle定理':'除端点等值，还需闭区间连续、开区间可导。',
 '可对角化':'有特征值不保证存在一组线性无关的特征向量。',
 'Cauchy中值定理':'使用导数比值前必须检查分母非零。'
}

def catalogue_edges(entities):
    edges=[]
    def edge(a,b,kind):
        if a in entities and b in entities:
            edges.append({'source':a,'target':b,'relation':kind,'basis':'系统整理：通用数学学习关系，非教材原句',
                          'confidence':'high','evidence':None})
    for name,item in CATALOGUE.items():
        for problem in item['types']:edge(name,problem,'APPLIES_TO')
    for name,parents in PREREQUISITES.items():
        for parent in parents:edge(name,parent,'REQUIRES') if entities.get(name,{}).get('type')=='Theorem' else edge(parent,name,'PREREQUISITE_OF')
    return edges
