"""Read Sandboxie's process and box mappings without changing sandbox policy."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from functools import lru_cache
import os
from pathlib import Path
import re


@lru_cache(maxsize=1)
def _library():
    if os.name != 'nt':
        return None
    roots = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Sandboxie') as key:
            roots.append(Path(winreg.QueryValueEx(key, 'Install_Dir')[0]))
    except OSError:
        pass
    for variable in ('ProgramW6432', 'ProgramFiles'):
        base = Path(os.environ.get(variable, 'C:/Program Files'))
        roots.extend((base/'Sandboxie-Plus', base/'Sandboxie'))
    for root in dict.fromkeys(roots):
        path = root/'SbieDll.dll'
        if path.is_file():
            try:
                return ctypes.WinDLL(str(path)), root/'Start.exe'
            except OSError:
                continue
    return None


def _dos_path(value):
    if value.startswith('\\??\\'):
        return Path(value[4:])
    if not value.startswith('\\Device\\'):
        return Path(value)
    query = ctypes.WinDLL('kernel32', use_last_error=True).QueryDosDeviceW
    query.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
    query.restype = wintypes.DWORD
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        buffer = ctypes.create_unicode_buffer(32768)
        if query(letter+':', buffer, len(buffer)):
            device = buffer.value
            if value.casefold().startswith((device+'\\').casefold()):
                return Path(letter+':'+value[len(device):])
    raise RuntimeError('无法解析沙盒文件目录，等待连接')


def process_box(pid):
    library = _library()
    if library is None:
        return ''
    query = library[0].SbieApi_QueryProcess
    query.argtypes = [ctypes.c_size_t, wintypes.LPWSTR, wintypes.LPWSTR,
                      wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG)]
    query.restype = wintypes.LONG
    box = ctypes.create_unicode_buffer(256)
    status = query(pid, box, None, None, None)
    return box.value if status == 0 else ''


def box_location(name):
    if not isinstance(name, str) or not re.fullmatch(r'[\w-]{1,64}', name):
        raise RuntimeError('沙盒名称无效，等待游戏启动')
    library = _library()
    if library is None:
        raise RuntimeError('未找到 Sandboxie，无法恢复沙盒游戏')
    query = library[0].SbieApi_QueryBoxPath
    query.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.LPWSTR,
                      wintypes.LPWSTR, ctypes.POINTER(wintypes.ULONG),
                      ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(wintypes.ULONG)]
    query.restype = wintypes.LONG
    buffer = ctypes.create_unicode_buffer(8192)
    length = wintypes.ULONG(ctypes.sizeof(buffer))
    if query(name, buffer, None, None, ctypes.byref(length), None, None) != 0 or not buffer.value:
        raise RuntimeError(f'无法读取沙盒 {name} 的文件目录')
    return _dos_path(buffer.value), library[1]


def virtual_path(path, pid):
    """Map a process's Sandboxie drive copy back to its in-box path."""
    path = Path(path)
    name = process_box(pid)
    if not name:
        return path
    root, _ = box_location(name)
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return path
    if len(parts) >= 3 and parts[0].casefold() == 'drive' and re.fullmatch('[A-Za-z]', parts[1]):
        return Path(parts[1]+':/')/Path(*parts[2:])
    return path


def connection(process, data, preferred=''):
    """Bind IPC to one process; inside the same box its virtual path is enough."""
    name = process_box(process.pid) if process is not None else preferred
    directory = data/'runtime'
    launcher = None
    if name and process_box(os.getpid()) != name:
        root, launcher = box_location(name)
        users = ['current', os.environ.get('USERNAME', '')]
        candidates = [root/'user'/user/'AppData/Local/WalletHeroesAssistant/runtime'
                      for user in dict.fromkeys(users) if user]
        directory = next((path for path in candidates if path.is_dir()), candidates[0])
    elif name:
        _, launcher = box_location(name)
    if process is not None:
        isolated = directory/'instances'/str(process.pid)
        if isolated.is_dir(): directory = isolated
    return {'sandbox': name, 'directory': directory, 'launcher': launcher,
            'pid': process.pid if process is not None else None,
            'created': process.create_time() if process is not None else None}
