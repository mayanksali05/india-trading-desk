from types import SimpleNamespace

from desk.llm import LLM, extract_json


def cfg(**kw):
    base = dict(provider="openai", base_url="https://example.invalid/v1", api_key_env="TEST_LLM_KEY",
                model="m", max_tokens=100)
    base.update(kw)
    return SimpleNamespace(**base)


def test_extract_json_tolerates_chatter():
    assert extract_json('Sure! {"verdict": "SKIP"} hope that helps') == {"verdict": "SKIP"}
    assert extract_json("no json here") is None


def test_missing_key_disables_ai(monkeypatch):
    monkeypatch.delenv("TEST_LLM_KEY", raising=False)
    llm = LLM(cfg())
    assert not llm.enabled and llm.json("s", "u") is None


def test_openai_compatible_provider(monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY", "k")
    llm = LLM(cfg())
    assert llm.enabled

    reply = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict": "WAIT"}'))])
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return reply

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert llm.json("system prompt", "user prompt") == {"verdict": "WAIT"}
    assert seen["messages"][0] == {"role": "system", "content": "system prompt"}


def test_api_error_fails_closed(monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY", "k")
    llm = LLM(cfg())

    def boom(**kwargs):
        raise RuntimeError("429 rate limited")

    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=boom)))
    assert llm.json("s", "u") is None


def test_local_ollama_needs_no_key():
    assert LLM(cfg(api_key_env="")).enabled
