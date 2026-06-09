from app.config import Settings


def test_configured_inbound_listeners_defaults_to_single_api_listener() -> None:
    settings = Settings(
        llmproxy_api_host="0.0.0.0",
        llmproxy_api_port=8000,
        llmproxy_inbound_listeners=[],
    )

    listeners = settings.configured_inbound_listeners()

    assert listeners == [
        {
            "listener_id": "default",
            "name": "Default API Listener",
            "host": "0.0.0.0",
            "port": 8000,
            "protocol": "http",
            "published_host": "127.0.0.1",
            "published_port": 8000,
            "exposes_admin": True,
            "exposes_platform_api": True,
            "exposes_proxy": True,
        }
    ]


def test_resolve_inbound_listener_matches_by_listener_id_and_published_port() -> None:
    settings = Settings(
        llmproxy_api_host="0.0.0.0",
        llmproxy_api_port=8000,
        llmproxy_inbound_listeners=[
            {
                "listener_id": "public-api",
                "name": "Public API",
                "host": "0.0.0.0",
                "port": 8000,
                "published_host": "api.example.test",
                "published_port": 8000,
                "exposes_admin": True,
                "exposes_platform_api": True,
                "exposes_proxy": False,
            },
            {
                "listener_id": "internal-tools",
                "name": "Internal Tools",
                "host": "0.0.0.0",
                "port": 8001,
                "published_host": "127.0.0.1",
                "published_port": 8001,
                "exposes_admin": False,
                "exposes_platform_api": False,
                "exposes_proxy": True,
            },
        ],
    )

    assert settings.resolve_inbound_listener(listener_id="internal-tools")["port"] == 8001
    assert settings.resolve_inbound_listener(host="127.0.0.1", port=8001)["listener_id"] == "internal-tools"
    assert settings.admin_inbound_listeners()[0]["listener_id"] == "public-api"
    assert settings.platform_inbound_listeners()[0]["listener_id"] == "public-api"
    assert settings.proxy_inbound_listeners()[0]["listener_id"] == "internal-tools"


def test_configured_model_monitors_normalizes_frequency_mode_and_prompt() -> None:
    settings = Settings(
        llmproxy_model_monitors=[
            {
                "monitor_id": "anthropic-sonnet",
                "provider_key": "anthropic",
                "model_id": "claude-sonnet-4-6",
                "frequency_minutes": "1",
                "monitor_mode": "unknown",
                "enabled": True,
                "prompt": "",
            }
        ]
    )

    monitors = settings.configured_model_monitors()

    assert monitors == [
        {
            "monitor_id": "anthropic-sonnet",
            "label": "claude-sonnet-4-6",
            "provider_key": "anthropic",
            "model_id": "claude-sonnet-4-6",
            "enabled": True,
            "frequency_minutes": 5,
            "monitor_mode": "frontdoor_stream",
            "listener_id": None,
            "prompt": "Respond with OK.",
        }
    ]
