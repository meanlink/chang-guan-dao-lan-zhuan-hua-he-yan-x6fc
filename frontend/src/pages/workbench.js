import {datasets,jobs,quotas} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify,fmt} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
export async function workbench(){
 const [ds,q]=await Promise.all([datasets.list(),quotas.mine()]);
 workspace.datasets=ds;workspace.quota=q.summary;const m=workspace.meta;
 const s=q.summary;
 const quotaBar='<div class="quota-strip"><div><span>可用额度</span><strong>'+fmt(s.available)+'</strong></div><div><span>预占中</span><strong>'+fmt(s.reserved)+'</strong></div><div><span>已用</span><strong>'+fmt(s.used)+'</strong></div><div><span>总额度</span><strong>'+fmt(s.total)+'</strong></div><a class="text-link" href="#/quotas">额度流水 ↗</a></div>';
 const canWrite=session.user.role!=='viewer'&&workspace.datasets.length>0;
 return heading('03 / ANALYSIS LAB',m.workbench_title,'选择业务批次和分析口径。每条参与分析的客流记录预占一单位核验额度，成功结算、失败或取消退还。')+quotaBar+'<div class="workbench-grid"><section class="panel"><form id="job-form"><label>分析任务名称<input name="name" required minlength="2" value="'+esc(m.name)+' · 复核试算"></label><label>数据批次<select name="dataset_id" required>'+workspace.datasets.map(d=>'<option value="'+d.id+'" data-rows="'+d.rows+'">'+esc(d.name)+' · '+d.rows+' 条</option>').join('')+'</select></label><p class="hint" id="quota-hint">本次将预占 <strong id="need-units">0</strong> 单位额度（按所选批次记录数）。</p><div class="parameter-grid">'+m.parameters.map(p=>'<label>'+esc(p.label)+(p.type==='select'?'<select name="param-'+esc(p.key)+'">'+p.options.map(o=>'<option value="'+esc(o.value)+'" '+(o.value==p.default?'selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>':'<input type="number" step="any" name="param-'+esc(p.key)+'" value="'+esc(p.default)+'" min="'+esc(p.min??'')+'" max="'+esc(p.max??'')+'" required>')+'</label>').join('')+'</div><button type="submit" class="primary" '+(!canWrite?'disabled':'')+'>'+esc(m.action_label||'执行分析')+' ↗</button><p class="hint">提交即预占额度并入队；观察员只有读取权限。余额不足时请求会被拒绝，不会建单。</p></form></section><section class="method-sheet"><p class="eyebrow">METHOD / BUSINESS RULE</p><h2>'+esc(m.method)+'</h2><p>'+esc(m.tagline)+'</p><h3>业务判读边界</h3><ul>'+m.limitations.map(v=>'<li>'+esc(v)+'</li>').join('')+'</ul><div class="method-trace"><span>输入</span><strong>'+esc(m.dataset_name)+'</strong><span>输出</span><strong>可复核结果 / 参数版本 / 分发归档</strong></div></section></div>';
}
export function bindWorkbench(){
 const form=document.querySelector('#job-form');
 const select=document.querySelector('[name=dataset_id]');
 const need=document.querySelector('#need-units');
 const hint=document.querySelector('#quota-hint');
 const submitBtn=form.querySelector('button.primary');
 const readOnly=session.user.role==='viewer';
 const sync=()=>{
   const rows=Number(select.selectedOptions[0]?.dataset.rows||0);
   need.textContent=fmt(rows);
   const s=workspace.quota;
   const short=!readOnly&&s&&rows>s.available;
   hint.classList.toggle('short',Boolean(short));
   if(!readOnly)submitBtn.disabled=short;
 };
 select?.addEventListener('change',sync);sync();
 submit(form,async f=>{
   const params={};for(const p of workspace.meta.parameters){const value=f.get('param-'+p.key);params[p.key]=p.type==='number'?Number(value):value;}
   const idempotency_key=(crypto.randomUUID?crypto.randomUUID():(Date.now()+'-'+Math.random().toString(16).slice(2)));
   const j=await jobs.create({name:f.get('name'),dataset_id:Number(f.get('dataset_id')),params,idempotency_key});
   workspace.selectedJob=j.id;notify('分析任务已提交，额度已预占');location.hash='#/results/'+j.id;
 });
}
