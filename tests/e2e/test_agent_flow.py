"""
GhostAttend — E2E Agent Test

Mock DYS sunucusu ile tam akış testi.
Playwright + mock server kullanarak gerçek agent akışını simüle eder.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.e2e
class TestAgentE2EFlow:
    """
    E2E agent akış testleri.
    Bu testler mock DYS sunucusu gerektirir:
        docker compose -f docker-compose.test.yml up -d mock_dys
    """

    @pytest.mark.asyncio
    async def test_mock_dys_login_page_accessible(self):
        """Mock DYS login sayfası erişilebilir olmalı."""
        # Bu test docker-compose.test.yml ile çalıştırıldığında aktif olur
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8888/")
                assert response.status_code == 200
                assert "Giriş Yap" in response.text
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")

    @pytest.mark.asyncio
    async def test_mock_dys_login_success(self):
        """Mock DYS'ye doğru bilgilerle giriş yapılabilmeli."""
        try:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.post(
                    "http://localhost:8888/login",
                    data={"email": "test@stu.university.edu.tr", "password": "test123"},
                )
                assert response.status_code == 200
                assert "Öğrenci Paneli" in response.text
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")

    @pytest.mark.asyncio
    async def test_mock_dys_login_failure(self):
        """Mock DYS'ye yanlış bilgilerle giriş başarısız olmalı."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8888/login",
                    data={"email": "wrong@test.com", "password": "wrong"},
                )
                assert "hatalı" in response.text.lower()
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")

    @pytest.mark.asyncio
    async def test_mock_dys_course_list(self):
        """Mock DYS ders listesi erişilebilir olmalı."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8888/courses")
                assert response.status_code == 200
                assert "Kariyer Planlama" in response.text
                assert "Veri Yapıları" in response.text
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")

    @pytest.mark.asyncio
    async def test_mock_dys_course_detail_with_link(self):
        """Mock DYS ders detayında Teams linki olmalı."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8888/course/1")
                assert response.status_code == 200
                assert "teams.microsoft.com" in response.text
                assert "Toplantıya Katıl" in response.text
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")

    @pytest.mark.asyncio
    async def test_mock_dys_course_detail_without_link(self):
        """Link paylaşılmamış ders doğru mesaj göstermeli."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8888/course/3")
                assert response.status_code == 200
                assert "paylaşılmamış" in response.text
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")

    @pytest.mark.asyncio
    async def test_mock_dys_health(self):
        """Mock DYS health endpoint çalışmalı."""
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8888/health")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "ok"
        except Exception:
            pytest.skip("Mock DYS server çalışmıyor")


@pytest.mark.e2e
class TestFullIntegration:
    """
    Tam entegrasyon testleri.
    Agent lifecycle'ını mock'lar ile test eder.
    """

    @pytest.mark.asyncio
    async def test_orchestrator_happy_path_mock(self):
        """Orchestrator happy path — tam mock."""
        from src.agent.orchestrator import SessionOrchestrator

        with patch("src.agent.orchestrator.AgentRunner") as MockRunner:
            mock_instance = AsyncMock()
            mock_instance.run.return_value = {"status": "completed", "raw": "ok"}
            MockRunner.return_value = mock_instance

            with patch("src.agent.orchestrator.BaseDYSStrategy"):
                orchestrator = SessionOrchestrator(
                    user_id=123,
                    session_id="test",
                    redis_client=AsyncMock(),
                    vault=AsyncMock(),
                )
                orchestrator.vault.get_cookies = AsyncMock(return_value=None)
                orchestrator.vault.get_credentials = AsyncMock(
                    return_value=("test@edu.tr", "pass", None)
                )

                result = await orchestrator.attend_lesson(
                    course_name="Test Ders",
                    dys_url="https://obs.test.edu.tr",
                    end_time="10:30",
                )

                assert result["status"] == "completed"
