"""Explain each module's current native prerequisites without dispatching work."""
from .policy import MODULES, active_characters, reserve, capacity_goal, growth_budget, salvage_review, empty_socket_count


def module_reasons(snapshot, opportunities, config):
    if not snapshot.get('connected'):
        return {key: '等待当前游戏实例连接' for key in MODULES}
    inv = snapshot.get('inventory', {})
    if not inv.get('server_inventory_mutation_safe'):
        return {key: '等待服务器权威库存就绪' for key in MODULES}
    active = active_characters(snapshot)
    progress = inv.get('character_progress_by_char', {})
    points = '、'.join(f"{owner} {progress.get(owner, {}).get('skill_points', 0)} 点" for owner in active)
    d = opportunities.get('dungeon', {})
    loot = opportunities.get('loot', {}).get('count', 0)
    free = max(0, inv.get('bag_unlocked_slots', 0)-inv.get('bag_occupied_slots', 0))
    cap = capacity_goal(snapshot, opportunities, config)
    budget = growth_budget(snapshot, opportunities, config, cap)
    gold, keep = reserve(inv, budget)
    rows = salvage_review(snapshot, opportunities, config)
    usable = sum(r['eligible'] for r in rows)
    grades = sum(r['reason'] == '品质未勾选' for r in rows)
    trade = sum(r['reason'] == '可交易保护或交易信息未就绪' for r in rows)
    craft = opportunities.get('recipes', [])
    missing = sorted({str(m.get('definition', {}).get('name', m.get('item_data_id', '材料')))
                      for r in craft for m in r.get('plan', {}).get('materials', []) if not m.get('sufficient')})
    collection = opportunities.get('collections', {})
    reasons = {
        'mainline': '原生自动推进已启用，等待战斗结算' if not snapshot.get('stage_hold') else '等待解除关卡停留',
        'mail': '等待邮件列表刷新或可容纳的奖励',
        'formation': f'已上阵 {len(active)}/{snapshot.get("formation_limit", 1)} 人，等待新阵位或可招募角色',
        'skills': f'{points}；等待满足前置、等级与点数条件的技能' if points else '等待上阵角色与技能预览',
        'stones': '现有魔石无更优替换或可安全合成的同配方组合',
        'identify': '当前没有可鉴定的背包装备',
        'equipment': '现有装备未达到换装提升门槛，或不满足角色条件',
        'runes': f'可用金币 {max(0, int(gold-keep))}，等待节点前置或升级成本',
        'craft': ('背包已满，先清理再制造' if free == 0 else '等待当前等级配方材料：'+ '、'.join(missing[:4]) if missing else '当前装备已达目标品质，等待下一阶配方'),
        'enhancement': '原生强化未就绪，等待解锁或强化材料' if not opportunities.get('enhancement_ready') else '等待可安全强化的主力装备、报价与维护间隔',
        'socket': '原生镶嵌尚未就绪' if not opportunities.get('socket_ready') else '缺少可用宝石' if not opportunities.get('socket_gems') else '等待有空槽的主力装备与维护间隔',
        'collection': '原生图鉴尚未就绪' if not collection.get('ready') else '图鉴请求结算中' if collection.get('busy') else '暂无未登记且可安全消耗的图鉴候选',
        'loot': f'待领奖励 {loot}；背包已满，先分解、图鉴或扩容' if loot and free == 0 else f'待领奖励 {loot}，装备空位 {free}',
        'inventory': f'可分解 {usable} 条；品质未勾选 {grades} 条，可交易保护 {trade} 条，其余为穿戴、投入或备用保护',
        'dungeon': '等待领取副本奖励并腾出奖励容量' if d.get('entry_blocked') else '等待服务器会话' if d.get('session_required') else '副本进行中' if snapshot.get('in_dungeon') else f'开放 {d.get("unlocked_floor", 0)} 层，钥匙 {d.get("keys", 0)}；等待储备门槛或挑战间隔',
        'consumables': '原生补给设置已生效，或等待现有药水／经验卷轴及解锁条件',
    }
    access = opportunities.get('enhancement_access', {})
    required = int(access.get('required_clear_map_id', 0))
    if not opportunities.get('enhancement_ready') and not required:
        reasons['enhancement'] = '游戏尚未提供强化解锁条件，等待原生系统开放'
    if not opportunities.get('enhancement_ready') and required > 0:
        index = required-500101
        stage = f'{index//10+1}-{index%10+1}' if index >= 0 else str(required)
        reasons['enhancement'] = f'强化需要主线通关 {stage}；当前最高 {access.get("highest_cleared_map_id", 0)}'
    if cap:
        reasons['runes'] += f'；扩容目标 {cap["name"]}，当前保留 {int(keep)} 金币'
    return reasons
