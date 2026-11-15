from sqlalchemy import String, Integer, Double, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class QuotaAccount(Base):
    __tablename__ = 'quota_accounts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (
        CheckConstraint('total >= 0 AND reserved >= 0 AND used >= 0', name='quota_account_non_negative'),
        CheckConstraint('reserved + used <= total', name='quota_account_within_total'),
    )
class QuotaTransaction(Base):
    __tablename__ = 'quota_transactions'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    reserved_after: Mapped[int] = mapped_column(Integer)
    used_after: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(200), default='')
    created_at: Mapped[float] = mapped_column(Double)
    # 同一任务的同一类额度动作只允许一条流水：并发/重试/重复取消均不会重复扣退
    __table_args__ = (UniqueConstraint('job_id', 'kind', name='uq_quota_txn_job_kind'),)
