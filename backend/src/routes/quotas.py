from fastapi import APIRouter, Depends
from src.config.database import get_db
from src.schemas.quota import QuotaAllocateInput
from src.middlewares.auth import current_user, admin_only
from src.services import quota
from src.services.audit import record
router = APIRouter(prefix='/quotas')
@router.get('/me')
def my_quota(db=Depends(get_db), u=Depends(current_user)):
    """当前用户的可用、预占、已用额度与逐任务流水。"""
    return {'summary': quota.summary(db, u.id), 'ledger': quota.ledger(db, u.id)}
@router.get('/accounts')
def accounts(db=Depends(get_db), u=Depends(admin_only)):
    """负责人查看全部分析员额度总览。"""
    return quota.admin_overview(db)
@router.get('/accounts/{user_id}/ledger')
def account_ledger(user_id: int, db=Depends(get_db), u=Depends(admin_only)):
    return quota.ledger(db, user_id, limit=500)
@router.post('/allocate')
def allocate(data: QuotaAllocateInput, db=Depends(get_db), u=Depends(admin_only)):
    """负责人为分析员分配（设置）总额度。"""
    acc = quota.allocate(db, data.user_id, data.total, u.email)
    record(db, u.email, 'quota.allocate',
           {'user_id': data.user_id, 'total': data.total})
    db.commit()
    return {'user_id': acc.user_id, 'total': acc.total,
            'reserved': acc.reserved, 'used': acc.used,
            'available': acc.total - acc.reserved - acc.used}
