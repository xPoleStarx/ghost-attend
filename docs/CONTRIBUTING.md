# Katkıda Bulunma

GhostAttend'e katkıda bulunmak isteyenler için rehber.

## Geliştirme Ortamı

```bash
# 1. Fork & clone
git clone https://github.com/your-fork/ghost-attend.git
cd ghost-attend

# 2. Poetry ile bağımlılıkları kur
pip install poetry
poetry install

# 3. Playwright browser kur
poetry run playwright install chromium

# 4. Development ortamı başlat
docker compose -f docker-compose.dev.yml up -d postgres redis

# 5. .env oluştur
cp .env.example .env
# → Test değerleri gir
```

## Kod Standartları

| Araç | Amaç | Komut |
|---|---|---|
| **Ruff** | Lint + Format | `make lint` |
| **Mypy** | Tip kontrolü | `make typecheck` |
| **Pytest** | Test | `make test` |

### Kurallar

- Tüm fonksiyonlara docstring yaz (Türkçe veya İngilizce)
- Type hint kullan (`def foo(x: int) -> str:`)
- Yeni özellik = yeni test
- Coverage %75 altına düşmemeli

## Branch Stratejisi

```
main          ← production (auto-deploy)
  └── develop ← entegrasyon
       ├── feature/xxx
       ├── fix/xxx
       └── docs/xxx
```

## PR Süreci

1. `develop`'dan branch oluştur
2. Değişiklikleri yap + test yaz
3. `make lint && make typecheck && make test`
4. PR aç → review bekle → merge

## Yeni DYS Stratejisi Ekleme

```python
# src/agent/strategies/obs_university.py
from src.agent.strategies.base import BaseDYSStrategy

class OBSUniversityStrategy(BaseDYSStrategy):
    async def get_login_hints(self) -> dict:
        return {
            "login_url": f"{self.dys_url}/login",
            "username_selector": "#email",
            "password_selector": "#password",
            "submit_selector": "#login-btn",
            "post_login_indicator": "Öğrenci Paneli",
        }

    async def get_course_navigation_hints(self, course_name: str) -> dict:
        return {
            "navigation_steps": ["Derslerim'e tıkla", f"'{course_name}' bul"],
            "course_search_url": f"{self.dys_url}/courses",
            "meeting_link_patterns": ["Canlı Ders", "Teams"],
        }
```

Sonra `base.py`'deki `detect_dys()` metoduna URL pattern ekle.
