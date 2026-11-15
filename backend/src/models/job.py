from sqlalchemy import String, JSON, Double, ForeignKey, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='queued')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(String(1000), default='')
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[float] = mapped_column(Double)
    finished_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    # 每条参与分析的客流记录占一单位额度；预占后在成功时结算、失败或取消时退还
    quota_units: Mapped[int] = mapped_column(Integer, default=0)
    quota_state: Mapped[str] = mapped_column(String(20), default='none')
    # 客户端请求重试的幂等键：同一分析员同一键只建一单
    idempotency_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
