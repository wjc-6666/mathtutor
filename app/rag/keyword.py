import re,math,collections
def normalize(text):return re.sub(r'\s+','',text.lower().replace('．','.').replace('。','.'))
def tokens(text):
    text=normalize(text);result=re.findall(r'[a-z]+|\d+(?:\.\d+)+',text)
    for run in re.findall(r'[\u4e00-\u9fff]+',text):
        result.extend(run[i:i+2] for i in range(len(run)-1))
        if len(run)==1:result.append(run)
    return result
def scores(query,rows):
    q=collections.Counter(tokens(query));corpus=[collections.Counter(tokens(r['text'])) for r in rows]
    lengths=[sum(c.values()) for c in corpus];avg=sum(lengths)/max(1,len(lengths));N=len(rows)
    df={t:sum(t in c for c in corpus) for t in q};exact=normalize(query)
    identifiers=re.findall(r'(?:例题|例|定义|定理|引理|推论)\d+(?:\.\d+)+',exact);result=[]
    for row,count,L in zip(rows,corpus,lengths):
        s=0.
        for t in q:
            f=count[t]
            if f:s+=math.log(1+(N-df[t]+.5)/(df[t]+.5))*f*2.2/(f+1.2*(.25+.75*L/max(1,avg)))
        normalized=normalize(row['text'])
        if len(exact)>=2 and exact in normalized:s+=8
        if identifiers and any(re.search(re.escape(i)+r'(?![\d.])',normalized) for i in identifiers):s+=40
        if identifiers and normalize(row.get('label') or '') in identifiers:s+=100
        result.append(s)
    return result
