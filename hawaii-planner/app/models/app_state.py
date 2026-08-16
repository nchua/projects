"""Single-row global version counter — bumped by every mutation, polled by clients."""
from sqlalchemy import BigInteger, Column, Integer

from app.core.database import Base


class AppState(Base):
    __tablename__ = "app_state"

    id = Column(Integer, primary_key=True, default=1)
    version = Column(BigInteger, nullable=False, default=1)
