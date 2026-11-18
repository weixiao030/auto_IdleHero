"""Transient Windows snapshot replacement must not bypass identity or freshness checks."""
import json
from pathlib import Path
from unittest.mock import patch


def run(check):
    from wallet_assistant import runtime

    fresh = {'connected': True, 'phase': 'ready', 'pid': 101, 'time_unix': 1000}
    directory = Path('fixture-runtime')

    def read(sequence):
        with patch.object(Path, 'read_text', side_effect=sequence) as reader, \
                patch.object(runtime.time, 'time', return_value=1000), \
                patch.object(runtime.time, 'sleep') as sleep:
            result = runtime.snapshot(directory, pid=101, created=900)
        return result, reader.call_count, sleep.call_count

    result, reads, waits = read([FileNotFoundError(), json.dumps(fresh)])
    check('快照替换瞬间路径缺失可重读恢复连接', result.get('connected') is True and reads == 2)
    result, reads, waits = read([PermissionError(), json.dumps(fresh)])
    check('快照短暂占用后可重读恢复连接', result.get('connected') is True and reads == 2)
    result, reads, waits = read([FileNotFoundError(), PermissionError(), json.dumps(fresh)])
    check('连续两次文件读取失败后可恢复', result.get('connected') is True and reads == 3 and waits == 2)
    result, reads, waits = read([FileNotFoundError()] * 4)
    check('持续缺失仍断线且最多读取三次', result.get('connected') is False and reads == 3 and waits == 2)
    result, reads, waits = read([PermissionError()] * 4)
    check('持续占用仍断线且重读次数有限', result.get('connected') is False and reads == 3 and waits == 2)
    for label, changed in [
        ('其他进程', {**fresh, 'pid': 102}),
        ('布尔进程号', {**fresh, 'pid': True}),
        ('进程创建前', {**fresh, 'time_unix': 899}),
        ('过期', {**fresh, 'time_unix': 991}),
        ('未来', {**fresh, 'time_unix': 1002}),
        ('非法时间', {**fresh, 'time_unix': float('nan')}),
        ('非对象', []),
    ]:
        result, reads, waits = read([FileNotFoundError(), json.dumps(changed)])
        check('重读后仍拒绝' + label + '快照', result.get('connected') is False and reads == 2)
    result, reads, waits = read(['{', json.dumps(fresh)])
    check('语法损坏的快照直接拒绝且不重读', result.get('connected') is False and reads == 1 and waits == 0)
    result, reads, waits = read([json.dumps(fresh)])
    check('正常快照读取不额外等待', result.get('connected') is True and reads == 1 and waits == 0)
