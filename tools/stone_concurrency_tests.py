"""Ensure native stone races wait without spending, success counts or replay."""
from pathlib import Path
from unittest.mock import patch
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import Action
    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000):
        def request(kind='stone_merge', reason='native_stone_busy', request_ids=None):
            runtime.atomic_json(runtime.DATA/'scheduler.json', {})
            engine = Engine()
            engine.snapshot = {'pid':999,'revision':17,'connected':True,
                               'account':{'player':{'id':1001}},'native_busy':{}}
            action = Action('stones', kind, [11,12], 'fixture stone race', 90)
            engine.dispatch(action)
            ident = engine.pending['id']
            runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
                {'status':'submitted','account_id':1001,'answer':{'ok':True,'skipped':True,'reason':reason},
                 'request_ids':request_ids or [],'time_unix':1000})
            return engine, action

        for kind in ('stone_merge','stone_equip'):
            for reason in ('native_stone_busy','stone_candidates_changed'):
                engine, action = request(kind, reason)
                before = engine.success_count
                engine.reconcile()
                check('魔石原生竞争跳过不消费不计成功:'+kind+':'+reason,
                      engine.pending is None and engine.success_count == before
                      and engine.cooldowns[action.key] == 1005
                      and engine.logs[0]['level'] == 'info' and engine.logs[0]['skipped'] is True)

        engine, action = request(request_ids=[41])
        engine.reconcile()
        check('含原生请求的跳过结果保持未知结果隔离', engine.success_count == 0
              and engine.logs[0]['uncertain'] is True and engine.cooldowns[action.key] == 87400)
        engine, action = request(reason='unrecognized')
        engine.reconcile()
        check('未识别跳过原因不能绕过结算', engine.success_count == 0 and engine.logs[0]['uncertain'] is True)
        engine, action = request(kind='craft')
        engine.reconcile()
        check('消费制造不能伪装成魔石候选跳过', engine.success_count == 0 and engine.logs[0]['uncertain'] is True)
        runtime.atomic_json(runtime.DATA/'scheduler.json', {})
        engine = Engine()
        engine.snapshot = {'pid':999,'revision':16,'account':{'player':{'id':1001}}}
        try:
            engine.dispatch(action)
        except RuntimeError:
            rejected = True
        else:
            rejected = False
        check('不识别魔石竞争的新旧桥接不能混用', rejected and engine.pending is None)
