"""Request native enhancement access without confusing missing metadata with a lock."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import tempfile
import time


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import normalize_config, plan, Action
    from wallet_assistant.diagnostics import module_reasons
    config = normalize_config({})
    snapshot = {'connected': True, 'phase': 'ready', 'pid': 101, 'revision': 21,
                'deck': ['hero'], 'owned_characters': ['hero'],
                'inventory': {'server_inventory_mutation_safe': True, 'items': [],
                              'materials': {'5': 10000}, 'bag_occupied_slots': 0,
                              'bag_unlocked_slots': 50,
                              'character_progress_by_char': {'hero': {'level': 34}}}}
    opportunities = {'enhancement_ready': False, 'enhancement_access_query_supported': True,
                     'enhancement_access': {'highest_cleared_map_id': 500137}}
    access = lambda s, o, c: [a for a in plan(s, o, {}, c) if a.kind == 'enhancement_access']
    actions = access(snapshot, opportunities, config)
    check('缺少强化解锁条件时先请求原生只读查询', len(actions) == 1 and actions[0].args == [])
    changed = deepcopy(opportunities)
    changed['enhancement_access']['required_clear_map_id'] = 500150
    check('已知未达解锁关卡时不反复查询', not access(snapshot, changed, config))
    changed['enhancement_access']['required_clear_map_id'] = 500110
    check('已知解锁条件后使用原生判定而不查询', not access(snapshot, changed, config))
    for capability in (False, None, 1, 'true'):
        changed = {**opportunities, 'enhancement_access_query_supported': capability}
        check('未明确支持查询的桥接不发请求：'+repr(capability), not access(snapshot, changed, config))
    check('关闭强化模块时不发查询', not access(snapshot, opportunities, normalize_config({'modules': {'enhancement': False}})))
    changed = deepcopy(snapshot)
    changed['inventory']['server_inventory_mutation_safe'] = False
    check('权威库存未就绪不发强化查询', not access(changed, opportunities, config))
    check('缺少条件说明等待查询而非断言解锁受限', '查询' in module_reasons(snapshot, opportunities, config)['enhancement'])
    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)):
        engine = Engine()
        action = Action('enhancement', 'enhancement_access', [], '查询强化解锁条件', 60)
        for success, uncertain in ((True, False), (False, False), (False, True)):
            engine.pending = {'id': 'fixture', 'pid': 101, 'action': action.json(), 'label': action.label}
            started = time.time()
            engine.finish(success, 'fixture', uncertain)
            delay = engine.cooldowns[action.key] - started
            check('只读强化查询五分钟退避且不因未知结果永久封锁：'+str((success, uncertain)),
                  299 <= delay <= 302 and engine.pending is None)
