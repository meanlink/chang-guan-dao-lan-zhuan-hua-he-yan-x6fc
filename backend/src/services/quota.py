"""按分析员的核验额度服务。

口径：每条参与分析的客流记录占一单位额度。
- 排队前预占（hold）：余额不足直接拒绝，不建任务
- 成功后结算（settle）：预占转为已用
- 失败或取消退还（refund）：预占退回可用余额
所有额度动作写一条不可变流水；(job_id, kind) 唯一约束保证并发抢额、
重复取消、请求重试都不会重复扣退。
"""
import time
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from src.models import QuotaAccount, QuotaTransaction, User, Job
from src.constants.enums import QuotaState

# 流水动作类型
KIND_ALLOCATE = 'allocate'
KIND_HOLD = 'hold'
KIND_SETTLE = 'settle'
KIND_REFUND_FAIL = 'refund_failed'
KIND_REFUND_CANCEL = 'refund_cancelled'


def _dialect(db):
    return db.bind.dialect.name if db.bind else ''


def _lock_account(db, user_id):
    """读取并锁定额度账户；不存在则以 0 额度开户。"""
    q = select(QuotaAccount).where(QuotaAccount.user_id == user_id)
    if _dialect(db) in ('postgresql', 'mysql'):
        q = q.with_for_update()
    acc = db.scalar(q)
    if acc is None:
        # 并发首次开户依赖 user_id 唯一约束兜底
        acc = QuotaAccount(user_id=user_id, total=0, reserved=0, used=0,
                           updated_at=time.time())
        db.add(acc)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            q = select(QuotaAccount).where(QuotaAccount.user_id == user_id)
            if _dialect(db) in ('postgresql', 'mysql'):
                q = q.with_for_update()
            acc = db.scalar(q)
    return acc


def _txn_exists(db, job_id, kind):
    return db.scalar(select(QuotaTransaction.id)
                     .where(QuotaTransaction.job_id == job_id,
                            QuotaTransaction.kind == kind)) is not None


def _add_txn(db, *, user_id, job_id, kind, amount, acc, note=''):
    """写一条额度流水。同一 (job_id, kind) 已存在时返回 None（幂等）。"""
    if job_id is not None and _txn_exists(db, job_id, kind):
        return None
    txn = QuotaTransaction(
        user_id=user_id, job_id=job_id, kind=kind, amount=amount,
        balance_after=acc.total - acc.reserved - acc.used,
        reserved_after=acc.reserved, used_after=acc.used,
        note=note, created_at=time.time())
    db.add(txn)
    try:
        db.flush()
    except IntegrityError:
        # 并发下唯一约束 uq_quota_txn_job_kind 兜底：该动作已发生过
        db.rollback()
        return None
    return txn


def get_or_create_account(db, user_id):
    return _lock_account(db, user_id)


def summary(db, user_id):
    acc = get_or_create_account(db, user_id)
    return {'total': acc.total, 'reserved': acc.reserved, 'used': acc.used,
            'available': acc.total - acc.reserved - acc.used}


def ledger(db, user_id, limit=200):
    rows = db.scalars(
        select(QuotaTransaction).where(QuotaTransaction.user_id == user_id)
        .order_by(QuotaTransaction.id.desc()).limit(limit)).all()
    return [{'id': t.id, 'job_id': t.job_id, 'kind': t.kind, 'amount': t.amount,
             'balance_after': t.balance_after, 'reserved_after': t.reserved_after,
             'used_after': t.used_after, 'note': t.note, 'created_at': t.created_at}
            for t in rows]


