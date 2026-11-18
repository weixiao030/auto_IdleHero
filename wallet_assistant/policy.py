"""Pure, account-independent growth planning from authoritative game projections."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import defaultdict
import math

MODULES = {
    'mainline': '主线推进', 'mail': '邮件奖励',
    'formation': '角色与阵容', 'skills': '技能养成', 'stones': '石头优化',
    'identify': '自动鉴定', 'equipment': '战力换装', 'runes': '星座加点', 'craft': '魔方制造',
    'enhancement': '装备强化', 'socket': '宝石镶嵌', 'collection': '永久图鉴',
    'loot': '自动宝箱', 'inventory': '换装后分解', 'dungeon': '副本挑战',
    'consumables': '战斗补给',
}
DEFAULTS = {
    'auto_start': True, 'auto_relaunch': False, 'tick_seconds': 6,
    'gold_reserve_ratio': 0.12, 'gold_reserve_min': 200,
    'equipment_improvement_ratio': 0.025, 'craft_target_grade': 3,
    'dungeon_interval_seconds': 900, 'dungeon_key_reserve': 0,
    'maintenance_interval_seconds': 180, 'spare_copies': 0,
    'allow_equipment_destruction': False,
    'stone_improvement_ratio': 0.025, 'salvage_grades': [1, 2, 3],
    'rune_priority': ['exp', 'gold', 'power', 'chest'],
    'prioritize_capacity': True, 'capacity_trigger_ratio': 0.85,
    'capacity_saving_ratio': 0.25, 'salvage_allow_tradeable': False,
    'salvage_include_materials': False, 'auto_salvage': False,
    'performance_mode': False, 'performance_fps': 10, 'minimal_effects': True,
    'modules': {key: True for key in MODULES},
}

def normalize_config(value):
    source = value if isinstance(value, dict) else {}
    out = {**DEFAULTS, 'modules': {**DEFAULTS['modules']}}
    ranges = {'tick_seconds': (3, 60), 'gold_reserve_ratio': (0, .8),
              'gold_reserve_min': (0, 1000000000), 'equipment_improvement_ratio': (0, .5),
              'craft_target_grade': (1, 5), 'dungeon_interval_seconds': (60, 86400),
              'dungeon_key_reserve': (0, 1000000), 'maintenance_interval_seconds': (30, 86400),
              'spare_copies': (0, 5), 'stone_improvement_ratio': (0, .5),
              'performance_fps': (10, 60), 'capacity_trigger_ratio': (.5, 1),
              'capacity_saving_ratio': (0, 1)}
    for key, default in DEFAULTS.items():
        if isinstance(default, bool) and isinstance(source.get(key), bool): out[key] = source[key]
    for key, (low, high) in ranges.items():
        v = source.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            out[key] = max(low, min(high, v))
            if isinstance(DEFAULTS[key], int): out[key] = int(out[key])
    if isinstance(source.get('modules'), dict):
        for key in MODULES:
            if isinstance(source['modules'].get(key), bool): out['modules'][key] = source['modules'][key]
    grades = source.get('salvage_grades')
    if isinstance(grades, list):
        out['salvage_grades'] = sorted({x for x in grades if type(x) is int and 1 <= x <= 10})
    priority = source.get('rune_priority')
    if isinstance(priority, list) and len(priority) == 4 and all(isinstance(x,str) for x in priority) and set(priority) == {'exp', 'gold', 'power', 'chest'}:
        out['rune_priority'] = list(priority)
    return out

@dataclass
class Action:
    module: str
    kind: str
    args: list
    label: str
    priority: float
    expected: dict | None = None

    @property
    def key(self):
        return f'{self.kind}:{self.args}'

    def json(self): return asdict(self)

def iid(item): return int(item.get('instance_id', item.get('id', 0)))
def did(item): return int(item.get('item_data_id', item.get('id', 0)))
def number(value, default=0):
    try:
        v = float(value)
        return v if math.isfinite(v) else default
    except (ValueError, TypeError): return default
def slot(item):
    return 'Weapon' if 'JobWeapon' in item.get('tags', []) else item.get('slot', item.get('type', ''))
def power(item):
    return max(0, number(item.get('power', item.get('stone_attack_power', 0))))
def stone_power(item): return power(item) / max(.1, number(item.get('cooldown_multiplier', 1), 1))

def valid_stone_merge_ids(opportunities, items, used):
    """Return only one current, unprotected merge group from native opportunities."""
    raw_ids = opportunities.get('stone_merge_ids', [])
    if not isinstance(raw_ids, list): return []
    ids = []
    for raw_id in raw_ids:
        try: current = int(raw_id)
        except (TypeError, ValueError): return []
        if current <= 0 or current in ids: return []
        ids.append(current)
    if len(ids) < 2 or any(current not in items for current in ids): return []
    rows = [items[current] for current in ids]
    data_ids = {did(row) for row in rows}
    if len(data_ids) != 1 or not next(iter(data_ids), 0): return []
    recipes = opportunities.get('stone_merge_recipes', {})
    if isinstance(recipes, dict) and recipes:
        data_id = next(iter(data_ids))
        result = recipes.get(str(data_id), recipes.get(data_id, 0))
        if not result or int(result) <= 0: return []
    protected_mask = 1 | 2 | 4 | 8 | 32 | 64
    if any(current in used or bool(row.get('steam_trade_protected', True))
           or int(row.get('state_flag', 0)) & protected_mask for current, row in zip(ids, rows)):
        return []
    return ids

def salvage_material_reserve_ids(snapshot, opportunities):
    """Keep the latest usable and next-tier recipe materials for each active hero."""
    active = active_characters(snapshot)
    progress = snapshot.get('inventory', {}).get('character_progress_by_char', {})
    levels = {owner: int(progress.get(owner, {}).get('level', 0)) for owner in active}
    if not levels or any(level <= 0 for level in levels.values()):
        return None
    recipes = opportunities.get('recipes', [])
    if not isinstance(recipes, list) or not recipes:
        return None
    grouped = defaultdict(list)
    for row in recipes:
        if not isinstance(row, dict): return None
        try:
            required_level = int(row.get('required_level', 0))
        except (TypeError, ValueError):
            return None
        category, subtype = row.get('category'), row.get('subtype')
        target = row.get('target', {})
        popup = target.get('popupArgs', {}) if isinstance(target, dict) else None
        plan_data = row.get('plan', {})
        materials = plan_data.get('materials') if isinstance(plan_data, dict) else None
        if required_level <= 0 or not category or not subtype or not isinstance(popup, dict) or not isinstance(materials, list):
            return None
        owner = str(popup.get('JobWeaponCharacterKey', popup.get('JobWeaponOwner', '')))
        grouped[(str(category), str(subtype), owner)].append((required_level, materials))

    reserved = set()
    for owner, level in levels.items():
        for (_, _, recipe_owner), rows in grouped.items():
            if recipe_owner and recipe_owner != owner:
                continue
            current = [row for row in rows if row[0] <= level]
            future = [row for row in rows if row[0] > level]
            selected_levels = set()
            if current:
                selected_levels.add(max(row[0] for row in current))
            if future:
                selected_levels.add(min(row[0] for row in future))
            for required_level, materials in rows:
                if required_level not in selected_levels:
                    continue
                for material in materials:
                    if not isinstance(material, dict): return None
                    try:
                        data_id = int(material.get('item_data_id', 0))
                    except (TypeError, ValueError):
                        return None
                    if data_id <= 0:
                        return None
                    reserved.add(data_id)
    return reserved

def collection_item_safe(item_id, snapshot, opportunities, material_reserve=None):
    """Require current authoritative, unlocked inventory metadata before registration."""
    inv = snapshot.get('inventory', {})
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        return False
    protected_mask = 1 | 2 | 4 | 8 | 32 | 64
    for item in inv.get('items', []):
        if iid(item) != item_id:
            continue
        return (not item.get('steam_trade_protected', True)
                and not item.get('stored') and not item.get('unidentified')
                and not int(item.get('state_flag', 0)) & protected_mask)

    record = next((row for row in inv.get('material_records', [])
                   if int(row.get('record_id', row.get('instance_id', row.get('id', 0))) or 0) == item_id), None)
    if record is None or int(record.get('count', 0)) <= 0 or record.get('stored'):
        return False
    if int(record.get('state_flag', 0)) & protected_mask:
        return False
    if not inv.get('server_inventory_mutation_safe'):
        return False
    if material_reserve is None:
        material_reserve = salvage_material_reserve_ids(snapshot, opportunities)
    if material_reserve is None:
        return False
    return did(record) not in material_reserve

def active_characters(snapshot):
    return [x for x in snapshot.get('deck', []) if x][:max(1, int(snapshot.get('formation_limit', 1)))]
def equipped_ids(inventory):
    ids = set()
    for mapping in inventory.get('equipped_equipment_ids_by_char', {}).values():
        ids.update(int(x) for x in mapping.values() if x)
    for values in inventory.get('equipped_stone_ids_by_char', {}).values():
        ids.update(int(x) for x in values if x)
    return ids
def reserve(inventory, config):
    gold = number(inventory.get('materials', {}).get('5', inventory.get('materials', {}).get(5, 0)))
    return gold, max(config['gold_reserve_min'], gold * config['gold_reserve_ratio'], config.get('_capacity_gold_reserve', 0))
def affordable(cost, inventory, config):
    gold, keep = reserve(inventory, config)
    materials = inventory.get('materials', {})
    for row in cost:
        key = int(row.get('item_data_id', row.get('item_id', 0)))
        needed = number(row.get('count', 0))
        have = number(materials.get(str(key), materials.get(key, 0)))
        if key == 5: have = max(0, gold - keep)
        if needed > have: return False
    return True

def skill_preview_affordable(preview, inventory, config, owner):
    cost = preview.get('cost')
    if not isinstance(cost, list) or not cost: return False
    combined = {}
    for row in cost:
        if not isinstance(row, dict): return False
        key = row.get('item_data_id', row.get('item_id', 0))
        needed = row.get('count', row.get('required', 0))
        if (type(key) not in (int, float) or not math.isfinite(key) or key <= 0 or int(key) != key
                or type(needed) not in (int, float) or not math.isfinite(needed) or needed <= 0 or int(needed) != needed):
            return False
        combined[int(key)] = combined.get(int(key), 0)+needed
    # Skill points belong to the skill's owner, never to the material bag.
    materials = dict(inventory.get('materials', {}))
    progress = inventory.get('character_progress_by_char', {}).get(owner, {})
    points = progress.get('skill_points')
    if 200501 in combined:
        if type(points) not in (int, float) or not math.isfinite(points) or points < 0 or int(points) != points:
            return False
        materials['200501'] = points
    return affordable([{'item_data_id':key,'count':count} for key,count in combined.items()],
                      {**inventory, 'materials': materials}, config)


def capacity_goal(snapshot, opportunities, config):
    """Find an attainable native capacity node, including its unmet prerequisites."""
    if not config['modules']['runes'] or not config['prioritize_capacity']: return None
    inv = snapshot.get('inventory', {})
    pressures = [
        ('equipment_inventory_slots', inv.get('bag_occupied_slots', 0), inv.get('bag_unlocked_slots', 0)),
        ('stone_inventory_slots', inv.get('stone_bag_occupied_slots', 0), inv.get('stone_bag_unlocked_slots', 0)),
        ('pending_loot_slots', opportunities.get('loot', {}).get('count', 0), inv.get('pending_loot_capacity', 0)),
    ]
    urgent = {key for key, used, cap in pressures if number(cap)>0 and number(used)/number(cap)>=config['capacity_trigger_ratio']}
    if not urgent: return None
    rows = {row['node_key']: row for row in opportunities.get('runes', []) if row.get('node_key')}

    def route(key, seen):
        row = rows.get(key)
        if key in seen or not row: return None
        if row.get('error', '') not in ['', 'insufficient_materials', 'rune_prerequisite_locked']: return None
        if int(row.get('from_level', 0)) >= int(row.get('max_level', 1)): return None
        path = {}
        for req in row.get('node', {}).get('prerequisites', []) if not row.get('from_level', 0) else []:
            parent = str(req.get('node', ''))
            if int(rows.get(parent, {}).get('from_level', 0)) >= int(req.get('level', 1)): continue
            before = route(parent, seen | {key})
            if before is None: return None
            path.update(before)
        path[key] = row
        return path

    choices = []
    for key, row in rows.items():
        if not any(effect.get('type')=='capacity' and effect.get('key') in urgent and number(effect.get('value'))>0 for effect in row.get('node', {}).get('effects', [])): continue
        path = route(key, set())
        if not path: continue
        frontier = [r for r in path.values() if not r.get('missing_requirements') and (r.get('ok') or r.get('error')=='insufficient_materials')]
        if not frontier: continue
        step = min(frontier, key=lambda r:(not affordable(r.get('cost', []), inv, config), sum(number(c.get('count')) for c in r.get('cost', [])), r['node_key']))
        choices.append((sum(number(c.get('count')) for r in path.values() for c in r.get('cost', [])), len(path), key, step))
    if not choices: return None
    _, _, target, step = min(choices, key=lambda value:value[:3])
    return {'target_key': target, 'node_key': step['node_key'], 'name': step.get('name', step['node_key']),
            'cost': step.get('cost', []), 'can_afford': bool(step.get('ok')) and affordable(step.get('cost', []), inv, config),
            'kinds': sorted(urgent)}

def growth_budget(snapshot, opportunities, config, capacity=None):
    capacity = capacity if capacity is not None else capacity_goal(snapshot, opportunities, config)
    if not capacity: return config
    gold_needed = sum(number(row.get('count')) for row in capacity['cost'] if int(row.get('item_data_id', row.get('item_id', 0)))==5)
    gold, base = reserve(snapshot.get('inventory', {}), config)
    # Once affordable, protect the whole next expansion. Until then, save a
    # bounded share so an expensive late node cannot freeze all other growth.
    available = max(0, gold-base)
    saving = gold_needed if gold_needed <= available else available*config['capacity_saving_ratio']
    return {**config, '_capacity_gold_reserve': base+saving}

def socket_gem_choices(item_id, snapshot, opportunities, config):
    """Use native costs, including the current expansion and growth reserve."""
    costs = opportunities.get('socket_gold_costs', {}).get(str(item_id), {})
    if not isinstance(costs, dict): return []
    gold, keep = reserve(snapshot.get('inventory', {}), growth_budget(snapshot, opportunities, config))
    choices = []
    for gem in opportunities.get('socket_gems', []):
        if not isinstance(gem, dict): continue
        ident, count, grade = gem.get('id'), gem.get('count'), gem.get('grade')
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 or int(value) != value
               for value in (ident, count, grade)):
            continue
        cost = costs.get(str(int(ident)))
        if (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0 or int(cost) != cost
                or cost > max(0, gold-keep)):
            continue
        choices.append({**gem, 'gold_cost': int(cost)})
    return choices


def has_socket_materials(item):
    """Keep real investments and unknown data, but ignore empty native slots."""
    layers = item.get('socket_materials', {})
    if not isinstance(layers, dict): return True
    return any(any(material != {} for material in slots) if isinstance(slots, list) else bool(slots)
               for slots in layers.values())


def empty_socket_count(item):
    # Native unified decoration policy: grade 3 has one slot, capped at six.
    slots = item.get('socket_slots')
    if slots is None:
        grade = item.get('grade', 1)
        if type(grade) is not int: return 0
        capacity = min(6, max(0, grade-2))
    elif isinstance(slots, dict) and type(slots.get('decoration', 0)) is int:
        capacity = slots.get('decoration', 0)
    else:
        return 0
    if not 0 <= capacity <= 6: return 0
    layers = item.get('socket_materials', {})
    if not isinstance(layers, dict): return 0
    materials = layers.get('decoration', [])
    if not isinstance(materials, list) or any(not isinstance(value, dict) for value in materials):
        return 0
    return sum(index >= len(materials) or materials[index] == {} for index in range(capacity))


def protected_items(snapshot, config, *, allow_tradeable=False):
    """Keep loadouts, investments, native locks, and useful spares for every owned job.

    A full bag changes the trade-off: the configured spare slot is a convenience,
    not a reason to leave disposable duplicates blocking rewards. Unowned job
    weapons are also disposable unless that job is actually part of the roster.
    """
    inv = snapshot.get('inventory', {})
    protected = equipped_ids(inv)
    groups = defaultdict(list)
    owned = set(snapshot.get('owned_characters', []))
    occupied = number(inv.get('bag_occupied_slots', 0))
    capacity = number(inv.get('bag_unlocked_slots', 0))
    bag_pressure = capacity > 0 and occupied / capacity >= float(config.get('capacity_trigger_ratio', .85))
    spare_copies = 0 if bag_pressure else int(config.get('spare_copies', 0))
    for item in inv.get('items', []):
        # Unknown Steam metadata is never permission to consume an item.
        trade_permission = (allow_tradeable and inv.get('steam_trade_ready') is True
                            and type(item.get('steam_trade_protected')) is bool)
        if item.get('steam_trade_protected', True) and not trade_permission:
            protected.add(iid(item))
        if item.get('stored') or item.get('unidentified') or int(item.get('state_flag', 0)) & (1|2|4|8|32|64):
            protected.add(iid(item))
        if item.get('enhance_level', 0) > 0 or item.get('socket_stats') or has_socket_materials(item):
            protected.add(iid(item))
        if item.get('category') == 'Equipment' or 'JobWeapon' in item.get('tags', []):
            # A stored or locked item cannot supply an automatic replacement loadout.
            if item.get('stored') or item.get('unidentified') or int(item.get('state_flag', 0)) & (2|4|8|32|64):
                continue
            popup = item.get('popupArgs', {})
            owner = popup.get('JobWeaponCharacterKey', popup.get('JobWeaponOwner', ''))
            groups[(slot(item), owner)].append(item)
    progress = inv.get('character_progress_by_char', {})
    for (item_slot, job), group in groups.items():
        # A job weapon for a character outside the owned roster has no current
        # or automatic next-stage consumer. Keeping it forever was the source
        # of the visible red-X backlog (for example, DLC-only heroes).
        if job and job not in owned:
            continue
        owners = [owner for owner in owned if not job or job == owner]
        if not owners or any(not progress.get(owner, {}).get('level') for owner in owners):
            # Incomplete roster metadata is not permission to discard equipment.
            protected.update(iid(item) for item in group)
            continue
        ranked = sorted(group, key=lambda x: (power(x), int(x.get('grade', 1)), -iid(x)), reverse=True)
        copies = 2 if item_slot == 'Ring' else 1
        group_ids = {iid(item) for item in group}
        equipped_by_owner = {
            owner: {int(value) for value in inv.get('equipped_equipment_ids_by_char', {}).get(owner, {}).values() if value}
            & group_ids
            for owner in owners
        }
        assigned = set().union(*equipped_by_owner.values()) if equipped_by_owner else set()
        # Allocate only missing slots. Equipped items already satisfy their
        # owner's requirement; they must not cause an unrelated duplicate to be
        # retained as if another character were unequipped.
        for owner in sorted(owners, key=lambda key: int(progress[key]['level'])):
            level = int(progress[owner]['level'])
            usable = [item for item in ranked if iid(item) not in assigned and int(item.get('requiredLevel', 1)) <= level]
            missing = max(0, copies - len(equipped_by_owner.get(owner, set())))
            assigned.update(iid(item) for item in usable[:missing])
        highest = max(int(progress[owner]['level']) for owner in owners)
        spares = [item for item in ranked if iid(item) not in assigned and int(item.get('requiredLevel', 1)) <= highest]
        assigned.update(iid(item) for item in spares[:spare_copies])
        future = [item for item in ranked if int(item.get('requiredLevel', 1)) > highest]
        if future:
            next_level = min(int(item.get('requiredLevel', 1)) for item in future)
            next_tier = [item for item in future if int(item.get('requiredLevel', 1)) == next_level]
            assigned.update(iid(item) for item in next_tier[:copies*len(owners)+spare_copies])
            # Also retain the strongest later drops without keeping every obsolete tier.
            assigned.update(iid(item) for item in future[:copies*len(owners)])
        protected.update(assigned)
    return protected

def plan(snapshot, opportunities, catalog, config):
    if not snapshot.get('connected') or snapshot.get('phase') != 'ready': return []
    if config['modules']['formation'] and snapshot.get('startup_selection_pending'):
        owned = snapshot.get('owned_characters', [])
        if owned:
            key = 'ayu' if 'ayu' in owned else owned[0]
            return [Action('formation', 'initial_pick', [key], '建立初始阵容', 200)]
    inv = snapshot.get('inventory', {})
    if not inv.get('server_inventory_mutation_safe'): return []
    out = []
    enabled = config['modules']
    active = active_characters(snapshot)
    owned = snapshot.get('owned_characters', [])
    heroes = snapshot.get('playable_characters', {})
    items = {iid(x): x for x in inv.get('items', [])}
    used = equipped_ids(inv)
    by_char = inv.get('equipped_equipment_ids_by_char', {})
    progress = inv.get('character_progress_by_char', {})
    capacity = capacity_goal(snapshot, opportunities, config)
    budget = growth_budget(snapshot, opportunities, config, capacity)
    gold, keep = reserve(inv, budget)
    protected = protected_items(snapshot, config)
    material_reserve = salvage_material_reserve_ids(snapshot, opportunities)
    defs = {int(x['id']): x for x in catalog.get('Items', [])}
    if enabled['mainline'] and snapshot.get('stage_hold'):
        out.append(Action('mainline', 'mainline_resume', [], '启用主线自动推进', 190))
    if enabled['consumables']:
        buffs = snapshot.get('consumables', {})
        if buffs.get('server_ready') and buffs.get('counts',{}).get('potion',0)>0 and not buffs.get('toggles', {}).get('potion'):
            out.append(Action('consumables', 'consumable_potion', [], '启用原生低血量自动补给', 170))
        if buffs.get('exp_scroll_unlocked') and not buffs.get('exp_scroll_enabled') and (buffs.get('usable_exp_count', 0)>0 or buffs.get('exp_scroll_active')):
            out.append(Action('consumables', 'consumable_exp', [], '启用现有经验卷轴', 85))
    if enabled['mail']:
        out.append(Action('mail', 'mail_refresh', [], '同步邮件奖励列表', 25))
        if opportunities.get('mail_ids'):
            out.append(Action('mail', 'mail_claim', [], '领取背包可容纳的邮件奖励', 159))
    if enabled['formation']:
        if snapshot.get('startup_selection_pending') and owned:
            key = 'ayu' if 'ayu' in owned else owned[0]
            out.append(Action('formation', 'initial_pick', [key], '建立初始阵容', 200))
        limit = max(1, int(snapshot.get('formation_limit', 1)))
        desired = list(active)
        remaining = [key for key in owned if key not in desired]
        # Keep the existing leader, add a healer when possible, then the strongest owned allies.
        remaining.sort(key=lambda key: (key == 'peach', inv.get('character_combat_power_by_char', {}).get(key, 0)), reverse=True)
        desired.extend(remaining[:max(0, limit-len(desired))])
        if desired and desired != active:
            out.append(Action('formation', 'formation', desired, '启用新阵位并补齐队伍', 180, {'formation': desired}))
        if len(owned) < limit:
            for row in opportunities.get('recruitment', []):
                if row.get('ok') and not row.get('owned') and not row.get('dlc_required') and 0 <= number(row.get('cost')) <= gold-keep:
                    out.append(Action('formation', 'character_purchase', [row['character_key']], f"招募 {row.get('name', '')}", 100))
    if enabled['skills']:
        for row in opportunities.get('skills', []):
            preview = row.get('preview', {})
            owner = row['owner']
            if (owner not in active or not preview.get('ok') or preview.get('can_afford') is not True
                    or not skill_preview_affordable(preview, inv, config, owner)): continue
            kind = 'skill_learn' if row['level'] == 0 else 'skill_level'
            # Spend points gradually across the unlocked tree, including late passive skills.
            prio = 120 - row['level'] * 3 + min(20, number(preview.get('required_spent_skill_points')) / 5)
            out.append(Action('skills', kind, [owner, row['id']], f"{heroes.get(owner, {}).get('char', owner)} · {row['name']} → {row['level']+1} 级", prio,
                              {'skill': [owner, row['id'], row['level']+1]}))
        # This native version activates every learned assist skill automatically.
    if enabled['equipment']:
        eligible = {int(x['instance_id']): x['owners'] for x in opportunities.get('equipment_eligibility', [])}
        for owner in active:
            equipped = by_char.get(owner, {})
            best = {}
            for id, owners in eligible.items():
                item = items.get(id, {})
                if owner not in owners or not item or item.get('unidentified') or item.get('stored'): continue
                if id in used and id not in equipped.values(): continue
                name = slot(item)
                # Each ring slot needs its own candidate; the strongest worn ring is not a replacement.
                if name == 'Ring' and id in equipped.values(): continue
                if name not in best or power(item) > power(best[name]): best[name] = item
            for name, item in best.items():
                if name == 'Ring':
                    ring_names = [k for k in equipped if k.startswith('Ring')]
                    weakest_name = min(ring_names, key=lambda k: power(items.get(int(equipped[k]), {}))) if len(ring_names)>=2 else ''
                    current = items.get(int(equipped.get(weakest_name, 0)), {})
                    if iid(item) in equipped.values(): continue
                else: current = items.get(int(equipped.get(name, 0)), {})
                if iid(item) == iid(current): continue
                if power(item) > power(current) * (1+config['equipment_improvement_ratio']):
                    out.append(Action('equipment', 'equipment_equip', [owner, iid(item)], f"{heroes.get(owner,{}).get('char',owner)} 换装 · {item.get('name','')}", 140,
                                      {'equipment': [owner, iid(item)]}))
    if enabled['identify']:
        unidentified = [id for id,item in items.items() if item.get('unidentified') and not item.get('stored') and not int(item.get('state_flag', 0)) & (2|4|32|64)]
        if unidentified: out.append(Action('identify', 'identify', unidentified[:160], f'鉴定 {len(unidentified[:160])} 件装备', 150))
    if enabled['stones']:
        stones = [x for x in items.values() if 'StoneWeapon' in x.get('tags', []) and not x.get('stored')]
        available = sorted([x for x in stones if iid(x) not in used], key=stone_power, reverse=True)
        for owner in active:
            slots = inv.get('equipped_stone_ids_by_char', {}).get(owner, [])
            count = int(opportunities.get('stone_slots', {}).get(owner, len(slots) or 1))
            if count <= 0: continue
            weakest = min(range(count), key=lambda i: stone_power(items.get(int(slots[i]), {})) if i<len(slots) else 0)
            current = items.get(int(slots[weakest]), {}) if weakest<len(slots) else {}
            if available and stone_power(available[0]) > stone_power(current)*(1+config['stone_improvement_ratio']):
                item = available.pop(0)
                out.append(Action('stones', 'stone_equip', [iid(item), weakest, owner], f"魔石择优 · {item.get('name','')} → 槽 {weakest+1}", 142,
                                  {'stone': [owner, weakest, iid(item)]}))
        ids = valid_stone_merge_ids(opportunities, items, used)
        if ids:
            out.append(Action('stones','stone_merge',ids,f"合成魔石 · {items[int(ids[0])].get('name','')}",90))
    if enabled['runes']:
        for row in opportunities.get('runes', []):
            is_capacity_step = capacity and row['node_key']==capacity['node_key']
            if not row.get('ok') or not affordable(row.get('cost', []), inv, config if is_capacity_step else budget): continue
            node = row.get('node', {})
            effects = node.get('effects', [])
            benefit = 5
            for effect in effects:
                kind, stat = effect.get('type'), effect.get('stat', effect.get('key', effect.get('flag', '')))
                if kind == 'unlock': benefit += 120 if stat in ['formation_slot', 'skill_slot', 'enhancement', 'socket'] else 45
                elif stat in ['ExpPercent','GoldPercent','ItemDropPercent']: benefit += 35
                elif stat in ['Attack','SkillDamagePercent','CooldownPercent','AttackSpeedPercent']: benefit += 25
                elif kind == 'capacity': benefit += 15
                else: benefit += 8
            cost = sum(number(x.get('count')) for x in row.get('cost', []))
            prio = 70 + benefit / (1+cost/max(1000,gold)*10) - int(row.get('from_level', 0))
            categories = set()
            for effect in effects:
                stat = str(effect.get('stat', effect.get('key', effect.get('flag', ''))))
                if 'Exp' in stat: categories.add('exp')
                elif 'Gold' in stat: categories.add('gold')
                elif 'chest' in stat.lower() or 'Drop' in stat: categories.add('chest')
                else: categories.add('power')
            rank = min((config['rune_priority'].index(key) for key in categories), default=3)
            # Respect the configured category order, then value/cost within a category.
            prio = 82 + (3-rank)*22 + min(20, max(0, prio-70)/10)
            if any(x.get('type')=='unlock' and x.get('flag',x.get('key','')) in ['formation_slot','skill_slot','enhancement','socket'] for x in effects): prio = 175
            if is_capacity_step: prio = 185
            out.append(Action('runes','rune_level',[row['node_key']],f"星图 · {row.get('name',row['node_key'])} → {row.get('to_level',1)}",prio,
                              {'rune':[row['node_key'],row.get('to_level',1)]}))
    if enabled['loot'] and number(opportunities.get('loot',{}).get('count'))>0:
        if int(inv.get('bag_occupied_slots',0)) < int(inv.get('bag_unlocked_slots',0)):
            # Native loot claiming is a local asynchronous controller action and
            # normally has no gateway request id. Keep the pre-claim count so the
            # scheduler can confirm that at least one reward left the queue.
            out.append(Action('loot','loot_claim',[],'领取待结算奖励',160,
                              {'loot_before': int(number(opportunities.get('loot',{}).get('count'), 0))}))
    if enabled['collection']:
        collections = opportunities.get('collections', {})
        if collections.get('ready') and not collections.get('busy'):
            collection_item_ids = set()
            for group in collections.get('collections', []):
                for row in group.get('slots', []):
                    if row.get('registered'): continue
                    for candidate in row.get('candidates', []):
                        id = int(candidate.get('item_id',0))
                        if id in protected or id in collection_item_ids or candidate.get('requires_confirmation'): continue
                        if not collection_item_safe(id, snapshot, opportunities, material_reserve): continue
                        out.append(Action('collection','collection_register',[str(group['id']),str(row['key']),id],f"图鉴登记 · {row.get('item_name','')}",186 if bag_pressure(snapshot, config) else 65))
                        collection_item_ids.add(id)
                        break
    if enabled['craft']:
        for row in opportunities.get('recipes', []):
            if not row.get('executable') or bag_pressure(snapshot, config): continue
            craft_gold = sum(number(m.get('required')) for m in row.get('plan', {}).get('materials', [])
                             if int(m.get('item_data_id', 0)) == 5)
            if craft_gold > max(0, gold-keep): continue
            target = row.get('target', {})
            target_slot = 'Weapon' if 'JobWeapon' in target.get('tags', []) else target.get('type','')
            job = target.get('popupArgs', {}).get('JobWeaponCharacterKey', target.get('popupArgs', {}).get('JobWeaponOwner',''))
            for owner in active:
                if job and job != owner: continue
                if int(row['required_level']) > int(progress.get(owner,{}).get('level',1)): continue
                equipped = by_char.get(owner, {})
                if target_slot == 'Ring':
                    rings = [items.get(int(value), {}) for key, value in equipped.items() if key.startswith('Ring')]
                    existing = min(rings, key=lambda item: (int(item.get('requiredLevel', 0)), int(item.get('grade', 1)))) if len(rings) >= 2 else {}
                else:
                    existing = items.get(int(equipped.get(target_slot, 0)), {})
                if int(existing.get('requiredLevel',0)) > int(row['required_level']): continue
                if int(existing.get('requiredLevel',0)) == int(row['required_level']) and int(existing.get('grade',1)) >= config['craft_target_grade']: continue
                # Skip obsolete tiers if a higher usable recipe exists, even when waiting for its materials.
                if any(r.get('subtype')==row['subtype'] and int(r['required_level'])>int(row['required_level']) and int(r['required_level'])<=int(progress.get(owner,{}).get('level',1)) for r in opportunities.get('recipes',[])): continue
                out.append(Action('craft','craft',[int(row['recipe_id']),False,0],f"魔方制造 · {target.get('name','')}（{owner}）",55+int(row['required_level'])/10))
    if enabled['inventory']:
        # Collection candidates get first use of surplus; retain material for usable recipes.
        collection_ids = {int(action.args[2]) for action in out if action.kind == 'collection_register'}
        review = salvage_review(snapshot, opportunities, config, collection_ids)
        surplus = [row['id'] for row in review if row['eligible']]
        salvage_rows = opportunities.get('salvage', {})
        material_records = {int(row.get('record_id', row.get('instance_id', row.get('id', 0)))): row
                            for row in inv.get('material_records', [])}
        selection = [int(x) for x in opportunities.get('salvage_selection', {})]
        quote_id = int(opportunities.get('salvage_quote', {}).get('request_id', 0))
        selected_counts = {int(id): int(count) for id, count in opportunities.get('salvage_selection', {}).items()}
        planned_counts = {}
        for id in selection:
            row = salvage_rows.get(str(id), salvage_rows.get(id, {}))
            planned_counts[id] = int(material_records[id]['count']) if row.get('category_filter') == 'material' and id in material_records else 1
        if (opportunities.get('salvage_can_execute') and quote_id > 0 and selection
                and all(id in surplus for id in selection) and selected_counts == planned_counts):
            selection.sort()
            request_rows = [{'id': id, 'count': planned_counts[id]} for id in selection]
            expected = {}
            gear_ids = [id for id in selection if salvage_rows.get(str(id), salvage_rows.get(id, {})).get('category_filter') != 'material']
            material_counts = {id: planned_counts[id] for id in selection
                               if salvage_rows.get(str(id), salvage_rows.get(id, {})).get('category_filter') == 'material'}
            if gear_ids: expected['consumed'] = gear_ids
            if material_counts: expected['material_counts'] = material_counts
            out.append(Action('inventory','salvage_execute',[int(snapshot['pid']),quote_id,request_rows],
                              '分解已报价的剩余装备与旧阶材料',188 if bag_pressure(snapshot, config) else 155,expected))
        elif surplus:
            full = int(inv.get('bag_occupied_slots',0)) / max(1,int(inv.get('bag_unlocked_slots',1)))
            out.append(Action('inventory','salvage_quote',surplus[:30],f'回收 {len(surplus[:30])} 件装备与旧阶材料',187 if full>=config['capacity_trigger_ratio'] else 45))
    if enabled['dungeon']:
        dungeon=opportunities.get('dungeon',{}); floor=min(int(dungeon.get('unlocked_floor',0)),max(0,int(dungeon.get('keys',0))-config['dungeon_key_reserve']))
        if floor>0 and not opportunities.get('in_dungeon') and not snapshot.get('in_dungeon') and not dungeon.get('entry_blocked') and not dungeon.get('session_required'):
            out.append(Action('dungeon','dungeon_enter',[floor],f'挑战副本第 {floor} 层',35))
    return sorted(out,key=lambda x:x.priority,reverse=True)


def bag_pressure(snapshot, config):
    inv = snapshot.get('inventory', {})
    cap = number(inv.get('bag_unlocked_slots'))
    return cap > 0 and number(inv.get('bag_occupied_slots'))/cap >= config['capacity_trigger_ratio']


def salvage_review(snapshot, opportunities, config, collection_ids=()):
    """Use the same live allow-list for automatic and standalone dismantling."""
    inv = snapshot.get('inventory', {})
    protected = protected_items(snapshot, config, allow_tradeable=config['salvage_allow_tradeable'])
    equipped = equipped_ids(inv)
    items = {iid(row): row for row in inv.get('items', [])}
    materials = {int(row.get('record_id', row.get('instance_id', row.get('id', 0)))): row
                 for row in inv.get('material_records', [])}
    material_reserve = salvage_material_reserve_ids(snapshot, opportunities)
    only = config.get('_salvage_ids')
    out = []
    for key, row in opportunities.get('salvage', {}).items():
        ident = int(key)
        category = row.get('category_filter')
        item = materials.get(ident) if category == 'material' else items.get(ident)
        reason = ''
        if only is not None and ident not in only: continue
        if category == 'material' and not config['salvage_include_materials']:
            reason = '材料分解已关闭'
        elif not item:
            reason = '库存记录已变化'
        elif ident in equipped:
            reason = '已穿戴'
        elif item.get('stored') or item.get('unidentified') or int(item.get('state_flag', 0)) & (1|2|4|8|32|64):
            reason = '锁定、仓库或未鉴定'
        elif category != 'material' and item.get('steam_trade_protected', True) and not (
                config['salvage_allow_tradeable'] and inv.get('steam_trade_ready') is True
                and type(item.get('steam_trade_protected')) is bool):
            reason = '可交易保护或交易信息未就绪'
        elif int(item.get('enhance_level', 0)) > 0 or item.get('socket_stats') or has_socket_materials(item) or int(row.get('level', 1)) > 1 or row.get('option', {}).get('slots'):
            reason = '强化或镶嵌投入'
        elif ident in protected:
            reason = '当前或下一阶段备用装备'
        elif ident in collection_ids:
            reason = '留作永久图鉴登记'
        elif int(row.get('grade', 1)) not in config['salvage_grades']:
            reason = '品质未勾选'
        elif not row.get('eligible'):
            reason = '原生分解条件未满足'
        elif category == 'material':
            data_id = int(row.get('item_data_id', row.get('definition', {}).get('id', 0)))
            if material_reserve is None or data_id in material_reserve:
                reason = '当前或下一阶配方材料'
            elif int(item.get('count', 0)) <= 0 or int(row.get('count', 0)) != int(item.get('count', 0)):
                reason = '材料数量已变化'
        elif category not in ('weapon', 'armor', 'accessory'):
            reason = '宝石或其他保留物品'
        count = int(item.get('count', 0)) if item and category == 'material' else 1
        out.append({'id': ident, 'name': (item or {}).get('name', row.get('definition', {}).get('name', str(ident))),
                    'grade': int(row.get('grade', 1)), 'count': count, 'category': category,
                    'tradeable': bool((item or {}).get('steam_trade_protected')),
                    'eligible': not bool(reason), 'reason': reason or '可分解'})
    return out
