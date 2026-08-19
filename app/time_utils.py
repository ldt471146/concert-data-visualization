from datetime import datetime, timezone


def utcnow():
    """Return a naive UTC datetime for database fields configured without timezone."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
