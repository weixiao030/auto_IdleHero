import React, {useEffect,useState,useRef} from 'react';
import {createRoot} from 'react-dom/client';
import {FluentProvider,webLightTheme,webDarkTheme,createLightTheme,createDarkTheme,Button,Switch,Spinner,Input,Tooltip,Checkbox} from '@fluentui/react-components';
import {ArrowTrendingLines24Regular,Grid24Regular,Settings24Regular,History24Regular,Play20Filled,Pause20Filled,WeatherSunny20Regular,WeatherMoon20Regular,ChevronRight16Regular,CheckmarkCircle16Regular,ArrowSync20Regular,ShieldCheckmark20Regular,Search20Regular,ArrowUp16Regular,ArrowDown16Regular} from '@fluentui/react-icons';
import './style.css';

const brand={10:'#04110c',20:'#0c241a',30:'#113a29',40:'#164b35',50:'#1b5d42',60:'#206f50',70:'#27815e',80:'#30936d',90:'#4aa37f',100:'#66b392',110:'#83c2a5',120:'#9ed0b8',130:'#b9decd',140:'#d1ebe0',150:'#e6f5ee',160:'#f5fbf8'};
const themes={light:{...createLightTheme(brand),colorBrandBackground:'#206f50',colorBrandBackgroundHover:'#1b5d42',colorBrandBackgroundPressed:'#164b35',colorCompoundBrandBackground:'#206f50'},dark:{...createDarkTheme(brand),colorBrandBackground:'#9bd3b2',colorBrandBackgroundHover:'#b9decd',colorBrandBackgroundPressed:'#83c2a5',colorNeutralForegroundOnBrand:'#14271b',colorCompoundBrandBackground:'#9bd3b2'}};
const fmt=(n)=>new Intl.NumberFormat('zh-CN',{notation:Number(n)>999999?'compact':'standard',maximumFractionDigits:1}).format(Number(n)||0);
const clock=(t)=>new Date(t*1000).toLocaleTimeString('zh-CN',{hour12:false});
const iconProps={fontSize:20};
// Native workbench inspired by the supplied Fanxiu reference. Fluent controls stay official.
// DESIGN_VARIANCE=4, MOTION_INTENSITY=2, VISUAL_DENSITY=6.
const moduleInfo={
 mainline:['探索与领取','使用原生自动推图，持续观察主线与战斗结算。'],
 loot:['探索与领取','背包有空间时领取待开宝箱，领取后交由鉴定与换装接续。'],
 mail:['探索与领取','同步邮件并领取可容纳的奖励。'],
 identify:['装备与魔石','批量鉴定背包内未鉴定装备，供换装策略重新比较。'],
 equipment:['装备与魔石','按原生装备条件和战力比较换装，保留其他角色的当前装备。'],
 stones:['装备与魔石','比较魔石输出与冷却，择优穿戴并合成未装备的可用魔石。'],
 inventory:['装备与魔石','先完成换装与图鉴安排，再回收符合品质与保护规则的剩余装备。'],
 enhancement:['装备与魔石','按原生报价强化合适装备，维护完成后自动恢复穿戴。'],
 socket:['装备与魔石','为符合条件的装备镶嵌现有宝石，完成后恢复穿戴。'],
 formation:['角色与成长','按解锁阵位与已拥有角色补齐队伍，满足条件时招募角色。'],
 skills:['角色与成长','按技能树原生条件学习与升级，已学辅助技能由游戏自动生效。'],
 runes:['角色与成长','按优先级选择可支付星座节点，阵位等关键解锁优先。'],
 craft:['角色与成长','根据角色等级与现有装备选择可用配方，避免制造落后阶段。'],
 collection:['角色与成长','使用未受保护的剩余物品登记图鉴，积累永久加成。'],
 dungeon:['探索与领取','按实际开放层数、钥匙储备与挑战间隔安排副本。'],
 consumables:['探索与领取','沿用原生低血量补给与现有经验卷轴，按库存自动启用。']
};
const fields={
 equipment_improvement_ratio:['最低换装提升','战力提升达到此比例才替换当前装备。',0,50,.5,100,'%'],
 stone_improvement_ratio:['最低魔石提升','按输出与冷却计算的提升门槛。',0,50,.5,100,'%'],
 craft_target_grade:['同阶段目标品质','达到目标品质后转向更高等级配方。',1,5,1,1,'阶'],
 dungeon_interval_seconds:['挑战间隔','一次挑战后，至少等待此时长再安排。',60,86400,60,1,'秒'],
 dungeon_key_reserve:['钥匙保留数量','先保留此数量，再计算可挑战层数。',0,1000000,1,1,'把'],
 spare_copies:['额外备用装备','默认不额外囤装备；已穿戴、双戒指槽和下一阶段装备仍会保护。',0,5,1,1,'件'],
 maintenance_interval_seconds:['装备维护间隔','同一件装备恢复穿戴后，再次维护的最短间隔。',30,86400,30,1,'秒'],
 tick_seconds:['成长操作间隔','完成一项操作后重新评估优先级。',3,60,1,1,'秒'],
 gold_reserve_min:['最低金币储备','与比例储备共同生效，取较高值。',0,1000000000,1,1,'金币'],
 gold_reserve_ratio:['金币保留比例','所有消费策略共用的保留预算。',0,80,1,100,'%'],
 performance_fps:['目标帧率','只限制画面帧率，战斗与收益仍由游戏结算。',10,60,1,1,'FPS']
 ,capacity_trigger_ratio:['容量联动阈值','装备背包、魔石背包或宝箱达到此占用比例时，优先扩容星座及其前置节点。',50,100,1,100,'%']
};
const moduleFields={equipment:['equipment_improvement_ratio'],stones:['stone_improvement_ratio'],craft:['craft_target_grade'],inventory:['spare_copies'],runes:['capacity_trigger_ratio'],enhancement:['maintenance_interval_seconds'],dungeon:['dungeon_interval_seconds','dungeon_key_reserve']};
const priorityNames={exp:'经验',gold:'金币',power:'战力',chest:'宝箱'};
function App(){
 const [data,setData]=useState(null),[fault,setFault]=useState(''),[feedback,setFeedback]=useState(''),[tab,setTab]=useState('strategy'),[busy,setBusy]=useState(false);
 const [mode,setMode]=useState(()=>localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));
 const revision=useRef(0),writeChain=useRef(Promise.resolve()),pending=useRef(0);
 useEffect(()=>{let alive=true,timer,controller;
  async function update(){controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),8000);const stamp=revision.current;try{const r=await fetch('/api/state',{signal:controller.signal});if(!r.ok)throw Error();const d=await r.json();if(alive&&stamp===revision.current){setData(d);setFault('')}}catch(e){if(alive)setFault('助手网页服务未响应，请确认助手仍在运行。页面会继续刷新状态，不会启动或重启游戏。')}finally{clearTimeout(timeout);if(alive)timer=setTimeout(update,document.hidden?15000:3000)}}
  update();return()=>{alive=false;controller?.abort();clearTimeout(timer)};
 },[]);
 function post(path,body={}){
  const instance=data?.instance_id;
  revision.current++;pending.current++;setBusy(true);setFeedback('');
  const task=writeChain.current.then(async()=>{const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':data.csrf},body:JSON.stringify({...body,_instance_id:instance}),signal:AbortSignal.timeout(10000)});const result=await r.json();if(!r.ok)throw Error(result.error||'操作未保存，请重试。');const state=await fetch('/api/state',{signal:AbortSignal.timeout(10000)});if(!state.ok)throw Error('操作已提交，正在等待服务刷新。');setData(await state.json());setFault('');setFeedback(path==='config'?'当前实例的参数已保存，下一轮生效。':path==='inspect'?'已安排当前实例巡检，结果见运行记录。':path==='config/open'?'已打开当前实例配置，修改后每 5 秒自动重载。':path==='connection/select'?'已切换查看实例，其他实例继续按各自设置运行。':path==='connection/refresh'?'已安排重新检测本机和沙盒实例。':'运行状态已更新。');return result;});
  writeChain.current=task.catch(()=>{});
  return task.then(()=>true).catch(e=>{setFault(e.message);return false}).finally(()=>{pending.current--;setBusy(pending.current>0)});
 }
 function theme(){const next=mode==='light'?'dark':'light';setMode(next);localStorage.setItem('theme',next)}
 const nav=[['strategy','成长策略',ArrowTrendingLines24Regular],['overview','远征总览',Grid24Regular],['settings','基础参数',Settings24Regular],['activity','运行记录',History24Regular]];
 return <FluentProvider key={mode} theme={themes[mode]}><div className={'app '+mode}>
  <header className="topbar"><div className="topbar-inner"><div className="workbench-brand"><span className="brand-mark"><ArrowTrendingLines24Regular/></span><strong>桌面勇者 <small>自动远征</small></strong></div><span className="local-label">{data?.connection?.sandbox?`沙盒 · ${data.connection.sandbox}`:'本机连接'}</span><div className="header-actions"><span className={'connection '+(data?.connected&&!fault?'online':'')}><i/>{data?.connected&&!fault?'游戏已连接':'等待连接'}</span><Tooltip content={mode==='light'?'切换深色':'切换浅色'} relationship="label"><Button appearance="subtle" icon={mode==='light'?<WeatherMoon20Regular/>:<WeatherSunny20Regular/>} onClick={theme}/></Tooltip></div></div></header>
  <main><div className="page-heading"><div><h1>桌面勇者自动化工作台</h1><p>连接当前队伍，让推图、装备与成长有序进行。</p></div><div className="main-actions"><Button icon={<ArrowSync20Regular/>} disabled={!data||busy||!!fault} onClick={()=>post('inspect')}>立即巡检</Button><Button appearance="primary" icon={data?.running?<Pause20Filled/>:<Play20Filled/>} disabled={!data||busy||!!fault} onClick={()=>post(data.running?'pause':'run')}>{data?.running?'暂停自动成长':'开始自动成长'}</Button></div></div>
  {fault&&<div className="notice error" role="alert">{fault}</div>}
  {feedback&&<div className="notice saved" role="status">{feedback}</div>}
  {!data?<div className="loading" aria-busy="true"><div className="skeleton-summary"/><div className="skeleton-cards">{[0,1,2,3].map(x=><div key={x}/>)}</div><p>正在读取游戏与成长策略</p></div>:<>
   {data.error&&<div className="notice error" role="alert">{data.error}</div>}
   <Connections data={data} busy={busy||!!fault} post={post}/>
   <Summary data={data}/>
   <nav className="tabs" aria-label="助手页面">{nav.map(([key,label,Icon])=><button key={key} className={tab===key?'selected':''} aria-current={tab===key?'page':undefined} onClick={()=>setTab(key)}><Icon/>{label}</button>)}</nav>
   {tab==='strategy'&&<Strategy data={data} busy={busy||!!fault} post={post} setTab={setTab}/>}
   {tab==='overview'&&<Overview data={data}/>}
   {tab==='activity'&&<section className="panel"><div className="panel-title"><h2>运行记录</h2><span className="quiet">已核验 {fmt(data.success_count)} 项操作</span></div><Logs rows={data.logs} full/></section>}
   {tab==='settings'&&<Settings data={data} busy={busy||!!fault} post={post}/>}
   <footer><span>桌面勇者自动远征 · 本机运行</span><span>F8 总开关 · F9 分解 · F10 换装</span><span>配置每 5 秒重载 · 运行 {Math.floor(data.uptime/60)} 分钟</span></footer>
  </>}</main></div></FluentProvider>
}
function Connections({data:d,busy,post}){
 const rows=d.instances||[],selected=rows.find(x=>x.id===d.instance_id),connected=d.connected;
 return <section className={'connection-panel '+(connected?'connected':'disconnected')} aria-label="实例连接管理">
  <div className="connection-title" role={connected?'status':'alert'}><strong>{connected?'已连接当前游戏实例':'当前游戏尚未连接'}</strong><span>{selected?.sandbox?`沙盒 ${selected.sandbox}`:'本机'} · PID {d.connection?.pid||'未运行'} · 自动重连{d.config.auto_relaunch?'已开启':'已关闭'}</span></div>
  <p>{connected?'下方设置与操作只作用于当前实例。其他已开启的实例独立运行。':'请先在本机或目标沙盒内启动游戏并完成登录，再点重新检测。自动重连关闭时助手不会自动启动或重启游戏。'}</p>
  {d.manager_error&&<p role="alert" className="field-error">{d.manager_error}</p>}
  <div className="instance-list">{rows.map(row=><button key={row.id} disabled={busy} className={'instance-card '+(row.id===d.instance_id?'selected':'')} aria-pressed={row.id===d.instance_id} onClick={()=>post('connection/select',{instance_id:row.id})}><strong>{row.sandbox?`沙盒 ${row.sandbox}`:'本机'} <small>PID {row.pid||'未运行'}</small></strong><span>{row.connected?'● 已连接':'○ 等待连接'} · {row.running?'自动化开启':'自动化暂停'}</span><small>{row.status}</small></button>)}</div>
  <div className="connection-controls"><Button disabled={busy} icon={<ArrowSync20Regular/>} onClick={()=>post('connection/refresh')}>重新检测本机与沙盒</Button>{selected&&!d.connection?.pid&&<Button disabled={busy} onClick={()=>post('connection/launch')}>手动启动此环境的游戏</Button>}<span>{rows.filter(x=>x.connected).length} / {rows.length} 个实例已连接 · F8 至 F10 只控制当前选中实例</span></div>
 </section>
}
function Summary({data:d}){const leader=d.team.find(x=>x.active);return <section className="character-panel" aria-label="当前队伍"><div className="character-heading"><span className="hero-avatar active">{leader?.name.slice(0,1)||'勇'}</span><div><h2>{leader?.name||'等待角色初始化'}</h2><p>{d.map.map_name||'正在同步关卡'} · {d.team.filter(x=>x.active).length} / {d.formation_limit} 人上阵</p></div><span className={'status-chip '+(d.running?'active':'')}>{d.status}</span></div><div className="stat-strip"><Stat label="角色等级" value={d.player.level||'待同步'} prefix="Lv."/><Stat label="队伍战力" value={fmt(d.team.filter(x=>x.active).reduce((a,x)=>a+x.power,0))}/><Stat label="金币储备" value={fmt(d.gold)}/><Stat label="装备背包" value={`${d.bag.used} / ${d.bag.capacity}`}/><Stat label="本次累计核验" value={fmt(d.success_count)}/></div></section>}
function NumericParameter({name,config,post,busy}){
 const [label,note,min,max,step,scale,unit]=fields[name];
 const display=String(Number((config[name]*scale).toFixed(4)));
 const [draft,setDraft]=useState(display),[error,setError]=useState(''),[saving,setSaving]=useState(false);const editing=useRef(false);
 useEffect(()=>{if(!editing.current&&!saving)setDraft(display)},[display,saving]);
 async function commit(event){editing.current=false;const raw=event.currentTarget.value,value=Number(raw);if(raw.trim()===''||!Number.isFinite(value)||value<min||value>max||!event.currentTarget.validity.valid){setError(`请输入 ${min} 至 ${max}，步长 ${step}。`);return}setError('');if(value/scale===config[name])return;setSaving(true);const ok=await post('config',{[name]:value/scale});if(!ok)setError('保存失败，保留输入以便重试。');setSaving(false)}
 return <div className="parameter"><label htmlFor={name}>{label}</label><div className="parameter-input"><Input id={name} type="number" min={min} max={max} step={step} value={draft} disabled={saving} aria-invalid={!!error} aria-describedby={name+'-help'} onFocus={()=>{editing.current=true}} onChange={(_,v)=>{setDraft(v.value);setError('')}} onBlur={commit} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();if(e.key==='Escape'){e.currentTarget.value=display;setDraft(display);setError('');e.currentTarget.blur()}}}/><span>{unit}</span></div><p id={name+'-help'} className={error?'field-error':''}>{error||(saving?'正在保存…':note)}</p></div>
}
function PriorityParameters({config,busy,post}){const order=config.rune_priority||['exp','gold','power','chest'];function move(index,offset){const next=[...order];[next[index],next[index+offset]]=[next[index+offset],next[index]];post('config',{rune_priority:next})}return <div className="priority-parameters"><span className="parameter-label">星座优先级</span><ol>{order.map((key,index)=><li key={key}><span className="priority-rank">{index+1}</span><strong>{priorityNames[key]}</strong><Button appearance="subtle" size="small" icon={<ArrowUp16Regular/>} aria-label={`提高${priorityNames[key]}优先级`} disabled={busy||index===0} onClick={()=>move(index,-1)}/><Button appearance="subtle" size="small" icon={<ArrowDown16Regular/>} aria-label={`降低${priorityNames[key]}优先级`} disabled={busy||index===order.length-1} onClick={()=>move(index,1)}/></li>)}</ol></div>}
function Protection({data:d,busy,post,standalone=false}){const grades=d.config.salvage_grades||[];return <div className={'protection-content '+(standalone?'standalone':'')}><div className="protection-fixed"><ShieldCheckmark20Regular/><div><strong>Steam 可交易物品始终保护</strong><p>已装备、锁定、仓库、未鉴定和已投入强化的装备一并保留；Steam 识别未完成时等待。</p></div></div><fieldset><legend>允许分解的品质</legend><div className="quality-options">{Array.from({length:10},(_,i)=>i+1).map(grade=><Checkbox key={grade} checked={grades.includes(grade)} disabled={busy} label={d.grade_names?.[String(grade)]||`品质 ${grade}`} onChange={(_,v)=>post('config',{salvage_grades:v.checked?[...grades,grade]:grades.filter(x=>x!==grade)})}/>)}</div></fieldset><p className="parameter-note">未勾选的品质不会分解。每次报价与实际分解前重新检查。</p></div>}
function Strategy({data:d,busy,post,setTab}){
 const [search,setSearch]=useState(''),[group,setGroup]=useState('全部'),[protection,setProtection]=useState(false);
 const groups=['全部','探索与领取','装备与魔石','角色与成长','性能与显示'];
 const cardOrder=["loot","identify","stones","equipment","runes","inventory","mainline","formation","skills","craft","enhancement","socket","collection","mail","dungeon","consumables"];
 const query=search.trim().toLocaleLowerCase();
 const displayGroup=group==='全部'||group==='性能与显示';
 const showPerformance=displayGroup&&'性能模式 目标帧率 fps'.includes(query);
 const showEffects=displayGroup&&'极简特效 图层'.includes(query);
 const modules=[...d.modules].sort((a,b)=>cardOrder.indexOf(a.key)-cardOrder.indexOf(b.key)).filter(m=>(group==='全部'||moduleInfo[m.key]?.[0]===group)&&[m.name,moduleInfo[m.key]?.[1],...(moduleFields[m.key]||[]).map(key=>fields[key][0])].join(' ').toLocaleLowerCase().includes(query));
 return <><div className="section-title"><div><h2>成长安排</h2><p>参数就在功能开关下方，修改后自动保存。</p></div><span className="quiet">{d.modules.filter(m=>m.enabled).length} / {d.modules.length} 项已开启</span></div><div className="function-tools"><Input contentBefore={<Search20Regular/>} value={search} onChange={(_,v)=>setSearch(v.value)} placeholder="搜索功能或参数" aria-label="搜索功能或参数"/><div className="group-filter" aria-label="筛选功能">{groups.map(x=><button key={x} aria-pressed={x===group} className={x===group?'active':''} onClick={()=>setGroup(x)}>{x}</button>)}</div></div>
  <div className="task-grid">{modules.map(m=><section className={'function-card '+(m.enabled?'on':'')} key={m.key} data-module={m.key} aria-labelledby={'title-'+m.key}><div className="function-heading"><h3 id={'title-'+m.key}>{m.name}</h3><Switch checked={m.enabled} disabled={busy} label={m.enabled?'已开启':'已关闭'} aria-label={'开启'+m.name} onChange={(_,v)=>post('config',{modules:{[m.key]:v.checked}})}/></div><p className="function-description">{moduleInfo[m.key]?.[1]}</p><div className="function-parameters">{(moduleFields[m.key]||[]).map(name=><NumericParameter key={name} name={name} config={d.config} post={post} busy={busy}/>)}{m.key==='runes'&&<><PriorityParameters config={d.config} busy={busy} post={post}/><div className="boolean-parameter"><Switch checked={d.config.prioritize_capacity} disabled={busy} label="容量不足时优先扩容" onChange={(_,v)=>post('config',{prioritize_capacity:v.checked})}/><p>装备、魔石或宝箱达到容量阈值时，优先升级扩容星座及其前置节点，并为下一步预留金币。</p>{d.capacity_goal&&<p role="status">当前扩容目标：{d.capacity_goal.name}{d.capacity_goal.can_afford?'，等待本轮调度':'，等待所需资源'}</p>}</div></>} {m.key==='inventory'&&<Protection data={d} busy={busy} post={post}/>}{m.key==='enhancement'&&<div className="boolean-parameter"><Switch checked={d.config.allow_equipment_destruction} disabled={busy} label="允许有损坏概率的强化" onChange={(_,v)=>post('config',{allow_equipment_destruction:v.checked})}/><p>默认关闭。开启后按原生报价承担装备损坏概率。</p></div>}{!(moduleFields[m.key]?.length)&&m.key!=='runes'&&<p className="parameter-note">执行条件：按实时解锁、库存与原生预览自动判断。</p>}</div><div className="function-status"><span className={'state-dot '+(m.enabled?'enabled':'')}/><span>{!m.enabled?'此项已关闭，参数保留':!d.running?'总开关已暂停，此项设置保留':m.reason}</span></div>{m.key==='runes'&&<div className="next-rune">下一候选：{d.rune_next||'暂无可支付的目标节点'}</div>}</section>)}
  {showPerformance&&<section className={'function-card '+(d.config.performance_mode?'on':'')} data-module="performance"><div className="function-heading"><h3>性能模式</h3><Switch checked={d.config.performance_mode} disabled={busy} label={d.config.performance_mode?'已开启':'已关闭'} aria-label="开启性能模式" onChange={(_,v)=>post('config',{performance_mode:v.checked})}/></div><p className="function-description">降低挂机画面帧率，保留正常的游戏结算。</p><div className="function-parameters"><NumericParameter name="performance_fps" config={d.config} post={post} busy={busy}/></div><div className="function-status">{d.display?.target_fps?`游戏帧率上限：${d.display.target_fps} FPS`:'等待游戏反馈帧率设置'}</div></section>}
   {showEffects&&<section className={'function-card '+(d.config.minimal_effects?'on':'')} data-module="effects"><div className="function-heading"><h3>极简特效</h3><Switch checked={d.config.minimal_effects} disabled={busy} label={d.config.minimal_effects?'已开启':'已关闭'} aria-label="开启极简特效" onChange={(_,v)=>post('config',{minimal_effects:v.checked})}/></div><p className="function-description">隐藏战斗特效图层，保留角色、敌人、血条与操作界面。</p><div className="function-parameters"><p className="parameter-note">关闭后自动恢复特效图层，设置每 5 秒同步。</p></div><div className="function-status">{d.display?.minimal_effects===undefined?'等待游戏反馈特效状态':d.display.minimal_effects?'极简特效已在游戏生效':'原有特效显示中'}</div></section>}
  {!modules.length&&!showPerformance&&!showEffects&&<div className="empty">没有匹配的功能。<Button appearance="subtle" onClick={()=>{setSearch('');setGroup('全部')}}>清除筛选</Button></div>}
  </div><div className="workbench-tools"><Button icon={<ArrowSync20Regular/>} disabled={busy} onClick={()=>post('inspect')}>立即巡检</Button><Button icon={<ShieldCheckmark20Regular/>} aria-expanded={protection} onClick={()=>setProtection(!protection)}>品质保护</Button><Button disabled={busy} onClick={()=>post('config/open')}>配置文件</Button><Button icon={<History24Regular/>} onClick={()=>setTab('activity')}>运行日志</Button></div>
  {protection&&<section className="panel protection-panel"><div className="panel-title"><h2>品质保护</h2><Button appearance="subtle" onClick={()=>setProtection(false)}>收起</Button></div><Protection data={d} busy={busy} post={post} standalone/></section>}
  <div className="hotkey-status">{Object.entries(d.hotkeys||{}).filter(([,ok])=>!ok).map(([key])=><span key={key}>{key} 已被其他程序占用，可使用页面开关。</span>)}</div>
 </>
}

