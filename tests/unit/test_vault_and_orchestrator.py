import pytest

from src.security.encryption import CredentialVault
from src.core.exceptions import CredentialDecryptFailed
from src.agent.orchestrator import SessionOrchestrator


def test_credential_vault_key_mismatch_raises_specific_error():
    user_id = 123456
    vault1 = CredentialVault("MASTER_KEY_1")
    vault2 = CredentialVault("MASTER_KEY_2")

    ciphertext = vault1.encrypt(user_id, "secret-password")

    with pytest.raises(CredentialDecryptFailed):
        _ = vault2.decrypt(user_id, ciphertext)


class DummyNotifier:
    def __init__(self):
        self.last_error = None

    async def send_error(self, user_id: int, error_code: str, details: str = ""):
        self.last_error = (user_id, error_code, details)
        return True


class DummyVault:
    async def get_cookies(self, user_id: int):
        return None

    async def get_credentials(self, user_id: int):
        raise CredentialDecryptFailed("test")


class DummyRepo:
    async def update_status(self, session_id, status: str, failure_reason: str | None = None):
        return


@pytest.mark.asyncio
async def test_orchestrator_handles_decrypt_failure_with_specific_status(monkeypatch):
    notifier = DummyNotifier()
    vault = DummyVault()
    repo = DummyRepo()

    orchestrator = SessionOrchestrator(
        user_id=111,
        session_id="00000000-0000-0000-0000-000000000000",
        redis_client=None,
        notifier=notifier,
        vault=vault,
        session_repo=repo,
    )

    result = await orchestrator.attend_lesson(
        course_name="Test Ders",
        dys_url="https://example.com",
        end_time="23:59",
    )

    assert result["status"] == "error"
    assert result["error"] == "credential_decrypt_failed"
    assert notifier.last_error is not None
    assert notifier.last_error[1] == "CREDENTIAL_ERROR_KEY_MISMATCH"

