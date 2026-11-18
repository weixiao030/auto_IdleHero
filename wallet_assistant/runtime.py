"""Account-independent installation, discovery, and native runtime connection."""
from __future__ import annotations
from datetime import datetime
import ctypes
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import psutil

APP_ID = '5052450'
GAME_EXE = 'Desktop Wallet Heroes.exe'
BEGIN = '; WALLET_HEROES_ASSISTANT_BEGIN'
END = '; WALLET_HEROES_ASSISTANT_END'
SOURCE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
DATA = Path(os.environ.get('WALLET_ASSISTANT_DATA', str(Path(os.environ['LOCALAPPDATA'])/'WalletHeroesAssistant')))


def game_candidates():
    """Enumerate names once; open handles only for matching Windows processes."""
    if os.name != 'nt': return list(psutil.process_iter(['name','exe','cmdline']))
    from ctypes import wintypes
    class Entry(ctypes.Structure):
        _fields_ = [('dwSize',wintypes.DWORD), ('cntUsage',wintypes.DWORD),
            ('th32ProcessID',wintypes.DWORD), ('th32DefaultHeapID',ctypes.c_size_t),
            ('th32ModuleID',wintypes.DWORD), ('cntThreads',wintypes.DWORD),
            ('th32ParentProcessID',wintypes.DWORD), ('pcPriClassBase',wintypes.LONG),
            ('dwFlags',wintypes.DWORD), ('szExeFile',wintypes.WCHAR*260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE,ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2,0)
    if handle == ctypes.c_void_p(-1).value: raise OSError('无法枚举游戏进程')
    matches=[]
    try:
        entry=Entry(); entry.dwSize=ctypes.sizeof(Entry)
        valid=kernel.Process32FirstW(handle,ctypes.byref(entry))
        while valid:
            if entry.szExeFile.casefold()==GAME_EXE.casefold():
                try:
                    process=psutil.Process(entry.th32ProcessID)
                    process.info=process.as_dict(attrs=['name','exe','cmdline'])
                    matches.append(process)
                except (OSError,psutil.Error): pass
            valid=kernel.Process32NextW(handle,ctypes.byref(entry))
    finally: kernel.CloseHandle(handle)
    return matches

def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
    os.replace(temporary, path)

def discover_game() -> Path | None:
    preferred = os.environ.get('WALLET_HEROES_GAME')
    if preferred and (Path(preferred)/GAME_EXE).is_file(): return Path(preferred)
    for process in game_candidates():
        if process.info['name'] == GAME_EXE and process.info['exe']:
            from .sandbox import virtual_path
            try:
                return virtual_path(process.info['exe'], process.pid).parent
            except (OSError, psutil.Error):
                continue
    roots = [Path('D:/SteamLibrary'), Path('C:/Program Files (x86)/Steam')]
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            roots.insert(0, Path(winreg.QueryValueEx(key, 'SteamPath')[0]))
    except OSError: pass
    for root in list(roots):
        vdf = root/'steamapps/libraryfolders.vdf'
        if vdf.is_file():
            for value in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding='utf8',errors='replace')):
                roots.append(Path(value.replace('\\\\','\\')))
    for root in dict.fromkeys(roots):
        manifest = root/f'steamapps/appmanifest_{APP_ID}.acf'
        name = 'Desktop Wallet Heroes'
        if manifest.is_file():
            match = re.search(r'"installdir"\s+"([^"]+)"', manifest.read_text(encoding='utf8'))
            if match: name = match[1]
        candidate = root/'steamapps/common'/name
        if (candidate/GAME_EXE).is_file(): return candidate
    return None

def game_processes(game: Path):
    expected = str((game/GAME_EXE).resolve()).casefold()
    matches = []
    for process in game_candidates():
        executable = process.info['exe']
        if not executable: continue
        if executable.casefold() != expected:
            if Path(executable).name.casefold() != GAME_EXE.casefold(): continue
            from .sandbox import virtual_path
            try:
                if str(virtual_path(executable, process.pid)).casefold() != expected: continue
            except (OSError, psutil.Error):
                continue
        if '--bi-loading-helper' in (process.info['cmdline'] or []): continue
        matches.append(process)
    return matches

def install(game: Path):
    DATA.mkdir(parents=True,exist_ok=True)
    bridge = DATA/'bridge/assistant.gd'
    bridge.parent.mkdir(exist_ok=True)
    loader_changed = False
    for name in ['assistant.gd', 'worker.gd']:
        target = bridge.parent/name
        source = SOURCE/'bridge'/name
        if target.exists() and target.read_bytes() == source.read_bytes():
            continue
        if name == 'assistant.gd': loader_changed = True
        if target.exists():
            previous = DATA/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            previous.mkdir(parents=True)
            shutil.copy2(target, previous/name)
        temporary = target.with_name(name+'.tmp')
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    cfg = game/'override.cfg'
    original = cfg.read_text(encoding='utf-8-sig') if cfg.exists() else ''
    if (BEGIN in original) != (END in original): raise RuntimeError('override.cfg 助手标记不完整')
    block = f'{BEGIN}\n[autoload]\nWalletHeroesAssistant="*{bridge.as_posix()}"\n{END}'
    updated = re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END), lambda _:block, original, flags=re.S) if BEGIN in original else original.rstrip()+'\n'+block+'\n'
    changed = original != updated
    if changed:
        backup = DATA/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup.mkdir(parents=True)
        if cfg.exists(): shutil.copy2(cfg,backup/'override.cfg')
        saves = Path(os.environ['APPDATA'])/'Godot/app_userdata/Taskstonebar Godot Runtime'
        if saves.exists():
            shutil.copytree(saves,backup/'user-data',ignore=shutil.ignore_patterns('logs','bi-loading'))
        atomic_json(backup/'manifest.json', {'game':str(game),'override_existed':cfg.exists(),'time':datetime.now().isoformat()})
        temporary = cfg.with_suffix('.cfg.assistant.tmp')
        temporary.write_text(updated,encoding='utf8')
        os.replace(temporary,cfg)
        atomic_json(DATA/'installation.json',{'game':str(game),'backup':str(backup),'bridge':str(bridge)})
    return changed or loader_changed

def connection_for(game: Path, preferred=''):
    from .sandbox import connection
    processes = game_processes(game)
    if len(processes) > 1:
        from .sandbox import process_box
        candidates = [p for p in processes if process_box(p.pid) == preferred]
        if len(candidates) != 1:
            raise RuntimeError('检测到多个游戏实例，请在网页选择目标实例')
        processes = candidates
    return connection(processes[0] if processes else None, DATA, preferred)


def install_connection(target):
    """Refresh a box's private bridge copy without changing Sandboxie policy."""
    directory = target['directory']
    if directory.parent.name == 'instances': directory = directory.parent.parent
    bridge = directory.parent/'bridge'
    bridge.mkdir(parents=True, exist_ok=True)
    for name in ('assistant.gd', 'worker.gd'):
        source = SOURCE/'bridge'/name
        destination = bridge/name
        if destination.exists() and destination.read_bytes() == source.read_bytes(): continue
        if destination.exists():
            backup = directory.parent/'backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            backup.mkdir(parents=True)
            shutil.copy2(destination, backup/name)
        temporary = destination.with_name(name+'.tmp')
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)


def snapshot(directory=None, pid=None, created=None):
    try:
        path = (directory or DATA/'runtime')/'snapshot.json'
        for attempt in range(3):
            try:
                payload = path.read_text(encoding='utf8')
                break
            except OSError:
                if attempt == 2: raise
                # Windows replacement can briefly hide or hold the file. Do not
                # reuse an old snapshot or retry invalid content/identity.
                time.sleep(.01)
        value = json.loads(payload)
        if not isinstance(value, dict): raise ValueError('invalid snapshot')
        stamp = value.get('time_unix', 0)
        if type(stamp) not in (int, float) or not math.isfinite(stamp): raise ValueError('invalid time')
        if pid is not None and (type(value.get('pid')) is not int or value['pid'] != pid
                or created is not None and stamp < created):
            return {'connected':False,'phase':'waiting_game'}
        age = time.time()-stamp
        if age < -1: raise ValueError('future snapshot')
        value['age_seconds'] = max(0,age)
        if value['age_seconds']>8: value.update(connected=False,phase='stale')
        return value
    except (OSError, ValueError): return {'connected':False,'phase':'waiting_game'}

def launch(game: Path, auto_start=True, sandbox=''):
    from .sandbox import process_box
    if any(process_box(p.pid) == sandbox for p in game_processes(game)): return False
    arguments = [str(game/GAME_EXE)]
    if auto_start: arguments += ['--', '--auto-start']
    if sandbox:
        from .sandbox import box_location
        _, launcher = box_location(sandbox)
        if not launcher.is_file(): raise RuntimeError('未找到沙盒启动器')
        arguments = [str(launcher), '/box:'+sandbox, *arguments]
    subprocess.Popen(arguments,cwd=game,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return True

def uninstall(game: Path):
    cfg=game/'override.cfg'
    if not cfg.exists(): return
    original=cfg.read_text(encoding='utf-8-sig')
    if BEGIN not in original: return
    if END not in original: raise RuntimeError('override.cfg 助手标记不完整')
    backup=DATA/'backups'/datetime.now().strftime('uninstall-%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    shutil.copy2(cfg,backup/'override.cfg')
    updated=re.sub(re.escape(BEGIN)+r'.*?'+re.escape(END), '', original, flags=re.S)
    temporary=cfg.with_suffix('.cfg.assistant.tmp')
    temporary.write_text(updated,encoding='utf8')
    os.replace(temporary,cfg)

def close_gracefully(game: Path, expected_pid=None, expected_create_time=None):
    processes=game_processes(game)
    if expected_pid is not None: processes = [p for p in processes if p.pid == expected_pid]
    if len(processes)>1: raise RuntimeError('检测到多个原生游戏实例，停止自动接管')
    if not processes:
        if expected_pid is not None: raise RuntimeError('游戏实例已变化，取消自动恢复')
        return
    pid=processes[0].pid
    created=processes[0].create_time()
    if ((expected_pid is not None and pid != expected_pid)
            or (expected_create_time is not None and created != expected_create_time)):
        raise RuntimeError('游戏实例已变化，取消自动恢复')
    user32=ctypes.windll.user32
    handles=[]
    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd,_):
        owner=ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==pid: handles.append(hwnd)
        return True
    user32.EnumWindows(callback,0)
    for handle in handles:
        # Root Godot window gets the application's normal close notification.
        title=ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(handle,title,512)
        if title.value=='Desktop Wallet Heroes':
            current=game_processes(game)
            if expected_pid is not None: current = [p for p in current if p.pid == expected_pid]
            if len(current)!=1 or current[0].pid!=pid or current[0].create_time()!=created:
                raise RuntimeError('关闭前游戏实例已变化，取消自动恢复')
            user32.PostMessageW(handle,0x0010,0,0)
            break
    else: raise RuntimeError('无法定位游戏主窗口，未强制终止')
    try: processes[0].wait(timeout=25)
    except psutil.TimeoutExpired: raise RuntimeError('游戏仍在正常退出结算中，未强制终止')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['status','install','launch','restart','uninstall'])
    args=parser.parse_args()
    game=discover_game()
    if not game: raise SystemExit('未找到已安装游戏')
    if args.action=='install': print('changed:',install(game))
    elif args.action=='launch': install(game); print('launched:',launch(game))
    elif args.action=='restart': install(game); close_gracefully(game); print('launched:',launch(game))
    elif args.action=='uninstall': uninstall(game)
    else: print(json.dumps({'game':str(game),'pids':[p.pid for p in game_processes(game)],'snapshot':snapshot()},ensure_ascii=False)[:3000])
