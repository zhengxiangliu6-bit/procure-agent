"""Server-side provider configuration. Credentials never enter graph state."""
import os

def provider():
    return os.environ.get('AGENT_PROVIDER','anthropic')

def has_key():
    name='MODEL_API_KEY' if provider()=='openai' else 'ANTHROPIC_API_KEY'
    return bool(os.environ.get(name))

def build_model():
    selected=provider()
    if selected=='openai':
        from langchain.chat_models import init_chat_model
        key=os.environ.get('MODEL_API_KEY')
        if not key: raise ValueError('OpenAI 兼容模式需要 MODEL_API_KEY 环境变量')
        return init_chat_model(
            os.environ.get('AGENT_MODEL','glm-5.2'),
            model_provider='openai',api_key=key,
            base_url=os.environ.get('MODEL_BASE_URL','https://dashscope.aliyuncs.com/compatible-mode/v1'),
            temperature=0,max_tokens=4096,timeout=45,max_retries=1,
        )
    if selected=='anthropic':
        from langchain_anthropic import ChatAnthropic
        if not os.environ.get('ANTHROPIC_API_KEY'): raise ValueError('Anthropic 模式需要 ANTHROPIC_API_KEY 环境变量')
        return ChatAnthropic(model=os.environ.get('AGENT_MODEL','claude-sonnet-4-5'),temperature=0,max_tokens=1800,timeout=45,max_retries=1)
    raise ValueError('AGENT_PROVIDER 仅支持 openai / anthropic')
