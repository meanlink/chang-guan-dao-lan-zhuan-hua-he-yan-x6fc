import time, json, logging
from pathlib import Path
from sqlalchemy import select, update
from redis import Redis
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models import Job, Dataset, Report
from src.services.business import analyze
from src.services.reports import deliver
from src.services import quota
from src.services.audit import record
logging.basicConfig(level=logging.INFO)
def execute(job_id):
    with Session() as db:
        j=db.get(Job,job_id)
        if not j or j.status!='queued':return
        # 条件更新抢占任务：只有仍在排队的任务才能进入执行，避免多 worker/重复消息并发执行
        claimed=db.execute(
            update(Job).where(Job.id==job_id,Job.status=='queued')
            .values(status='running')).rowcount
        db.commit()
        if not claimed:return
    # 计算在事务外进行，长计算不持有数据库连接/行锁
    result=None; error=None
    try:
        with Session() as db:
            j=db.get(Job,job_id)
            d=db.get(Dataset,j.dataset_id)
            records, params = d.records, j.params
        result=analyze(records,params)
        json.dumps(result,allow_nan=False)
    except Exception as e:
        logging.exception('Analysis failed')
        error=str(e)[:990]
    with Session() as db:
        j=db.get(Job,job_id)
        # 计算期间任务可能已被分析员取消；取消生效后迟到结果一律不发布
        if j.status!='running':
            logging.info('Job %s no longer running (%s), discard result',job_id,j.status)
            return
        if error is None:
            # 条件更新：仅 running -> completed，保证取消与完成互斥
            done=db.execute(
                update(Job).where(Job.id==job_id,Job.status=='running')
                .values(status='completed',result=result,finished_at=time.time())).rowcount
            if done:
                quota.settle(db,j)  # 预占转已用；幂等
                record(db,'worker','job.completed',{'id':j.id,'quota_units':j.quota_units})
        else:
            failed=db.execute(
                update(Job).where(Job.id==job_id,Job.status=='running')
                .values(status='failed',error=error,finished_at=time.time())).rowcount
            if failed:
                quota.refund(db,j,quota.KIND_REFUND_FAIL,'执行失败，退还预占额度')
                record(db,'worker','job.failed',{'id':j.id,'error':error,'quota_units':j.quota_units})
        db.commit()
def tick():
    with Session() as db:
        # SQL 排队状态兜底：Redis 不可用或消息丢失时仍能被捞起
        queued=list(db.scalars(select(Job.id).where(Job.status=='queued').limit(3)))
    for job_id in queued:execute(job_id)
    with Session() as db:
        for r in db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=time.time())):
            d=deliver(db,r)
            if d:record(db,'worker','report.delivered',{'id':r.id,'delivery':d.id})
        db.commit()
def main():
    r=Redis.from_url(REDIS_URL,socket_timeout=3)
    # This Compose stack has a single worker. A crash must not strand its jobs.
    with Session() as db:
        # 预占后中断可恢复执行：running 任务回到 queued，额度保持预占，不重复扣
        for j in db.scalars(select(Job).where(Job.status=='running')):
            j.status='queued';record(db,'worker','job.recovered',{'id':j.id})
        db.commit()
    while True:
        Path('/tmp/heartbeat').touch()
        try:
            item=r.blpop('analysis:queue',timeout=1)
            if item:execute(int(item[1]))
            tick()
        except Exception:
            logging.exception('Worker retry');time.sleep(2)
if __name__=='__main__':main()
