def test_openai_compatible_parameters(monkeypatch):
    import langchain.chat_models
    from backend.model_config import build_model,has_key
    monkeypatch.setenv('AGENT_PROVIDER','openai')
    monkeypatch.setenv('MODEL_API_KEY','test-placeholder')
    monkeypatch.setenv('AGENT_MODEL','glm-5.2')
    monkeypatch.setenv('MODEL_BASE_URL','https://dashscope.aliyuncs.com/compatible-mode/v1')
    seen={}
    def fake(model,**kwargs): seen.update(model=model,**kwargs);return 'model'
    monkeypatch.setattr(langchain.chat_models,'init_chat_model',fake)
    assert build_model()=='model' and has_key()
    assert seen['model']=='glm-5.2' and seen['model_provider']=='openai'
    assert seen['base_url']=='https://dashscope.aliyuncs.com/compatible-mode/v1'
    assert seen['api_key']=='test-placeholder'

def test_missing_compatible_key(monkeypatch):
    import pytest
    from backend.model_config import build_model,has_key
    monkeypatch.setenv('AGENT_PROVIDER','openai');monkeypatch.delenv('MODEL_API_KEY',raising=False)
    assert not has_key()
    with pytest.raises(ValueError,match='MODEL_API_KEY'): build_model()
