"""One scheduler and journal per game instance, with a cached web overview."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil
import threading
import time
import uuid
from . import runtime, sandbox
from .engine import Engine, read_json
from .policy import normalize_config


class Manager:
    def __init__(self):
        runtime.DATA.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.hotkeys = {}
        self.engines = {}
        self.records = {}
        self.views = {}
        self.workers = {}
        self.threaded = False
        self.selected = ''
        self.game = None
        self.error = ''
        self.last_scan = 0
        self.started = time.time()
        self.template = normalize_config(read_json(runtime.DATA/'config.json', {}))
        saved = read_json(runtime.DATA/'instances.json', {}) or {}
        # The first upgrade explicitly turns recovery off, preserving every
        # other preference. Later user changes are respected per instance.
        self.first_upgrade = saved.get('version') != 1
        self.selected = saved.get('selected', '')
        self.saved_records = saved.get('instances', []) if isinstance(saved.get('instances'), list) else []
        if self.first_upgrade:
            self.template['auto_relaunch'] = False
            runtime.atomic_json(runtime.DATA/'config.json', self.template)
        self.empty = Engine(runtime.DATA/'console', {'sandbox':'', 'directory':runtime.DATA/'console/runtime', 'pid':None, 'created':None})
        self.empty.running = False
        self.empty.status = '请先启动本机或沙盒内的游戏'
        self.empty.config['auto_relaunch'] = False
        self.empty_view = self.empty.public_state()

    def persist(self):
        with self.lock:
            for engine in list(self.engines.values()):
                with engine.lock: engine.persist()
            runtime.atomic_json(runtime.DATA/'instances.json', {
                'version': 1, 'selected': self.selected,
                'instances': list(self.records.values())})

    def _new_engine(self, record, target, migrate=False):
        ident = record['id']
        directory = runtime.DATA/'instances'/ident
        directory.mkdir(parents=True, exist_ok=True)
        if not (directory/'config.json').exists():
            runtime.atomic_json(directory/'config.json', self.template)
        if migrate:
            for name in ('scheduler.json',):
                source = runtime.DATA/name
                if source.is_file() and not (directory/name).exists():
                    shutil.copy2(source, directory/name)
        engine = Engine(directory, target)
        if self.first_upgrade and engine.config['auto_relaunch']:
            engine.update_config({'auto_relaunch': False})
        engine.game = self.game
        engine.booted = True
        engine.refresh_connection(force=True)
        self.engines[ident] = engine
        self.records[ident] = record
        if self.threaded:
            worker = threading.Thread(target=engine.run, name='instance-'+str(record.get('pid')), daemon=True)
            self.workers[ident] = worker
            worker.start()
        return engine

    def scan(self, force=False):
        now = time.monotonic()
        if not force and now-self.last_scan < 5: return
        self.last_scan = now
        game = runtime.discover_game()
        if game is None:
            self.error = '未发现游戏安装目录，请先启动一次游戏。'
            return
        if game != self.game:
            runtime.install(game)
            self.game = game
        targets = []
        for process in runtime.game_processes(game):
            try:
                target = sandbox.connection(process, runtime.DATA)
                runtime.install_connection(target)
                targets.append(target)
            except (OSError, RuntimeError, runtime.psutil.Error): continue
        counts = Counter(str(t['directory']).casefold() for t in targets)
        if self.saved_records:
            for record in self.saved_records:
                if not isinstance(record, dict): continue
                ident = record.get('id', '')
                if not isinstance(ident, str) or len(ident) != 32 or any(c not in '0123456789abcdef' for c in ident): continue
                try:
                    target = next((t for t in targets if (t['pid'], t['created']) == (record.get('pid'), record.get('created'))), None)
                    if target is not None and counts[str(target['directory']).casefold()] > 1: continue
                    if target is None:
                        target = sandbox.connection(None, runtime.DATA, record.get('sandbox', ''))
                        old_channel = target['directory']/'instances'/str(record.get('pid'))
                        if old_channel.is_dir(): target['directory'] = old_channel
                    self._new_engine(record, target)
                except (OSError,RuntimeError): continue
            self.saved_records = []
        if not targets and not self.engines:
            target = sandbox.connection(None, runtime.DATA)
            self._new_engine({'id':uuid.uuid4().hex, 'sandbox':'', 'pid':None, 'created':None}, target)
        live = set()
        for target in targets:
            # Legacy workers share a directory. Only revision 18's PID channel
            # permits two processes in the same box to receive commands.
            if counts[str(target['directory']).casefold()] > 1:
                self.error = '同一环境中的旧桥接共享目录，等待桥接热更新后接入多实例。'
                continue
            identity = (target['pid'], target['created'])
            ident = next((k for k, r in self.records.items()
                          if (r.get('pid'), r.get('created')) == identity), '')
            if not ident:
                record = next((r for r in self.saved_records if isinstance(r, dict)
                    and isinstance(r.get('id'), str) and len(r['id']) == 32
                    and all(c in '0123456789abcdef' for c in r['id'])
                    and (r.get('pid'), r.get('created')) == identity), None)
                if record is None:
                    # Reuse an offline slot only when its box has one live PID.
                    offline = [r for k, r in self.records.items() if k not in live
                               and r.get('sandbox', '') == target['sandbox']
                               and not any(t['pid'] == r.get('pid') and t['created'] == r.get('created') for t in targets)]
                    record = dict(offline[0]) if len(offline) == 1 and sum(t['sandbox'] == target['sandbox'] for t in targets) == 1 else {'id': uuid.uuid4().hex}
                record.update(pid=target['pid'], created=target['created'], sandbox=target['sandbox'])
                ident = record['id']
                if ident not in self.engines:
                    preferred = read_json(runtime.DATA/'scheduler.json', {}) or {}
                    migrate = self.first_upgrade and not self.engines and target['sandbox'] == preferred.get('sandbox', '')
                    self._new_engine(record, target, migrate)
                else:
                    self.records[ident] = record
            engine = self.engines[ident]
            with engine.lock:
                engine.fixed_target = target
                engine.game = game
            live.add(ident)
        for ident, engine in self.engines.items():
            if ident not in live:
                with engine.lock:
                    engine.fixed_target = {**engine.fixed_target, 'pid': None, 'created': None}
        self.error = '' if len(live) == len(targets) else self.error
        if self.selected not in self.engines and self.engines: self.selected = next(iter(self.engines))
        runtime.atomic_json(runtime.DATA/'instances.json', {
            'version': 1, 'selected': self.selected, 'instances': list(self.records.values())})

    def target_engine(self, ident=None):
        with self.lock:
            selected = self.selected if ident is None else ident
            if selected not in self.engines: raise ValueError('实例已离线或尚未选择，请刷新实例列表。')
            return self.engines[selected]

    def select(self, ident):
        engine = self.target_engine(ident)
        with self.lock: self.selected = ident
        return engine

    def refresh(self):
        with self.lock: self.last_scan = 0

    def handle_hotkey(self, key):
        try: self.target_engine().handle_hotkey(key)
        except ValueError: pass

    def run_once(self):
        with self.lock: self.scan()
        for ident, engine in list(self.engines.items()):
            try:
                if self.threaded:
                    view = dict(engine.view or {})
                    if not view: continue
                else:
                    engine.tick()
                    view = engine.public_state()
            except Exception as exc:
                with engine.lock:
                    engine.error = f'{type(exc).__name__}: {exc}'
                    engine.status = '等待恢复'
                    if not engine.logs or engine.logs[0].get('message') != engine.error:
                        engine.log('system', engine.error, 'error')
                view = engine.public_state()
            view['instance_id'] = ident
            view['hotkeys'] = dict(self.hotkeys)
            with self.lock: self.views[ident] = view

    def run(self):
        self.threaded = True
        while not self.stop_event.is_set():
            try: self.run_once()
            except Exception as exc:
                with self.lock: self.error = f'{type(exc).__name__}: {exc}'
            self.stop_event.wait(1)
        self.stop()

    def stop(self):
        self.stop_event.set()
        for engine in list(self.engines.values()): engine.stop_event.set()

    def public_state(self):
        with self.lock:
            view = dict(self.views.get(self.selected, self.empty_view))
            if self.selected in self.engines:
                engine = self.engines[self.selected]
                # Configuration is replaced atomically, so HTTP need not wait
                # behind a scheduler doing file I/O or native reconciliation.
                view['config'] = engine.config
                view['running'] = engine.running
            if time.time()-view.get('snapshot_time', 0) > 8:
                view['connected'] = False
            rows = []
            for ident, record in self.records.items():
                state = self.views.get(ident, {})
                rows.append({'id': ident, 'sandbox': record.get('sandbox', ''),
                    'pid': record.get('pid'), 'connected': state.get('connected', False) and time.time()-state.get('snapshot_time',0) <= 8,
                    'running': state.get('running', False), 'status': state.get('status', '正在读取'),
                    'auto_relaunch': state.get('config', {}).get('auto_relaunch', False)})
            view['instances'] = rows
            view['instance_id'] = self.selected
            view['manager_error'] = self.error
            view['hotkeys'] = dict(self.hotkeys)
            view['uptime'] = time.time()-self.started
            return view
