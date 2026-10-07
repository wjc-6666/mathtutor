import math,statistics,collections
def relevant(row,target):
 return row['name']==target['book'] and row['page']==target['pdf_page'] and (not target.get('label') or row.get('label')==target['label'])
def score(rows,targets):
 positive=[t for t in targets if t.get('grade',3)>0]
 ranks=[next((i+1 for i,r in enumerate(rows) if relevant(r,t)),None) for t in positive];first=min([r for r in ranks if r] or [999999])
 values={f'Recall@{k}':sum(r is not None and r<=k for r in ranks)/len(ranks) for k in [5,10,20,50]}
 values.update({'Hit@1':float(first==1),'MRR@10':1/first if first<=10 else 0,'MRR@50':1/first if first<=50 else 0,'first_relevant_rank':first if first<=50 else None,'relevant_ranks':ranks})
 seen=set();gains=[]
 for r in rows[:10]:
  gain=0
  for i,t in enumerate(targets):
   if i not in seen and relevant(r,t):seen.add(i);gain=max(gain,2**t.get('grade',3)-1)
  gains.append(gain)
 ideal=sorted([2**t.get('grade',3)-1 for t in positive],reverse=True)[:10];idcg=sum(g/math.log2(i+2) for i,g in enumerate(ideal))
 values['nDCG@10']=sum(g/math.log2(i+2) for i,g in enumerate(gains))/idcg if idcg else 0
 negatives=[t for t in targets if t.get('grade',3)==0];values['hard_negative_in_top5']=float(any(relevant(r,t) for r in rows[:5] for t in negatives)) if negatives else None
 values['failure_class']='Recall Failure' if first>50 else 'Ranking Opportunity' if first>10 else 'Near Success' if first>5 else 'Success'
 return values
KEYS=['Hit@1','Recall@5','Recall@10','Recall@20','Recall@50','MRR@10','MRR@50','nDCG@10']
def aggregate(cases):
 return {'n':len(cases),**{k:round(statistics.mean(c[k] for c in cases),6) for k in KEYS},'failure_classes':dict(collections.Counter(c['failure_class'] for c in cases))}
def summarize(cases):
 return {'overall':aggregate(cases),'categories':{key:aggregate([c for c in cases if c['category']==key]) for key in sorted({c['category'] for c in cases})},'subjects':{key:aggregate([c for c in cases if c['subject']==key]) for key in sorted({c['subject'] for c in cases})},'source_styles':{key:aggregate([c for c in cases if c['source_style']==key]) for key in sorted({c['source_style'] for c in cases})}}
