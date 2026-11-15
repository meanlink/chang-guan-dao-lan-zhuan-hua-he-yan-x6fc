from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models

# 已有数据库上新增列的幂等补丁（全新库由 create_all 直接建出完整结构）
_JOB_PATCHES = {
    'quota_units': "ALTER TABLE jobs ADD COLUMN quota_units INTEGER NOT NULL DEFAULT 0",
    'quota_state': "ALTER TABLE jobs ADD COLUMN quota_state VARCHAR(20) NOT NULL DEFAULT 'none'",
    'idempotency_key': "ALTER TABLE jobs ADD COLUMN idempotency_key VARCHAR(80)",
}

# 幂等键的部分唯一索引：同一分析员的同一键只能有一单（NULL 不参与）
_IDEMPOTENCY_INDEX = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_creator_idempotency "
    "ON jobs (created_by, idempotency_key) WHERE idempotency_key IS NOT NULL"
)


def _patch_existing(engine):
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    with engine.begin() as conn:
        if 'jobs' in table_names:
            columns = {c['name'] for c in inspector.get_columns('jobs')}
            for name, ddl in _JOB_PATCHES.items():
                if name not in columns:
                    conn.execute(text(ddl))
            indexes = {ix['name'] for ix in inspector.get_indexes('jobs')}
            if 'uq_jobs_creator_idempotency' not in indexes:
                conn.execute(text(_IDEMPOTENCY_INDEX))


def migrate():
    Base.metadata.create_all(engine)
    _patch_existing(engine)


if __name__ == '__main__':
    migrate()
