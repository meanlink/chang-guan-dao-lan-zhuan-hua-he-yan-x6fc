import {quotas} from '../api/entities.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,date,notify,fmt} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {QuotaKind} from '../constants/enums.js';
function metricCards(s){
 const cards=[['总额度',s.total],['可用额度',s.available],['预占额度',s.reserved],['已用额度',s.used]];
 return '<div class="quota-metrics">'+cards.map(([k,v])=>'<div class="quota-card"><span>'+k+'</span><strong>'+fmt(v)+'</strong><small>单位：条客流记录</small></div>').join('')+'</div>';
}
function ledgerColumns(){
 return [{key:'created_at',label:'时间',render:v=>date(v)},{key:'kind',label:'动作',render:v=>esc(QuotaKind[v]||v)},{key:'job_id',label:'任务',render:v=>v?('#'+v):'—'},{key:'amount',label:'变动',render:v=>(v>=0?'+':'')+fmt(v)},{key:'balance_after',label:'变动后可用'},{key:'reserved_after',label:'变动后预占'},{key:'used_after',label:'变动后已用'},{key:'note',label:'说明'}];
}
export async function quotaPage(){
 const isAdmin=session.user.role==='admin';
 const [mine,accounts]=await Promise.all([quotas.mine(),isAdmin?quotas.accounts():Promise.resolve([])]);
 const rows=mine.ledger;
 const adminPanel=isAdmin?('<section class="panel"><div class="section-title"><h2>分析员额度分配</h2><span>负责人设置总额度</span></div><form id="allocate-form"><label>选择账户<select name="user_id" required>'+accounts.map(a=>'<option value="'+a.user_id+'">'+esc(a.name)+' · '+esc(a.email)+'</option>').join('')+'</select></label><label>新总额度（条）<input name="total" type="number" min="0" step="1" required placeholder="不低于当前预占+已用"></label><button type="submit" class="primary">分配总额度</button><p class="hint">总额度不得低于该账户已预占与已用之和；分配动作本身写入流水。</p></form><div class="table-wrap">'+table([{key:'name',label:'分析员'},{key:'email',label:'账号'},{key:'total',label:'总额度'},{key:'available',label:'可用'},{key:'reserved',label:'预占'},{key:'used',label:'已用'},{key:'active_jobs',label:'进行中任务'}],accounts)+'</div></section>'):'';
 return heading('06 / QUOTA LEDGER','核验额度与逐任务流水','每条参与分析的客流记录占一单位额度：排队前预占，成功后结算，失败或取消退还。旧任务保留且不补扣。')+metricCards(mine.summary)+adminPanel+'<section class="panel"><div class="section-title"><h2>我的额度流水</h2><span>'+mine.ledger.length+' 条</span></div><div class="table-wrap">'+table(ledgerColumns(),rows)+'</div><p class="hint">预占（hold）在排队/执行期间占用；成功转结算（settle）计入已用；失败或取消退还（refund）回可用。同一任务的每类动作仅一条流水。</p></section>';
}
export function bindQuota(refresh){
 const form=document.querySelector('#allocate-form');
 if(form)submit(form,async f=>{await quotas.allocate({user_id:Number(f.get('user_id')),total:Number(f.get('total'))});notify('总额度已分配');await refresh();});
}
