"""Sandbox IPC integration checks. No live game or Sandboxie state is changed."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile


def run(check):
    from wallet_assistant import runtime, sandbox
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import Action

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)/'host'), \
            patch('wallet_assistant.engine.time.time', return_value=1000), \
            patch('wallet_assistant.engine.time.monotonic', return_value=100):
        root = Path(temporary)/'box'
        channel = root/'user/current/AppData/Local/WalletHeroesAssistant/runtime'
        launcher = root/'Start.exe'
        launcher.parent.mkdir(parents=True)
        launcher.write_bytes(b'fixture')
        process = SimpleNamespace(pid=999, create_time=lambda:900)
        game = Path(temporary)/'game'
        logical_game = Path('D:/SteamLibrary/steamapps/common/Desktop Wallet Heroes')
        logical_exe = logical_game/runtime.GAME_EXE
        shadow_exe = root/'drive/D/SteamLibrary/steamapps/common/Desktop Wallet Heroes'/runtime.GAME_EXE
        updated = SimpleNamespace(pid=999, create_time=lambda:900, info={
            'name':runtime.GAME_EXE, 'exe':str(shadow_exe), 'cmdline':[str(logical_exe)]})
        helper = SimpleNamespace(pid=999, info={**updated.info, 'cmdline':[str(logical_exe),'--','--bi-loading-helper']})
        with patch.object(sandbox, 'process_box', side_effect=lambda pid:'fixture' if pid==999 else ''), \
                patch.object(sandbox, 'box_location', return_value=(root, launcher)):
            check('更新后的沙盒副本映射回虚拟安装路径', sandbox.virtual_path(shadow_exe,999)==logical_exe)
            check('沙盒未复制时保留原始路径', sandbox.virtual_path(logical_exe,999)==logical_exe)
            check('普通进程不按沙盒目录推断', sandbox.virtual_path(shadow_exe,998)==shadow_exe)
            outsider = root.parent/'otherbox'/shadow_exe.relative_to(root)
            check('其他沙盒副本不会冒用当前沙盒映射', sandbox.virtual_path(outsider,999)==outsider)
            with patch.dict(runtime.os.environ, {'WALLET_HEROES_GAME':''}), \
                    patch.object(runtime, 'game_candidates', return_value=[updated]):
                check('启动助手发现游戏时不缓存物理沙盒副本路径', runtime.discover_game()==logical_game)
            with patch.object(runtime, 'game_candidates', return_value=[updated,helper]), \
                    patch.object(runtime.subprocess, 'Popen') as popen:
                check('游戏更新为沙盒副本后仍识别原安装的当前实例', runtime.game_processes(logical_game)==[updated])
                check('更新后的在运行游戏不被误判为缺席而重复启动', runtime.launch(logical_game,sandbox='fixture') is False and not popen.called)
                check('更新后连接仍绑定当前PID及沙盒目录', runtime.connection_for(logical_game)['pid']==999
                      and runtime.connection_for(logical_game)['directory']==channel)
            selected = sandbox.connection(process, runtime.DATA)
            check('沙盒目录由进程映射获取且不依赖固定盘符', selected['directory']==channel
                  and selected['sandbox']=='fixture' and selected['pid']==999)
            with patch.object(sandbox.os, 'getpid', return_value=999):
                check('助手与游戏同在沙盒时使用虚拟目录', sandbox.connection(process, runtime.DATA)['directory']==runtime.DATA/'runtime')
            with patch.object(runtime, 'game_processes', return_value=[process,process]):
                try: runtime.connection_for(game)
                except RuntimeError: refused=True
                else: refused=False
                check('多个游戏实例拒绝自动接管', refused)

        normal = {**selected, 'sandbox':'', 'directory':runtime.DATA/'runtime', 'pid':998}
        engine = Engine()
        engine.game = game
        engine.booted = True
        engine.snapshot = {'pid':998, 'revision':17, 'account':{'player':{'id':1001}}}
        engine.dispatch(Action('mail', 'mail_refresh', [], 'fixture mail list', 20))
        pending = engine.pending
        old_command = runtime.DATA/'runtime/commands'/pending['command_file']
        with patch.object(runtime, 'connection_for', return_value=selected):
            engine.refresh_connection(force=True)
        check('连接沙盒前隔离旧目录请求并移除旧命令', engine.pending is None and not old_command.exists())
        check('沙盒收到原配置而配置文件保留本机',
              json.loads((channel/'control.json').read_text(encoding='utf8'))==engine.config
              and (runtime.DATA/'config.json').exists())
        check('保存沙盒选择供下次启动恢复', json.loads((runtime.DATA/'scheduler.json').read_text(encoding='utf8'))['sandbox']=='fixture')

        fresh = {'pid':999, 'revision':17, 'time_unix':1000, 'connected':True, 'phase':'ready',
                 'account':{'player':{'id':1001}}, 'pending_requests':{}}
        runtime.atomic_json(channel/'snapshot.json', fresh)
        check('从沙盒读取当前进程快照', engine.read_snapshot()['connected'] is True)
        for label, changed in [
            ('其他PID', {**fresh,'pid':998}),
            ('PID复用前数据', {**fresh,'time_unix':899}),
            ('未来时间', {**fresh,'time_unix':1002}),
            ('无效时间', {**fresh,'time_unix':float('nan')}),
            ('非对象', []),
        ]:
            runtime.atomic_json(channel/'snapshot.json', changed)
            check(label+'无法作为有效沙盒连接', engine.read_snapshot().get('connected') is False)
        runtime.atomic_json(channel/'snapshot.json', {**fresh,'time_unix':990})
        check('过期沙盒快照仍标记断线', engine.read_snapshot()['phase']=='stale')
        runtime.atomic_json(channel/'snapshot.json', fresh)
        engine.snapshot = engine.read_snapshot()
        engine.cooldowns = {}
        engine.dispatch(Action('mail', 'mail_refresh', [], 'fixture sandbox mail', 20))
        task = engine.pending
        check('命令只发布到已绑定沙盒', (channel/'commands'/task['command_file']).is_file()
              and not (runtime.DATA/'runtime/commands'/task['command_file']).exists())
        runtime.atomic_json(channel/'results'/f"{task['id']}.json", {
            'status':'submitted','account_id':1001,'request_ids':[17], 'answer':{'ok':True}, 'time_unix':1000})
        runtime.atomic_json(channel/'receipt-999-1001-17.json', {
            'ok':True,'time_unix':1000,'response':{'ok':True}})
        (channel/'commands'/task['command_file']).unlink()
        with patch('wallet_assistant.engine.time.time', return_value=1003):
            engine.reconcile()
        check('沙盒原生回执可完成核验', engine.pending is None and engine.success_count==1)

        engine.dispatch(Action('mail', 'mail_refresh', [], 'fixture restart', 20))
        old_command = channel/'commands'/engine.pending['command_file']
        restarted = Engine()
        restarted.game = game
        with patch.object(sandbox, 'process_box', return_value=''), \
                patch.object(sandbox, 'box_location', return_value=(root,launcher)), \
                patch.object(runtime, 'connection_for', return_value=normal):
            restarted.refresh_connection(force=True)
        check('重启后切换环境也能清理已确认的原沙盒命令', restarted.pending is None and not old_command.exists())
        engine.pending = None

        public = engine.public_state()
        check('页面状态包含沙盒名称与绑定PID', public['connection']['sandbox']=='fixture' and public['connection']['pid']==999)
        with patch.object(runtime, 'connection_for', side_effect=RuntimeError('multiple instances')):
            try: engine.refresh_connection(force=True)
            except RuntimeError: pass
        try: engine.refresh_connection()
        except RuntimeError: retained=True
        else: retained=False
        check('识别失败后持续阻止调度而不回落旧快照', retained and not engine.snapshot and not engine.actions)
        with patch.object(runtime, 'connection_for', return_value=normal):
            engine.refresh_connection(force=True)
        check('切回普通游戏恢复本机通道', engine.runtime_dir==runtime.DATA/'runtime' and not engine.connection_error)

        with patch.object(runtime, 'game_processes', return_value=[]), \
                patch.object(sandbox, 'box_location', return_value=(root,launcher)), \
                patch.object(runtime.subprocess, 'Popen') as popen:
            runtime.launch(game, auto_start=True, sandbox='fixture')
            check('沙盒重启经过原沙盒启动器并透传自动开始', popen.call_args.args[0]==[
                str(launcher),'/box:fixture',str(game/runtime.GAME_EXE),'--','--auto-start'])
        engine.connection['sandbox']='fixture'
        with patch.object(runtime, 'launch') as launch:
            engine.launch_game()
            check('调度恢复沿用沙盒而非启动到沙盒外', launch.call_args.kwargs=={'auto_start':True,'sandbox':'fixture'})
