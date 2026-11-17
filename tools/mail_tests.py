"""Offline mail-query retries; never sends a live mail or game request."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import Action

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000) as clock:
        action = Action('mail', 'mail_refresh', [], 'fixture mail list', 25)
        fresh = {'pid':999, 'revision':17, 'account':{'player':{'id':1001}}, 'connected':True, 'phase':'ready', 'time_unix':1000,
                 'pending_requests':{}, 'native_busy':{}}

        def new_engine():
            clock.return_value = 1000
            runtime.atomic_json(runtime.DATA/'scheduler.json', {})
            engine = Engine()
            engine.snapshot = deepcopy(fresh)
            return engine

        engine = new_engine()
        check('邮件列表新鲜连接可读取', engine.action_ready(action))
        for name, changes in [
            ('断线', {'connected':False}), ('未知连接', {'connected':1}),
            ('过期阶段', {'phase':'stale'}), ('过期时间', {'time_unix':991}),
            ('未来时间', {'time_unix':1001}), ('NaN时间', {'time_unix':float('nan')}),
            ('无穷时间', {'time_unix':float('inf')}), ('字符串时间', {'time_unix':'1000'}),
            ('缺失时间', {'time_unix':None}), ('未知请求表', {'pending_requests':None}),
            ('错误请求表', {'pending_requests':[]}),
            ('错误请求项', {'pending_requests':{'1':None}}),
            ('缺少请求指令', {'pending_requests':{'1':{}}}),
            ('空请求指令', {'pending_requests':{'1':{'command':''}}}),
            ('非字符串指令', {'pending_requests':{'1':{'command':1}}}),
            ('原生列表挂起', {'pending_requests':{'1':{'command':'mail.list'}}}),
            ('原生领奖挂起', {'pending_requests':{'1':{'command':'mail.read'}}}),
        ]:
            engine.snapshot = {**deepcopy(fresh), **changes}
            check('邮件读取等待'+name, not engine.action_ready(action))
        engine.snapshot = {**deepcopy(fresh), 'pending_requests':{'2':{'command':'inventory.list'}}}
        check('其他只读请求不误锁邮件', engine.action_ready(action))

        # Reconcile actual command/result journals through each unknown-outcome path.
        for failure in ['missing_result', 'missing_receipt', 'transport_lost', 'disconnected', 'session_changed']:
            engine = new_engine()
            engine.dispatch(action)
            ident = engine.pending['id']
            command_path = runtime.DATA/'runtime/commands'/engine.pending['command_file']
            engine.pending['started'] = 950
            if failure != 'missing_result':
                # A native worker consumes this command after journaling acceptance.
                command_path.unlink()
                runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
                    {'status':'submitted','account_id':1001, 'answer':{'request_id':401}, 'request_ids':[401], 'time_unix':996})
                receipt_path = runtime.DATA/'runtime/receipt-999-1001-401.json'
                if failure == 'missing_receipt':
                    # Each case has a fresh operation id, and this fixture request id is reused.
                    if receipt_path.exists(): receipt_path.unlink()
                elif failure == 'transport_lost':
                    runtime.atomic_json(receipt_path, {'time_unix':1000,'ok':False,'response':{'transport_lost':True,'outcome_unknown':True}})
                else:
                    runtime.atomic_json(receipt_path, {'time_unix':1000,'ok':True,'response':{'ok':True}})
            if failure == 'disconnected': engine.snapshot['connected'] = False
            if failure == 'session_changed': engine.snapshot['pid'] = 1001
            before = engine.success_count
            engine.reconcile()
            check('邮件未知结果保留120秒退避:'+failure,
                  engine.pending is None and engine.success_count == before
                  and engine.cooldowns[action.key] == 1120 and engine.logs[0]['uncertain'])
            check('邮件旧命令不重发:'+failure, not command_path.exists())
            engine.snapshot = deepcopy(fresh)
            clock.return_value = 1119
            engine.snapshot['time_unix'] = 1119
            check('邮件两分钟内不重读:'+failure, not engine.action_ready(action))
            clock.return_value = 1120
            engine.snapshot['time_unix'] = 1120
            check('邮件两分钟后生成新读取:'+failure, engine.action_ready(action))
            engine.dispatch(action)
            check('新读取使用独立操作ID:'+failure, engine.pending['id'] != ident)
            persisted = Engine()
            check('助手重启保留新读取操作ID:'+failure, persisted.pending['id'] == engine.pending['id'])

        engine = new_engine()
        engine.dispatch(action)
        ident = engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
            {'status':'submitted','account_id':1001,'answer':{'request_id':402},'request_ids':[402],'time_unix':996})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-402.json', {'time_unix':1000,'ok':True,'response':{'ok':True}})
        before = engine.success_count
        engine.reconcile()
        check('邮件原生成功后300秒冷却',engine.pending is None
              and engine.success_count == before+1 and engine.cooldowns[action.key] == 1300)
        engine = new_engine()
        engine.dispatch(action)
        ident = engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
            {'status':'submitted','account_id':1001,'answer':{'request_id':403},'request_ids':[403],'time_unix':996})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-403.json', {'time_unix':1000,'ok':False,'response':{'ok':False}})
        engine.reconcile()
        check('邮件明确失败仍120秒退避',engine.pending is None
              and engine.cooldowns[action.key] == 1120 and not engine.logs[0]['uncertain'])

        for kind in ['mail_claim','craft','salvage_execute','skill_level']:
            engine = new_engine()
            spend = Action('mail' if kind == 'mail_claim' else 'inventory', kind, [1], 'fixture spend', 25)
            engine.dispatch(spend)
            engine.finish(False, 'fixture unknown', uncertain=True)
            check('未知消费继续隔离一天:'+kind, engine.cooldowns[spend.key] == 87400)

        new_engine()
        runtime.atomic_json(runtime.DATA/'scheduler.json',{'cooldowns':{
            action.key:87400, 'mail_claim:[1]':87400}})
        migrated = Engine()
        saved = json.loads((runtime.DATA/'scheduler.json').read_text(encoding='utf8'))
        check('旧邮件一天退避自动迁移并落盘', migrated.cooldowns[action.key] == 1120
              and saved['cooldowns'][action.key] == 1120 and saved['cooldowns']['mail_claim:[1]'] == 87400)
        clock.return_value = 1010
        restarted = Engine()
        check('助手重启不重置邮件迁移退避',restarted.cooldowns[action.key] == 1120)
        for deadline in [1300,1120,999]:
            clock.return_value = 1000
            runtime.atomic_json(runtime.DATA/'scheduler.json',{'cooldowns':{action.key:deadline}})
            check('正常邮件期限不迁移:'+str(deadline),Engine().cooldowns[action.key] == deadline)
