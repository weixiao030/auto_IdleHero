"""Continuous salvage and material opt-in, exercised through the real scheduler."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import tempfile
import time


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import MODULES, normalize_config, plan, salvage_review

    config = normalize_config({'auto_start': False, 'salvage_grades': [1, 2, 3, 4]})
    check('材料分解与独立自动分解默认关闭', not config['salvage_include_materials'] and not config['auto_salvage'])
    for value in ('true', 1, None, [], {}):
        check('材料分解不把非布尔值当作许可：'+repr(value),
              not normalize_config({'salvage_include_materials': value})['salvage_include_materials'])
    snapshot = {'pid': 100, 'revision': 20, 'connected': True, 'phase': 'ready',
                'time_unix': time.time(), 'account': {'player': {'id': 501}},
                'deck': ['hero'], 'owned_characters': ['hero'], 'formation_limit': 1,
                'inventory': {'server_inventory_mutation_safe': True, 'steam_trade_ready': True,
                              'bag_occupied_slots': 2, 'bag_unlocked_slots': 50, 'materials': {'5': 10000},
                              'character_progress_by_char': {'hero': {'level': 19}},
                              'equipped_equipment_ids_by_char': {'hero': {'Head': 1}},
                              'items': [{'id': 1, 'name': 'worn', 'category': 'Equipment', 'type': 'Head',
                                         'grade': 3, 'power': 20, 'steam_trade_protected': False},
                                        {'id': 2, 'name': 'spare', 'category': 'Equipment', 'type': 'Head',
                                         'grade': 3, 'power': 10, 'steam_trade_protected': False}],
                              'material_records': [{'record_id': 11, 'item_data_id': 900, 'grade': 1,
                                                    'name': 'old material', 'count': 4, 'state_flag': 0}]},
                'native_busy': {}, 'pending_requests': {}}
    opportunities = {'pid': 100, 'account_id': 501, 'time_unix': time.time(),
                     'salvage': {'1': {'eligible': True, 'category_filter': 'armor', 'grade': 3},
                                 '2': {'eligible': True, 'category_filter': 'armor', 'grade': 3},
                                 '11': {'eligible': True, 'category_filter': 'material', 'grade': 1,
                                        'count': 4, 'item_data_id': 900}},
                     'recipes': [{'recipe_id': level, 'category': 'equipment', 'subtype': 'Necklace',
                                  'required_level': level, 'target': {'popupArgs': {}},
                                  'plan': {'materials': [{'item_data_id': data_id, 'required': 1}]}}
                                 for level, data_id in ((1, 900), (10, 901), (20, 902))]}
    eligible = lambda s, o, c: [row['id'] for row in salvage_review(s, o, c) if row['eligible']]
    check('默认自动候选只含剩余装备而不含材料', eligible(snapshot, opportunities, config) == [2])
    check('材料关闭明确显示保留原因', next(row for row in salvage_review(snapshot, opportunities, config)
                                         if row['id'] == 11)['reason'] == '材料分解已关闭')
    permitted = {**config, 'salvage_include_materials': True, 'salvage_allow_tradeable': True}
    check('材料明确开启后才允许旧阶剩余材料', eligible(snapshot, opportunities, permitted) == [2, 11])
    for option in (config, permitted):
        changed = deepcopy(snapshot)
        changed['inventory']['equipped_equipment_ids_by_char']['other'] = {'Head': 2}
        check('所有角色穿戴映射保护优先于交易和材料开关：'+str(option['salvage_include_materials']),
              1 not in eligible(changed, opportunities, option) and 2 not in eligible(changed, opportunities, option))
    changed = deepcopy(snapshot)
    changed['inventory']['material_records'][0]['state_flag'] = 4
    check('开启材料分解仍保护锁定材料', 11 not in eligible(changed, opportunities, permitted))
    stale_quote = {**opportunities, 'salvage_can_execute': True,
                   'salvage_selection': {'2': 1, '11': 4}, 'salvage_quote': {'request_id': 88}}
    check('材料关闭后旧混合报价不能执行', not any(a.kind == 'salvage_execute'
                                                     for a in plan(snapshot, stale_quote, {}, config)))

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)):
        engine = Engine()
        engine.booted = True
        engine.account_id = 501
        engine.snapshot = deepcopy(snapshot)
        engine.opportunities = deepcopy(opportunities)
        engine.config = normalize_config({**config, 'modules': {key: False for key in MODULES}})
        engine.running = False
        preview = engine.preview_salvage()
        engine.update_config({'salvage_include_materials': True})
        check('材料开关变化立即清空旧手动预览', engine.salvage_preview is None)
        try:
            engine.start_salvage(preview['token'])
            rejected = False
        except ValueError:
            rejected = True
        check('材料开关改变后旧预览令牌失效', rejected)
        engine.update_config({'salvage_include_materials': False, 'auto_salvage': True})
        engine.cached_json = lambda name: ({'rows': [], 'account_id': 501, 'pid': 100}
                                          if name == 'skill-previews.json' else engine.opportunities
                                          if name == 'opportunities.json' else {})

        def tick():
            engine.last_plan = 0
            engine.last_dispatch = 0
            with patch.object(engine, 'reload_config'), patch.object(engine, 'refresh_connection'), \
                    patch.object(engine, 'read_snapshot', return_value=engine.snapshot):
                engine.tick()

        tick()
        check('独立自动分解在总开关和16模块关闭时仍仅报价装备',
              not engine.running and engine.pending['action']['kind'] == 'salvage_quote'
              and engine.pending['action']['args'] == [2])
        engine.pending = None
        engine.opportunities.update(salvage_can_execute=True, salvage_selection={'2': 1},
                                    salvage_quote={'request_id': 90})
        tick()
        check('独立自动分解仍要求原生报价后才执行',
              engine.pending['action']['kind'] == 'salvage_execute'
              and engine.pending['action']['args'] == [100, 90, [{'id': 2, 'count': 1}]])
        engine.pending = None
        engine.opportunities.update(salvage_can_execute=False, salvage_selection={}, salvage_quote={})
        engine.snapshot['inventory']['items'].append({**engine.snapshot['inventory']['items'][1], 'id': 3})
        engine.opportunities['salvage']['3'] = {'eligible': True, 'category_filter': 'armor', 'grade': 3}
        tick()
        check('持续模式会重新评估后续掉落而非复用一次性预览', engine.pending['action']['args'] == [2, 3])
        pending_id = engine.pending['id']
        engine.stop_salvage(disable_auto=True)
        check('停止独立自动分解保留已提交请求且不启动成长',
              not engine.config['auto_salvage'] and not engine.running and engine.pending['id'] == pending_id)
        engine.pending = None
        tick()
        check('关闭独立自动分解后暂停状态不再提交新请求', engine.pending is None)
        engine.update_config({'auto_salvage': True})
        restarted = Engine()
        check('独立自动分解偏好持久化且材料仍默认关闭',
              restarted.config['auto_salvage'] and not restarted.config['salvage_include_materials'])
        engine.snapshot['account']['player']['id'] = 502
        tick()
        check('独立自动分解拒绝其他账号的旧候选', engine.pending is None)
