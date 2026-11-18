"""Offline maintenance transaction scenarios; never touch a live account."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine, maintenance_context_ready
    from wallet_assistant.policy import has_socket_materials, empty_socket_count, protected_items

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000):
        base = {'pid':999, 'revision':17, 'account':{'player':{'id':1001}}, 'time_unix':1000, 'phase':'ready', 'connected':True,
            'deck':['hero'], 'owned_characters':['hero'], 'inventory':{
                'server_inventory_mutation_safe':True, 'materials':{'5':10000},
                'character_progress_by_char':{'hero':{'level':30}},
                'equipped_equipment_ids_by_char':{'hero':{'Head':101}},
                'items':[{'id':101, 'name':'test', 'category':'Equipment', 'type':'Head',
                    'grade':3, 'enhance_level':0, 'state_flag':1, 'steam_trade_protected':False,
                    'socket_slots':{'decoration':1}, 'socket_materials':{'decoration':[{}]}}]},
            'native_busy':{'skill':False,'equipment':False,'enhancement':False,'socket':False,
                           'loot':False,'craft':0,'disassembly':0},
            'pending_requests':{}}
        opportunities = {'pid':999, 'account_id':1001, 'time_unix':1000, 'enhancement_ready':True}
        def fresh():
            engine = Engine()
            engine.pending = None
            engine.maintenance = None
            engine.snapshot = deepcopy(base)
            engine.account_id = 1001
            engine.opportunities = deepcopy(opportunities)
            engine.cooldowns = {}
            engine.running = True
            engine.config['modules']['enhancement'] = True
            engine.config['modules']['socket'] = True
            return engine

        check('维护要求新鲜连接、无请求且原生控制器全部空闲', maintenance_context_ready(base))
        blocked_contexts = []
        for key, value in [('skill', True), ('equipment', True), ('enhancement', True),
                           ('socket', True), ('loot', True), ('craft', 1), ('disassembly', 1)]:
            changed = deepcopy(base); changed['native_busy'][key] = value
            blocked_contexts.append((key+'忙碌', changed))
        changed=deepcopy(base); changed['pending_requests']={'451':{'command':'equipment.update'}}
        blocked_contexts.append(('原生请求待结算', changed))
        changed=deepcopy(base); del changed['native_busy']['equipment']
        blocked_contexts.append(('忙碌状态缺字段', changed))
        changed=deepcopy(base); changed['native_busy']['craft']=False
        blocked_contexts.append(('忙碌字段类型错误', changed))
        changed=deepcopy(base); changed['phase']='stale'
        blocked_contexts.append(('快照过期', changed))
        for stamp in (990,1001,float('nan'),float('inf'),None,True,'1000'):
            changed=deepcopy(base); changed['time_unix']=stamp
            blocked_contexts.append(('无效维护时间戳：'+repr(stamp),changed))
        changed=deepcopy(base); changed['connected']=False
        blocked_contexts.append(('连接中断', changed))
        changed=deepcopy(base); changed['inventory']['server_inventory_mutation_safe']=False
        blocked_contexts.append(('库存非权威', changed))
        changed=deepcopy(base); changed['inventory']['equipped_equipment_ids_by_char']='unknown'
        blocked_contexts.append(('穿戴投影类型未知', changed))
        for label, changed in blocked_contexts:
            check(label+'不会进入装备维护', not maintenance_context_ready(changed))

        item = base['inventory']['items'][0]
        check('空镶嵌槽不视为投入材料',not has_socket_materials(item) and empty_socket_count(item)==1)
        for label, layers in [('实际宝石',{'decoration':[{'item_data_id':1}]}),
                              ('异常字典值',{'decoration':{'unknown':1}}),
                              ('未知空值',None),('未知数组',[])]:
            check(label+'保留装备',has_socket_materials({**item,'socket_materials':layers}))
        check('已嵌宝石不重复安排',empty_socket_count({**item,'socket_materials':{'decoration':[{'id':1}]}})==0)
        for slots in [None,[],{'decoration':-1},{'decoration':7},{'decoration':'1'}]:
            changed = {**item,'socket_slots':slots}
            if slots is None: changed['grade'] = '3'
            check('无效槽位等待原生确认：'+repr(slots),empty_socket_count(changed)==0)
        spare = deepcopy(base)
        spare['inventory']['equipped_equipment_ids_by_char'] = {}
        spare['inventory']['items'] = [{**item,'state_flag':0,'power':10},
                                      {**item,'id':102,'state_flag':0,'power':20}]
        check('空槽占位不永久保护低战力备用',101 not in protected_items(spare,fresh().config))

        engine = fresh()
        action = engine.maintenance_action()
        check('维护卸下使用明确目标状态',action.args==['hero',101,False] and action.expected=={'unequipped':['hero',101]})
        engine.dispatch(action)
        task = engine.pending
        runtime.atomic_json(runtime.DATA/'runtime/results'/f"{task['id']}.json",
            {'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[901],'time_unix':997})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-901.json',{'time_unix':1000,'ok':True,'response':{'ok':True}})
        engine.reconcile()
        check('卸下回执不代替穿戴状态核验',engine.pending is not None and engine.maintenance['phase']=='prepare')
        engine.snapshot['inventory']['server_inventory_mutation_safe']=False
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
        engine.reconcile()
        check('回执后的非权威空穿戴状态不计成功',engine.pending is not None and engine.maintenance['phase']=='prepare')
        engine.snapshot['inventory']['server_inventory_mutation_safe']=True
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero'] = {}
        engine.reconcile()
        check('卸下状态确认后进入维护阶段',engine.pending is None and engine.maintenance['phase']=='operate')
        check('下一步读取原生强化报价',engine.maintenance_action().kind=='enhancement_quote')
        quote = {'item':{'id':101},'scroll_count':1,'success_percent':80,'gold_cost':100,'destruction_percent':0}
        engine.opportunities['enhancement_quote'] = deepcopy(quote)
        action = engine.maintenance_action()
        check('有效报价预算通过后才强化',action.kind=='enhancement_execute')
        engine.dispatch(action)
        engine.finish(True,'fixture enhancement settled')
        action = engine.maintenance_action()
        check('强化结算后无条件安排穿回',action.args==['hero',101,True] and action.expected=={'equipment':['hero',101]})
        engine.dispatch(action)
        task = engine.pending
        runtime.atomic_json(runtime.DATA/'runtime/results'/f"{task['id']}.json",
            {'status':'submitted','account_id':1001,'answer':{'ok':True,'already_satisfied':True},'request_ids':[],'time_unix':997})
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero'] = {'Head':101}
        engine.reconcile()
        check('幂等恢复无新请求仍须核验穿戴后结算',engine.pending is None)
        check('穿回后结束事务并设置维护间隔',engine.maintenance_action() is None and engine.maintenance is None
              and engine.cooldowns['maintenance:enhancement:101']>=1180)
        check('维护间隔内不再次卸下',engine.maintenance_action() is None)

        for label, change in [('无材料',{'scroll_count':0}),('金币不足',{'gold_cost':10000}),
                              ('有破坏风险',{'destruction_percent':1}),('成本NaN',{'gold_cost':float('nan')}),
                              ('成功率缺失',{'success_percent':None}),('负费用',{'gold_cost':-1})]:
            engine = fresh()
            engine.maintenance_action()
            engine.maintenance['phase'] = 'operate'
            engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero'] = {}
            engine.opportunities['enhancement_quote'] = {**quote,**change}
            action = engine.maintenance_action()
            check(label+'停止消费并立即恢复装备',action.args==['hero',101,True]
                  and engine.maintenance['phase']=='restore' and engine.cooldowns['maintenance:enhancement:101']>=1600)
        for label, change in [('成功率越界',{'success_percent':101}),('破坏率越界',{'destruction_percent':101}),
                              ('小数材料数',{'scroll_count':0.5}),('小数金币成本',{'gold_cost':0.5})]:
            engine=fresh();engine.maintenance_action();engine.maintenance['phase']='operate'
            engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
            engine.opportunities['enhancement_quote']={**quote,**change}
            action=engine.maintenance_action()
            check(label+'按异常报价恢复装备',action.args==['hero',101,True] and engine.maintenance['phase']=='restore')

        for reason in ['pause','module_off','session','expired','stale_opportunities','socket_gone','unknown_module']:
            engine = fresh()
            engine.maintenance_action()
            engine.maintenance['phase'] = 'operate'
            engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero'] = {}
            if reason=='pause': engine.running=False
            elif reason=='module_off': engine.config['modules']['enhancement']=False
            elif reason=='session': engine.maintenance['pid']=998
            elif reason=='expired': engine.maintenance['started']=930
            elif reason=='stale_opportunities': engine.opportunities['time_unix']=900
            elif reason=='socket_gone': engine.maintenance['module']='socket'
            else:
                engine.maintenance['module']='inventory'
            action = engine.maintenance_action()
            check(reason+'仅恢复不再消费',action is not None and action.args==['hero',101,True]
                  and engine.maintenance['phase']=='restore')
        engine = fresh()
        engine.maintenance_action()
        engine.maintenance['phase']='operate'
        engine.persist()
        restarted = Engine()
        check('助手重启将未完成维护转为恢复并持久化',restarted.maintenance['phase']=='restore'
              and json.loads((runtime.DATA/'scheduler.json').read_text(encoding='utf8'))['maintenance']['phase']=='restore')
        for malformed in [None, [], {'module':'unknown','id':101,'owner':'hero'},
                          {'module':'socket','id':0,'owner':'hero'}, {'module':'socket','id':101,'owner':''}]:
            runtime.atomic_json(runtime.DATA/'scheduler.json', {'maintenance':malformed})
            recovered=Engine()
            check('损坏的维护日志不会卡住调度：'+repr(malformed),recovered.maintenance is None)
        runtime.atomic_json(runtime.DATA/'scheduler.json', {})
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
        engine.maintenance['phase']='restore'
        engine.booted=True
        engine.last_dispatch=0
        with patch.object(runtime,'snapshot',return_value=deepcopy(engine.snapshot)):
            runtime.atomic_json(runtime.DATA/'runtime/opportunities.json',{'time_unix':900,'pid':999})
            engine.tick()
        check('机会预览过期不再阻塞已卸装备恢复',engine.pending is not None
              and engine.pending['action']['args']==['hero',101,True])
        for label in ['disconnect','non_authoritative','other_owner','missing_item']:
            engine=fresh();engine.maintenance_action();engine.maintenance['phase']='restore'
            engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
            if label=='disconnect': engine.snapshot['connected']=False
            elif label=='non_authoritative': engine.snapshot['inventory']['server_inventory_mutation_safe']=False
            elif label=='other_owner': engine.snapshot['inventory']['equipped_equipment_ids_by_char']['other']={'Head':101}
            else: engine.snapshot['inventory']['items']=[]
            check(label+'不盲目操作装备',engine.maintenance_action() is None)
        engine=fresh();engine.maintenance_action();engine.maintenance['phase']='operate'
        check('其他入口已穿回后不反向卸装',engine.maintenance_action() is None and engine.maintenance['phase']=='restore')
        engine=fresh();engine.config['modules']['enhancement']=False
        engine.opportunities.update(socket_ready=True,socket_gems=[{'id':501,'grade':1,'count':1}],socket_gold_costs={'101':{'501':4000}})
        check('仅空槽且有材料才开始镶嵌维护',engine.maintenance_action().args==['hero',101,False]
              and engine.maintenance['module']=='socket')
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
        engine.maintenance['phase']='operate'
        engine.opportunities['socket_items']=[{'id':101,'empty_slots':[0]}]
        check('镶嵌只使用原生确认的空槽',engine.maintenance_action().args==[101,0,501,1200])
        for cost in (None, True, '4000', -1, 1.5, float('nan')):
            engine=fresh();engine.config['modules']['enhancement']=False
            engine.opportunities.update(socket_ready=True,socket_gems=[{'id':501,'grade':1,'count':1}],socket_gold_costs={'101':{'501':cost}})
            check('镶嵌成本未知或无效时不卸装：'+repr(cost),engine.maintenance_action() is None)
        engine=fresh();engine.config['modules']['enhancement']=False
        engine.opportunities.update(socket_ready=True,socket_gems=[{'id':501,'grade':1,'count':1}],socket_gold_costs={'101':{'501':9000}})
        check('镶嵌保留共享金币预算且不先卸装',engine.maintenance_action() is None)
        engine.opportunities['socket_gold_costs']['101']['501']=4000
        engine.opportunities['time_unix']=990
        check('镶嵌成本快照过期时不卸装',engine.maintenance_action() is None)
        engine.opportunities['time_unix']=1000
        engine.opportunities['runes']=[{'node_key':'bag','name':'bag','ok':True,'from_level':0,'max_level':5,'cost':[{'item_data_id':5,'count':8000}], 'node':{'effects':[{'type':'capacity','key':'equipment_inventory_slots','value':1}]}}]
        engine.snapshot['inventory'].update(bag_occupied_slots=50,bag_unlocked_slots=50)
        check('镶嵌不占用已可支付的扩容预算',engine.maintenance_action() is None)
        engine.opportunities['runes']=[]
        check('预算足够后正常开始镶嵌维护',engine.maintenance_action().args==['hero',101,False])
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
        engine.maintenance['phase']='operate'
        engine.opportunities['socket_items']=[{'id':101,'empty_slots':[0]}]
        engine.snapshot['inventory']['materials']['5']=3000
        check('卸装后金币减少时先恢复装备而非提交镶嵌',engine.maintenance_action().args==['hero',101,True] and engine.maintenance['phase']=='restore')
        for state in [2,4,8,32,64]:
            engine=fresh();engine.snapshot['inventory']['items'][0]['state_flag']=state
            check('受保护装备不进入维护：'+str(state),engine.maintenance_action() is None)
        engine=fresh()
        unequip=engine.maintenance_action()
        engine.dispatch(unequip)
        engine.finish(False,'fixture unknown unequip',uncertain=True)
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']={}
        restore=engine.maintenance_action()
        check('卸下结果未知后不重放卸下而安排穿回',restore.args==['hero',101,True]
              and engine.cooldowns['maintenance:enhancement:101']>=87400)
        engine.dispatch(restore)
        engine.finish(False,'fixture unknown restore',uncertain=True)
        retry=engine.maintenance_action()
        check('恢复结果未知进入两分钟状态复核而非锁死一天',not engine.action_ready(retry,1119)
              and engine.action_ready(retry,1120))
        engine.snapshot['pending_requests']={'902':{'command':'equipment.update'}}
        check('恢复退避结束也不与未决原生请求并发',engine.maintenance_action() is None)
