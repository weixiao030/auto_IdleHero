"""Offline regression scenarios; never changes a game account."""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json
import threading
import tempfile
import time
import urllib.request

def run(output: Path):
    from wallet_assistant import runtime
    from wallet_assistant.policy import Action, normalize_config, plan, protected_items, affordable, capacity_goal, growth_budget, reserve
    from wallet_assistant.engine import Engine, opportunities_ready
    from wallet_assistant.server import Server
    tests=[]
    def check(name, condition):
        tests.append({'name':name,'passed':bool(condition)})
        if not condition: raise AssertionError(name)
    cfg=normalize_config({})
    snapshot={'connected':True,'phase':'ready','revision':17,'pid':999,'account':{'player':{'id':1001}},'deck':['new_hero'],
        'formation_limit':1,'owned_characters':['new_hero'],'inventory':{
            'server_inventory_mutation_safe':True,'materials':{'5':10000},'items':[],
            'character_progress_by_char':{'new_hero':{'level':150}},
            'bag_occupied_slots':0,'bag_unlocked_slots':100}}
    check('通用模块与自动化默认开启且不囤额外备件',all(cfg['modules'].values()) and cfg['auto_start'] and cfg['spare_copies']==0)
    invalid=normalize_config({'tick_seconds':-20,'gold_reserve_ratio':float('nan'),'modules':{'skills':'false'}})
    check('损坏配置回落并限幅',invalid['tick_seconds']==3 and invalid['gold_reserve_ratio']==.12 and invalid['modules']['skills'])
    bootstrap=deepcopy(snapshot);bootstrap['startup_selection_pending']=True
    bootstrap['inventory']['server_inventory_mutation_safe']=False
    check('新号选角不被库存条件阻塞',plan(bootstrap,{}, {},cfg)[0].kind=='initial_pick')
    check('金币储备由消费共享',not affordable([{'item_data_id':5,'count':9500}],snapshot['inventory'],cfg))
    s=deepcopy(snapshot);s['inventory']['server_inventory_mutation_safe']=False
    check('非权威库存禁止消费',plan(s,{}, {},cfg)==[])
    check('跨快照旧机会不会触发动作',not opportunities_ready({'pid':1,'time_unix':100},{'pid':1,'time_unix':80},now=100))
    check('同步机会快照允许继续调度',opportunities_ready({'pid':1,'time_unix':100},{'pid':1,'time_unix':95},now=100))
    skill_ready=deepcopy(snapshot);skill_ready['inventory']['character_progress_by_char']['new_hero']['skill_points']=1
    late={'skills':[{'owner':'new_hero','id':700001,'name':'后期技能','level':9,'preview':{'ok':True,'can_afford':True,'cost':[{'item_data_id':200501,'count':1}]}}]}
    check('任意角色150级仍加点',any(a.kind=='skill_level' and a.args==['new_hero',700001] for a in plan(skill_ready,late,{},cfg)))
    exhausted=deepcopy(late);exhausted['skills'][0]['preview']['can_afford']=False
    check('技能预览报告点数不足时不请求',not any(a.module=='skills' for a in plan(skill_ready,exhausted,{},cfg)))
    exhausted['skills'][0]['preview']['can_afford']=True
    check('预览过期但权威库存点数不足时不请求',not any(a.module=='skills' for a in plan(snapshot,exhausted,{},cfg)))
    check('技能点到账后自动继续加点',any(a.kind=='skill_level' for a in plan(skill_ready,exhausted,{},cfg)))
    del exhausted['skills'][0]['preview']['can_afford']
    check('技能资源预览缺失时等待刷新',not any(a.module=='skills' for a in plan(snapshot,exhausted,{},cfg)))
    malformed=deepcopy(late);malformed['skills'][0]['preview']['cost']=[]
    check('技能预览缺少成本时安全等待',not any(a.module=='skills' for a in plan(skill_ready,malformed,{},cfg)))
    cfg_off=normalize_config({'modules':{'skills':False}})
    check('关闭模块停止产生动作',not any(a.module=='skills' for a in plan(snapshot,late,{},cfg_off)))
    s=deepcopy(snapshot);s.update(formation_limit=3,owned_characters=['new_hero','healer','tank'])
    check('按开放阵位补齐队伍',any(a.kind=='formation' and len(a.args)==3 for a in plan(s,{}, {},cfg)))
    s=deepcopy(snapshot);s['inventory']['items']=[{'id':1,'category':'Equipment','type':'Head','power':100,'state_flag':4},{'id':2,'category':'Equipment','type':'Head','power':20,'enhance_level':5}]
    check('锁定和投资装备受保护',{1,2}.issubset(protected_items(s,cfg)))
    s['inventory']['equipped_equipment_ids_by_char']={'new_hero':{'Head':1}}
    check('不分解已穿戴装备',not any(a.kind=='salvage_quote' and 1 in a.args for a in plan(s,{'salvage':{'1':{'eligible':True,'category_filter':'armor'}}},{},cfg)))
    s=deepcopy(snapshot);s['inventory']['items']=[{'id':1,'tags':['StoneWeapon'],'power':100}]
    s['inventory']['equipped_stone_ids_by_char']={'new_hero':[1]}
    check('不合成已穿戴魔石',not any(a.kind=='stone_merge' for a in plan(s,{'stone_merge_ids':[1,2],'stone_slots':{'new_hero':1}},{},cfg)))
    stones=deepcopy(snapshot)
    stones['inventory']['items']=[
        {'id':1,'item_data_id':200205,'tags':['StoneWeapon'],'power':11,'state_flag':1,'steam_trade_protected':False},
        {'id':2,'item_data_id':200205,'tags':['StoneWeapon'],'power':11,'state_flag':0,'steam_trade_protected':False},
        {'id':3,'item_data_id':200205,'tags':['StoneWeapon'],'power':11,'state_flag':0,'steam_trade_protected':False},
    ]
    stones['inventory']['equipped_stone_ids_by_char']={'new_hero':[1]}
    stone_opportunities={'stone_merge_ids':[1,2,3],'stone_merge_recipes':{'200205':200206}}
    check('合成候选排除已装备魔石',not any(a.kind=='stone_merge' for a in plan(stones,stone_opportunities,{},cfg)))
    stone_opportunities['stone_merge_ids']=[2,3]
    check('合成候选要求当前同配方且未保护',any(a.kind=='stone_merge' and a.args==[2,3] for a in plan(stones,stone_opportunities,{},cfg)))
    stone_opportunities['stone_merge_ids']=[2,99]
    check('过期魔石候选直接丢弃等待刷新',not any(a.kind=='stone_merge' for a in plan(stones,stone_opportunities,{},cfg)))
    stones['inventory']['items'][1]['state_flag']=1
    stone_opportunities['stone_merge_ids']=[2,3]
    check('状态位变化后的魔石候选不再提交',not any(a.kind=='stone_merge' for a in plan(stones,stone_opportunities,{},cfg)))
    check('零魔石槽不会中断其他成长调度',any(a.kind=='mail_refresh' for a in plan(s,{'stone_slots':{'new_hero':0}},{},cfg)))
    rings=deepcopy(snapshot)
    rings['inventory']['items']=[{'id':i,'category':'Equipment','type':'Ring','power':v} for i,v in [(1,100),(2,10),(3,50)]]
    rings['inventory']['equipped_equipment_ids_by_char']={'new_hero':{'Ring':1,'Ring2':2}}
    rings_o={'equipment_eligibility':[{'instance_id':i,'owners':['new_hero']} for i in [1,2,3]]}
    check('最强戒指已穿戴仍能替换另一个弱戒指',any(a.kind=='equipment_equip' and a.args==['new_hero',3] for a in plan(rings,rings_o,{},cfg)))
    rings['inventory']['items'][2]['power']=5
    check('戒指择优不会降级已装备的戒指',not any(a.kind=='equipment_equip' for a in plan(rings,rings_o,{},cfg)))
    check('副本内不重复入场',not any(a.kind=='dungeon_enter' for a in plan(snapshot,{'in_dungeon':True,'dungeon':{'unlocked_floor':100,'keys':200}},{},cfg)))
    check('支持后期副本层数',any(a.kind=='dungeon_enter' and a.args==[100] for a in plan(snapshot,{'dungeon':{'unlocked_floor':100,'keys':200}},{},cfg)))
    check('副本奖励容量满时等待清理',not any(a.kind=='dungeon_enter' for a in plan(snapshot,{'dungeon':{'unlocked_floor':100,'keys':200,'entry_blocked':True}},{},cfg)))
    check('副本会话未就绪时不请求',not any(a.kind=='dungeon_enter' for a in plan(snapshot,{'dungeon':{'unlocked_floor':100,'keys':200,'session_required':True}},{},cfg)))
    check('即时快照已入副本时不重复入场',not any(a.kind=='dungeon_enter' for a in plan({**snapshot,'in_dungeon':True},{'dungeon':{'unlocked_floor':100,'keys':200}},{},cfg)))
    s=deepcopy(snapshot)
    s['inventory']['items']=[{'id':x,'category':'Equipment','type':'Head','power':x*10,'grade':1,'steam_trade_protected':False} for x in range(1,5)]
    salvage={'salvage':{str(x):{'eligible':True,'category_filter':'armor','grade':1,'level':1} for x in range(1,5)}}
    check('默认只保留当前装备且回收额外普通装备',any(a.kind=='salvage_quote' and a.args==[1,2,3] for a in plan(s,salvage,{},cfg)))
    late_bag=deepcopy(snapshot)
    late_bag['owned_characters']=['a','b','c']
    late_bag['inventory']['character_progress_by_char']={key:{'level':150} for key in ['a','b','c']}
    late_bag['inventory']['items']=[{'id':1+tier*100+copy,'category':'Equipment','type':'Head','power':(tier+1)*100+copy,
        'requiredLevel':1+tier*10,'grade':1,'steam_trade_protected':False} for tier in range(15) for copy in range(4)]
    held=protected_items(late_bag,cfg)
    check('后期不按每个旧等级段重复保留装备',len(held)==3)
    late_salvage={'salvage':{str(item['id']):{'eligible':True,'category_filter':'armor','grade':1,'level':1} for item in late_bag['inventory']['items']}}
    check('旧等级装备能进入分解清理链',any(a.kind=='salvage_quote' and a.args==[item['id'] for item in late_bag['inventory']['items'][:30]] for a in plan(late_bag,late_salvage,{},cfg)))
    material_bag=deepcopy(snapshot)
    material_bag['inventory']['character_progress_by_char']['new_hero']['level']=19
    material_bag['inventory']['material_records']=[
        {'record_id':101,'item_data_id':901,'count':8,'state_flag':0},
        {'record_id':102,'item_data_id':902,'count':4,'state_flag':0},
        {'record_id':103,'item_data_id':903,'count':5,'state_flag':0},
        {'record_id':104,'item_data_id':904,'count':2,'state_flag':0},
        {'record_id':105,'item_data_id':905,'count':3,'state_flag':4},
        {'record_id':106,'item_data_id':906,'count':7,'state_flag':0},
    ]
    material_opportunities={'salvage':{
        '101':{'eligible':True,'category_filter':'material','item_data_id':901,'grade':1,'count':8},
        '102':{'eligible':True,'category_filter':'material','item_data_id':902,'grade':1,'count':4},
        '103':{'eligible':True,'category_filter':'material','item_data_id':903,'grade':1,'count':5},
        '104':{'eligible':True,'category_filter':'material','item_data_id':904,'grade':1,'count':2},
        '105':{'eligible':True,'category_filter':'material','item_data_id':905,'grade':1,'count':3},
        '106':{'eligible':True,'category_filter':'material','item_data_id':906,'grade':1,'count':6},
    },'recipes':[
        {'recipe_id':1,'category':'equipment','subtype':'Necklace','required_level':1,'executable':False,'target':{'popupArgs':{}},'plan':{'materials':[{'item_data_id':901,'required':1}]}},
        {'recipe_id':10,'category':'equipment','subtype':'Necklace','required_level':10,'executable':True,'target':{'popupArgs':{}},'plan':{'materials':[{'item_data_id':902,'required':1}]}},
        {'recipe_id':20,'category':'equipment','subtype':'Necklace','required_level':20,'executable':False,'target':{'popupArgs':{}},'plan':{'materials':[{'item_data_id':903,'required':1}]}},
        {'recipe_id':30,'category':'equipment','subtype':'Necklace','required_level':30,'executable':False,'target':{'popupArgs':{}},'plan':{'materials':[{'item_data_id':904,'required':1}]}},
    ]}
    material_cfg=normalize_config({'salvage_include_materials':True,'modules':{'craft':False}})
    material_actions=plan(material_bag,material_opportunities,{},material_cfg)
    material_quote=next(a for a in material_actions if a.kind=='salvage_quote')
    check('旧阶材料进入回收但保留当前阶段与下一阶段配方材料',material_quote.args==[101,104])
    partial_current=deepcopy(material_opportunities)
    partial_current['recipes'][1]['executable']=False
    partial_actions=plan(material_bag,partial_current,{},material_cfg)
    partial_quote=next(a for a in partial_actions if a.kind=='salvage_quote')
    check('当前阶材料不足时仍保留可继续凑齐的配方材料',partial_quote.args==[101,104])
    unknown_recipes=deepcopy(material_opportunities)
    del unknown_recipes['recipes'][1]['subtype']
    check('配方投影不完整时禁止分解材料',not any(a.kind=='salvage_quote' for a in plan(material_bag,unknown_recipes,{},material_cfg)))
    new_account=deepcopy(material_bag)
    new_account['inventory']['character_progress_by_char']['new_hero']['level']=1
    new_account_actions=plan(new_account,material_opportunities,{},material_cfg)
    new_account_quote=next(a for a in new_account_actions if a.kind=='salvage_quote')
    check('新号保留当前等级未凑齐配方与下一阶段材料',new_account_quote.args==[103,104])
    mixed_tier=deepcopy(material_bag)
    mixed_tier['deck']=['new_hero','fighter']
    mixed_tier['formation_limit']=2
    mixed_tier['owned_characters']=['new_hero','fighter']
    mixed_tier['inventory']['character_progress_by_char']['fighter']={'level':21}
    mixed_actions=plan(mixed_tier,material_opportunities,{},material_cfg)
    mixed_quote=next(a for a in mixed_actions if a.kind=='salvage_quote')
    check('队伍等级不一致时分别保留各角色当前阶与下一阶材料',mixed_quote.args==[101])
    check('材料报价数量必须与权威堆叠数一致',not any(a.kind=='salvage_quote' and 106 in a.args for a in material_actions))
    check('锁定材料不进入分解',not any(a.kind=='salvage_quote' and 105 in a.args for a in material_actions))
    material_opportunities.update(salvage_can_execute=True,salvage_selection={'101':8,'104':2},salvage_quote={'request_id':93})
    material_execute=next(a for a in plan(material_bag,material_opportunities,{},material_cfg) if a.kind=='salvage_execute')
    check('材料分解绑定整叠数量并等库存清零确认',material_execute.args==[999,93,[{'id':101,'count':8},{'id':104,'count':2}]] and material_execute.expected=={'material_counts':{101:8,104:2}})
    mixed=deepcopy(late_bag);mixed['owned_characters']=['a','b'];mixed['inventory']['character_progress_by_char']={'a':{'level':1},'b':{'level':150}}
    held=protected_items(mixed,cfg)
    check('低等级队友仍保留实际可穿戴装备',any(item['id'] in held and item['requiredLevel']==1 for item in mixed['inventory']['items']))
    future=deepcopy(snapshot);future['inventory']['character_progress_by_char']['new_hero']['level']=10
    future['inventory']['items']=[{'id':level,'category':'Equipment','type':'Head','power':level,'requiredLevel':level,'grade':1,'steam_trade_protected':False} for level in [1,10,20,30,40,50,100,150]]
    held=protected_items(future,cfg)
    check('保留当前和下一阶段及最强远期装备',10 in held and 20 in held and 150 in held and 30 not in held)
    unknown=deepcopy(future);unknown['inventory']['character_progress_by_char']={}
    check('角色等级元数据未知时保留待判断装备',len(protected_items(unknown,cfg))==8)
    locked=deepcopy(future);locked['inventory']['items'][3]['state_flag']=4
    locked['inventory']['items'][4]['steam_trade_protected']=True
    locked['inventory']['items'][5]['enhance_level']=2
    check('淘汰筛选仍保留锁定Steam和已投入装备',{30,40,50}.issubset(protected_items(locked,cfg)))
    job=deepcopy(snapshot);job['owned_characters']=['new_hero','fighter'];job['inventory']['character_progress_by_char']['fighter']={'level':1}
    job['inventory']['items']=[{'id':i,'category':'Weapon','tags':['JobWeapon'],'popupArgs':{'JobWeaponOwner':owner},'power':i,'requiredLevel':level,'steam_trade_protected':False} for i,owner,level in [(1,'fighter',1),(2,'fighter',10),(3,'new_hero',100)]]
    check('职业专属武器按各自等级保留',{1,2,3}.issubset(protected_items(job,cfg)))
    unowned_job=deepcopy(snapshot);unowned_job['inventory']['items']=[{'id':1,'category':'Weapon','tags':['JobWeapon'],'popupArgs':{'JobWeaponOwner':'fighter'},'power':1,'requiredLevel':1,'steam_trade_protected':False}]
    unowned_job['inventory']['character_progress_by_char']={'new_hero':{'level':150}}
    unowned_salvage={'salvage':{'1':{'eligible':True,'category_filter':'weapon','grade':1,'level':1}}}
    check('未拥有角色的专属武器不再永久保护',1 not in protected_items(unowned_job,cfg) and any(a.kind=='salvage_quote' and a.args==[1] for a in plan(unowned_job,unowned_salvage,{},cfg)))
    two_rings=deepcopy(snapshot);two_rings['inventory']['items']=[{'id':i,'category':'Equipment','type':'Ring','power':i,'requiredLevel':1,'steam_trade_protected':False} for i in range(1,5)]
    check('默认只保留双戒指所需槽位',protected_items(two_rings,cfg)=={3,4})
    check('备用份数为零仍保留双戒指槽位',protected_items(two_rings,normalize_config({'spare_copies':0}))=={3,4})
    pressure=deepcopy(snapshot);pressure['inventory']['items']=[{'id':1,'category':'Equipment','type':'Head','power':100,'requiredLevel':1,'steam_trade_protected':False},{'id':2,'category':'Equipment','type':'Head','power':10,'requiredLevel':1,'steam_trade_protected':False}]
    pressure['inventory'].update(bag_occupied_slots=90,bag_unlocked_slots=100,character_progress_by_char={'new_hero':{'level':150}})
    pressure['owned_characters']=['new_hero'];pressure['deck']=['new_hero'];pressure['formation_limit']=1
    check('背包接近满时自动释放备用垃圾',protected_items(pressure,cfg)=={1})
    collection_salvage=deepcopy(salvage)
    collection_salvage['collections']={'ready':True,'collections':[{'id':'set','slots':[{'key':'head','registered':False,'candidates':[{'item_id':1},{'item_id':2}]}]}]}
    combined=plan(s,collection_salvage,{},cfg)
    check('图鉴只保留本轮登记候选其余副本能清理',any(a.kind=='collection_register' and a.args[2]==1 for a in combined) and any(a.kind=='salvage_quote' and a.args==[2,3] for a in combined))
    check('关闭图鉴后不积压所有图鉴候选',any(a.kind=='salvage_quote' and a.args==[1,2,3] for a in plan(s,collection_salvage,{},normalize_config({'modules':{'collection':False}}))))
    collection_salvage['collections']['collections'][0]['slots'][0]['candidates'][0]['requires_confirmation']=True
    combined=plan(s,collection_salvage,{},cfg)
    check('需要手工确认的登记不会阻塞其他普通装备清理',any(a.kind=='collection_register' and a.args[2]==2 for a in combined) and any(a.kind=='salvage_quote' and a.args==[1,3] for a in combined))
    duplicate_collection=deepcopy(s)
    duplicate_collection['inventory']['items']=[]
    duplicate_collection['inventory']['material_records']=[{'record_id':7,'item_data_id':210811,'count':1,'state_flag':0}]
    duplicate_opportunities={'collections':{'ready':True,'busy':False,'collections':[
        {'id':'gem_grade_1','slots':[{'key':'e1','registered':False,'candidates':[{'item_id':7}]}]},
        {'id':'gem_grade_2','slots':[{'key':'e1','registered':False,'candidates':[{'item_id':7}]}]},
    ]},'recipes':[{'recipe_id':1,'category':'equipment','subtype':'Necklace','required_level':10,
        'target':{'popupArgs':{}},'plan':{'materials':[{'item_data_id':210999,'required':1}]}}]}
    duplicate_actions=[a for a in plan(duplicate_collection,duplicate_opportunities,{},cfg) if a.kind=='collection_register']
    check('同一材料只排一个图鉴登记请求',len(duplicate_actions)==1 and duplicate_actions[0].args[2]==7)
    duplicate_collection['inventory']['material_records'][0]['state_flag']=4
    locked_collection=[a for a in plan(duplicate_collection,duplicate_opportunities,{},cfg) if a.kind=='collection_register']
    check('图鉴跳过被锁定的材料记录',not locked_collection)
    reserved_collection=deepcopy(duplicate_collection)
    reserved_collection['inventory']['material_records'][0].update(state_flag=0,item_data_id=902)
    reserved_opportunities=deepcopy(duplicate_opportunities)
    reserved_opportunities['recipes']=[{'recipe_id':1,'category':'equipment','subtype':'Necklace','required_level':10,'target':{'popupArgs':{}},'plan':{'materials':[{'item_data_id':902,'required':1}]}}]
    check('图鉴跳过当前配方保留材料',not any(a.kind=='collection_register' for a in plan(reserved_collection,reserved_opportunities,{},cfg)))
    unknown_collection=deepcopy(duplicate_collection)
    unknown_collection['inventory']['material_records'][0]['state_flag']=0
    incomplete_opportunities=deepcopy(duplicate_opportunities)
    incomplete_opportunities['recipes']=[]
    check('配方投影不完整时不登记材料',not any(a.kind=='collection_register' for a in plan(unknown_collection,incomplete_opportunities,{},cfg)))
    stale_collection=deepcopy(duplicate_collection)
    stale_collection['inventory']['material_records']=[{'record_id':8,'item_data_id':210811,'count':1,'state_flag':0}]
    stale_opportunities=deepcopy(duplicate_opportunities)
    stale_opportunities['collections']['collections'][0]['slots'][0]['candidates'][0]['item_id']=7
    check('背包不存在的图鉴候选不发请求',not any(a.kind=='collection_register' for a in plan(stale_collection,stale_opportunities,{},cfg)))
    s['inventory']['items'][0]['steam_trade_protected']=True
    check('Steam可交易装备不进入报价',not any(a.kind=='salvage_quote' and 1 in a.args for a in plan(s,salvage,{},cfg)))
    del s['inventory']['items'][1]['steam_trade_protected']
    unknown_trade_actions=[a for a in plan(s,salvage,{},cfg) if a.kind=='salvage_quote']
    check('Steam元数据未知的装备不进入报价',all(1 not in a.args and 2 not in a.args for a in unknown_trade_actions))
    s['inventory']['items'][0]['steam_trade_protected']=False
    s['inventory']['items'][1]['steam_trade_protected']=False
    grade_off=normalize_config({'salvage_grades':[]})
    check('关闭所有品质后没有分解报价',not any(a.kind.startswith('salvage') for a in plan(s,salvage,{},grade_off)))
    stale={**salvage,'salvage_can_execute':True,'salvage_selection':{'1':1,'4':1}}
    check('报价中出现受保护主力装备时不执行',not any(a.kind=='salvage_execute' for a in plan(s,stale,{},cfg)))
    fresh={**salvage,'salvage_can_execute':True,'salvage_selection':{'1':1,'2':1},'salvage_quote':{'request_id':91}}
    quoted=next(a for a in plan(s,fresh,{},cfg) if a.kind=='salvage_execute')
    check('分解执行绑定会话报价和物品清单',quoted.args==[999,91,[{'id':1,'count':1},{'id':2,'count':1}]] and quoted.expected=={'consumed':[1,2]})
    fresh['salvage_quote']['request_id']=92
    newer=next(a for a in plan(s,fresh,{},cfg) if a.kind=='salvage_execute')
    check('新报价使用独立消费上下文',newer.key!=quoted.key)
    del fresh['salvage_quote']
    check('缺少报价编号时不执行分解',not any(a.kind=='salvage_execute' for a in plan(s,fresh,{},cfg)))
    s['inventory']['items']=[{'id':1,'unidentified':True,'state_flag':8}]
    identify_only=normalize_config({'modules':{'equipment':False,'identify':True}})
    check('鉴定与战力换装独立开关',any(a.kind=='identify' and a.module=='identify' for a in plan(s,{}, {},identify_only)))
    check('非法优先级安全回落',normalize_config({'rune_priority':[{},1,2,3]})['rune_priority']==cfg['rune_priority'])
    check('截图默认品质仅普通高级稀有',cfg['salvage_grades']==[1,2,3])
    check('截图默认星座优先级',cfg['rune_priority']==['exp','gold','power','chest'])
    check('截图显示模式默认值',not cfg['performance_mode'] and cfg['performance_fps']==10 and cfg['minimal_effects'])
    rows=[{'ok':True,'node_key':key,'name':key,'from_level':0,'to_level':1,
           'cost':[{'item_data_id':5,'count':cost}],
           'node':{'effects':[{'type':'stat','stat':stat}]}}
          for key,stat,cost in [('chest','ItemDropPercent',1),('power','Attack',1),('gold','GoldPercent',1),('exp','ExpPercent',8000)]]
    ordered=[a.args[0] for a in plan(snapshot,{'runes':rows},{},cfg) if a.kind=='rune_level']
    check('可支付星座严格按分类排序再比成本',ordered==['exp','gold','power','chest'])
    reverse=normalize_config({'rune_priority':['chest','power','gold','exp']})
    check('调整星座优先级确实改变调度',[a.args[0] for a in plan(snapshot,{'runes':rows},{},reverse) if a.kind=='rune_level']==['chest','power','gold','exp'])
    unlocked=deepcopy(rows[1]);unlocked['node_key']='formation';unlocked['node']['effects']=[{'type':'unlock','flag':'formation_slot'}]
    check('关键阵位解锁优先',[a.args[0] for a in plan(snapshot,{'runes':rows+[unlocked]},{},cfg) if a.kind=='rune_level'][0]=='formation')
    def rune_node(key, cost, effects, prerequisites=None, error='', missing=None, level=0, max_level=5):
        return {'node_key':key,'name':key,'ok':not error,'error':error,'from_level':level,
                'to_level':level+1,'max_level':max_level,'missing_requirements':missing or [],
                'cost':[{'item_data_id':5,'count':cost}],
                'node':{'effects':effects,'prerequisites':prerequisites or []}}
    capacity_effect=[{'type':'capacity','key':'equipment_inventory_slots','value':1}]
    cap=rune_node('bag',2000,capacity_effect)
    s=deepcopy(snapshot);s['inventory'].update(bag_occupied_slots=90,bag_unlocked_slots=100,materials={'5':3000})
    check('容量联动默认开启且正常容量不预留',cfg['prioritize_capacity'] and capacity_goal(snapshot,{'runes':[cap]},cfg) is None)
    check('背包接近满时选择扩容星座',capacity_goal(s,{'runes':[cap]},cfg)['node_key']=='bag')
    budget=growth_budget(s,{'runes':[cap]},cfg)
    check('扩容预算叠加基础金币储备',reserve(s['inventory'],budget)[1]==2360)
    exp=rune_node('exp',800,[{'type':'stat','stat':'ExpPercent'}])
    cap_actions=[a for a in plan(s,{'runes':[cap,exp]},{},cfg) if a.kind=='rune_level']
    check('扩容使用预留预算且其他加点不能挤占',[a.args[0] for a in cap_actions]==['bag'])
    parent=rune_node('root',500,[{'type':'stat','stat':'Attack'}])
    locked=rune_node('bag',2000,capacity_effect,[{'node':'root','level':1}],'rune_prerequisite_locked',[{'node':'root','level':1,'current':0}])
    check('未解锁扩容节点会先安排可达前置',capacity_goal(s,{'runes':[locked,parent]},cfg)['node_key']=='root')
    off=normalize_config({'prioritize_capacity':False})
    check('关闭容量联动恢复原预算',capacity_goal(s,{'runes':[cap]},off) is None and growth_budget(s,{'runes':[cap]},off)==off)
    check('关闭星座不为扩容锁预算',capacity_goal(s,{'runes':[cap]},normalize_config({'modules':{'runes':False}})) is None)
    full=deepcopy(cap);full.update(from_level=5,error='rune_max_level',ok=False)
    check('扩容已满级时不会无限预留',capacity_goal(s,{'runes':[full]},cfg) is None)
    check('缺少前置预览时等待且不锁金币',capacity_goal(s,{'runes':[locked]},cfg) is None)
    cyclic=deepcopy(parent);cyclic['node']['prerequisites']=[{'node':'bag','level':1}]
    check('错误循环前置不会递归卡死',capacity_goal(s,{'runes':[locked,cyclic]},cfg) is None)
    poor=deepcopy(s);poor['inventory']['materials']['5']=1500
    waiting=deepcopy(cap);waiting.update(ok=False,error='insufficient_materials')
    check('金币不足时保留扩容目标等待积累',not capacity_goal(poor,{'runes':[waiting]},cfg)['can_afford'])
    for kind,updates,loot in [('stone_inventory_slots',{'bag_occupied_slots':0,'stone_bag_occupied_slots':20,'stone_bag_unlocked_slots':20},{}),('pending_loot_slots',{'bag_occupied_slots':0,'pending_loot_capacity':5},{'count':5})]:
        pressure=deepcopy(s);pressure['inventory'].update(updates)
        node=rune_node(kind,500,[{'type':'capacity','key':kind,'value':1}])
        check('魔石与宝箱容量分别触发扩容：'+kind,capacity_goal(pressure,{'runes':[node],'loot':loot},cfg)['node_key']==kind)
    recipe={'executable':True,'recipe_id':1,'required_level':150,'subtype':'Ring','target':{'type':'Ring'},'plan':{'materials':[{'item_data_id':5,'required':800}]}}
    check('制造遵守容量预留金币',not any(a.kind=='craft' for a in plan(s,{'runes':[cap],'recipes':[recipe]},{},cfg)))
    check('容量正常时可制造',any(a.kind=='craft' for a in plan(snapshot,{'recipes':[recipe]},{},cfg)))
    rings=deepcopy(snapshot);rings['inventory']['items']=[{'id':101,'requiredLevel':150,'grade':3},{'id':102,'requiredLevel':150,'grade':4}]
    rings['inventory']['equipped_equipment_ids_by_char']={'new_hero':{'Ring1':101,'Ring2':102}}
    check('双戒指已达目标品质后停止同阶制造',not any(a.kind=='craft' for a in plan(rings,{'recipes':[recipe]},{},cfg)))
    del rings['inventory']['equipped_equipment_ids_by_char']['new_hero']['Ring2']
    check('第二戒指空槽仍允许制造补齐',any(a.kind=='craft' for a in plan(rings,{'recipes':[recipe]},{},cfg)))
    s=deepcopy(snapshot);s['inventory']['skills_by_char']={'new_hero':{'1':{'skill_item_data_id':1,'level':3,'max_level':10,'effect':{'cooldown':10,'dps_ratio':3}}}}
    check('原生技能自动生效不重复装槽',not any(a.kind=='skill_equip' for a in plan(s,{}, {},cfg)))
    with tempfile.TemporaryDirectory() as temporary, patch.object(runtime,'DATA',Path(temporary)):
        engine=Engine();engine.snapshot=deepcopy(snapshot)
        initial_running=engine.running
        engine.handle_hotkey('F8');check('F8切换总开关并保存配置',engine.running != initial_running and json.loads((runtime.DATA/'config.json').read_text(encoding='utf8'))['auto_start']==engine.running)
        check('助手重启恢复已保存的自动化状态',Engine().running==engine.running)
        merge_a=Action('stones','stone_merge',[2,3],'fixture merge A',90)
        merge_b=Action('stones','stone_merge',[4,5],'fixture merge B',90)
        engine.pending={'id':'fixture','pid':999,'action':{'module':'stones','kind':'stone_merge','args':[2,3],'label':'fixture merge A','priority':90,'expected':None}}
        engine.finish(False,'fixture merge A · protected_stone')
        blocked_until=engine.cooldowns['stone_merge:protected']
        check('保护拒绝后短暂暂停其它魔石合成候选',not engine.action_ready(merge_b,blocked_until-1) and engine.action_ready(merge_b,blocked_until))
        engine.handle_hotkey('F8')
        engine.handle_hotkey('F9');check('F9只切换分解',not engine.config['modules']['inventory'] and engine.config['modules']['equipment'])
        engine.handle_hotkey('F9')
        engine.handle_hotkey('F10');check('F10只切换换装',not engine.config['modules']['equipment'] and engine.config['modules']['inventory'])
        engine.handle_hotkey('F10')
        candidate={**engine.config,'performance_fps':15,'rune_priority':['chest','exp','gold','power']}
        (runtime.DATA/'config.json').write_text(json.dumps(candidate),encoding='utf-8-sig')
        engine.last_config_check=0;engine.reload_config()
        check('支持BOM配置外部重载',engine.config['performance_fps']==15 and engine.config['rune_priority'][0]=='chest')
        check('带BOM配置在启动首轮即生效',Engine().config['performance_fps']==15)
        (runtime.DATA/'config.json').write_text('{broken',encoding='utf8')
        engine.last_config_check=0;engine.reload_config()
        check('无效配置保留上次有效值',engine.config['performance_fps']==15)
        engine.update_config({'performance_fps':10})
        action=Action('skills','skill_level',['new_hero',1],'fixture',100)
        engine.dispatch(action);ident=engine.pending['id']
        check('命令发布前持久化ID',json.loads((runtime.DATA/'scheduler.json').read_text(encoding='utf8'))['pending']['id']==ident)
        restarted=Engine();check('重启保留操作ID',restarted.pending['id']==ident)
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[321],'time_unix':time.time()-4})
        engine.reconcile();check('提交不等于成功',engine.pending is not None and engine.success_count==0)
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-321.json',{'time_unix':time.time(),'ok':True,'response':{'ok':True}})
        engine.reconcile();check('服务器回执后计成功',engine.pending is None and engine.success_count==1)
        engine.dispatch(action);engine.pending['started']=time.time()-60;engine.reconcile()
        check('未知消费不重复重试',engine.pending is None and engine.cooldowns[action.key]>time.time()+80000)
        rune=Action('runes','rune_level',['exp'],'fixture rune',100,{'rune':['exp',1]})
        engine.dispatch(rune);ident=engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[322],'time_unix':time.time()-4})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-322.json',{'time_unix':time.time(),'ok':True,'response':{'ok':True}})
        engine.opportunities={'runes':[{'node_key':'exp','from_level':0}]}
        engine.reconcile();check('星座回执后等待节点等级更新',engine.pending is not None)
        engine.opportunities['runes'][0]['from_level']=1
        engine.reconcile();check('星座等级更新后核验成功',engine.pending is None and engine.success_count==2)
        loot_engine=Engine();loot_engine.snapshot=deepcopy(snapshot)
        loot_success_before=loot_engine.success_count
        loot_engine.dispatch(Action('loot','loot_claim',[],'领取待结算奖励',160,{'loot_before':2}));ident=loot_engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[],'time_unix':time.time()-3})
        loot_engine.opportunities={'loot':{'count':2}};loot_engine.reconcile()
        check('宝箱领取先等待队列变化',loot_engine.pending is not None)
        loot_engine.opportunities={'loot':{'count':1}};loot_engine.reconcile()
        check('宝箱队列减少后核验成功',loot_engine.pending is None and loot_engine.success_count==loot_success_before+1)
        exp_engine=Engine();exp_engine.snapshot=deepcopy(snapshot)
        exp_success_before=exp_engine.success_count
        exp_engine.dispatch(Action('consumables','consumable_exp',[],'启用经验卷轴',85));ident=exp_engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[],'time_unix':time.time()-3})
        exp_engine.snapshot['consumables']={'exp_scroll_enabled':False,'exp_scroll_active':False};exp_engine.reconcile()
        check('经验卷轴启用先等待状态变化',exp_engine.pending is not None)
        exp_engine.snapshot['consumables']['exp_scroll_enabled']=True;exp_engine.reconcile()
        check('经验卷轴启用状态后核验成功',exp_engine.pending is None and exp_engine.success_count==exp_success_before+1)
        engine.dispatch(action);engine.snapshot['pid']=1000;engine.reconcile()
        check('会话变更不重放',engine.pending is None)
        engine.snapshot=deepcopy(snapshot)
        engine.snapshot['inventory']['items']=[{'id':101,'grade':3,'enhance_level':0,'name':'维护装备'}]
        engine.snapshot['native_busy']={'skill':False,'equipment':False,'enhancement':False,'socket':False,
            'loot':False,'craft':0,'disassembly':0}
        engine.snapshot['pending_requests']={}
        engine.snapshot['time_unix']=time.time()
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']={'new_hero':{}}
        engine.maintenance={'module':'enhancement','id':101,'owner':'new_hero','pid':999,'account_id':1001,'started':time.time(),'phase':'prepare'}
        engine.running=False
        restore=engine.maintenance_action()
        check('暂停维护后只恢复装备不继续消费',restore.kind=='equipment_equip' and engine.maintenance['phase']=='restore')
        engine.running=True;engine.config['modules']['enhancement']=False;engine.maintenance['phase']='prepare'
        check('关闭强化模块后恢复维护装备',engine.maintenance_action().kind=='equipment_equip' and engine.maintenance['phase']=='restore')
        engine.snapshot['inventory']['equipped_equipment_ids_by_char']={'new_hero':{'Head':101}}
        check('装备恢复后结束维护任务',engine.maintenance_action() is None and engine.maintenance is None)
        engine.module_last_run['dungeon']=time.time()
        dungeon=Action('dungeon','dungeon_enter',[101],'新开放楼层',35)
        check('副本解锁新层仍遵守全局挑战间隔',not engine.action_ready(dungeon))
        engine.module_last_run['dungeon']=time.time()-cfg['dungeon_interval_seconds']-1
        check('副本间隔结束后继续挑战',engine.action_ready(dungeon))
        salvage_engine=Engine();salvage_engine.snapshot=deepcopy(snapshot)
        salvage_engine.snapshot['inventory']['items']=[{'id':1},{'id':2}]
        salvage_engine.cooldowns['salvage_execute:[]']=time.time()+86400
        check('历史空参数分解退避不阻塞新的有效报价',salvage_engine.action_ready(quoted))
        salvage_engine.dispatch(quoted);ident=salvage_engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':True,'request_ids':[401],'time_unix':time.time()-4})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-401.json',{'time_unix':time.time(),'ok':True,'response':{'ok':True}})
        before=salvage_engine.success_count
        salvage_engine.reconcile()
        check('分解成功回执后等待库存消失',salvage_engine.pending is not None and salvage_engine.success_count==before)
        salvage_engine.snapshot['inventory']['items']=[]
        salvage_engine.reconcile()
        check('分解物品消失后核验成功',salvage_engine.pending is None and salvage_engine.success_count==before+1)
        salvage_engine.dispatch(quoted);ident=salvage_engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':True,'request_ids':[402],'time_unix':time.time()-4})
        runtime.atomic_json(runtime.DATA/'runtime/receipt-999-1001-402.json',{'time_unix':time.time(),'ok':False,'response':{'ok':False,'outcome_unknown':True,'transport_lost':True}})
        salvage_engine.reconcile()
        check('传输断开回执保留未知结果',salvage_engine.pending is None and salvage_engine.logs[0]['uncertain'])
        check('未知分解仅隔离原报价',not salvage_engine.action_ready(quoted) and salvage_engine.action_ready(newer))
        dungeon_engine=Engine();dungeon_engine.snapshot=deepcopy(snapshot)
        dungeon_engine.dispatch(Action('dungeon','dungeon_enter',[100],'副本测试',35));ident=dungeon_engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[],'time_unix':time.time()-3})
        dungeon_engine.reconcile()
        check('副本本地切图留出快照刷新时间',dungeon_engine.pending is not None)
        dungeon_engine.snapshot['in_dungeon']=True
        dungeon_engine.reconcile()
        check('即时副本快照核验不依赖旧预览',dungeon_engine.pending is None and dungeon_engine.logs[0]['level']=='success')
        dungeon_engine.snapshot['in_dungeon']=False
        dungeon_engine.dispatch(Action('dungeon','dungeon_enter',[100],'副本测试',35));ident=dungeon_engine.pending['id']
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True,'in_dungeon':True},'request_ids':[],'time_unix':time.time()-3})
        dungeon_engine.reconcile()
        check('原生入口即时入场结果可核验',dungeon_engine.pending is None and dungeon_engine.logs[0]['level']=='success')
        dungeon_engine.dispatch(Action('dungeon','dungeon_enter',[100],'副本测试',35));ident=dungeon_engine.pending['id']
        dungeon_engine.pending['started']=time.time()-12
        runtime.atomic_json(runtime.DATA/'runtime/results'/f'{ident}.json',{'status':'submitted','account_id':1001,'answer':{'ok':True},'request_ids':[],'time_unix':time.time()-12})
        dungeon_engine.reconcile()
        check('副本未实际入场不会计成功',dungeon_engine.pending is None and dungeon_engine.logs[0]['level']=='warning')
        stop_engine=Engine()
        stop_server=Server(stop_engine,port=0)
        stop_thread=threading.Thread(target=stop_server.serve_forever,daemon=True)
        stop_thread.start()
        request=urllib.request.Request(stop_server.origin+'/api/stop',data=b'{}',headers={
            'Origin':stop_server.origin,'X-CSRF-Token':stop_server.csrf,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=3) as response:
                check('助手停止接口成功关闭本地服务',response.status==200)
            stop_thread.join(timeout=3)
            check('停止助手不清除自动化开启偏好',json.loads((runtime.DATA/'config.json').read_text(encoding='utf8'))['auto_start'] is True)
        finally:
            stop_server.server_close()
    output.parent.mkdir(parents=True,exist_ok=True)
    from tools.recovery_tests import run as recovery_checks
    recovery_checks(check)
    from tools.mail_tests import run as mail_checks
    mail_checks(check)
    from tools.startup_tests import run as startup_checks
    startup_checks(check)
    from tools.maintenance_tests import run as maintenance_checks
    maintenance_checks(check)
    from tools.account_tests import run as account_checks
    account_checks(check)
    from tools.stone_concurrency_tests import run as stone_concurrency_checks
    stone_concurrency_checks(check)
    from tools.build_tests import run as build_checks
    build_checks(check)
    from tools.sandbox_tests import run as sandbox_checks
    sandbox_checks(check)
    from tools.multi_instance_tests import run as multi_instance_checks
    multi_instance_checks(check)
    from tools.growth_recovery_tests import run as growth_recovery_checks
    growth_recovery_checks(check)
    from tools.salvage_control_tests import run as salvage_control_checks
    salvage_control_checks(check)
    from tools.craft_lifecycle_tests import run as craft_lifecycle_checks
    craft_lifecycle_checks(check)
    from tools.upgrade_disposal_tests import run as upgrade_disposal_checks
    upgrade_disposal_checks(check)
    from tools.snapshot_reader_tests import run as snapshot_reader_checks
    snapshot_reader_checks(check)
    from tools.salvage_scheduling_tests import run as salvage_scheduling_checks
    salvage_scheduling_checks(check)
    from tools.enhancement_access_tests import run as enhancement_access_checks
    enhancement_access_checks(check)
    output.write_text(json.dumps({'passed':len(tests),'tests':tests},ensure_ascii=False,indent=2),encoding='utf8')
    print(f'{len(tests)} regression scenarios passed; {output}')

if __name__=='__main__':
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    run(Path(sys.argv[1]) if len(sys.argv)>1 else Path('runtime/self-test.json'))
