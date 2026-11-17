"""Exercise two native IPC sessions and independent schedulers without a game."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import json
import tempfile
import threading
import time
import urllib.request
import urllib.error


def run(check):
    from wallet_assistant import runtime, sandbox, VERSION
    from wallet_assistant.manager import Manager
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import Action
    from wallet_assistant.server import Server
    original_launch = runtime.launch
    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)/'host'):
        game = Path(temporary)/'game'
        p1 = SimpleNamespace(pid=101, create_time=lambda: time.time()-60)
        p2 = SimpleNamespace(pid=102, create_time=lambda: time.time()-60)
        created = time.time()-60
        p1.create_time = p2.create_time = lambda: created
        channels = {101: Path(temporary)/'local/instances/101', 102: Path(temporary)/'box/instances/102'}
        def connection(process, data, preferred=''):
            if process is None:
                return {'sandbox':preferred, 'directory':data/'runtime', 'pid':None, 'created':None}
            return {'sandbox':'' if process.pid == 101 else 'box2', 'directory':channels[process.pid],
                    'pid':process.pid, 'created':process.create_time()}
        def export(pid, account):
            runtime.atomic_json(channels[pid]/'snapshot.json', {
                'revision':18, 'pid':pid, 'time_unix':time.time(), 'connected':True, 'phase':'ready',
                'account':{'player':{'id':account}}, 'pending_requests':{}, 'native_busy':{}, 'inventory':{}})
        for pid, account in ((101,1001),(102,1002)): export(pid, account)
        with patch.object(runtime,'discover_game',return_value=game), \
                patch.object(runtime,'install'), patch.object(runtime,'install_connection'), \
                patch.object(runtime,'game_processes',return_value=[p1,p2]) as processes, \
                patch.object(sandbox,'connection',side_effect=connection), patch.object(runtime,'launch') as launch:
            manager = Manager()
            manager.run_once()
            check('本机与沙盒同时发现并各自连接', len(manager.engines)==2 and all(e.snapshot['connected'] for e in manager.engines.values()))
            engines = list(manager.engines.values())
            check('多实例拥有独立配置与持久日志目录', engines[0].data_dir != engines[1].data_dir)
            check('首次升级默认关闭每个实例的自动重连', all(e.config['auto_relaunch'] is False for e in engines))
            engines[0].update_config({'auto_start':False, 'tick_seconds':12})
            check('一个实例暂停和参数修改不影响另一个', not engines[0].running and engines[1].running and engines[1].config['tick_seconds']==6)
            for e in engines:
                e.dispatch(Action('mail','mail_refresh',[],'Read mailbox',20))
            tasks = [e.pending for e in engines]
            check('多实例能够各自保持一个并行原生请求', all(tasks) and tasks[0]['id']!=tasks[1]['id'])
            check('命令不会写入另一个实例目录', all((e.runtime_dir/'commands'/t['command_file']).exists() for e,t in zip(engines,tasks)))
            task=tasks[0]; engine=engines[0]
            runtime.atomic_json(engine.runtime_dir/'results'/f"{task['id']}.json", {
                'status':'submitted','account_id':1002,'request_ids':[99], 'answer':{'ok':True}, 'time_unix':time.time()-3})
            engine.reconcile()
            check('其他实例账号回执不能结算当前请求', engine.pending is None and engine.success_count==0 and engines[1].pending is tasks[1])
            manager.selected = next(iter(manager.engines))
            manager.persist()
            restored=Manager(); restored.run_once()
            check('重启恢复两个实例及各自暂停偏好', len(restored.engines)==2 and [e.running for e in restored.engines.values()]==[False,True])
            check('重启保留另一个实例请求且不重发新ID', list(restored.engines.values())[1].pending['id']==tasks[1]['id'])
            processes.return_value=[]
            manager.scan(force=True)
            for e in manager.engines.values(): e.tick()
            check('默认关闭重连时所有实例退出均不自动启动', not launch.called and all(not e.snapshot.get('connected') for e in manager.engines.values()))
            check('界面切换不暂停其他实例', manager.select(list(manager.engines)[1]) is engines[1] and engines[1].running)
            server=Server(manager,port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            def post(path,value):
                request=urllib.request.Request(server.origin+path,data=json.dumps(value).encode(),headers={
                    'Origin':server.origin,'X-CSRF-Token':server.csrf,'Content-Type':'application/json'})
                try:
                    with urllib.request.urlopen(request,timeout=3) as response: return response.status
                except urllib.error.HTTPError as exc: return exc.code
            try:
                check('缺少实例身份的写请求拒绝执行', post('/api/pause',{})==409 and engines[1].running)
                check('伪造实例身份无法控制其他账号', post('/api/pause',{'_instance_id':'missing'})==409 and engines[1].running)
                check('写请求按明确实例路由而非页面当前选择', post('/api/pause',{'_instance_id':list(manager.engines)[0]})==200 and engines[1].running)
                check('网页服务健康检查在多实例下可用', json.load(urllib.request.urlopen(server.origin+'/api/health'))['version']==VERSION)
            finally: server.shutdown(); server.server_close(); thread.join(3)
            with patch.object(runtime, 'DATA', Path(temporary)/'same-box-host'), \
                    patch.object(sandbox, 'connection', side_effect=lambda p,d,preferred='': {**connection(p,d,preferred), 'sandbox':'shared'}):
                processes.return_value=[p1,p2]
                shared=Manager(); shared.run_once()
                check('同一沙盒可接入两个独立PID通道', len(shared.engines)==2 and len({e.runtime_dir for e in shared.engines.values()})==2)
                check('同一沙盒的两个账号均可独立读取', {e.account_id for e in shared.engines.values()}=={1001,1002})
            with patch.object(sandbox,'process_box',return_value=''), patch.object(runtime.subprocess,'Popen') as popen, \
                    patch.object(sandbox,'box_location',return_value=(Path(temporary),Path(temporary)/'Start.exe')):
                (Path(temporary)/'Start.exe').write_bytes(b'fixture')
                check('本机游戏运行不会阻止另一个沙盒手动启动', original_launch(game,sandbox='newbox') and popen.called)
        engine=Engine(runtime.DATA/'cache-check')
        runtime.atomic_json(engine.runtime_dir/'catalog.json',{'Items':[{'id':1}]})
        with patch('wallet_assistant.engine.read_json',wraps=__import__('wallet_assistant.engine',fromlist=['read_json']).read_json) as read:
            first=engine.cached_json('catalog.json')
            second=engine.cached_json('catalog.json')
            check('静态JSON不变时只解析一次', read.call_count==1 and first is second)
            runtime.atomic_json(engine.runtime_dir/'catalog.json',{'Items':[{'id':2}]})
            check('同长度原子替换会使JSON缓存失效', engine.cached_json('catalog.json')['Items'][0]['id']==2 and read.call_count==2)
            (engine.runtime_dir/'catalog.json').unlink()
            check('文件删除不能继续使用旧缓存', engine.cached_json('catalog.json')=={})
        engine.update_config({'auto_relaunch':False})
        with patch.object(runtime,'discover_game',return_value=game), patch.object(runtime,'install'), \
                patch.object(runtime,'game_processes',return_value=[]), patch.object(runtime,'launch') as launch:
            engine.boot()
            check('自动重连关闭覆盖首次启动路径', not launch.called)
        # A deliberately slow scheduler must not block another scheduler or HTTP.
        manager = Manager(); manager.game = game; manager.threaded=True
        release=threading.Event()
        target={'sandbox':'','directory':runtime.DATA/'slow/runtime','pid':None,'created':None}
        with patch.object(Engine,'tick',side_effect=lambda:release.wait(.2)):
            a=manager._new_engine({'id':'a'*32,'sandbox':'','pid':None},target)
            b=manager._new_engine({'id':'b'*32,'sandbox':'b','pid':None},{**target,'directory':runtime.DATA/'fast/runtime'})
            check('每个实例使用独立调度线程', len(manager.workers)==2 and all(w.is_alive() for w in manager.workers.values()))
            start=time.perf_counter(); manager.public_state()
            check('网页读取缓存无需等待其他实例调度锁', time.perf_counter()-start<.1)
            manager.stop(); release.set()
            for worker in manager.workers.values(): worker.join(3)
            check('停止助手会关闭所有实例调度线程', all(not w.is_alive() for w in manager.workers.values()))
    selection_checks(check)


def selection_checks(check):
    """Reproduce stale selected PIDs across restarts with conflicting preferences."""
    from wallet_assistant import runtime, sandbox
    from wallet_assistant.manager import Manager
    from wallet_assistant.policy import normalize_config

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)/'host'):
        game = Path(temporary)/'game'
        created = time.time()-60
        p1 = SimpleNamespace(pid=201, create_time=lambda: created)
        p2 = SimpleNamespace(pid=202, create_time=lambda: created+1)
        records = [
            {'id':'a'*32, 'sandbox':'box', 'pid':101, 'created':created-100},
            {'id':'b'*32, 'sandbox':'', 'pid':102, 'created':created-90},
            {'id':'c'*32, 'sandbox':'box', 'pid':103, 'created':created-80},
            {'id':'d'*32, 'sandbox':'box', 'pid':201, 'created':created},
        ]
        for record in records:
            runtime.atomic_json(runtime.DATA/'instances'/record['id']/'config.json', normalize_config({
                'auto_start': record['id']=='a'*32, 'auto_relaunch':False,
                'tick_seconds': 12 if record['id']=='d'*32 else 6}))
        runtime.atomic_json(runtime.DATA/'instances.json', {'version':1, 'selected':'a'*32, 'instances':records})

        def connection(process, data, preferred=''):
            pid = process.pid if process else None
            return {'sandbox':'box' if process else preferred, 'directory':data/'runtime'/'instances'/str(pid),
                    'pid':pid, 'created':process.create_time() if process else None}

        def export(process):
            target=connection(process,runtime.DATA)
            runtime.atomic_json(target['directory']/'snapshot.json', {'revision':18, 'pid':process.pid,
                'time_unix':time.time(), 'connected':True, 'phase':'ready', 'account':{'player':{'id':1001}},
                'pending_requests':{}, 'native_busy':{}, 'inventory':{}})

        export(p1); export(p2)
        with patch.object(runtime,'discover_game',return_value=game), patch.object(runtime,'install'), \
                patch.object(runtime,'install_connection'), patch.object(runtime,'game_processes',return_value=[p1]) as processes, \
                patch.object(sandbox,'connection',side_effect=connection), patch.object(runtime,'launch') as launch:
            manager=Manager(); manager.run_once()
            state=manager.public_state()
            check('多个旧PID残留时页面自动跟随同沙盒唯一在运行实例', manager.selected=='d'*32 and state['connected'])
            check('自动选择保留真实实例暂停与参数且不复制旧实例开关', not state['running']
                  and state['config']['tick_seconds']==12 and manager.engines['a'*32].running)
            check('旧PID卡片明确退出且不能借用在线快照', all(row['pid'] is None and not row['connected']
                  and row['status']=='游戏未运行' and row['last_pid'] in (101,102,103)
                  for row in state['instances'] if row['id']!='d'*32))
            manager.persist(); restarted=Manager(); restarted.run_once()
            check('重启助手后保留在线选择且不新增重复实例', restarted.selected=='d'*32
                  and len(restarted.engines)==4 and restarted.public_state()['connected'])
            manager.select('a'*32); manager.scan(force=True)
            check('手动查看离线实例不会被下一次进程检测抢走', manager.selected=='a'*32)
            manager.select('d'*32); processes.return_value=[p2]
            manager.scan(force=True)
            check('在线实例退出并换PID后选择跟随同环境新实例', manager.selected in manager.live
                  and manager.records[manager.selected]['pid']==202)
            check('刚退出的选中实例跨PID复用原配置目录与暂停偏好', manager.selected=='d'*32
                  and len(manager.engines)==4 and not manager.target_engine().running
                  and manager.target_engine().config['tick_seconds']==12)
            check('PID切换尚未刷新时页面拒绝缓存中的旧进程连接', not manager.public_state()['connected'])
            manager.run_once()
            check('新进程只绑定自己的通信目录且旧请求不跨实例重放', manager.target_engine().connection['pid']==202
                  and manager.target_engine().runtime_dir.name=='202' and not manager.target_engine().pending)
            processes.return_value=[]; manager.scan(force=True)
            p3=SimpleNamespace(pid=203,create_time=lambda:created+2)
            export(p3); processes.return_value=[p3]
            manager.scan(force=True); manager.run_once()
            check('游戏退出一段时间后重开仍沿用选中实例暂停与参数', manager.selected=='d'*32
                  and len(manager.engines)==4 and not manager.target_engine().running
                  and manager.target_engine().config['tick_seconds']==12 and manager.public_state()['connected'])
            manager.persist()
            p4=SimpleNamespace(pid=204,create_time=lambda:created+3)
            export(p4); processes.return_value=[p4]
            rebooted=Manager(); rebooted.run_once()
            check('助手和游戏同时重启换PID也保留原配置且不累积实例', rebooted.selected=='d'*32
                  and len(rebooted.engines)==4 and not rebooted.target_engine().running
                  and rebooted.target_engine().config['tick_seconds']==12 and rebooted.public_state()['connected'])
            check('连接选择修复不启动或重启游戏', not launch.called)
            # A stored local-game slot must not silently redirect controls to a sandbox.
            runtime.atomic_json(runtime.DATA/'instances.json', {'version':1, 'selected':'b'*32, 'instances':records})
            local=Manager(); local.run_once()
            check('已选本机离线实例不会自动切换到其他沙盒', local.selected=='b'*32)
            runtime.atomic_json(runtime.DATA/'instances.json', {'version':1, 'selected':'a'*32, 'instances':records})
            processes.return_value=[p1,p2]
            concurrent=Manager(); concurrent.run_once()
            check('同沙盒两个实时PID时不猜测替代选中实例', concurrent.selected=='a'*32 and len(concurrent.live)==2)
            # A console created before any game exists has no process identity to preserve.
            with patch.object(runtime,'DATA',Path(temporary)/'first-launch'):
                processes.return_value=[]
                first=Manager(); first.run_once()
                processes.return_value=[p1]
                export(p1); first.scan(force=True); first.run_once()
                check('先开助手后开沙盒游戏可自动选中首次在线实例', first.selected in first.live
                      and first.public_state()['connected'])
