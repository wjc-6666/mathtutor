import argparse,json
from app.rag.service import scan,retrieve
from app.llm.providers import chat_model
from app.prompts.tutor import messages
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['index','ask','index-v12','search-v12','benchmark-v12','index-v121','search-v121','promote-v121']);p.add_argument('question',nargs='?',default='一致收敛');p.add_argument('--subject',default='all');a=p.parse_args()
    if a.command=='index': print(json.dumps(scan(a.subject),ensure_ascii=False,indent=2))
    elif a.command=='index-v12':
        from app.rag.v12 import build
        print(json.dumps(build(),ensure_ascii=False,indent=2))
    elif a.command=='search-v12':
        from app.rag.v12 import search
        print(json.dumps(search(a.question,a.subject),ensure_ascii=False,indent=2))
    elif a.command=='benchmark-v12':
        from app.rag.benchmark import run
        print(json.dumps(run(),ensure_ascii=False,indent=2))
    elif a.command=='index-v121':
        from app.rag.v121 import build
        print(json.dumps(build(),ensure_ascii=False,indent=2))
    elif a.command=='search-v121':
        from app.rag.v121 import search
        print(json.dumps(search(a.question,a.subject),ensure_ascii=False,indent=2))
    elif a.command=='promote-v121':
        from app.rag.v121 import promote
        print(json.dumps(promote(a.question),ensure_ascii=False,indent=2))
    else:
        sources=retrieve(a.question,a.subject);print(chat_model().answer(messages(a.question,'detail',sources,[])))
        print(json.dumps(sources,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
