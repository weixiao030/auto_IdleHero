"""Offline connection recovery scenarios. Every process operation uses a fake."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import Action

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000), \
            patch('wallet_assistant.engine.time.monotonic', return_value=100) as clock:
        process = SimpleNamespace(pid=999, create_time=lambda: 900)
        failure = {'pid':999, 'revision':17, 'account':{'player':{'id':1001}}, 'connected':False, 'phase':'waiting', 'time_unix':1000,
            'connection':{'known':True, 'fatal':True, 'fatal_kind':'retry',
                'intentional_shutdown':False, 'login_retry_pending':False, 'fatal_restart_requested':False},
            'pending_requests':{}, 'native_busy':{'skill':False, 'equipment':False,
                'enhancement':False, 'socket':False, 'loot':False, 'craft':0, 'disassembly':0}}
        engine = Engine()
        engine.update_config({'auto_relaunch': True})
        engine.game = Path(temporary)/'game'
        engine.booted = True
        engine.snapshot = deepcopy(failure)
        check('新鲜空闲的明确重连终止状态可识别',engine.recovery_identity([process], failure) == (999,900,'retry'))
        variants = [
            ('普通断线', ('connection','fatal'), False),
            ('原生登录重试中', ('connection','login_retry_pending'), True),
            ('主动退出中', ('connection','intentional_shutdown'), True),
            ('原生已安排重启', ('connection','fatal_restart_requested'), True),
            ('未知连接状态', ('connection','known'), False),
            ('维护或被踢', ('connection','fatal_kind'), 'quit'),
            ('处罚状态', ('connection','fatal_kind'), 'sanction'),
            ('无明确原因', ('connection','fatal_kind'), ''),
            ('过期快照', ('time_unix',), 990),
            ('未来快照', ('time_unix',), 1001),
            ('NaN时间', ('time_unix',), float('nan')),
            ('无穷时间', ('time_unix',), float('inf')),
            ('字符串时间', ('time_unix',), '1000'),
            ('布尔时间', ('time_unix',), True),
            ('PID不匹配', ('pid',), 998),
            ('PID类型不符', ('pid',), '999'),
            ('stale状态', ('phase',), 'stale'),
            ('存在原生请求', ('pending_requests',), {'1':{}}),
            ('原生请求字段缺失', ('pending_requests',), None),
            ('忙碌字段缺失', ('native_busy',), {}),
            ('忙碌状态类型不符', ('native_busy','skill'), 0),
            ('制造计数类型不符', ('native_busy','craft'), False),
            ('连接标志类型不符', ('connection','fatal'), 1),
        ]
        variants += [(key+'仍在结算', ('native_busy',key), True if key not in ('craft','disassembly') else 1)
                     for key in failure['native_busy']]
        for label, path, value in variants:
            changed = deepcopy(failure)
            target = changed if len(path)==1 else changed[path[0]]
            target[path[-1]] = value
            check(label+'不会授权关闭游戏',engine.recovery_identity([process], changed) is None)
        check('多个游戏实例不自动关闭',engine.recovery_identity([process,process], failure) is None)
        reused = SimpleNamespace(pid=999, create_time=lambda:1001)
        check('PID复用后的旧快照不自动关闭',engine.recovery_identity([reused], failure) is None)
        engine.pending = {'id':'pending'}
        check('助手待结算期间不自动关闭',engine.recovery_identity([process], failure) is None)
        engine.pending = None
        with patch.object(runtime,'game_processes',return_value=[process]) as processes, \
                patch.object(runtime,'snapshot',return_value=deepcopy(failure)) as snapshot, \
                patch.object(runtime,'close_gracefully') as close, patch.object(runtime,'launch') as launch:
            engine.recover_connection()
            clock.return_value = 129
            engine.recover_connection()
            check('终止状态未持续30秒不关闭',not close.called and not launch.called)
            clock.return_value = 131
            snapshot.return_value = {**failure,'connected':True}
            engine.recover_connection()
            check('关闭前连接恢复则取消',not close.called and engine.recovery_candidate is None)
            snapshot.return_value = deepcopy(failure)
            engine.recover_connection()
            clock.return_value = 162
            processes.side_effect = [[process],[reused]]
            engine.recover_connection()
            check('关闭前实例改变则取消',not close.called and engine.recovery_candidate is None)
            processes.side_effect = None
            engine.recover_connection()
            clock.return_value = 193
            close.side_effect = RuntimeError('fixture close failure')
            try: engine.recover_connection()
            except RuntimeError: pass
            journal = json.loads((runtime.DATA/'scheduler.json').read_text(encoding='utf8'))
            check('恢复失败也先持久化五分钟退避',journal['next_recovery_at']==1300 and not launch.called)
            close.side_effect = None
            engine.recover_connection()
            clock.return_value = 224
            engine.recover_connection()
            check('退避期间不重复关闭',close.call_count==1)
            restarted = Engine()
            check('重启助手保留恢复退避',restarted.next_recovery_at==1300)
            with patch.object(runtime,'discover_game',return_value=engine.game), patch.object(runtime,'install',return_value=False):
                processes.return_value = []
                restarted.boot()
                check('启动流程不能绕过持久退避',not launch.called)
            engine.next_recovery_at = 0
            engine.recover_connection()
            check('游戏已退出才重新启动',launch.call_count==1 and close.call_count==1)
            engine.recover_connection()
            check('游戏缺席时仍遵守五分钟启动退避',launch.call_count==1)
            processes.return_value = [process]
            engine.next_recovery_at = 0
            clock.return_value = 300
            engine.recover_connection()
            clock.return_value = 331
            engine.recover_connection()
            check('稳定终止且空闲才正常关闭并恢复',close.call_count==2 and launch.call_count==2
                  and close.call_args.kwargs=={'expected_pid':999,'expected_create_time':900})
            engine.recovery_candidate = ((999,900,'retry'),100)
            engine.disconnected_since = 800
            engine.actions = [Action('skills','skill_level',['a',1],'old candidate',100)]
            snapshot.return_value = {**failure,'connection':{**failure['connection'],'fatal':False}}
            engine.tick()
            check('普通断线超过两分钟仍等待且清空旧候选',close.call_count==2 and launch.call_count==2
                  and engine.actions==[] and engine.recovery_candidate is None)
            snapshot.return_value = {**failure,'connected':True}
            engine.recovery_candidate = ((999,900,'retry'),100)
            engine.last_dispatch = 1000
            engine.tick()
            check('正常连接重置必要恢复计时',engine.recovery_candidate is None)
            engine.snapshot = deepcopy(failure)
            engine.dispatch(Action('inventory','salvage_execute',[1],'fixture salvage',100,{'consumed':[1]}))
            ident = engine.pending['id']
            runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
                {'status':'submitted','account_id':1001,'answer':True,'request_ids':[401],'time_unix':996})
            runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-401.json',{'time_unix':1000,'ok':True,'response':{'ok':True}})
            engine.snapshot['inventory'] = {'items':[]}
            before = engine.success_count
            engine.reconcile()
            check('断线不以旧库存计成功',engine.pending is not None and engine.success_count==before)
            engine.pending['started'] = 950
            engine.reconcile()
            check('断线结果未明超过45秒隔离而非重放',engine.pending is None
                  and engine.success_count==before and engine.logs[0]['uncertain'])
            engine.dispatch(Action('skills','skill_level',['a',1],'fixture failure',100))
            ident = engine.pending['id']
            runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',
                {'status':'submitted','account_id':1001,'answer':{'ok':False,'error':'fixture rejection'}})
            engine.reconcile()
            check('断线仍处理明确失败回执',engine.pending is None and engine.success_count==before)
        # The window API itself is fake; these checks never inspect or close real windows.
        user32 = Mock()
        user32.EnumWindows.side_effect = lambda callback, _: callback(17,0)
        user32.GetWindowThreadProcessId.side_effect = lambda _, owner: setattr(owner._obj,'value',999)
        user32.GetWindowTextW.side_effect = lambda _, title, size: setattr(title,'value','Desktop Wallet Heroes')
        process.wait = Mock()
        with patch.object(runtime.ctypes,'windll',SimpleNamespace(user32=user32)), \
                patch.object(runtime,'game_processes',return_value=[process]) as processes:
            for expected_pid, expected_time in [(998,900),(999,901)]:
                try: runtime.close_gracefully(engine.game,expected_pid,expected_time)
                except RuntimeError: pass
            check('关闭函数拒绝身份不符且不触碰窗口',not user32.EnumWindows.called)
            processes.side_effect = [[process],[reused]]
            try: runtime.close_gracefully(engine.game,999,900)
            except RuntimeError: pass
            check('发送关闭消息前二次核对实例',not user32.PostMessageW.called)
            processes.side_effect = None
            runtime.close_gracefully(engine.game,999,900)
            check('正常恢复只发送WM_CLOSE并等待退出',user32.PostMessageW.call_args.args==(17,0x0010,0,0)
                  and process.wait.call_args.kwargs=={'timeout':25})