function Overview({data:d}){
 const p=d.player||{},map=d.map||{};const leader=d.team.find(x=>x.active);const pct=Math.round(Math.max(0,Math.min(1,Number(map.stage_progress)||0))*100);
 return <>
 <div className="overview-grid"><section className="panel expedition"><div className="panel-title"><h2>当前远征</h2><span className={'status-chip '+(d.running&&d.connected?'active':'')}>{d.status}</span></div><div className="expedition-body"><div><div className="quiet">主线进度</div><h2 className="map-title">{map.map_name||'正在同步关卡'}</h2><div className="map-id">关卡 {map.map_id||'待同步'}<span>最高通关 {map.highest_cleared_main_map_id||'待同步'}</span></div></div><div className="progress-orbit"><span>{pct}<small>%</small></span><div>本轮战斗进度</div></div></div><div className="progress-track" role="progressbar" aria-label="本轮战斗进度" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><div style={{width:pct+'%'}}/></div><div className="current-action"><span className="activity-indicator"/><div><strong>{d.pending?.label||(d.running?'根据当前资源选择下一项提升':'自动操作已暂停')}</strong><p>{d.pending?`等待原生结算 · ${Math.floor(d.pending.elapsed)} 秒`:'战斗结果由游戏结算，成长策略持续观察。'}</p></div></div><div className="journey"><span className="done">自动推图</span><ChevronRight16Regular/><span className="done">积累资源</span><ChevronRight16Regular/><span className="done">联动养成</span><ChevronRight16Regular/><span>更高关卡</span></div></section>
 <section className="panel growth"><div className="panel-title"><h2>队伍成长</h2><span className="quiet">实时战力</span></div><PowerChart metrics={d.metrics}/><div className="capacity-row"><span>装备背包</span><strong>{d.bag.used}<small> / {d.bag.capacity}</small></strong></div><div className="mini-track"><div style={{width:Math.min(100,d.bag.used/Math.max(1,d.bag.capacity)*100)+'%'}}/></div><div className="capacity-row"><span>魔石背包</span><strong>{d.bag.stones}<small> / {d.bag.stone_capacity}</small></strong></div></section>
 <section className="panel team"><div className="panel-title"><h2>我的队伍</h2><span className="quiet">新阵位开放后自动补齐</span></div>{d.team.length?d.team.map((x,i)=><div className="hero-row" key={x.key}><div className={'hero-avatar '+(x.active?'active':'')}>{x.name.slice(0,1)}</div><div className="hero-name"><strong>{x.name}</strong><span>{x.job}</span></div><span className="hero-level">Lv.{x.level||1}</span><div className="hero-power">{fmt(x.power)}<span>战力</span></div><span className={'status-chip '+(x.active?'active':'')}>{x.active?'上阵':'待命'}</span></div>):<div className="empty">正在读取角色列表</div>}</section>
 <section className="panel next"><div className="panel-title"><h2>下一步提升</h2><span className="quiet">实时优先级</span></div>{d.queue.length?<ol className="queue">{d.queue.slice(0,4).map((x,i)=><li key={x.kind+JSON.stringify(x.args)}><span className="queue-num">{String(i+1).padStart(2,'0')}</span><span>{x.label}</span><ChevronRight16Regular/></li>)}</ol>:<div className="empty"><ArrowSync20Regular/><p>正在观察资源与解锁条件</p><span>新奖励到账后，策略会自动继续。</span></div>}</section>
 <section className="panel recent"><div className="panel-title"><h2>最近动态</h2><span className="quiet">提交与结算分别记录</span></div><Logs rows={d.logs.slice(0,5)}/></section></div></>
}
function Stat({label,value,sub,prefix}){return <div className="stat"><div>{label}</div><strong>{prefix&&<small>{prefix}</small>}{value}</strong><span>{sub}</span></div>}
function PowerChart({metrics}){const values=metrics.slice(-30).map(x=>x.power||0),max=Math.max(1,...values),min=Math.min(...values,0);const points=values.map((v,i)=>`${8+i/Math.max(1,values.length-1)*284},${84-(v-min)/Math.max(1,max-min)*66}`).join(' ');return <div className="chart"><div className="chart-value">{fmt(values.at(-1)||0)}<span>队伍总战力</span></div>{values.length>1?<svg viewBox="0 0 300 98" role="img" aria-label={`最近 ${values.length} 次记录的战力变化，当前 ${fmt(values.at(-1))}`}><path d="M8 84H292 M8 51H292 M8 18H292" className="chart-grid"/><polyline points={points} fill="none" className="chart-line" strokeWidth="2.5" vectorEffect="non-scaling-stroke"/></svg>:<div className="chart-placeholder">运行中持续记录成长曲线</div>}</div>}
function Logs({rows,full}){return <div className={'log-list '+(full?'full':'')}>{rows.length?rows.map((x,i)=><div className="log-row" key={x.time+'-'+i}><time>{clock(x.time)}</time><span className={'log-mark '+x.level}>{x.level==='success'?<CheckmarkCircle16Regular/>:x.level==='pending'?<ArrowSync20Regular/>:<span>·</span>}</span><span>{x.message}</span><small>{x.level==='success'?'已结算':x.level==='pending'?'已提交':x.level==='warning'?'已退避':x.level==='error'?'待恢复':'系统'}</small></div>):<div className="empty">还没有运行记录</div>}</div>}
function Settings({data:d,busy,post}){return <div className="settings-layout"><section className="panel"><div className="panel-title"><h2>启动与共享预算</h2><span className="quiet">新账号与已有角色共用</span></div><div className="global-parameters">{['tick_seconds','gold_reserve_min','gold_reserve_ratio'].map(name=><NumericParameter key={name} name={name} config={d.config} post={post} busy={busy}/>)}</div>{[['auto_start','启动后自动成长','双击助手后自动接入并执行已开启的功能。'],['auto_relaunch','自动重连 默认关闭','关闭时不会自动启动或重启游戏；开启后仅恢复此实例，普通断线仍等待原生重连，消费结果未明时停止恢复。']].map(([key,label,note])=><div className="setting-row" key={key}><div><strong>{label}</strong><p>{note}</p></div><Switch checked={d.config[key]} disabled={busy} aria-label={label} onChange={(_,v)=>post('config',{[key]:v.checked})}/></div>)}</section><aside className="panel settings-note"><ShieldCheckmark20Regular/><h2>配置文件</h2><p>功能参数放在「成长策略」的对应开关下方。此处配置在所有消费策略之间共享的预算。</p><p>本机配置文件每 5 秒自动重载。文件内容无效时继续使用上次有效参数，并写入运行记录。</p><code>{d.config_path||'正在定位配置文件'}</code><Button disabled={busy} onClick={()=>post('config/open')}>打开配置文件</Button><div className="path-label">当前游戏目录</div><code>{d.game_path||'检测中'}</code></aside></div>}

createRoot(document.getElementById('root')).render(<App/>);
