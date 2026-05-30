from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column, Mapped
from datetime import datetime, timezone


# This is the base class all your tables will inherit from.
# SQLAlchemy needs this to know "these classes are database tables".
class Base(DeclarativeBase):
    pass


# A mixin is like a snippet you can add to any class.
# This one just adds a created_at column automatically
# to any table that uses it — so you don't have to repeat it everywhere.
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )