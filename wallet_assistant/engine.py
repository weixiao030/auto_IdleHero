"""Durable single-flight scheduler. Only native replies count as successful operations."""
from __future__ import annotations
from collections import deque
from dataclasses import asdict
from pathlib import Path
import json
import math
import os
import threading
import time
import uuid
from . import runtime
from .policy import Action, MODULES, normalize_config, plan, active_characters, equipped_ids, iid, power, reserve, capacity_goal, growth_budget, empty_socket_count

def read_json(path, fallback=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError): return fallback

def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)

def snapshot_account_id(snapshot):
    account = snapshot.get('account')
    player = account.get('player') if isinstance(account, dict) else None
    value = player.get('id') if isinstance(player, dict) else None
    return value if type(value) is int and value > 0 else None

def valid_maintenance(job, account_id=None):
    return (isinstance(job, dict) and job.get('module') in ('enhancement', 'socket')
            and type(job.get('id')) is int and job['id'] > 0
            and isinstance(job.get('owner'), str) and bool(job['owner'])
            and type(job.get('account_id')) is int and job['account_id'] > 0
            and (account_id is None or job['account_id'] == account_id))


def opportunities_ready(snapshot, opportunities, now=None):
    """Reject an opportunity export that predates the current authoritative snapshot."""
    account_id = snapshot_account_id(snapshot)
    if snapshot.get('revision', 0) >= 15 and (account_id is None
            or type(opportunities.get('account_id')) is not int or opportunities['account_id'] != account_id):
        return False
    if snapshot.get('startup_selection_pending'):
        return True
    if opportunities.get('pid') != snapshot.get('pid'):
        return False
    try:
        current = float(snapshot.get('time_unix', 0))
        exported = float(opportunities.get('time_unix', 0))
    except (TypeError, ValueError):
        return False
    now = time.time() if now is None else now
    if not exported or now - exported > 15:
        return False
    return current <= 0 or current - exported <= 8


def maintenance_context_ready(snapshot):
    if snapshot.get('connected') is not True or snapshot.get('phase') != 'ready': return False
    stamp = snapshot.get('time_unix')
    if not finite_number(stamp) or not 0 <= time.time()-stamp <= 8: return False
    inv = snapshot.get('inventory')
    if not isinstance(inv, dict) or inv.get('server_inventory_mutation_safe') is not True: return False
    busy = snapshot.get('native_busy')
    if not isinstance(busy, dict): return False
    for key in ('skill', 'equipment', 'enhancement', 'socket', 'loot'):
        if busy.get(key) is not False: return False
    for key in ('craft', 'disassembly'):
        if type(busy.get(key)) is not int or busy[key] != 0: return False
    requests = snapshot.get('pending_requests')
    if not isinstance(requests, dict) or requests: return False
    if not isinstance(inv.get('items'), list): return False
    equipped = inv.get('equipped_equipment_ids_by_char')
    return isinstance(equipped, dict) and all(isinstance(value, dict) for value in equipped.values())


class Engine:
    def __init__(self, data_dir=None, target=None):
        self.data_dir = Path(data_dir) if data_dir else runtime.DATA
        self.fixed_target = target
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.config = normalize_config(read_json(self.data_dir/'config.json', {}))
        self.running = self.config['auto_start']
        self.state = read_json(self.data_dir/'scheduler.json', {}) or {}
        self.runtime_dir = target['directory'] if target else runtime.DATA/'runtime'
        self.connection = {'sandbox': self.state.get('sandbox', ''), 'directory': self.runtime_dir}
        self.last_connection_check = 0
        self.connection_bound = False
        self.connection_error = ''
        self.pending = self.state.get('pending')
        self.maintenance = self.state.get('maintenance')
        self.cooldowns = self.state.get('cooldowns', {})
        self.module_last_run = self.state.get('module_last_run', {})
        stored_account_id = self.state.get('account_id')
        self.account_id = stored_account_id if type(stored_account_id) is int and stored_account_id > 0 else None
        saved_accounts = self.state.get('account_states', {})
        self.account_states = saved_accounts if isinstance(saved_accounts, dict) else {}
        self.success_count = self.state.get('success_count', 0)
        self.logs = deque(self.state.get('logs', []), maxlen=160)
        self.metrics = deque(self.state.get('metrics', []), maxlen=240)
        if self.maintenance is not None:
            if not valid_maintenance(self.maintenance):
                self.maintenance = None
                self.log('system', '持久维护记录缺少可靠账号身份，已隔离以避免跨账号操作装备', 'warning')
            else:
                self.maintenance['phase'] = 'restore'
        self.last_sample = 0
        self.last_dispatch = 0
        self.started = time.time()
        self.status = '正在启动'
        self.error = ''
        self.game = None
        self.snapshot = {}
        self.opportunities = {}
        self.catalog = {}
        self.actions = []
        self.file_cache = {}
        self.last_plan = 0
        self.view = None
        self.stop_event = threading.Event()
        self.booted = False
        self.disconnected_since = None
        self.recovery_candidate = None
        saved_recovery = self.state.get('next_recovery_at', 0)
        self.next_recovery_at = max(0, saved_recovery) if finite_number(saved_recovery) else 0
        self.inspection_requested = False
        self.last_config_check = 0
        self.config_stamp = None
        self.hotkeys = {}
        # Old releases quarantined this read-only list query like a spend. A
        # persisted short deadline makes this migration stable across restarts.
        mail_until = self.cooldowns.get('mail_refresh:[]', 0)
        now = time.time()
        if finite_number(mail_until) and mail_until > now+300:
            self.cooldowns['mail_refresh:[]'] = now+120
            self.log('mail', '已恢复邮件列表同步，等待两分钟后重新读取')
            self.persist()
        self.publish_config()
        self.log('system', '助手启动，正在检测游戏与账号状态')
        if self.maintenance: self.persist()

    def log(self, module, message, level='info', **extra):
        row = {'time': time.time(), 'module': module, 'message': message, 'level': level, **extra}
        self.logs.appendleft(row)
        with (self.data_dir/'actions.jsonl').open('a', encoding='utf8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False)+'\n')

    def persist(self):
        runtime.atomic_json(self.data_dir/'scheduler.json', {'pending': self.pending,
            'maintenance': self.maintenance, 'cooldowns': self.cooldowns, 'module_last_run': self.module_last_run,
            'account_id': self.account_id, 'account_states': self.account_states,
            'success_count': self.success_count, 'logs': list(self.logs), 'metrics': list(self.metrics),
            'next_recovery_at': self.next_recovery_at, 'sandbox': self.connection.get('sandbox', '')})

    def _quarantine_pending(self, reason):
        task = self.pending
        if not isinstance(task, dict): return
        action_data = task.get('action')
        if isinstance(action_data, dict):
            try:
                action = Action(**action_data)
                delay = 120 if action.kind in ('mail_refresh', 'equipment_equip') else 86400
                self.cooldowns[action.key] = max(self.cooldowns.get(action.key, 0), time.time()+delay)
            except (TypeError, KeyError):
                pass
        filename = task.get('command_file')
        if isinstance(filename, str) and Path(filename).name == filename:
            directory = self.runtime_dir
            saved = task.get('runtime_dir')
            # A restarted helper has not bound IPC yet. Resolve a saved box via
            # Sandboxie before cleaning its command; do not trust arbitrary paths.
            if isinstance(saved, str) and Path(saved) != directory and self.connection.get('sandbox'):
                try:
                    from .sandbox import connection
                    previous = connection(None, runtime.DATA, self.connection['sandbox'])['directory']
                    if previous == Path(saved): directory = previous
                except (OSError, RuntimeError):
                    pass
            path = directory/'commands'/filename
            if path.is_file(): path.unlink()
        self.log('system', reason+'；旧请求已隔离且不会跨账号重放', 'warning',
                 operation_id=task.get('id'), account_id=task.get('account_id'))
        self.pending = None

    def bind_account(self, account_id):
        if type(account_id) is not int or account_id <= 0: return False
        if self.account_id == account_id: return False
        previous = self.account_id
        if previous is not None:
            self._quarantine_pending('检测到账号切换')
            old_state = {'cooldowns': self.cooldowns, 'module_last_run': self.module_last_run}
            if valid_maintenance(self.maintenance, previous):
                self.maintenance['phase'] = 'restore'
                old_state['maintenance'] = self.maintenance
            self.account_states[str(previous)] = old_state
            self.cooldowns = {}
            self.module_last_run = {}
            self.maintenance = None
        elif self.pending and self.pending.get('account_id') != account_id:
            self._quarantine_pending('旧版或未知账号请求无法绑定当前账号')
        if self.maintenance and self.maintenance.get('account_id') != account_id:
            owner_id = self.maintenance.get('account_id')
            if type(owner_id) is int and owner_id > 0:
                saved = self.account_states.get(str(owner_id))
                if not isinstance(saved, dict): saved = {}
                self.maintenance['phase'] = 'restore'
                saved['maintenance'] = self.maintenance
                self.account_states[str(owner_id)] = saved
            else:
                self.log('system', '无法确认维护装备所属账号，已隔离该恢复任务', 'warning')
            self.maintenance = None
        self.account_id = account_id
        saved = self.account_states.pop(str(account_id), None)
        if isinstance(saved, dict):
            if isinstance(saved.get('cooldowns'), dict): self.cooldowns = saved['cooldowns']
            if isinstance(saved.get('module_last_run'), dict): self.module_last_run = saved['module_last_run']
            if valid_maintenance(saved.get('maintenance'), account_id):
                job = saved['maintenance']
                if job.get('account_id') == account_id:
                    job['phase'] = 'restore'
                    self.maintenance = job
        self.persist()
        return True

    def update_config(self, changes):
        with self.lock:
            merged = {**self.config, **changes}
            if 'modules' in changes: merged['modules'] = {**self.config['modules'], **changes['modules']}
            self.config = normalize_config(merged)
            self.running = self.config['auto_start']
            runtime.atomic_json(self.data_dir/'config.json', self.config)
            self.config_stamp = (self.data_dir/'config.json').stat().st_mtime_ns
            self.publish_config()
            self.log('system', '已保存策略参数，下一轮调度生效')
            return self.config

    def publish_config(self):
        runtime.atomic_json(self.runtime_dir/'control.json', self.config)
        if not (self.data_dir/'config.json').exists():
            runtime.atomic_json(self.data_dir/'config.json', self.config)

    def reload_config(self):
        now = time.time()
        if now-self.last_config_check < 5: return
        self.last_config_check = now
        path = self.data_dir/'config.json'
        try:
            stamp = path.stat().st_mtime_ns
            if stamp == self.config_stamp: return
            candidate = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(candidate,dict): raise ValueError('配置必须是 JSON 对象')
            candidate = normalize_config(candidate)
            self.running = candidate['auto_start']
            self.config_stamp = stamp
            if candidate != self.config:
                self.config = candidate
                self.publish_config()
                self.log('system','已重新载入配置文件，下一轮按新参数检查')
        except (OSError,ValueError) as exc:
            message = f'配置文件暂时无法读取，继续使用上次有效参数：{exc}'
            if not self.logs or self.logs[0].get('message') != message: self.log('system',message,'warning')

    def inspect_now(self):
        with self.lock:
            self.last_dispatch = 0
            self.inspection_requested = True
            self.log('system','已安排立即巡检，沿用当前开关、资源保护与请求退避')

    def handle_hotkey(self, key):
        with self.lock:
            if key == 'F8': self.set_running(not self.running)
            elif key in ['F9','F10']:
                module = 'inventory' if key == 'F9' else 'equipment'
                self.update_config({'modules':{module:not self.config['modules'][module]}})

    def set_running(self, value):
        with self.lock:
            self.running = bool(value)
            if self.config['auto_start'] != self.running:
                self.config = normalize_config({**self.config, 'auto_start': self.running})
                path = self.data_dir/'config.json'
                runtime.atomic_json(path, self.config)
                self.config_stamp = path.stat().st_mtime_ns
                self.publish_config()
                self.log('system', '已保存自动化启停状态', auto_start=self.running)
            self.log('system', '继续自动成长' if self.running else '已暂停新操作，当前请求继续等待原生结算')

    def boot(self):
        self.game = runtime.discover_game()
        if self.game is None:
            self.status = '等待安装游戏'
            self.error = '未发现 Steam 游戏，请启动一次游戏后重试'
            return
        self.refresh_connection(force=True)
        changed = runtime.install(self.game)
        current = self.read_snapshot()
        if changed and runtime.game_processes(self.game) and current.get('revision', 0) < 2:
            self.log('system', '安装执行桥接，等待游戏正常结算后重启')
            runtime.close_gracefully(self.game)
        if self.config['auto_relaunch'] and not runtime.game_processes(self.game) and not self.pending and time.time() >= self.next_recovery_at:
            self.reserve_recovery()
            self.launch_game()
        self.booted = True
        self.error = ''

    def read_snapshot(self):
        if self.connection_bound and self.connection.get('pid') is None:
            return {'connected': False, 'phase': 'waiting_game'}
        return runtime.snapshot(self.runtime_dir, self.connection.get('pid'), self.connection.get('created'))

    def launch_game(self):
        options = {'auto_start': self.running}
        if self.connection.get('sandbox'): options['sandbox'] = self.connection['sandbox']
        return runtime.launch(self.game, **options)

    def refresh_connection(self, force=False):
        if not self.game: return
        if self.fixed_target is not None:
            force = force or any(self.fixed_target.get(key) != self.connection.get(key) for key in ('directory','pid','created'))
        now = time.monotonic()
        if not force and now-self.last_connection_check < 5:
            if self.connection_error: raise RuntimeError(self.connection_error)
            return
        self.last_connection_check = now
        try:
            selected = dict(self.fixed_target) if self.fixed_target is not None else runtime.connection_for(self.game, self.connection.get('sandbox', ''))
        except (OSError, runtime.psutil.Error, RuntimeError) as exc:
            self.snapshot = {}
            self.actions = []
            self.connection_bound = True
            self.connection['pid'] = None
            self.connection_error = str(exc)
            raise
        self.connection_error = ''
        old_identity = (self.runtime_dir, self.connection.get('pid'), self.connection.get('created'))
        new_identity = (selected['directory'], selected['pid'], selected['created'])
        if self.connection_bound and old_identity == new_identity:
            return
        if self.pending and (self.pending.get('pid') != selected['pid']
                or self.pending.get('runtime_dir', str(runtime.DATA/'runtime')) != str(selected['directory'])):
            self._quarantine_pending('游戏实例或连接目录已切换')
        self.runtime_dir = selected['directory']
        self.connection = selected
        self.connection_bound = True
        self.snapshot = {}
        self.opportunities = {}
        self.catalog = {}
        self.file_cache.clear()
        self.actions = []
        self.recovery_candidate = None
        self.publish_config()
        name = selected['sandbox']
        self.log('system', f'已选择沙盒 {name}，等待当前游戏数据' if name else '已选择本机游戏连接')
        self.persist()

    def cached_json(self, name):
        """Cache immutable JSON exports until atomic replacement changes their identity."""
        path = self.runtime_dir/name
        try:
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
            cached = self.file_cache.get(name)
            if cached and cached[0] == stamp: return cached[1]
            value = read_json(path, {})
            if not isinstance(value, dict): value = {}
            # A racing replacement must be read again next tick, never cached indefinitely.
            after = path.stat()
            if stamp == (after.st_mtime_ns, after.st_size, after.st_ino):
                self.file_cache[name] = (stamp, value)
            return value
        except OSError:
            self.file_cache.pop(name, None)
            return {}

    def dispatch(self, action):
        if self.stop_event.is_set(): return
        now = time.time()
        if self.pending is not None:
            raise RuntimeError('已有待结算请求，拒绝并发发布命令')
        if type(self.snapshot.get('revision')) is not int or self.snapshot['revision'] < 17:
            raise RuntimeError('等待支持账号隔离的桥接版本')
        account_id = snapshot_account_id(self.snapshot)
        if account_id is None:
            raise RuntimeError('拒绝发布缺少可验证账号身份的游戏命令')
        if self.account_id is None:
            self.bind_account(account_id)
        if self.account_id != account_id:
            raise RuntimeError('拒绝发布与当前账号身份不匹配的游戏命令')
        ident = uuid.uuid4().hex
        command = {'id': ident, 'pid': self.snapshot['pid'], 'account_id': account_id,
                   'action': action.kind, 'args': action.args}
        filename = f'{time.time_ns()}-{ident}.json'
        self.pending = {'id': ident, 'pid': self.snapshot['pid'], 'account_id': account_id, 'command_file': filename,
                        'runtime_dir': str(self.runtime_dir),
                        'action': asdict(action), 'started': now, 'label': action.label}
        # Persist before publishing. A restart reconciles this exact command, never generates a retry id.
        self.persist()
        runtime.atomic_json(self.runtime_dir/'commands'/filename, command)
        self.last_dispatch = now
        self.module_last_run[action.module] = now
        self.log(action.module, action.label, 'pending', action=action.kind, operation_id=ident)

    def finish(self, success, message, uncertain=False):
        task = self.pending
        if not task: return
        action = Action(**task['action'])
        if uncertain and action.kind == 'mail_refresh':
            message += '；120 秒后重新读取列表，旧请求不重放'
        self.log(action.module, message, 'success' if success else 'warning',
                 action=action.kind, operation_id=task['id'], uncertain=uncertain)
        if success: self.success_count += 1
        delay = 9 if success else 120
        if action.kind == 'dungeon_enter': delay = self.config['dungeon_interval_seconds']
        if action.kind == 'craft': delay = 15 if success else 180
        if action.kind in ['enhancement_quote', 'salvage_quote']: delay = 8 if success else 120
        if action.kind == 'mail_refresh': delay = 300 if success else 120
        self.cooldowns[action.key] = time.time()+delay
        if not success and action.kind == 'stone_merge' and 'protected_stone' in message:
            self.cooldowns['stone_merge:protected'] = time.time()+30
        if uncertain and action.kind != 'mail_refresh': self.cooldowns[action.key] = time.time()+86400
        if uncertain and action.kind == 'equipment_equip':
            # Explicit desired-state equipment commands consume no materials.
            # Their old operation remains unknown; a new attempt is permitted
            # only after current authoritative inventory and native idle checks.
            self.cooldowns[action.key] = time.time()+120
        if (self.maintenance and self.maintenance.get('pid') == task['pid']
                and self.maintenance.get('account_id') == task.get('account_id')):
            if action.kind in ['enhancement_execute', 'socket'] or not success:
                self.restore_maintenance(86400 if uncertain else 0)
            elif action.kind == 'equipment_equip' and action.expected and 'unequipped' in action.expected and self.maintenance['phase'] == 'prepare':
                self.maintenance['phase'] = 'operate'
        self.pending = None
        self.last_dispatch = time.time()
        self.persist()

    def reconcile(self):
        if not self.pending: return
        task = self.pending
        account_id = snapshot_account_id(self.snapshot)
        if account_id is None: return
        if type(task.get('account_id')) is not int or task['account_id'] != account_id:
            self._quarantine_pending('结算时账号身份与请求不一致')
            self.persist()
            return
        elapsed = time.time()-task['started']
        if self.snapshot.get('pid') and self.snapshot['pid'] != task['pid']:
            path = self.runtime_dir/'commands'/task['command_file']
            if path.is_file(): path.unlink()
            self.finish(False, '游戏会话已切换，旧操作停止重放并保留记录', True)
            return
        result = read_json(self.runtime_dir/'results'/f"{task['id']}.json", {}) or {}
        if result.get('status') != 'submitted':
            if elapsed > 45:
                path = self.runtime_dir/'commands'/task['command_file']
                if path.is_file(): path.unlink()
                self.finish(False, '原生调用被中断，结果未明，已阻止自动重复消费', True)
            return
        if type(result.get('account_id')) is not int or result['account_id'] != account_id:
            self._quarantine_pending('原生命令结果缺少匹配账号身份')
            self.persist()
            return
        answer = result.get('answer')
        if isinstance(answer, dict) and answer.get('skipped') is True:
            # A native operation may win the race after the last snapshot. This
            # branch proves nothing was submitted; it must never count success.
            if (task['action']['kind'] in ('stone_merge', 'stone_equip')
                    and answer.get('ok') is True
                    and answer.get('reason') in ('native_stone_busy', 'stone_candidates_changed')
                    and not result.get('request_ids') and not answer.get('request_id')):
                action = Action(**task['action'])
                self.log(action.module, f'{task["label"]} · 原生魔石操作或候选已变化，等待刷新',
                         action=action.kind, operation_id=task['id'], skipped=True,
                         reason=answer['reason'])
                self.cooldowns[action.key] = time.time()+5
                self.pending = None
                self.last_dispatch = time.time()
                self.persist()
            else:
                self.finish(False, f'{task["label"]} · 跳过结果包含请求或无法验证，保留未知结果', True)
            return
        if answer is False or isinstance(answer, dict) and answer.get('ok') is False:
            reason = answer.get('message', answer.get('error', '条件改变')) if isinstance(answer, dict) else '原生条件不满足'
            self.finish(False, f"{task['label']} · {reason}")
            return
        if isinstance(answer, dict) and 'request_id' in answer and answer['request_id']<=0:
            self.finish(False, f"{task['label']} · 原生请求尚未就绪")
            return
        ids = result.get('request_ids', [])
        if isinstance(answer, dict) and answer.get('request_id', 0)>0:
            ids = sorted(set(ids+[answer['request_id']]))
        receipts = [read_json(self.runtime_dir/f"receipt-{task['pid']}-{account_id}-{rid}.json", {}) or {} for rid in ids]
        receipts = [row if finite_number(row.get('time_unix')) and task['started'] <= row['time_unix'] <= time.time() else {}
                    for row in receipts]
        if any(row.get('response', {}).get('outcome_unknown') or row.get('response', {}).get('transport_lost') for row in receipts):
            self.finish(False, f"{task['label']} · 连接中断，结果未明，已隔离本次请求", True)
            return
        if any(row and (not row.get('ok') or row.get('response', {}).get('ok') is False) for row in receipts):
            self.finish(False, f"{task['label']} · 服务器拒绝，已退避等待")
            return
        if ids and not all(receipts):
            if elapsed>45: self.finish(False, f"{task['label']} · 回执超时，保留未知结果并阻止重放", True)
            return
        if not self.snapshot.get('connected'):
            if elapsed > 45:
                self.finish(False, f"{task['label']} · 断线期间状态未确认，已隔离并阻止重放", True)
            return
        if any(self.snapshot.get('native_busy', {}).values()) or time.time()-result.get('time_unix', 0)<2:
            return
        kind = task['action']['kind']
        args = task['action']['args']
        expected = task['action'].get('expected') or {}
        if kind == 'equipment_equip' and expected and not maintenance_context_ready(self.snapshot):
            if elapsed > 45:
                self.finish(False, f"{task['label']} · 穿戴状态无法核验，已隔离请求", True)
            return
        worn = self.snapshot.get('inventory', {}).get('equipped_equipment_ids_by_char', {})
        equipment_ok = ('equipment' in expected and expected['equipment'][1] in worn.get(expected['equipment'][0], {}).values())
        unequipped_ok = ('unequipped' in expected and all(expected['unequipped'][1] not in values.values() for values in worn.values()))
        local_ok = ((kind == 'equipment_equip' and (equipment_ok or unequipped_ok))
            or (kind == 'initial_pick' and not self.snapshot.get('startup_selection_pending') and bool(active_characters(self.snapshot)))
            or (kind == 'dungeon_enter' and (self.snapshot.get('in_dungeon')
                or isinstance(answer, dict) and answer.get('in_dungeon')))
            or (kind == 'consumable_potion' and self.snapshot.get('consumables',{}).get('toggles',{}).get('potion'))
            or (kind == 'consumable_exp' and (self.snapshot.get('consumables',{}).get('exp_scroll_enabled')
                or self.snapshot.get('consumables',{}).get('exp_scroll_active')))
            or (kind == 'loot_claim' and int(self.opportunities.get('loot',{}).get('count', 0))
                < int((task['action'].get('expected') or {}).get('loot_before', 0)))
            or (kind == 'mainline_resume' and not self.snapshot.get('stage_hold')))
        if not ids and not local_ok:
            # Some native controllers mutate local state without creating a
            # gateway request. Give their snapshots time to settle before
            # treating the command as a failed/unknown operation.
            if kind == 'dungeon_enter' and elapsed < 10:
                return
            if kind in {'loot_claim', 'consumable_exp', 'equipment_equip'} and elapsed < 45:
                return
            self.finish(False, f"{task['label']} · 未发起有效请求，等待状态刷新")
            return
        expected = task['action'].get('expected') or {}
        inv = self.snapshot.get('inventory',{})
        confirmed = True
        if 'consumed' in expected:
            remaining = {iid(item) for item in inv.get('items', [])}
            confirmed = confirmed and all(int(id) not in remaining for id in expected['consumed'])
        if 'material_counts' in expected:
            remaining = {int(row.get('record_id', row.get('instance_id', row.get('id', 0)))): int(row.get('count', 0))
                         for row in inv.get('material_records', [])}
            confirmed = confirmed and all(remaining.get(int(id), 0) <= 0
                                          for id in expected['material_counts'])
        if 'formation' in expected: confirmed = active_characters(self.snapshot) == expected['formation']
        if 'equipment' in expected:
            owner,id = expected['equipment']
            confirmed = id in inv.get('equipped_equipment_ids_by_char',{}).get(owner,{}).values()
        if 'unequipped' in expected:
            confirmed = confirmed and unequipped_ok
        if 'skill_slot' in expected:
            owner,index,id = expected['skill_slot']; slots=inv.get('server_equipped_skill_ids_by_char',{}).get(owner,[])
            confirmed = len(slots)>index and int(slots[index])==id
        if 'stone' in expected:
            owner,index,id = expected['stone']; slots=inv.get('equipped_stone_ids_by_char',{}).get(owner,[])
            confirmed = len(slots)>index and int(slots[index])==id
        if 'skill' in expected:
            owner,id,level = expected['skill']
            learned=inv.get('skills_by_char',{}).get(owner,{})
            confirmed=any(int(x.get('skill_item_data_id',0))==id and int(x.get('level',0))>=level for x in learned.values())
        if 'rune' in expected:
            node, level = expected['rune']
            confirmed = any(row.get('node_key') == node and int(row.get('from_level', 0)) >= level
                            for row in self.opportunities.get('runes', []))
        if not confirmed:
            if elapsed>30: self.finish(False,f"{task['label']} · 回执后状态未匹配，已保留记录",True)
            return
        self.finish(True, f"已结算 · {task['label']}")

    def restore_maintenance(self, retry_delay=0):
        job = self.maintenance
        job['phase'] = 'restore'
        if retry_delay:
            key = f"maintenance:{job['module']}:{job['id']}"
            self.cooldowns[key] = max(self.cooldowns.get(key, 0), time.time()+retry_delay)
        self.persist()

    def maintenance_equipment_action(self, job, equipped):
        owner, item_id = job['owner'], job['id']
        expected = {'equipment' if equipped else 'unequipped': [owner, item_id]}
        label = '恢复维护后的装备' if equipped else '临时卸下装备，准备原生工坊维护'
        return Action('equipment', 'equipment_equip', [owner, item_id, equipped], label, 200, expected)

    def maintenance_action(self):
        inv = self.snapshot.get('inventory', {})
        # Restoring a loadout also needs authoritative current inventory, never an old export.
        if self.pending or not maintenance_context_ready(self.snapshot): return None
        account_id = snapshot_account_id(self.snapshot)
        if account_id is None or self.account_id != account_id: return None
        if any(not isinstance(row, dict) for row in inv['items']): return None
        items = {iid(x): x for x in inv['items']}
        o = self.opportunities
        now = time.time()
        if self.maintenance:
            job = self.maintenance
            item_id, owner = job['id'], job['owner']
            if job.get('account_id') != account_id: return None
            item = items.get(item_id)
            by_owner = inv.get('equipped_equipment_ids_by_char', {})
            eq = by_owner.get(owner, {})
            if not item or any(item_id in values.values() for key, values in by_owner.items() if key != owner):
                self.log(job['module'], '维护目标已不存在或由其他角色穿戴，停止接管并保留当前装备', 'warning')
                self.maintenance = None
                self.persist()
                return None
            phase = job.get('phase')
            started = job.get('started')
            elapsed = now-started if finite_number(started) else float('inf')
            if (phase not in ('prepare', 'operate', 'restore') or job.get('pid') != self.snapshot.get('pid')
                    or not self.running or not self.config['modules'][job['module']]
                    or elapsed < 0 or elapsed > 65):
                job.update(pid=self.snapshot['pid'], phase='restore')
                self.persist()
            if job['phase'] == 'restore':
                if item_id not in eq.values():
                    return self.maintenance_equipment_action(job, True)
                key = f"maintenance:{job['module']}:{item_id}"
                self.cooldowns[key] = max(self.cooldowns.get(key, 0), now+self.config['maintenance_interval_seconds'])
                self.maintenance = None
                self.persist()
                return None
            if job['phase'] == 'prepare':
                if not opportunities_ready(self.snapshot, o): return None
                if item_id in eq.values(): return self.maintenance_equipment_action(job, False)
                job['phase'] = 'operate'
                self.persist()
            if job['phase'] == 'operate' and item_id in eq.values():
                # Another controller restored it: do not toggle it off again.
                self.restore_maintenance()
                return None
            if not opportunities_ready(self.snapshot, o):
                self.restore_maintenance()
                return self.maintenance_equipment_action(job, True)
            if job['module'] == 'enhancement':
                quote = o.get('enhancement_quote', {})
                if int(quote.get('item', {}).get('id', 0)) != item_id:
                    if o.get('enhancement_ready'):
                        return Action('enhancement', 'enhancement_quote', [item_id], '读取服务器强化报价', 200)
                    self.restore_maintenance()
                    return self.maintenance_equipment_action(job, True)
                gold, keep = reserve(inv, growth_budget(self.snapshot, o, self.config))
                required = ('scroll_count', 'success_percent', 'gold_cost', 'destruction_percent')
                valid_quote = all(finite_number(quote.get(key)) and quote[key] >= 0
                                  and float(quote[key]).is_integer() for key in required)
                if (not valid_quote or quote['scroll_count'] < 1 or quote['success_percent'] <= 0
                        or quote['success_percent'] > 100 or quote['destruction_percent'] > 100
                        or quote['gold_cost'] > gold-keep
                        or quote['destruction_percent'] > 0 and not self.config['allow_equipment_destruction']):
                    self.restore_maintenance(max(600, self.config['maintenance_interval_seconds']))
                    return self.maintenance_equipment_action(job, True)
                return Action('enhancement', 'enhancement_execute', [item_id], f"强化 {item.get('name', '装备')}", 200)
            if job['module'] == 'socket':
                target = next((x for x in o.get('socket_items', []) if int(x['id']) == item_id), {})
                gems = o.get('socket_gems', [])
                if not target.get('empty_slots') or not gems or not o.get('socket_ready'):
                    self.restore_maintenance()
                    return self.maintenance_equipment_action(job, True)
                gem = max(gems, key=lambda x: int(x.get('grade', 1)))
                return Action('socket', 'socket', [item_id, int(target['empty_slots'][0]), int(gem['id'])],
                              f"为 {item.get('name', '装备')} 镶嵌宝石", 200)
            self.restore_maintenance()
            return self.maintenance_equipment_action(job, True)
        if not self.running: return None
        for owner in active_characters(self.snapshot):
            for raw_id in inv.get('equipped_equipment_ids_by_char', {}).get(owner, {}).values():
                item_id = int(raw_id)
                item = items.get(item_id, {})
                if (int(item.get('grade', 1)) < 3 or item.get('stored') or item.get('unidentified')
                        or int(item.get('state_flag', 0)) & (2 | 4 | 8 | 32 | 64)):
                    continue
                module = None
                if (self.config['modules']['enhancement'] and o.get('enhancement_ready')
                        and all(self.cooldowns.get(key, 0) <= now for key in
                            (f'maintenance:enhancement:{item_id}', f'enhancement_execute:[{item_id}]', f'enhancement_quote:[{item_id}]'))
                        and int(item.get('enhance_level', 0)) < min(15, max(3, int(inv.get('character_progress_by_char', {}).get(owner, {}).get('level', 1))//10))):
                    module = 'enhancement'
                elif (self.config['modules']['socket'] and o.get('socket_ready') and o.get('socket_gems')
                        and self.cooldowns.get(f'maintenance:socket:{item_id}', 0) <= now
                        and empty_socket_count(item) > 0):
                    module = 'socket'
                if module:
                    self.maintenance = {'module': module, 'id': item_id, 'owner': owner, 'pid': self.snapshot['pid'],
                                        'account_id': account_id,
                                        'started': now, 'phase': 'prepare'}
                    self.persist()
                    return self.maintenance_equipment_action(self.maintenance, False)
        return None

    def action_ready(self, action, now=None):
        now = time.time() if now is None else now
        if self.cooldowns.get(action.key, 0) > now: return False
        if action.kind == 'mail_refresh':
            # mail.list is read-only, but wait for a fresh connection and any
            # native list/claim to finish before issuing a new operation id.
            if self.snapshot.get('connected') is not True or self.snapshot.get('phase') == 'stale': return False
            stamp = self.snapshot.get('time_unix')
            if not finite_number(stamp) or not 0 <= now-stamp <= 8: return False
            requests = self.snapshot.get('pending_requests')
            if not isinstance(requests, dict): return False
            for request in requests.values():
                if not isinstance(request, dict) or not isinstance(request.get('command'), str) or not request['command']: return False
                if request['command'] in ('mail.list', 'mail.read'): return False
        if action.kind == 'stone_merge' and self.cooldowns.get('stone_merge:protected', 0) > now: return False
        # The advertised challenge interval covers every floor, including newly unlocked floors.
        return action.kind != 'dungeon_enter' or now-self.module_last_run.get('dungeon', 0) >= self.config['dungeon_interval_seconds']

    def reserve_recovery(self):
        # Journal before touching the process, including failed launch/close attempts.
        self.next_recovery_at = time.time() + 300
        self.recovery_candidate = None
        self.persist()

    def recovery_identity(self, processes, snapshot):
        """Only a fresh, idle, explicitly retryable native failure permits a restart."""
        if self.pending or len(processes) != 1 or not isinstance(snapshot, dict): return None
        if snapshot.get('connected') is not False or snapshot.get('phase') == 'stale': return None
        process = processes[0]
        if type(snapshot.get('pid')) is not int or snapshot['pid'] != process.pid: return None
        stamp = snapshot.get('time_unix')
        if not finite_number(stamp) or not 0 <= time.time()-stamp <= 8: return None
        try: created = process.create_time()
        except (OSError, runtime.psutil.Error): return None
        if not finite_number(created) or created > stamp: return None
        connection = snapshot.get('connection')
        if not isinstance(connection, dict): return None
        if connection.get('known') is not True or connection.get('fatal') is not True: return None
        if connection.get('fatal_kind') != 'retry': return None
        for key in ('intentional_shutdown', 'login_retry_pending', 'fatal_restart_requested'):
            if connection.get(key) is not False: return None
        requests = snapshot.get('pending_requests')
        if not isinstance(requests, dict) or requests: return None
        busy = snapshot.get('native_busy')
        if not isinstance(busy, dict): return None
        for key in ('skill', 'equipment', 'enhancement', 'socket', 'loot'):
            if busy.get(key) is not False: return None
        for key in ('craft', 'disassembly'):
            if type(busy.get(key)) is not int or busy[key] != 0: return None
        return process.pid, created, connection['fatal_kind']

    def recover_connection(self):
        if not self.config['auto_relaunch'] or not self.game or self.pending:
            self.recovery_candidate = None
            return
        processes = runtime.game_processes(self.game)
        if self.fixed_target is not None:
            # A managed instance can only recover this exact process. The manager
            # adopts a newly launched PID into a new isolated channel.
            all_processes = processes
            processes = [p for p in processes if p.pid == self.connection.get('pid')
                         and p.create_time() == self.connection.get('created')]
            if not processes:
                from .sandbox import process_box
                if self.connection.get('pid') is not None: return
                if any(process_box(p.pid) == self.connection.get('sandbox', '') for p in all_processes): return
                if time.time() >= self.next_recovery_at and not self.maintenance:
                    self.reserve_recovery()
                    self.launch_game()
                return
        if not processes:
            self.recovery_candidate = None
            if time.time() >= self.next_recovery_at:
                self.reserve_recovery()
                self.launch_game()
            return
        identity = self.recovery_identity(processes, self.snapshot)
        if identity is None:
            self.recovery_candidate = None
            return
        now = time.monotonic()
        if self.recovery_candidate is None or self.recovery_candidate[0] != identity:
            self.recovery_candidate = identity, now
            return
        if now-self.recovery_candidate[1] < 30 or time.time() < self.next_recovery_at: return
        # Re-read both sources immediately before closing; never trust an old fatal flag.
        current = runtime.snapshot(self.runtime_dir, identity[0], identity[1])
        current_processes = runtime.game_processes(self.game)
        if self.fixed_target is not None: current_processes = [p for p in current_processes if p.pid == identity[0]]
        if self.recovery_identity(current_processes, current) != identity:
            self.recovery_candidate = None
            return
        self.reserve_recovery()
        self.log('system', '游戏报告可重连终止状态且无挂起请求，等待正常退出后恢复', 'warning')
        runtime.close_gracefully(self.game, expected_pid=identity[0], expected_create_time=identity[1])
        self.launch_game()

    def tick(self):
        with self.lock:
            self.reload_config()
            if not self.booted:
                self.boot()
                return
            self.refresh_connection()
            self.snapshot=self.read_snapshot()
            self.error = ''
            self.catalog=self.cached_json('catalog.json')
            self.opportunities=dict(self.cached_json('opportunities.json'))
            skill_data=self.cached_json('skill-previews.json')
            self.opportunities['skills']=skill_data.get('rows',[])
            current_account_id = snapshot_account_id(self.snapshot)
            if self.snapshot.get('connected') is True and self.snapshot.get('phase') == 'ready':
                if current_account_id is None:
                    self.status='等待可验证账号身份'
                    self.actions=[]
                    return
                switched = self.bind_account(current_account_id)
                if switched:
                    self.actions=[]
                    self.metrics.clear()
                    self.recovery_candidate=None
                    self.last_sample=0
                if type(self.snapshot.get('revision')) is not int or self.snapshot['revision'] < 17:
                    self.status='等待账号隔离桥接更新'
                    self.actions=[]
                    return
                if skill_data.get('account_id') != current_account_id or skill_data.get('pid') != self.snapshot.get('pid'):
                    self.opportunities['skills']=[]
            if not self.snapshot.get('connected'):
                self.status='等待游戏连接'
                self.actions=[]
                if self.disconnected_since is None: self.disconnected_since=time.time()
                self.reconcile()
                self.recover_connection()
                return
            self.disconnected_since=None
            self.recovery_candidate=None
            if self.pending:
                self.status='等待原生结算'
                self.reconcile()
                return
            if any(self.snapshot.get('native_busy',{}).values()):
                self.status='等待游戏当前操作结算'
                return
            if time.time()-self.last_dispatch < self.config['tick_seconds']: return
            if not self.pending and not self.maintenance and not self.inspection_requested and time.monotonic()-self.last_plan < self.config['tick_seconds']:
                return
            self.last_plan = time.monotonic()
            if self.maintenance:
                self.status = '恢复维护装备' if self.maintenance['phase'] == 'restore' else '装备维护中'
                action = self.maintenance_action()
                if action and self.action_ready(action): self.dispatch(action)
                return
            if not opportunities_ready(self.snapshot, self.opportunities):
                self.status='等待内容与条件预览'
                return
            self.status='自动成长中' if self.running else '已暂停'
            if time.time()-self.last_sample>=30:
                sim=self.snapshot.get('sim',{}); inv=self.snapshot.get('inventory',{})
                self.metrics.append({'time':time.time(),'level':sim.get('player',{}).get('level',1),
                    'gold':reserve(inv,self.config)[0],'map':sim.get('map_id',0),
                    'power':sum(inv.get('character_combat_power_by_char',{}).get(x,0) for x in active_characters(self.snapshot))})
                self.last_sample=time.time()
                self.persist()
            self.actions=plan(self.snapshot,self.opportunities,self.catalog,self.config)
            if not self.running and not self.inspection_requested: return
            eligible=[a for a in self.actions if self.action_ready(a)]
            now=time.time()
            eligible.sort(key=lambda a:a.priority+min(90,max(0,now-self.module_last_run.get(a.module,self.started))/3),reverse=True)
            # Higher impact formation/skills/rune upgrades settle before gear maintenance.
            action=eligible[0] if eligible and eligible[0].priority>=75 else self.maintenance_action()
            if not action and eligible: action=eligible[0]
            self.inspection_requested = False
            if action: self.dispatch(action)

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
                self.view = self.public_state()
            except Exception as exc:
                with self.lock:
                    self.error=f'{type(exc).__name__}: {exc}'
                    self.status='等待恢复'
                    if not self.logs or self.logs[0].get('message')!=self.error: self.log('system',self.error,'error')
                    self.view = self.public_state()
                self.stop_event.wait(5)
            self.stop_event.wait(1)

    def public_state(self):
        with self.lock:
            s=self.snapshot; inv=s.get('inventory',{}); sim=s.get('sim',{})
            heroes=s.get('playable_characters',{})
            active=active_characters(s)
            candidates={k:[] for k in MODULES}
            for a in self.actions: candidates[a.module].append(a.label)
            wait_reasons = {}
            if any(row.get('owner') in active and row.get('preview', {}).get('ok')
                   and row.get('preview', {}).get('can_afford') is False
                   for row in self.opportunities.get('skills', [])):
                wait_reasons['skills'] = '技能点或材料不足，等待下一次资源到账'
            dungeon = self.opportunities.get('dungeon', {})
            if dungeon.get('entry_blocked'):
                wait_reasons['dungeon'] = '等待领取副本奖励，腾出奖励容量后继续挑战'
            elif dungeon.get('session_required'):
                wait_reasons['dungeon'] = '等待游戏服务器会话就绪'
            capacity = capacity_goal(s, self.opportunities, self.config)
            if capacity:
                wait_reasons['runes'] = f"容量联动：为 {capacity['name']} 保留金币，等待资源到账"
            return {'version':'0.4.0','status':self.status,'error':self.error,'running':self.running,
                'connection': {'mode': 'sandbox' if self.connection.get('sandbox') else 'local',
                    'sandbox': self.connection.get('sandbox', ''), 'pid': self.connection.get('pid'),
                    'runtime_path': str(self.runtime_dir)},
                'display':s.get('assistant_display',{}),'hotkeys':self.hotkeys,
                'config_path':str(self.data_dir/'config.json'),'grade_names':s.get('grade_names',{}),
                'rune_next':next((a.label for a in self.actions if a.kind=='rune_level'),''),
                'capacity_goal':capacity,
                'connected':s.get('connected',False),'uptime':time.time()-self.started,
                'snapshot_time':s.get('time_unix',0),'phase':s.get('phase','waiting_game'),
                'game_path':str(self.game or ''),'config':self.config,'success_count':self.success_count,
                'player':sim.get('player',{}),'map':{k:sim.get(k) for k in ['map_id','map_name','highest_cleared_main_map_id','highest_cleared_dungeon_map_id','combat_phase','stage_progress','result']},
                'gold':reserve(inv,self.config)[0], 'bag':{'used':inv.get('bag_occupied_slots',0),'capacity':inv.get('bag_unlocked_slots',0),
                    'stones':inv.get('stone_bag_occupied_slots',0),'stone_capacity':inv.get('stone_bag_unlocked_slots',0)},
                'formation_limit':s.get('formation_limit',1),'team':[{'key':key,'name':heroes.get(key,{}).get('char',key),
                    'job':heroes.get(key,{}).get('name',''),'active':key in active,
                    **inv.get('character_progress_by_char',{}).get(key,{}),
                    'power':inv.get('character_combat_power_by_char',{}).get(key,0)} for key in s.get('owned_characters',[])],
                'modules':[{'key':k,'name':name,'enabled':self.config['modules'][k],
                    'candidates':len(candidates[k]),'reason':candidates[k][0] if candidates[k] else wait_reasons.get(k, '等待资源、解锁条件或下一轮刷新')} for k,name in MODULES.items()],
                'queue':[a.json() for a in self.actions[:10]],'logs':list(self.logs),'metrics':list(self.metrics),
                'pending':{'label':self.pending['label'],'elapsed':time.time()-self.pending['started']} if self.pending else None,
                'maintenance':self.maintenance}
