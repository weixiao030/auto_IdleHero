"""Regression cases derived from the full-bag live failure, without account writes."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import tempfile
import time


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import normalize_config, plan, skill_preview_affordable, growth_budget, reserve, salvage_review, MODULES
    from wallet_assistant.diagnostics import module_reasons
    config = normalize_config({'auto_start':False, 'salvage_grades':[1,2,3,4], 'gold_reserve_min':0})
    inv = {'server_inventory_mutation_safe':True,'materials':{'5':270000,'200501':999}, 'steam_trade_ready':True,
           'character_progress_by_char':{'a':{'level':34,'skill_points':2},'b':{'level':34,'skill_points':0}},
           'bag_unlocked_slots':50,'bag_occupied_slots':50,
           'items':[{'id':1,'name':'worn','grade':3,'category':'Equipment','type':'Head','power':20,'steam_trade_protected':False},
                    {'id':2,'name':'duplicate','grade':3,'category':'Equipment','type':'Head','power':10,'steam_trade_protected':True}],
           'equipped_equipment_ids_by_char':{'a':{'Head':1}}}
    s = {'connected':True,'phase':'ready','revision':19,'pid':101,'time_unix':time.time(),
         'account':{'player':{'id':501}},'deck':['a'],'owned_characters':['a'],'formation_limit':1,'inventory':inv,'native_busy':{},'pending_requests':{}}
    preview = {'ok':True,'can_afford':True,'cost':[{'item_data_id':200501,'count':1}]}
    check('技能点按所属角色读取且不依赖材料背包',skill_preview_affordable(preview,inv,config,'a'))
    check('不能借用其他角色或材料背包的技能点',not skill_preview_affordable(preview,inv,config,'b'))
    check('未知角色没有技能点消费权限',not skill_preview_affordable(preview,inv,config,'missing'))
    for value in [None,True,'3',-1,1.5,float('nan')]:
        changed=deepcopy(inv);changed['character_progress_by_char']['a']['skill_points']=value
        check('拒绝无效角色点数 '+str(value),not skill_preview_affordable(preview,changed,config,'a'))
    mixed={**preview,'cost':preview['cost']+[{'item_data_id':5,'count':300000}]}
    check('混合技能成本仍遵守金币储备',not skill_preview_affordable(mixed,inv,config,'a'))
    combined={**preview,'cost':preview['cost']*3}
    check('重复技能成本按总数复核',not skill_preview_affordable(combined,inv,config,'a'))
    rune=lambda key,cost,effect:{'node_key':key,'name':key,'ok':True,'from_level':0,'to_level':1,'max_level':5,'cost':[{'item_data_id':5,'count':cost}],'node':{'effects':[effect]}}
    cap=rune('bag',740000,{'type':'capacity','key':'equipment_inventory_slots','value':1});cap.update(ok=False,error='insufficient_materials')
    exp=rune('exp',150000,{'type':'stat','stat':'ExpPercent','value':1})
    o={'time_unix':time.time(),'pid':101,'account_id':501,'runes':[cap,exp],
       'skills':[{'id':10,'owner':'a','level':0,'name':'Skill','preview':preview}],
       'salvage':{'1':{'eligible':False,'category_filter':'armor','grade':3,'level':1},'2':{'eligible':True,'category_filter':'armor','grade':3,'level':1}},'loot':{'count':30}}
    actions=plan(s,o,{},config)
    check('高价扩容不会冻结所有普通星座',any(a.kind=='rune_level' and a.args==['exp'] for a in actions))
    check('扩容金币预留不影响角色技能点',any(a.kind=='skill_learn' for a in actions))
    check('买不起扩容时仅预留配置比例',reserve(inv,growth_budget(s,o,config))[1]==270000*.12+270000*.88*.25)
    check('满包时不继续提交开箱',not any(a.kind=='loot_claim' for a in actions))
    check('默认继续保护可交易装备',not any(r['eligible'] for r in salvage_review(s,o,config)))
    permitted={**config,'salvage_allow_tradeable':True}
    check('明确允许后低品质可交易重复装备进入分解', [r['id'] for r in salvage_review(s,o,permitted) if r['eligible']]==[2])
    for changes,label in [({'grade':5},'英雄品质'),({'state_flag':4},'锁定'),({'enhance_level':1},'强化'),({'socket_materials':{'decoration':[{'item_data_id':1}]}},'镶嵌'),({'stored':True},'仓库'),({'unidentified':True},'未鉴定')]:
        changed=deepcopy(s);changed['inventory']['items'][1].update(changes)
        oo=deepcopy(o);oo['salvage']['2'].update(grade=changes.get('grade',3))
        check('允许交易仍保护'+label,not any(r['id']==2 and r['eligible'] for r in salvage_review(changed,oo,permitted)))
    changed=deepcopy(s);changed['inventory']['steam_trade_ready']=False
    check('允许交易不允许未知交易目录',not any(r['eligible'] for r in salvage_review(changed,o,permitted)))
    changed=deepcopy(s);del changed['inventory']['items'][1]['steam_trade_protected']
    check('允许交易不允许未知物品交易标记',not any(r['eligible'] for r in salvage_review(changed,o,permitted)))
    check('全部16模块均提供具体阻塞原因',set(module_reasons(s,o,config))==set(MODULES) and all(module_reasons(s,o,config).values()))
    check('断线时全部模块明确等待连接',all('连接' in v for v in module_reasons({},o,config).values()))
    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime,'DATA',Path(temporary)):
        engine=Engine();engine.booted=True;engine.snapshot=deepcopy(s);engine.account_id=501
        engine.opportunities=deepcopy(o);engine.config=normalize_config(permitted);engine.running=False
        engine.publish_config()
        p=engine.preview_salvage()
        check('独立分解预览列出候选与保留原因',p['count']==1 and p['candidates'][0]['id']==2 and p['protected']['已穿戴']==1)
        try:engine.start_salvage('bad');accepted=True
        except ValueError:accepted=False
        check('独立分解拒绝没有匹配预览的执行',not accepted and engine.salvage_job is None)
        engine.config['salvage_allow_tradeable']=False
        try:engine.start_salvage(p['token']);accepted=True
        except ValueError:accepted=False
        check('保护设置变化使预览失效',not accepted)
        engine.config['salvage_allow_tradeable']=True
        p=engine.preview_salvage();engine.start_salvage(p['token'])
        action=engine.standalone_salvage_action()
        check('暂停时独立分解只产生分解动作',not engine.running and action.kind=='salvage_quote' and action.args==[2])
        engine.opportunities.update(salvage_can_execute=True,salvage_selection={'2':1},salvage_quote={'request_id':90})
        action=engine.standalone_salvage_action()
        check('独立分解必须走原生报价编号',action.kind=='salvage_execute' and action.args==[101,90,[{'id':2,'count':1}]])
        engine.dispatch(action);task=engine.pending
        runtime.atomic_json(engine.runtime_dir/'results'/f"{task['id']}.json",{'status':'submitted','account_id':501,'request_ids':[90],'answer':{'ok':True},'time_unix':time.time()-3})
        runtime.atomic_json(engine.runtime_dir/'receipt-101-501-90.json',{'ok':True,'time_unix':time.time(),'response':{'ok':True}})
        engine.reconcile()
        check('独立分解收到回执但物品仍在时不计完成',engine.pending is not None and engine.salvage_job['completed']==0)
        engine.snapshot['inventory']['items']=engine.snapshot['inventory']['items'][:1]
        engine.reconcile()
        check('独立分解仅在回执且库存消失后完成',engine.pending is None and engine.salvage_job['completed']==1 and not engine.salvage_job['active'])
        engine.snapshot=deepcopy(s);engine.opportunities=deepcopy(o)
        p=engine.preview_salvage();engine.start_salvage(p['token']);engine.stop_salvage()
        check('停止独立分解不改变自动成长或模块配置',not engine.salvage_job['active'] and not engine.running and engine.config['modules']==config['modules'])
        p=engine.preview_salvage();engine.start_salvage(p['token']);engine.snapshot['account']['player']['id']=502
        check('独立分解不会跨账号继续',engine.standalone_salvage_action() is None and not engine.salvage_job['active'])
        engine.snapshot=deepcopy(s);p=engine.preview_salvage();engine.start_salvage(p['token'])
        engine.snapshot['inventory']['items'].append({'id':3,'name':'new drop','grade':1,'category':'Equipment','type':'Head','power':1,'steam_trade_protected':False})
        engine.opportunities['salvage']['3']={'eligible':True,'category_filter':'armor','grade':1,'level':1}
        check('独立分解不消耗预览后新掉落装备',engine.standalone_salvage_action().args==[2])
        engine.salvage_preview['time']-=121
        engine.stop_salvage()
        try:engine.start_salvage(p['token']);accepted=True
        except ValueError:accepted=False
        check('独立分解拒绝过期预览',not accepted)
        # Full scheduler path: a paused instance must not run the skill/mail plan.
        engine.snapshot=deepcopy(s);engine.opportunities=deepcopy(o);engine.salvage_preview=None
        p=engine.preview_salvage();engine.start_salvage(p['token'])
        engine.cached_json=lambda name: ({'rows':o['skills'],'account_id':501,'pid':101} if name=='skill-previews.json' else o if name=='opportunities.json' else {})
        with patch.object(engine,'reload_config'),patch.object(engine,'refresh_connection'),patch.object(engine,'read_snapshot',return_value=engine.snapshot):
            engine.tick()
        check('暂停状态真实调度入口仅发布本次独立分解',engine.pending and engine.pending['action']['kind']=='salvage_quote' and not engine.running)
        check('分解开始后预览标记为已使用',engine.salvage_preview.get('used') is True)
        engine.stop_salvage()
        try:engine.start_salvage(p['token']);accepted=True
        except ValueError:accepted=False
        check('一次性预览不能重复开启清理',not accepted)
        saved=Engine()
        check('助手重启仅保留待结算请求不自动扩大独立清理范围',saved.salvage_job is None and saved.pending['id']==engine.pending['id'])

        from wallet_assistant.server import Server
        import threading
        import urllib.request
        import urllib.error
        engine.pending=None
        engine.snapshot=deepcopy(s)
        engine.salvage_job=None
        engine.opportunities=deepcopy(o)
        server=Server(engine,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def post(path,body,token=True):
            req=urllib.request.Request(server.origin+path,data=json.dumps(body).encode('utf8'),headers={
                'Origin':server.origin,'X-CSRF-Token':server.csrf if token else 'bad','Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as error:return error.code,json.load(error)
        try:
            code,data=post('/api/salvage/preview',{})
            check('独立分解预览API返回当前候选',code==200 and data['result']['count']==1)
            code,_=post('/api/salvage/start',{'token':'wrong'})
            check('独立分解API拒绝无效预览',code==409)
            code,_=post('/api/salvage/start',{'token':data['result']['token']},token=False)
            check('独立分解API拒绝伪造CSRF',code==403)
            code,_=post('/api/salvage/start',{'token':data['result']['token']})
            check('独立分解API支持暂停时显式启动',code==200 and engine.salvage_job['active'] and not engine.running)
            code,_=post('/api/salvage/stop',{})
            check('独立分解API停止后仍保持暂停',code==200 and not engine.salvage_job['active'] and not engine.running)
        finally:server.shutdown();server.server_close();thread.join(3)
