"""Thin adapter around the pinned FSRS implementation; no model-generated intervals."""
from datetime import datetime, timezone
from importlib.metadata import version
import hashlib
from fsrs import Card, Rating, Scheduler

VERSION = 'fsrs-' + version('fsrs')


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Timestamps must include a time zone')
    return parsed.astimezone(timezone.utc)


def default_settings():
    return {'schema_version': 1, 'scheduler_version': VERSION,
            'scheduler': Scheduler(enable_fuzzing=False).to_dict(), 'estimated_review_seconds': 60}


def initial(card_id, now):
    numeric_id = int(hashlib.sha256(card_id.encode()).hexdigest()[:12], 16)
    return Card(card_id=numeric_id, due=now).to_dict()


def advance(card, rating, now, duration, settings):
    if settings['scheduler_version'] != VERSION:
        raise ValueError('Scheduler version mismatch; migrate explicitly before reviewing')
    scheduler = Scheduler.from_dict(settings['scheduler'])
    source = Card.from_dict(card['scheduler'])
    if source.last_review and now <= source.last_review:
        raise ValueError('Review time must be later than the previous review')
    updated, log = scheduler.review_card(source, getattr(Rating, rating.title()),
                                         review_datetime=now, review_duration=round(duration * 1000))
    return updated.to_dict(), log.to_dict()