def admin_overview(db):
    """负责人视角：全部分析员（admin/analyst）的额度与任务量。"""
    users = db.scalars(select(User).where(User.role.in_(('admin', 'analyst')))
                       .order_by(User.id)).all()
    out = []
    for u in users:
        acc = db.scalar(select(QuotaAccount).where(QuotaAccount.user_id == u.id))
        job_count = db.scalar(select(func.count()).select_from(Job)
                              .where(Job.created_by == u.id))
        active = db.scalar(select(func.count()).select_from(Job)
                           .where(Job.created_by == u.id,
                                  Job.status.in_(('queued', 'running'))))
        total = acc.total if acc else 0
        reserved = acc.reserved if acc else 0
        used = acc.used if acc else 0
        out.append({'user_id': u.id, 'email': u.email, 'name': u.name,
                    'role': u.role, 'total': total, 'reserved': reserved,
                    'used': used, 'available': total - reserved - used,
                    'jobs': job_count or 0, 'active_jobs': active or 0})
    return out


def allocate(db, target_user_id, amount, actor_email):
    """负责人分配（设置）总额度。新总额不得低于当前预占+已用。"""
    if not isinstance(amount, int) or amount < 0:
        raise HTTPException(422, '总额度必须是不小于 0 的整数')
    target = db.get(User, target_user_id)
    if target is None or target.role not in ('admin', 'analyst'):
        raise HTTPException(404, '分析员账户不存在')
    acc = _lock_account(db, target_user_id)
    locked = acc.reserved + acc.used
    if amount < locked:
        raise HTTPException(409, f'额度不得低于已预占与已用之和（当前 {locked} 单位）')
    delta = amount - acc.total
    acc.total = amount
    acc.updated_at = time.time()
    db.flush()
    _add_txn(db, user_id=target_user_id, job_id=None, kind=KIND_ALLOCATE,
             amount=delta, acc=acc, note=f'{actor_email} 分配总额度为 {amount}')
    return acc


def hold(db, user_id, job, units):
    """排队前预占。余额不足抛 409；成功则写入 hold 流水并挂到任务上。"""
    if units <= 0:
        raise HTTPException(422, '该批次没有可参与分析的客流记录，无法预占额度')
    if job.quota_state == QuotaState.held.value:
        return  # 已预占（重试场景），不重复扣
    acc = _lock_account(db, user_id)
    available = acc.total - acc.reserved - acc.used
    if available < units:
        raise HTTPException(409, f'核验额度不足：需要 {units} 单位，可用仅 {available} 单位')
    acc.reserved += units
    acc.updated_at = time.time()
    db.flush()
    txn = _add_txn(db, user_id=user_id, job_id=job.id, kind=KIND_HOLD,
                   amount=units, acc=acc, note='排队前预占')
    if txn is None:
        raise HTTPException(409, '该任务已预占过额度，请勿重复提交')
    job.quota_units = units
    job.quota_state = QuotaState.held.value
    db.flush()


def settle(db, job):
    """任务成功：预占转为已用。幂等——已结算/已退还的任务不再动作。"""
    if job.quota_state != QuotaState.held.value:
        return False
    if _txn_exists(db, job.id, KIND_SETTLE):
        job.quota_state = QuotaState.settled.value
        db.flush()
        return False
    acc = _lock_account(db, job.created_by)
    units = job.quota_units
    acc.reserved -= units
    acc.used += units
    acc.updated_at = time.time()
    db.flush()
    txn = _add_txn(db, user_id=job.created_by, job_id=job.id, kind=KIND_SETTLE,
                   amount=units, acc=acc, note='分析成功，额度结算')
    if txn is None:
        return False
    job.quota_state = QuotaState.settled.value
    db.flush()
    return True


def refund(db, job, kind, note):
    """任务失败或取消：预占退回可用。幂等——重复取消/重试只退一次。"""
    if job.quota_state != QuotaState.held.value:
        return False
    if _txn_exists(db, job.id, kind):
        job.quota_state = QuotaState.refunded.value
        db.flush()
        return False
    acc = _lock_account(db, job.created_by)
    units = job.quota_units
    acc.reserved -= units
    acc.updated_at = time.time()
    db.flush()
    txn = _add_txn(db, user_id=job.created_by, job_id=job.id, kind=kind,
                   amount=units, acc=acc, note=note)
    if txn is None:
        return False
    job.quota_state = QuotaState.refunded.value
    db.flush()
    return True
