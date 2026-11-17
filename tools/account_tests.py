"""Offline account-isolation scenarios; no live game or account is accessed."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine, snapshot_account_id, opportunities_ready
    from wallet_assistant.policy import Action

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000):
        check('账号身份只接受正整数玩家ID',
              snapshot_account_id({'account':{'player':{'id':1001}}}) == 1001
              and snapshot_account_id({'account':{'player':{'id':True}}}) is None
              and snapshot_account_id({'account':{'player':{'id':'1001'}}}) is None
              and snapshot_account_id({'account':{'player':{}}}) is None)

        action = Action('skills', 'skill_level', ['hero', 7], 'fixture upgrade', 90)
        engine = Engine()
        engine.snapshot = {'pid':999, 'revision':17, 'account':{'player':{'id':1001}}}
        engine.dispatch(action)
        task = engine.pending
        command_path = runtime.DATA/'runtime/commands'/task['command_file']
        command = json.loads(command_path.read_text(encoding='utf8'))
        journal = json.loads((runtime.DATA/'scheduler.json').read_text(encoding='utf8'))
        check('命令及调度日志都绑定当前账号', command['account_id'] == 1001
              and task['account_id'] == 1001 and journal['account_id'] == 1001)

        engine.cooldowns['old-account'] = 1100
        engine.module_last_run['skills'] = 900
        engine.maintenance = {'module':'enhancement', 'id':51, 'owner':'hero', 'pid':999,
                              'account_id':1001, 'started':950, 'phase':'operate'}
        engine.bind_account(2002)
        saved_old = engine.account_states['1001']
        check('切号隔离旧请求并将旧维护暂存为恢复', engine.pending is None and not command_path.exists()
              and saved_old['cooldowns'][action.key] == 87400
              and saved_old['cooldowns']['old-account'] == 1100
              and saved_old['maintenance']['phase'] == 'restore'
              and engine.maintenance is None and engine.cooldowns == {})

        engine.snapshot = {'pid':999, 'revision':17, 'account':{'player':{'id':2002}}}
        check('新账号不会读取旧账号维护装备', engine.maintenance_action() is None)
        engine.bind_account(1001)
        check('切回原账号后只恢复原维护事务', engine.maintenance is not None
              and engine.maintenance['account_id'] == 1001
              and engine.maintenance['phase'] == 'restore'
              and engine.cooldowns['old-account'] == 1100)

        restarted = Engine()
        check('助手重启保留账号隔离和待恢复事务', restarted.account_id == 1001
              and restarted.maintenance['account_id'] == 1001
              and restarted.maintenance['phase'] == 'restore'
              and restarted.account_states['2002']['cooldowns'] == {})

        ready_equipment = {'pid':999, 'revision':15, 'time_unix':1000, 'phase':'ready', 'connected':True,
            'account':{'player':{'id':1001}}, 'inventory':{'server_inventory_mutation_safe':True,
                'items':[{'id':51}], 'equipped_equipment_ids_by_char':{'hero':{}}},
            'native_busy':{'skill':False,'equipment':False,'enhancement':False,'socket':False,
                           'loot':False,'craft':0,'disassembly':0}, 'pending_requests':{}}
        restarted.snapshot = deepcopy(ready_equipment)
        restore = restarted.maintenance_action()
        check('切回后权威装备状态只安排明确穿回', restore.args == ['hero',51,True])
        restarted.snapshot['account']['player']['id'] = 2002
        check('相同物品ID在其他账号也不恢复原装备', restarted.maintenance_action() is None)

        engine.snapshot = {'pid':999, 'revision':17, 'account':{'player':{'id':True}}}
        try:
            engine.dispatch(action)
        except RuntimeError:
            rejected = True
        else:
            rejected = False
        check('缺失或非法账号身份拒绝发布命令', rejected)

        runtime.atomic_json(runtime.DATA/'scheduler.json', {})
        legacy = Engine()
        legacy.pending = {'id':'legacy', 'pid':999, 'command_file':'legacy.json',
                          'action':{'module':'skills','kind':'skill_level','args':['hero',7],
                                    'label':'legacy request','priority':90,'expected':None}}
        legacy.snapshot = {'pid':999, 'revision':17, 'account':{'player':{'id':3003}}}
        legacy.bind_account(3003)
        check('旧版未绑定账号的待处理请求首次接入即隔离', legacy.pending is None
              and any('无法绑定当前账号' in row['message'] for row in legacy.logs))

        current = {'pid':999, 'revision':17, 'time_unix':1000, 'phase':'ready', 'connected':True,
                   'account':{'player':{'id':3003}}, 'native_busy':{}, 'inventory':{'items':[]}}
        preview = {'pid':999, 'account_id':3003, 'time_unix':1000}
        check('当前账号的新鲜预览可调度', opportunities_ready(current, preview, now=1000))
        for account_id in [1001, None, True, '3003']:
            check('跨账号或无身份预览被拒绝:'+repr(account_id),
                  not opportunities_ready(current, {**preview,'account_id':account_id}, now=1000))

        def new_request():
            runtime.atomic_json(runtime.DATA/'scheduler.json', {})
            candidate = Engine()
            candidate.snapshot = deepcopy(current)
            candidate.dispatch(action)
            return candidate

        candidate = new_request()
        count = candidate.success_count
        ident = candidate.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
            {'status':'submitted','account_id':3003,'answer':True,'request_ids':[71],'time_unix':996})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-71.json',
            {'ok':True,'time_unix':1000,'response':{'ok':True}})
        candidate.reconcile()
        check('其他账号复用请求号的旧回执不计成功', candidate.pending is not None and candidate.success_count == count)
        own_receipt = runtime.DATA/'runtime/receipt-999-3003-71.json'
        runtime.atomic_json(own_receipt, {'ok':True,'time_unix':999,'response':{'ok':True}})
        candidate.reconcile()
        check('同账号早于命令的旧回执也不计成功', candidate.pending is not None and candidate.success_count == count)
        runtime.atomic_json(own_receipt, {'ok':True,'time_unix':1000,'response':{'ok':True}})
        candidate.reconcile()
        check('当前账号当前请求的回执正常结算', candidate.pending is None and candidate.success_count == count+1)

        candidate = new_request()
        ident = candidate.pending['id']
        command_path = runtime.DATA/'runtime/commands'/candidate.pending['command_file']
        candidate.snapshot['account']['player']['id'] = 4004
        candidate.reconcile()
        check('同PID切号不会按新库存确认旧请求', candidate.pending is None and not command_path.exists()
              and candidate.success_count == 0)

        candidate = new_request()
        ident = candidate.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
            {'status':'submitted','account_id':4004,'answer':True,'request_ids':[],'time_unix':996})
        candidate.reconcile()
        check('结果文件账号不匹配即隔离', candidate.pending is None and candidate.success_count == 0)

        candidate = new_request()
        ident = candidate.pending['id']
        candidate.snapshot['account'] = {}
        candidate.reconcile()
        check('身份暂时缺失保持旧请求不结算不重放', candidate.pending['id'] == ident and candidate.success_count == 0)
        candidate.booted = True
        candidate.actions = [action]
        with patch.object(runtime,'snapshot',return_value=deepcopy(candidate.snapshot)):
            candidate.tick()
        check('身份缺失时整轮调度清空旧候选并等待', candidate.actions == [] and candidate.status == '等待可验证账号身份')

        candidate = new_request()
        previous = candidate.pending['id']
        try:
            candidate.dispatch(action)
        except RuntimeError:
            rejected = True
        else:
            rejected = False
        check('单飞调度拒绝覆盖未结算的命令', rejected and candidate.pending['id'] == previous)

        runtime.atomic_json(runtime.DATA/'scheduler.json', {})
        candidate = Engine()
        candidate.snapshot = {**deepcopy(current),'revision':15}
        try:
            candidate.dispatch(action)
        except RuntimeError:
            rejected = True
        else:
            rejected = False
        check('旧桥接未支持请求归属时禁止发布', rejected and candidate.pending is None)

        runtime.atomic_json(runtime.DATA/'scheduler.json', {'account_id':1001,
            'account_states':{'3003':{'maintenance':{'account_id':3003}}}})
        candidate = Engine()
        candidate.bind_account(3003)
        check('损坏的其他账号维护记录不阻塞切换', candidate.maintenance is None)
