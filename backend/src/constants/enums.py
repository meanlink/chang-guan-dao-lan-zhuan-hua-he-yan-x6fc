from enum import Enum
class Role(str, Enum):
    admin = 'admin'
    analyst = 'analyst'
    viewer = 'viewer'
class JobStatus(str, Enum):
    queued = 'queued'
    running = 'running'
    completed = 'completed'
    failed = 'failed'
    cancelled = 'cancelled'
class QuotaState(str, Enum):
    # none：功能上线前的旧任务，不参与额度扣退
    none = 'none'
    held = 'held'           # 已预占，排队或执行中
    settled = 'settled'     # 成功结算，额度计入已用
    refunded = 'refunded'   # 失败或取消，已退还
