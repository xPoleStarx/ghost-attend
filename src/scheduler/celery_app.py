"""
GhostAttend — Celery Application

Celery konfigürasyonu ve worker başlatma.
Redis broker + backend kullanır.
architecture.md Section 11.1
"""

from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "ghostattend",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Bu app'in process-wide default/current olması kritik.
# Aksi halde `shared_task` veya farklı import sıralarında Celery default app'i
# AMQP (RabbitMQ) varsayılanına düşebilir ve `amqp://guest@127.0.0.1:5672`
# gibi hatalarla publish başarısız olur.
celery_app.set_default()
celery_app.set_current()

# Celery ayarları
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="Europe/Istanbul",
    enable_utc=True,

    # Worker ayarları
    worker_concurrency=2,           # Aynı anda max 2 agent
    worker_prefetch_multiplier=1,    # Prefetch yapmayı minimize et
    worker_max_tasks_per_child=10,   # Memory leak önleme

    # Task ayarları
    task_soft_time_limit=3600,       # 1 saat soft limit
    task_time_limit=3900,            # 1 saat 5dk hard limit
    task_acks_late=True,             # İşlem bitince acknowledge
    task_reject_on_worker_lost=True, # Worker ölünce task'ı tekrar kuyruğa al

    # Queue ayarları
    task_default_queue="agent_queue",
    task_routes={
        "src.scheduler.tasks.attend_lesson_task": {"queue": "agent_queue"},
        "src.scheduler.tasks.check_cookie_expiry_task": {"queue": "maintenance_queue"},
        "src.scheduler.tasks.health_check_task": {"queue": "maintenance_queue"},
    },

    # Beat schedule (periyodik görevler)
    beat_schedule={
        "check-cookie-expiry": {
            "task": "src.scheduler.tasks.check_cookie_expiry_task",
            "schedule": 86400.0,  # Her 24 saatte bir
        },
        "health-check": {
            "task": "src.scheduler.tasks.health_check_task",
            "schedule": 300.0,  # Her 5 dakikada bir
        },
    },
)

# Task modüllerini otomatik keşfet
celery_app.autodiscover_tasks(["src.scheduler"])
