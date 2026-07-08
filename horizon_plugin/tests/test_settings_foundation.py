from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "rca_copilot_horizon"


def test_settings_page_is_admin_only() -> None:
    source = (ROOT / "dashboards/rca_copilot/settings/views.py").read_text()

    assert "is_admin(request)" in source
    assert "HttpResponseForbidden" in source


def test_provider_list_rendering_and_actions_exist() -> None:
    template = (ROOT / "templates/rca_copilot/settings_provider_section.html").read_text()

    for expected in ["display_name", "provider_kind", "provider_type", "base_url", "model_name", "capabilities"]:
        assert expected in template
    for action in ["test", "activate", "disable", "rollback", "delete"]:
        assert f'value="{action}"' in template


def test_provider_form_validation_options_exist() -> None:
    template = (ROOT / "templates/rca_copilot/settings.html").read_text()

    for provider_type in ["llm", "embedding", "reranker", "vector_store"]:
        assert f'value="{provider_type}"' in template
    for provider_kind in ["ollama", "openai_compatible", "gemini", "anthropic", "custom_http", "chroma"]:
        assert f'value="{provider_kind}"' in template
    assert "required" in template


def test_masked_secret_and_unavailable_provider_messages_exist() -> None:
    settings = (ROOT / "templates/rca_copilot/settings.html").read_text()
    section = (ROOT / "templates/rca_copilot/settings_provider_section.html").read_text()

    assert "API keys are write-only" in settings
    assert "api_key_masked" in section
    assert "No AI provider configured. Deterministic RCA remains available." in section
    assert "AI provider unavailable. Ingestion, correlation, incident detection, and enrichment are unaffected." in section
