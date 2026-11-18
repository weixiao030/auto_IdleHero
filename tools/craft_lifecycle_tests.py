"""Craft readiness and useful material diagnostics, without account writes."""
from copy import deepcopy


def run(check):
    from wallet_assistant.policy import normalize_config, plan
    from wallet_assistant.diagnostics import module_reasons
    config = normalize_config({})
    snapshot = {'connected': True, 'phase': 'ready', 'revision': 21, 'pid': 101,
                'deck': ['hero'], 'owned_characters': ['hero'],
                'inventory': {'server_inventory_mutation_safe': True, 'items': [],
                              'materials': {'5': 10000}, 'bag_occupied_slots': 0,
                              'bag_unlocked_slots': 50,
                              'character_progress_by_char': {'hero': {'level': 34, 'skill_points': 0}}}}

    def recipe(level, material, job=''):
        return {'recipe_id': level, 'subtype': 'Head', 'required_level': level,
                'executable': True, 'target': {'name': 'fixture', 'type': 'Head',
                                              'popupArgs': {'JobWeaponOwner': job}},
                'plan': {'materials': [{'item_data_id': 99, 'required': 1,
                                       'sufficient': False, 'definition': {'name': material}}]}}

    opportunities = {'craft_state': {'ready': True, 'reason': 'ready'},
                     'recipes': [recipe(1, 'obsolete'), recipe(30, 'current'), recipe(40, 'future'),
                                 recipe(34, 'other-owner', 'other')]}
    actions = [row for row in plan(snapshot, opportunities, {}, config) if row.kind == 'craft']
    check('制造客户端已确认后继续产生当前配方动作', len(actions) == 1 and actions[0].args == [30, False, 0])
    reason = module_reasons(snapshot, opportunities, config)['craft']
    check('制造缺料只解释当前角色可用阶配方', 'current' in reason and all(label not in reason for label in ('obsolete', 'future', 'other-owner')))
    for state, phrase in [('pending', '结算'), ('outcome_unknown', '结果不明'),
                          ('result_unconfirmed', '来源核验'), ('unavailable', '客户端')]:
        changed = deepcopy(opportunities)
        changed['craft_state'] = {'ready': False, 'reason': state}
        check('原生制造状态阻塞时策略不消费：'+state,
              not any(row.kind == 'craft' for row in plan(snapshot, changed, {}, config)))
        check('原生制造状态阻塞原因可见：'+state,
              phrase in module_reasons(snapshot, changed, config)['craft'])
    changed = deepcopy(opportunities)
    changed['recipes'][1]['executable'] = False
    check('生命周期就绪不能覆盖原生配方不可执行', not any(row.kind == 'craft' for row in plan(snapshot, changed, {}, config)))
    disabled = normalize_config({'modules': {'craft': False}})
    check('关闭制造模块不会因生命周期恢复而消费', not any(row.kind == 'craft' for row in plan(snapshot, opportunities, {}, disabled)))
