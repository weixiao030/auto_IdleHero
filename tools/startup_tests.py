"""Startup preference and launch scenarios; all game operations are mocked."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000), \
            patch('wallet_assistant.engine.time.monotonic', return_value=100) as clock:
        game = Path(temporary)/'game'
        process = SimpleNamespace(pid=999, create_time=lambda: 900)
        with patch.object(runtime, 'game_processes', return_value=[]) as processes, \
                patch.object(runtime.subprocess, 'Popen') as popen:
            check('开启时启动游戏成功', runtime.launch(game, auto_start=True) is True)
            check('开启时透传游戏原生自动开始参数', popen.call_args.args[0] == [str(game/runtime.GAME_EXE), '--', '--auto-start']
                  and popen.call_args.kwargs['cwd'] == game)
            popen.reset_mock()
            check('暂停时仍可正常启动游戏', runtime.launch(game, auto_start=False) is True)
            check('暂停时不附带自动开始参数', popen.call_args.args[0] == [str(game/runtime.GAME_EXE)])
            popen.reset_mock()
            processes.return_value = [process]
            check('已有游戏实例不会再启动', runtime.launch(game, auto_start=True) is False and not popen.called)
        main = SimpleNamespace(info={'exe': str((game/runtime.GAME_EXE).resolve()), 'cmdline': [runtime.GAME_EXE]})
        helper = SimpleNamespace(info={'exe': main.info['exe'], 'cmdline': [runtime.GAME_EXE, '--', '--bi-loading-helper']})
        with patch.object(runtime, 'game_candidates', return_value=[main, helper]):
            check('加载展示子进程不被当成游戏主进程', runtime.game_processes(game) == [main])

        engine = Engine()
        check('自动重连默认关闭', engine.config['auto_relaunch'] is False)
        read = lambda name: json.loads((runtime.DATA/name).read_text(encoding='utf8'))
        engine.set_running(False)
        check('暂停同时保存配置和桥接控制', engine.running is False and read('config.json')['auto_start'] is False
              and read('runtime/control.json')['auto_start'] is False)
        check('重新打开助手保留暂停', Engine().running is False)
        engine.handle_hotkey('F8')
        check('F8开启立即持久保存', engine.running is True and read('config.json')['auto_start'] is True
              and read('runtime/control.json')['auto_start'] is True)
        check('重新打开助手保留开启', Engine().running is True)
        engine.update_config({'auto_start': False, 'modules': {'inventory': False}})
        check('保存页面配置同步暂停状态', engine.running is False and read('runtime/control.json')['auto_start'] is False)
        engine.update_config({'tick_seconds': 3})
        check('修改其他参数保留总开关和模块偏好', engine.running is False and engine.config['modules']['inventory'] is False)
        config = read('config.json')
        config['auto_start'] = True
        runtime.atomic_json(runtime.DATA/'config.json', config)
        engine.last_config_check = 0
        engine.config_stamp = None
        engine.reload_config()
        check('外部重载开启配置同步运行和桥接', engine.running is True and read('runtime/control.json')['auto_start'] is True)
        config['auto_start'] = False
        runtime.atomic_json(runtime.DATA/'config.json', config)
        engine.last_config_check = 0
        engine.config_stamp = None
        engine.reload_config()
        check('外部重载暂停配置同步运行和桥接', engine.running is False and read('runtime/control.json')['auto_start'] is False)
        runtime.atomic_json(runtime.DATA/'config.json', [])
        engine.last_config_check = 0
        engine.config_stamp = None
        engine.reload_config()
        check('无效配置不改变最后有效启停状态', engine.running is False and read('runtime/control.json')['auto_start'] is False)

        failure = {'pid':999, 'account':{'player':{'id':1001}}, 'connected':False, 'phase':'waiting_session', 'time_unix':1000,
            'connection':{'known':True, 'fatal':True, 'fatal_kind':'retry',
                'intentional_shutdown':False, 'login_retry_pending':False, 'fatal_restart_requested':False},
            'pending_requests':{}, 'native_busy':{'skill':False, 'equipment':False,
                'enhancement':False, 'socket':False, 'loot':False, 'craft':0, 'disassembly':0}}
        for enabled in (True, False):
            engine.update_config({'auto_start': enabled, 'auto_relaunch': True})
            engine.pending = None
            engine.next_recovery_at = 0
            with patch.object(runtime, 'discover_game', return_value=game), \
                    patch.object(runtime, 'install', return_value=False), \
                    patch.object(runtime, 'snapshot', return_value=deepcopy(failure)), \
                    patch.object(runtime, 'game_processes', return_value=[]) as processes, \
                    patch.object(runtime, 'close_gracefully') as close, patch.object(runtime, 'launch') as launch:
                engine.boot()
                check(f'启动流程透传保存的开启状态{enabled}', launch.call_count == 1 and launch.call_args.kwargs == {'auto_start': enabled})
                launch.reset_mock()
                engine.next_recovery_at = 0
                engine.recover_connection()
                check(f'游戏缺席恢复透传开启状态{enabled}', launch.call_count == 1 and launch.call_args.kwargs == {'auto_start': enabled})
                launch.reset_mock()
                engine.next_recovery_at = 0
                engine.recovery_candidate = None
                engine.snapshot = deepcopy(failure)
                processes.return_value = [process]
                clock.return_value = 200
                engine.recover_connection()
                clock.return_value = 231
                engine.recover_connection()
                check(f'必要终止恢复透传开启状态{enabled}', launch.call_count == 1 and launch.call_args.kwargs == {'auto_start': enabled}
                      and close.call_args.kwargs == {'expected_pid':999, 'expected_create_time':900})
                launch.reset_mock()
                close.reset_mock()
                engine.boot()
                check(f'接回已有游戏无需重启{enabled}', not launch.called and not close.called)
