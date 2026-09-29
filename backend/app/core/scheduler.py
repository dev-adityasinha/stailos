"""Background scheduler for periodic jobs.

APScheduler runs in-process (a single Python thread) — no Redis/Celery broker
needed at this scale. `run_due_reminders_for_all_users` replaces the old
lazy/on-request reminder generation with a real periodic sweep so overdue
tasks and upcoming events get surfaced (and emailed) even if nobody opens the
notifications panel. `run_event_reminders` sweeps published events starting
within 48h and reminds registrants at the 48h/24h marks. `run_post_event_followups`
sweeps investor events whose end_at has passed and dispatches attended/no-show
follow-up sequences.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings

logger = logging.getLogger("crm.scheduler")

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.reminder_scheduler_enabled or _scheduler is not None:
        return

    from app.modules.events.service import run_event_reminders, run_post_event_followups
    from app.modules.notifications.service import run_due_reminders_for_all_users

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        run_due_reminders_for_all_users,
        "interval",
        minutes=settings.reminder_interval_minutes,
        id="due_reminders",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
    )
    _scheduler.add_job(
        run_post_event_followups,
        "interval",
        minutes=settings.event_followup_interval_minutes,
        id="event_followups",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )
    _scheduler.add_job(
        run_event_reminders,
        "interval",
        minutes=settings.event_followup_interval_minutes,
        id="event_reminders",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started (reminders every %sm, event follow-ups every %sm)",
        settings.reminder_interval_minutes, settings.event_followup_interval_minutes,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
