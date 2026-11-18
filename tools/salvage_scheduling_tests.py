"""Continuous dismantling must share growth scheduling without blocking full bags."""
from copy import deepcopy
from itertools import count
from pathlib import Path
from unittest.mock import patch
import tempfile


def run(check):
    from wallet_assistant import runtime
    from wallet_assistant.engine import Engine
    from wallet_assistant.policy import MODULES, normalize_config

    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime, 'DATA', Path(temporary)), \
            patch('wallet_assistant.engine.time.time', return_value=1000):
        sequence = count()

        def engine(*, skill=False, rune=False, loot=False, upgrade=False, full=False,
                   quoted=False, running=True, auto=True, modules=None):
            e = Engine(data_dir=Path(temporary)/str(next(sequence)))
            e.booted = True
            e.account_id = 501
            e.running = running
            e.config = normalize_config({'auto_start': running, 'auto_salvage': auto,
                                         'modules': modules or {}})
            e.snapshot = {'connected': True, 'phase': 'ready', 'revision': 21,
                          'pid': 101, 'time_unix': 1000, 'account': {'player': {'id': 501}},
                          'deck': ['hero'], 'owned_characters': ['hero'], 'formation_limit': 1,
                          'native_busy': {}, 'pending_requests': {},
                          'inventory': {'server_inventory_mutation_safe': True,
                                        'bag_occupied_slots': 50 if full else 10, 'bag_unlocked_slots': 50,
                                        'materials': {'5': 10000},
                                        'character_progress_by_char': {'hero': {'level': 30, 'skill_points': int(skill)}},
                                        'equipped_equipment_ids_by_char': {'hero': {'Head': 1}},
                                        'items': [{'id': ident, 'category': 'Equipment', 'type': 'Head',
                                                   'grade': 1, 'power': power, 'steam_trade_protected': False}
                                                  for ident, power in [(1, 20), (2, 10)]]}}
            e.opportunities = {'pid': 101, 'account_id': 501, 'time_unix': 1000,
                               'salvage': {'2': {'eligible': True, 'category_filter': 'armor', 'grade': 1}},
                               'skills': [{'id': 700001, 'owner': 'hero', 'level': 0, 'name': 'fixture skill',
                                           'preview': {'ok': True, 'can_afford': True,
                                                       'cost': [{'item_data_id': 200501, 'count': 1}]}}] if skill else [],
                               'runes': [{'node_key': 'fixture_exp', 'name': 'fixture exp', 'ok': True,
                                          'from_level': 0, 'to_level': 1, 'max_level': 5,
                                          'cost': [{'item_data_id': 5, 'count': 1000}],
                                          'node': {'effects': [{'type': 'stat', 'stat': 'ExpPercent', 'value': 1}]}}] if rune else [],
                               'loot': {'count': 1 if loot else 0}}
            if upgrade:
                e.snapshot['inventory']['items'].append({**e.snapshot['inventory']['items'][0], 'id': 3, 'power': 50})
                e.opportunities['equipment_eligibility'] = [{'instance_id': 3, 'owners': ['hero']}]
            if quoted:
                e.opportunities.update(salvage_can_execute=True, salvage_selection={'2': 1},
                                       salvage_quote={'request_id': 90})
            e.cached_json = lambda name: ({'rows': e.opportunities['skills'], 'pid': 101, 'account_id': 501}
                                          if name == 'skill-previews.json' else e.opportunities
                                          if name == 'opportunities.json' else {})
            return e

        def tick(e):
            e.last_plan = e.last_dispatch = 0
            with patch.object(e, 'reload_config'), patch.object(e, 'refresh_connection'), \
                    patch.object(e, 'read_snapshot', return_value=e.snapshot):
                e.tick()
            return e.pending['action']['kind'] if e.pending else None

        check('低背包压力时独立自动不抢占可学习技能', tick(engine(skill=True)) == 'skill_learn')
        check('低背包压力时独立自动不抢占可支付星座', tick(engine(rune=True)) == 'rune_level')
        check('有空位时先领取现有宝箱而非反复报价', tick(engine(loot=True)) == 'loot_claim')
        check('低背包压力时先穿可用升级再清理剩余物品', tick(engine(upgrade=True)) == 'equipment_equip')
        e = engine(full=True, skill=True, rune=True, loot=True, upgrade=True)
        check('满包仍先清理真正弱件再执行成长', tick(e) == 'salvage_quote' and e.pending['action']['args'] == [2])
        e = engine(full=True, quoted=True, skill=True, rune=True)
        check('满包有效报价仍优先执行回收', tick(e) == 'salvage_execute')
        e = engine(running=False, skill=True, rune=True, loot=True, upgrade=True)
        check('暂停成长时独立自动仅分解而不启动成长', tick(e) == 'salvage_quote')
        e = engine(running=False, skill=True, rune=True)
        e.inspection_requested = True
        check('暂停的独立模式巡检也不擅自加点', tick(e) == 'salvage_quote' and not e.running)
        e = engine(modules={key: False for key in MODULES})
        check('关闭16模块仍可独立自动清理', tick(e) == 'salvage_quote')
        e = engine(skill=True, modules={'inventory': False})
        first = tick(e)
        e.pending = None
        e.snapshot['inventory']['character_progress_by_char']['hero']['skill_points'] = 0
        check('正常分解模块关闭时独立模式先让出成长再继续清理',
              first == 'skill_learn' and tick(e) == 'salvage_quote')
        e = engine(skill=True, auto=False, modules={'inventory': False})
        check('独立和正常分解均关闭时仍正常学习技能', tick(e) == 'skill_learn')
        e = engine(skill=True, quoted=True)
        e.module_last_run.update(skills=700, inventory=1000)
        check('长期等待的技能能获得机会而非被连续回收饿死', tick(e) == 'skill_learn')
        e = engine(skill=True, quoted=True)
        original = {'id': 'existing', 'label': 'fixture pending', 'started': 1000, 'action': {'kind': 'mail_refresh'}}
        e.pending = deepcopy(original)
        with patch.object(e, 'reconcile'):
            tick(e)
        check('共享调度仍保留现有待结算请求且不并发', e.pending == original)
        e = engine(skill=True, auto=False)
        e.preview_salvage()
        e.start_salvage(e.salvage_preview['token'])
        check('用户手动一次性清理仍按预览优先执行', tick(e) == 'salvage_quote')
