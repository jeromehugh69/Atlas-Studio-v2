import pytest
from pydantic import ValidationError

from atlas_studio.config import Settings


def test_community_mode_rejects_external_integrations():
    with pytest.raises(ValidationError):
        Settings(mode="community", minio_enabled=True)


def test_additional_local_services_mode_requires_no_keys():
    settings = Settings(mode="integrations")
    assert settings.default_provider == "ollama"


def test_local_avatar_requires_no_key_or_integration_mode():
    settings = Settings(mode="community", avatar_local_enabled=True)
    assert settings.avatar_provider == "triposr-local"
