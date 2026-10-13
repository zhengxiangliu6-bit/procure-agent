"""Start live model service without storing credentials or rerunning older tests."""
import argparse
import getpass
import os
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8011);p.add_argument('--data',default='data-live-validation');args=p.parse_args()
    key=os.environ.get('MODEL_API_KEY') or getpass.getpass('API key (hidden): ')
    os.environ.update(AGENT_MODE='live',AGENT_PROVIDER='openai',AGENT_MODEL='glm-5.2',MODEL_BASE_URL='https://dashscope.aliyuncs.com/compatible-mode/v1',MODEL_API_KEY=key,LANGCHAIN_TRACING_V2='false',LANGSMITH_TRACING='false',PROCURE_DATA_DIR=str(Path(__file__).resolve().parents[1]/args.data))
    import uvicorn
    uvicorn.run('backend.main:app',host='127.0.0.1',port=args.port)

if __name__=='__main__':main()
