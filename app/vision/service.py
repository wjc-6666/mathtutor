import base64,os,json
from app.llm.providers import request

def recognize(raw,mime):
    if os.getenv('LLM_PROVIDER','offline')!='api': raise ValueError('图片识别需要配置 API 和支持图片的 VISION_MODEL')
    model=os.getenv('VISION_MODEL','')
    if not model: raise ValueError('请配置 VISION_MODEL')
    content=[{'type':'text','text':'只识别数学题，不解答。返回 JSON 对象，字段 question（LaTeX 题目文本）、uncertain（模糊或不确定的字符数组）。不要猜测关键公式，无法辨认用 [?]。'}, {'type':'image_url','image_url':{'url':'data:'+mime+';base64,'+base64.b64encode(raw).decode()}}]
    result=request('LLM','chat/completions',{'model':model,'messages':[{'role':'user','content':content}]})['choices'][0]['message']['content']
    result=result.strip()
    if result.startswith('```'): result=result.split('\n',1)[1].rsplit('```',1)[0]
    try:
        parsed=json.loads(result)
        if not isinstance(parsed.get('question'),str) or not isinstance(parsed.get('uncertain'),list): raise ValueError()
        return dict(parsed,requires_confirmation=True)
    except (ValueError,TypeError): raise ValueError('识别结果格式无效，请重新上传或手动输入') from None
