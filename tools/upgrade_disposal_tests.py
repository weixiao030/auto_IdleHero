"""Keep real equipment upgrades out of salvage and collection consumption."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import tempfile
import time


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.diagnostics import module_reasons
    from wallet_assistant.policy import MODULES, normalize_config, plan, salvage_review

    config = normalize_config({'auto_start': True, 'auto_salvage': True, 'spare_copies': 0})
    snapshot = {'pid': 101, 'revision': 21, 'connected': True, 'phase': 'ready',
                'time_unix': time.time(), 'account': {'player': {'id': 501}},
                'deck': ['hero'], 'owned_characters': ['hero'], 'formation_limit': 1,
                'native_busy': {}, 'pending_requests': {},
                'inventory': {'server_inventory_mutation_safe': True, 'steam_trade_ready': True,
                              'bag_occupied_slots': 50, 'bag_unlocked_slots': 50,
                              'materials': {'5': 1000}, 'character_progress_by_char': {'hero': {'level': 30}},
                              'equipped_equipment_ids_by_char': {'hero': {'Head': 1}},
                              'items': [{'id': ident, 'name': name, 'category': 'Equipment', 'type': 'Head',
                                         'grade': 3, 'power': power, 'steam_trade_protected': False}
                                        for ident, name, power in ((1, 'worn', 10), (2, 'upgrade', 20), (3, 'surplus', 5))]}}
    opportunities = {'pid': 101, 'account_id': 501, 'time_unix': time.time(),
                     'equipment_eligibility': [{'instance_id': ident, 'owners': ['hero']} for ident in (1, 2, 3)],
                     'salvage': {str(ident): {'eligible': True, 'category_filter': 'armor', 'grade': 3, 'level': 1}
                                 for ident in (1, 2, 3)}}

    def allowed(s=snapshot, o=opportunities, c=config):
        return [row['id'] for row in salvage_review(s, o, c) if row['eligible']]

    check('满包分解保留已达到换装门槛的装备', allowed() == [3])
    check('升级装备有具体保留原因', next(row for row in salvage_review(snapshot, opportunities, config)
                                         if row['id'] == 2)['reason'] == '留作战力换装')
    check('分解面板等待原因包含待换装计数', '待换装 1 条' in module_reasons(snapshot, opportunities, config)['inventory'])
    actions = plan(snapshot, opportunities, {}, config)
    check('正常成长换装与分解使用同一候选',
          any(a.kind == 'equipment_equip' and a.args == ['hero', 2] for a in actions)
          and next(a for a in actions if a.kind == 'salvage_quote').args == [3])
    disabled = normalize_config({**config, 'modules': {key: False for key in MODULES}})
    check('暂停或关闭换装模块仍保留有用升级', allowed(c=disabled) == [3]
          and not any(a.kind == 'equipment_equip' for a in plan(snapshot, opportunities, {}, disabled)))
    changed = deepcopy(snapshot)
    changed['inventory']['items'][1]['power'] = 10.2
    check('未达到配置提升门槛的重复装备仍可清理', allowed(s=changed) == [2, 3])
    changed = deepcopy(opportunities)
    changed['equipment_eligibility'][1]['owners'] = ['other']
    check('其他角色专属物品不会误判成当前角色升级', allowed(o=changed) == [2, 3])
    changed = deepcopy(snapshot)
    changed['inventory']['equipped_equipment_ids_by_char']['other'] = {'Head': 2}
    check('其他角色已穿戴仍是硬保护', allowed(s=changed) == [3])
    changed = deepcopy(opportunities)
    changed.update(salvage_can_execute=True, salvage_selection={'2': 1}, salvage_quote={'request_id': 90})
    check('旧报价中的物品成为升级后禁止执行',
          not any(a.kind == 'salvage_execute' for a in plan(snapshot, changed, {}, config)))
    changed = deepcopy(opportunities)
    changed['collections'] = {'ready': True, 'busy': False, 'collections': [
        {'id': 'fixture', 'slots': [{'key': 'head', 'registered': False,
                                   'candidates': [{'item_id': 2}, {'item_id': 3}]}]}]}
    actions = plan(snapshot, changed, {}, config)
    check('图鉴跳过待换装升级而使用真正剩余物品',
          next(a for a in actions if a.kind == 'collection_register').args[-1] == 3
          and not any(a.kind in ('salvage_quote', 'salvage_execute') for a in actions))
    ring = deepcopy(snapshot)
    for row in ring['inventory']['items']:
        row['type'] = 'Ring'
    ring['inventory']['items'].append({**ring['inventory']['items'][0], 'id': 4, 'power': 100})
    ring['inventory']['equipped_equipment_ids_by_char'] = {'hero': {'Ring': 1, 'Ring2': 4}}
    check('双戒指按弱槽判断升级且保留强槽穿戴', allowed(s=ring) == [3]
          and any(a.kind == 'equipment_equip' and a.args == ['hero', 2]
                  for a in plan(ring, opportunities, {}, config)))
    multiple = deepcopy(snapshot)
    multiple['formation_limit'] = 2
    multiple['deck'].append('ally')
    multiple['owned_characters'].append('ally')
    multiple['inventory']['character_progress_by_char']['ally'] = {'level': 30}
    multiple['inventory']['items'][2]['power'] = 15
    multiple['inventory']['items'].append({**multiple['inventory']['items'][0], 'id': 4})
    multiple['inventory']['equipped_equipment_ids_by_char']['ally'] = {'Head': 4}
    multi_opportunities = deepcopy(opportunities)
    for row in multi_opportunities['equipment_eligibility']:
        row['owners'].append('ally')
    check('多角色同时缺升级时次强可用装备也保留', allowed(s=multiple, o=multi_opportunities) == [])
    multiple['inventory']['equipped_equipment_ids_by_char']['hero']['Head'] = 2
    check('主力换上最强后仍给另一角色保留次强升级', allowed(s=multiple, o=multi_opportunities) == [1])
    multiple['inventory']['equipped_equipment_ids_by_char']['ally']['Head'] = 3
    multiple['inventory']['items'].append({**multiple['inventory']['items'][0], 'id': 5, 'power': 12})
    multi_opportunities['equipment_eligibility'].append({'instance_id': 5, 'owners': ['hero', 'ally']})
    multi_opportunities['salvage']['5'] = {'eligible': True, 'category_filter': 'armor', 'grade': 3, 'level': 1}
    check('全队换装后不再保留无法提升的旧件', allowed(s=multiple, o=multi_opportunities) == [1, 5])

    with tempfile.TemporaryDirectory() as directory, patch.object(runtime, 'DATA', Path(directory)):
        engine = Engine()
        engine.booted = True
        engine.account_id = 501
        engine.snapshot = deepcopy(snapshot)
        engine.opportunities = deepcopy(opportunities)
        engine.config = deepcopy(config)
        engine.running = True
        engine.cached_json = lambda name: ({'rows': [], 'account_id': 501, 'pid': 101}
                                          if name == 'skill-previews.json' else engine.opportunities
                                          if name == 'opportunities.json' else {})

        def tick():
            engine.last_plan = 0
            engine.last_dispatch = 0
            with patch.object(engine, 'reload_config'), patch.object(engine, 'refresh_connection'), \
                    patch.object(engine, 'read_snapshot', return_value=engine.snapshot):
                engine.tick()

        tick()
        check('真实调度独立自动只清理弱件不抢走升级', engine.pending['action']['kind'] == 'salvage_quote'
              and engine.pending['action']['args'] == [3])
        engine.pending = None
        engine.snapshot['inventory']['items'] = engine.snapshot['inventory']['items'][:2]
        engine.opportunities['salvage'].pop('3')
        tick()
        check('清理后真实调度接续换装', engine.pending['action']['kind'] == 'equipment_equip'
              and engine.pending['action']['args'] == ['hero', 2])
        engine.pending = None
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']['hero']['Head'] = 2
        tick()
        check('完成换装后旧弱件可回收且新穿戴不分解', engine.pending['action']['kind'] == 'salvage_quote'
              and engine.pending['action']['args'] == [1])
        engine.pending = None
        engine.snapshot = deepcopy(snapshot)
        engine.opportunities = deepcopy(opportunities)
        engine.config['auto_salvage'] = False
        engine.running = False
        preview = engine.preview_salvage()
        check('暂停时手动预览同样不包含待换装升级', [r['id'] for r in preview['candidates']] == [3])
        engine.start_salvage(preview['token'])
        check('一次性独立执行同样只处理弱件', engine.standalone_salvage_action().args == [3])
        engine.stop_salvage()
        engine.config['auto_salvage'] = True
        engine.config['modules'] = {key: False for key in MODULES}
        tick()
        check('成长暂停时独立自动保留升级且不暗中换装', not engine.running
              and engine.pending['action']['kind'] == 'salvage_quote' and engine.pending['action']['args'] == [3])
