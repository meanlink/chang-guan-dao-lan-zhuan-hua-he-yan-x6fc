import time
from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services.business import metadata
from src.services import quota
def create(db, data, user):
    # 请求重试幂等：同一分析员 + 同一幂等键只建一单，直接返回原任务
    if data.idempotency_key:
        existing = db.scalar(select(Job).where(
            Job.created_by == user.id,
            Job.idempotency_key == data.idempotency_key))
        if existing:
            return existing, True
    if not db.get(Dataset, data.dataset_id): raise HTTPException(404, '数据批次不存在')
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    if set(data.params)-set(allowed): raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update(data.params)
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    d=db.get(Dataset,data.dataset_id)
    units=len(d.records)  # 每条参与分析的客流记录占一单位额度
    j=Job(name=data.name, dataset_id=data.dataset_id, params=params,
          created_by=user.id, created_at=time.time(), status='queued',
          idempotency_key=data.idempotency_key or None)
    db.add(j)
    try:
        db.flush()
    except IntegrityError:
        # 并发重试下 (created_by, idempotency_key) 唯一索引兜底：回查已建任务
        db.rollback()
        if data.idempotency_key:
            existing = db.scalar(select(Job).where(
                Job.created_by == user.id,
                Job.idempotency_key == data.idempotency_key))
            if existing:
                return existing, True
        raise HTTPException(409, '任务提交冲突，请重试')
    # 排队前预占：余额不足会抛 409，整笔事务回滚，任务不会落库
    quota.hold(db, user.id, j, units)
    return j, False
def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # SQL queued status is the durable fallback
def cancel(db, job, user):
    """分析员取消自己的排队/执行中任务；重复取消返回 False。"""
    if job.created_by != user.id:
        raise HTTPException(403, '只能取消本人发起的分析任务')
    if job.status not in ('queued', 'running'):
        return False
    job.status = 'cancelled'
    job.finished_at = time.time()
    job.error = '分析员取消任务'
    # 取消生效即退还预占；已结算/已退还时幂等不重复退
    quota.refund(db, job, quota.KIND_REFUND_CANCEL, '分析员取消，退还预占额度')
    return True
