"""Parse the self-written bridge in an isolated Godot pack, without a game session."""
from pathlib import Path
import hashlib, struct, subprocess, shutil, os, json, re

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / '.private/lab'
ENGINE = Path(r'C:\Users\catmaotou\IdleLegions-analysis-60\tools\gdre_tools.exe')

def write_pack(path, files):
    entries = []
    offset = 100
    for name, data in files.items():
        name = name.encode('utf8')
        name += b'\0' * (-len(name) % 4)
        entries.append([name, data, 0])
        offset += 40 + len(name)
    offset = (offset+15)//16*16
    for entry in entries:
        entry[2] = offset
        offset = (offset+len(entry[1])+15)//16*16
    with path.open('wb') as out:
        out.write(struct.pack('<4s5IQ',b'GDPC',2,4,7,2,0,0)+bytes(64))
        out.write(struct.pack('<I',len(entries)))
        for name, data, at in entries:
            out.write(struct.pack('<I',len(name))+name+struct.pack('<QQ',at,len(data))+hashlib.md5(data).digest()+struct.pack('<I',0))
        for name, data, at in entries:
            out.write(bytes(at-out.tell()))
            out.write(data)

if __name__ == '__main__':
    LAB.mkdir(parents=True,exist_ok=True)
    engine = LAB/'syntax-engine.exe'
    if not engine.exists(): shutil.copy2(ENGINE, engine)
    shutil.copy2(ENGINE.parent/'GodotMonoDecompNativeAOT.dll', LAB/'GodotMonoDecompNativeAOT.dll')
    write_pack(LAB/'syntax.pck',{
        'res://project.godot': b'config_version=5\n[application]\nconfig/name="WalletAssistantSyntax"\nrun/main_scene="res://main.tscn"\n[autoload]\nObserver="*res://assistant.gd"\n',
        'res://main.tscn':b'[gd_scene load_steps=2 format=3]\n[ext_resource type="Script" path="res://consumption_check.gd" id="1"]\n[node name="NoGame" type="Node"]\nscript = ExtResource("1")\n',
        'res://assistant.gd':(ROOT/'bridge/assistant.gd').read_bytes(),
        'res://worker.gd':(ROOT/'bridge/worker.gd').read_bytes(),
        'res://consumption_check.gd':b'''extends Node
class FakeUI extends RefCounted:
    var fatal_handling = true
    var fatal_kind = "retry"
    var fatal_restart_requested = false
    var intentional_shutdown = false
    var fatal_message = "PRIVATE_SENTINEL"

class FakeCoordinator extends RefCounted:
    var retry_pending = false
    var skill_calls: Array = []
    func request_skill_learn(owner, id):
        skill_calls.append([owner,id])
        return {"request_id":77}
    func request_skill_level_up(owner, id):
        skill_calls.append([owner,id])
        return {"request_id":78}
    func login_retry_pending():
        return retry_pending

class FakeBatch extends RefCounted:
    var active = false

class FakeStoneLoadout extends RefCounted:
    var pending = false
    func has_pending_requests():
        return pending

class FakeSteam extends RefCounted:
    func prewarm_catalog():
        pass
    func is_catalog_ready():
        return true
    func exportable_definition(_a, _b, _c, _d, _e):
        return {}

class FakeActions extends RefCounted:
    var calls: Array = []
    var manual_batch = FakeBatch.new()
    func merge_stones_with_ids(ids):
        calls.append(ids)
        return {"ok":true,"request_id":99}
    func toggle_equipment_instance(id: int, owner: String) -> Dictionary:
        calls.append([id, owner])
        return {"ok": true}

class FakeGateway extends RefCounted:
    var account_data: Dictionary = {}
    func snapshot():
        return account_data

class FakeInventory extends RefCounted:
    var view = {"items":[],"server_inventory_mutation_safe":true}
    func _inventory_view_snapshot():
        return view

class FakeBootstrap extends RefCounted:
    var selected = ""
    func confirm_initial_character_selection(character):
        selected = character

class FakeHeroes extends RefCounted:
    func skill_item_owner_key(_id):
        return "hero"
    func owned_character_keys():
        return ["hero"]

class FakeSkills extends RefCounted:
    func unlock_preview(_id, _level):
        return {"ok":true,"can_afford":true,"cost":[{"item_data_id":200501,"count":1}]}
    func level_preview(_id):
        return {"ok":true,"can_afford":true,"cost":[{"item_data_id":200501,"count":1}]}

class FakeHost extends Node:
    var hero_progression_facade = FakeHeroes.new()
    var skill_runtime_facade = FakeSkills.new()
    var server_connection_ui_controller = FakeUI.new()
    var server_runtime_coordinator = FakeCoordinator.new()
    var world_socket_gateway = RefCounted.new()
    var progression_selectors = FakeInventory.new()
    var progression_actions = FakeActions.new()
    var account_bootstrap_coordinator = FakeBootstrap.new()
    var server_stone_merge_request_id = 0
    var server_stone_loadout_coordinator = FakeStoneLoadout.new()
    var steam_inventory_coordinator = FakeSteam.new()

func _ready() -> void:
    var worker = Node.new()
    worker.set_script(load("res://worker.gd"))
    worker.setup(OS.get_environment("LOCALAPPDATA").path_join("isolated-channel"))
    if worker.data_dir.get_file() != str(OS.get_process_id()) or not DirAccess.dir_exists_absolute(worker.data_dir.path_join("commands")):
        push_error("Per-process IPC channel missing")
        worker.free()
        return
    worker._write("snapshot.json", {"pid":OS.get_process_id(),"connected":true})
    var ipc_probe = JSON.parse_string(FileAccess.get_file_as_string(worker.data_dir.path_join("snapshot.json")))
    if not ipc_probe is Dictionary or int(ipc_probe.get("pid",0)) != OS.get_process_id():
        push_error("Per-process IPC snapshot write failed")
        worker.free()
        return
    worker.control = JSON.parse_string("{\\"salvage_grades\\":[1,2,3]}")
    var item = {"instance_id":10,"grade":1,"level":1,"state_flag":0,"steam_trade_protected":false,"socket_stats":[]}
    var view = {"items":[item]}
    var checks = 0
    var fake_gateway = FakeGateway.new()
    fake_gateway.account_data = {"player":{"id":501}}
    worker.gateway = fake_gateway
    if worker._account_id(fake_gateway.snapshot()) != 501 or worker._account_id({"player":{"id":true}}) != 0 or worker._account_id({"player":{"id":"501"}}) != 0:
        push_error("Malformed account identity accepted")
        worker.free()
        return
    checks += 1
    worker.observed_account_id = 502
    worker.request_account_ids["71"] = 501
    if worker._receipt_account(71) != 501 or worker._receipt_account(72) != 0:
        push_error("Late receipt was not bound to its originating account")
        worker.free()
        return
    checks += 1
    for invalid in [null, true, "501", -1, 0, 1.5, INF, NAN]:
        if worker._positive_id(invalid) != 0:
            push_error("Invalid account ID accepted")
            worker.free()
            return
        checks += 1
    var parsed_identity = JSON.parse_string('{"account_id":501}')
    if worker._positive_id(parsed_identity.account_id) != 501:
        push_error("JSON integer identity rejected")
        worker.free()
        return
    checks += 1
    if worker._execute({"pid":OS.get_process_id(),"action":"initial_pick","args":["hero"]}) != {"ok":false,"error":"account_identity_missing"}:
        push_error("Command without account identity accepted")
        worker.free()
        return
    checks += 1
    if worker._execute({"pid":OS.get_process_id(),"account_id":502,"action":"initial_pick","args":["hero"]}) != {"ok":false,"error":"account_changed"}:
        push_error("Different account command accepted")
        worker.free()
        return
    checks += 1
    fake_gateway.account_data = {"player":{}}
    if worker._execute({"pid":OS.get_process_id(),"account_id":501,"action":"initial_pick","args":["hero"]}) != {"ok":false,"error":"account_identity_unavailable"}:
        push_error("Command without native identity accepted")
        worker.free()
        return
    checks += 1
    fake_gateway.account_data = {"player":{"id":501}}
    var account_host = FakeHost.new()
    worker.host = account_host
    var matching_request = JSON.parse_string('{"account_id":501,"action":"initial_pick","args":["hero"]}')
    matching_request["pid"] = OS.get_process_id()
    if worker._execute(matching_request) != {"ok":true} or account_host.account_bootstrap_coordinator.selected != "hero":
        push_error("Matching JSON account command failed native dispatch")
        account_host.free()
        worker.free()
        return
    checks += 1
    account_host.progression_selectors.view = {"server_inventory_mutation_safe":true,"items":[],"materials":{"200501":99},"character_progress_by_char":{"hero":{"skill_points":1},"other":{"skill_points":99}}}
    var skill_request = {"account_id":501,"action":"skill_learn","args":["hero",200101]}
    if worker._execute(skill_request) != {"request_id":77} or account_host.server_runtime_coordinator.skill_calls.size() != 1:
        push_error("Owner points did not dispatch skill learning")
        worker.free()
        return
    checks += 1
    skill_request.args[0] = "other"
    if worker._execute(skill_request) != {"ok":false,"error":"skill_owner_changed"} or account_host.server_runtime_coordinator.skill_calls.size() != 1:
        push_error("Wrong skill owner reached native dispatch")
        worker.free()
        return
    checks += 1
    skill_request.args[0] = "hero"
    account_host.progression_selectors.view.character_progress_by_char.hero.skill_points = 0
    var rejected = worker._execute(skill_request)
    if rejected.get("ok", true) or account_host.server_runtime_coordinator.skill_calls.size() != 1:
        push_error("Stale affordable preview ignored current owner balance")
        worker.free()
        return
    checks += 1
    account_host.progression_selectors.view.character_progress_by_char.hero.skill_points = 1
    skill_request.action = "skill_level"
    if worker._execute(skill_request) != {"request_id":78}:
        push_error("Owner skill level request did not dispatch")
        worker.free()
        return
    checks += 1
    var stone_request = {"account_id":501,"action":"stone_merge","args":[81,82]}
    var stone_view = {"server_inventory_mutation_safe":true,"equipped_stone_ids_by_char":{},"items":[
        {"instance_id":81,"item_data_id":200201,"state_flag":0},
        {"instance_id":82,"item_data_id":200201,"state_flag":0}]}
    account_host.progression_selectors.view = stone_view
    if worker._stone_operations_busy() or worker._execute(stone_request) != {"ok":true,"request_id":99} or account_host.progression_actions.calls.size() != 1:
        push_error("Idle native merge did not dispatch exactly once")
        worker.free()
        return
    checks += 1
    account_host.server_stone_merge_request_id = 9
    if worker._execute(stone_request) != {"ok":true,"skipped":true,"reason":"native_stone_busy"} or account_host.progression_actions.calls.size() != 1:
        push_error("Native automatic merge was not respected")
        worker.free()
        return
    checks += 1
    account_host.server_stone_merge_request_id = 0
    account_host.server_stone_loadout_coordinator.pending = true
    if worker._execute({"account_id":501,"action":"stone_equip","args":["hero",81,0]}) != {"ok":true,"skipped":true,"reason":"native_stone_busy"}:
        push_error("Stone loadout race did not wait")
        worker.free()
        return
    checks += 1
    account_host.server_stone_loadout_coordinator.pending = false
    account_host.progression_actions.manual_batch.active = true
    if worker._execute(stone_request) != {"ok":true,"skipped":true,"reason":"native_stone_busy"}:
        push_error("Manual batch race did not wait")
        worker.free()
        return
    checks += 1
    account_host.progression_actions.manual_batch.active = false
    account_host.progression_selectors.view.items.pop_back()
    if worker._execute(stone_request) != {"ok":true,"skipped":true,"reason":"stone_candidates_changed"} or account_host.progression_actions.calls.size() != 1:
        push_error("Consumed stale candidate reached the native merge")
        worker.free()
        return
    checks += 1
    account_host.progression_selectors.view.items.append({"instance_id":82,"item_data_id":200201,"state_flag":1})
    if worker._execute(stone_request) != {"ok":true,"skipped":true,"reason":"stone_candidates_changed"} or account_host.progression_actions.calls.size() != 1:
        push_error("Protected candidate reached the native merge")
        worker.free()
        return
    checks += 1
    if worker._execute({"account_id":501,"action":"stone_merge","args":[81,81]}) != {"ok":false,"error":"invalid_arguments"}:
        push_error("Duplicate merge IDs accepted")
        worker.free()
        return
    checks += 1
    account_host.server_stone_loadout_coordinator = null
    if not worker._stone_operations_busy():
        push_error("Missing stone coordinator failed open")
        worker.free()
        return
    checks += 1
    worker.host = null
    account_host.free()
    for grade in [1,2,3]:
        item.grade = grade
        if not worker._consumable_instance(10, view, true):
            push_error("JSON quality whitelist rejected allowed grade")
            worker.free()
            return
        checks += 1
    item.grade = 4
    if worker._consumable_instance(10, view, true):
        push_error("Disallowed quality accepted")
        worker.free()
        return
    checks += 1
    item.grade = 1
    worker.control = JSON.parse_string("{\\"salvage_grades\\":[]}")
    if worker._consumable_instance(10, view, true):
        push_error("Empty quality whitelist accepted")
        worker.free()
        return
    checks += 1
    worker.control = JSON.parse_string("{\\"salvage_grades\\":[1,2,3]}")
    item.steam_trade_protected = true
    if worker._consumable_instance(10, view, true):
        push_error("Steam protection regressed")
        worker.free()
        return
    checks += 1
    worker.control["salvage_allow_tradeable"] = true
    view["steam_trade_ready"] = true
    if not worker._consumable_instance(10, view, true) or worker._consumable_instance(10, view, false):
        push_error("Trade permission did not remain salvage-specific")
        worker.free()
        return
    checks += 1
    view.steam_trade_ready = false
    if worker._consumable_instance(10, view, true):
        push_error("Trade permission accepted unknown catalog")
        worker.free()
        return
    checks += 1
    view.steam_trade_ready = true
    item.erase("steam_trade_protected")
    if worker._consumable_instance(10, view, true):
        push_error("Trade permission accepted unknown metadata")
        worker.free()
        return
    checks += 1
    item.steam_trade_protected = true
    item.grade = 5
    if worker._consumable_instance(10, view, true):
        push_error("Trade permission bypassed quality protection")
        worker.free()
        return
    checks += 1
    item.grade = 1
    item.socket_materials = {"decoration":[{"item_data_id":1}]}
    if worker._consumable_instance(10, view, true):
        push_error("Trade permission bypassed socket investment")
        worker.free()
        return
    checks += 1
    item.socket_materials = {}
    worker.control["salvage_allow_tradeable"] = false
    item.steam_trade_protected = false
    item.state_flag = 4
    if worker._consumable_instance(10, view, true):
        push_error("Locked equipment accepted")
        worker.free()
        return
    checks += 1
    item.state_flag = 0
    item.enhance_level = 1
    if worker._consumable_instance(10, view, true):
        push_error("Invested equipment accepted")
        worker.free()
        return
    checks += 1
    var material = {"record_id":20,"item_data_id":210811,"count":3,"state_flag":0}
    var material_view = {"items":[],"material_records":[material]}
    if not worker._consumable_instance(20, material_view, false):
        push_error("Collection material record was rejected")
        worker.free()
        return
    checks += 1
    if not worker._consumable_instance(20, material_view, true):
        push_error("Eligible material record was rejected for salvage")
        worker.free()
        return
    checks += 1
    material.state_flag = 4
    if worker._consumable_instance(20, material_view, true):
        push_error("Locked material record accepted for salvage")
        worker.free()
        return
    checks += 1
    material.state_flag = 0
    item.enhance_level = 0
    material_view["items"] = [item.duplicate(true)]
    var selected = {10:1,20:3}
    var quoted = {"request_id":91}
    var arguments = JSON.parse_string('[%d,91,[{"id":20,"count":3},{"id":10,"count":1}]]' % OS.get_process_id())
    if not worker._salvage_quote_matches(arguments, selected, quoted, material_view):
        push_error("Current JSON quote rejected")
        worker.free()
        return
    checks += 1
    for invalid in [[OS.get_process_id(),91,[{"id":10,"count":1}]], [OS.get_process_id(),92,[{"id":10,"count":1},{"id":20,"count":3}]], [OS.get_process_id()+1,91,[{"id":10,"count":1},{"id":20,"count":3}]], [], [OS.get_process_id(),91,[]]]:
        if worker._salvage_quote_matches(invalid, selected, quoted, material_view):
            push_error("Changed salvage context accepted")
            worker.free()
            return
        checks += 1
    selected[10] = 2
    if worker._salvage_quote_matches(arguments, selected, quoted, material_view):
        push_error("Changed salvage quantity accepted")
        worker.free()
        return
    checks += 1
    selected[10] = 1
    selected[20] = 2
    if worker._salvage_quote_matches(arguments, selected, quoted, material_view):
        push_error("Changed material quantity accepted")
        worker.free()
        return
    checks += 1
    selected[20] = 3
    material.count = 2
    if worker._salvage_quote_matches(arguments, selected, quoted, material_view):
        push_error("Changed material stock accepted")
        worker.free()
        return
    checks += 1
    var equipment_view = {"items":[{"instance_id":70}], "equipped_equipment_ids_by_char":{"hero":{"Head":70}}}
    var equipment_actions = FakeActions.new()
    var already_equipped = worker._set_equipment_state(["hero",70,true], equipment_view, equipment_actions)
    if already_equipped != {"ok":true,"already_satisfied":true} or not equipment_actions.calls.is_empty():
        push_error("Idempotent equipped-state request toggled equipment")
        worker.free()
        return
    checks += 1
    var removed = worker._set_equipment_state(["hero",70,false], equipment_view, equipment_actions)
    if removed != {"ok":true} or equipment_actions.calls != [[70,"hero"]]:
        push_error("Explicit unequip request did not toggle once")
        worker.free()
        return
    checks += 1
    equipment_view.equipped_equipment_ids_by_char.hero = {}
    var restored = worker._set_equipment_state(["hero",70,true], equipment_view, equipment_actions)
    if restored != {"ok":true} or equipment_actions.calls.size() != 2:
        push_error("Explicit restore request did not equip missing item")
        worker.free()
        return
    checks += 1
    equipment_view.equipped_equipment_ids_by_char.hero = {"Head":70}
    var default_equip = worker._set_equipment_state(["hero",70], equipment_view, equipment_actions)
    if default_equip != {"ok":true,"already_satisfied":true} or equipment_actions.calls.size() != 2:
        push_error("Two-argument equipment request no longer defaults to equip")
        worker.free()
        return
    checks += 1
    equipment_view.equipped_equipment_ids_by_char.other = {"Head":70}
    if worker._set_equipment_state(["hero",70,true], equipment_view, equipment_actions) != {"ok":false,"error":"equipment_owner_changed"}:
        push_error("Equipment assigned to another hero was accepted")
        worker.free()
        return
    checks += 1
    equipment_view.equipped_equipment_ids_by_char.other = {}
    if worker._set_equipment_state(["hero",71,true], equipment_view, equipment_actions) != {"ok":false,"error":"equipment_missing"}:
        push_error("Missing equipment was accepted")
        worker.free()
        return
    checks += 1
    if worker._set_equipment_state(["hero",70,"false"], equipment_view, equipment_actions) != {"ok":false,"error":"invalid_arguments"}:
        push_error("Non-boolean equipment state was accepted")
        worker.free()
        return
    checks += 1
    equipment_view.equipped_equipment_ids_by_char = "invalid"
    if worker._set_equipment_state(["hero",70,true], equipment_view, equipment_actions) != {"ok":false,"error":"equipment_state_unknown"}:
        push_error("Unknown equipment state was accepted")
        worker.free()
        return
    checks += 1
    if worker._set_equipment_state([], equipment_view, equipment_actions) != {"ok":false,"error":"invalid_arguments"}:
        push_error("Missing equipment arguments were accepted")
        worker.free()
        return
    checks += 1
    var skill_view = {"materials":{}, "character_progress_by_char":{"hero":{"skill_points":1}}}
    var skill_cost = [{"item_data_id":200501,"count":1}]
    if not worker._current_inventory_covers_cost(skill_cost, skill_view, "hero"):
        push_error("Current skill-point balance rejected an affordable upgrade")
        worker.free()
        return
    checks += 1
    skill_view.character_progress_by_char.hero.skill_points = 0
    if worker._current_inventory_covers_cost(skill_cost, skill_view, "hero"):
        push_error("Insufficient current skill points accepted")
        worker.free()
        return
    checks += 1
    skill_view.character_progress_by_char.hero.erase("skill_points")
    if worker._current_inventory_covers_cost(skill_cost, skill_view, "hero"):
        push_error("Missing current skill-point balance accepted")
        worker.free()
        return
    checks += 1
    if worker._current_inventory_covers_cost([], skill_view):
        push_error("Missing skill preview cost accepted")
        worker.free()
        return
    checks += 1
    if worker._current_inventory_covers_cost([{"item_data_id":200501,"count":0}], skill_view):
        push_error("Invalid zero skill cost accepted")
        worker.free()
        return
    checks += 1
    skill_view.character_progress_by_char.hero.skill_points = 1
    if worker._current_inventory_covers_cost(skill_cost, skill_view, "other") or worker._current_inventory_covers_cost(skill_cost, skill_view):
        push_error("Unrelated skill-point owner accepted")
        worker.free()
        return
    checks += 1
    if worker._current_inventory_covers_cost(skill_cost + skill_cost, skill_view, "hero"):
        push_error("Duplicate skill cost not totaled")
        worker.free()
        return
    checks += 1
    for invalid in [true, "2", -1, 1.5, INF, NAN]:
        skill_view.character_progress_by_char.hero.skill_points = invalid
        if worker._current_inventory_covers_cost(skill_cost, skill_view, "hero"):
            push_error("Invalid skill-point balance accepted")
            worker.free()
            return
        checks += 1
    var connection_checks = _connection_checks(worker)
    var fixture = load("res://loading_check.gd").new()
    var loading_checks = fixture.run(worker)
    worker.free()
    if connection_checks < 0 or loading_checks < 0:
        return
    print("[WalletHeroesAssistant] consumption checks passed: ", checks)
    print("[WalletHeroesAssistant] connection checks passed: ", connection_checks)
    print("[WalletHeroesAssistant] loading checks passed: ", loading_checks)

func _connection_checks(worker) -> int:
    var checks = 0
    if worker._connection_state() != {"known":false}:
        push_error("Missing host accepted")
        return -1
    checks += 1
    var incomplete = Node.new()
    worker.host = incomplete
    var incomplete_result = worker._connection_state()
    worker.host = null
    incomplete.free()
    if incomplete_result != {"known":false}:
        push_error("Missing host properties accepted")
        return -1
    checks += 1
    var fake = FakeHost.new()
    worker.host = fake
    for key in ["server_connection_ui_controller", "server_runtime_coordinator", "world_socket_gateway"]:
        var original = fake.get(key)
        fake.set(key, null)
        var missing = worker._connection_state()
        fake.set(key, original)
        if missing != {"known":false}:
            push_error("Missing connection object accepted: " + key)
            fake.free()
            return -1
        checks += 1
    var ui = fake.server_connection_ui_controller
    fake.server_connection_ui_controller = RefCounted.new()
    var missing_ui = worker._connection_state()
    fake.server_connection_ui_controller = ui
    if missing_ui != {"known":false}:
        push_error("Incomplete UI accepted")
        fake.free()
        return -1
    checks += 1
    var coordinator = fake.server_runtime_coordinator
    fake.server_runtime_coordinator = RefCounted.new()
    var missing_method = worker._connection_state()
    fake.server_runtime_coordinator = coordinator
    if missing_method != {"known":false}:
        push_error("Missing native retry method accepted")
        fake.free()
        return -1
    checks += 1
    var expected = {"known":true,"fatal":true,"fatal_kind":"retry","fatal_restart_requested":false,"intentional_shutdown":false,"login_retry_pending":false}
    var state = worker._connection_state()
    if state != expected or state.size() != 6 or JSON.stringify(state).contains("PRIVATE_SENTINEL"):
        push_error("Connection whitelist or privacy boundary failed")
        fake.free()
        return -1
    checks += 1
    for kind in ["retry", "quit", "sanction", "unknown", "", 12, null]:
        ui.fatal_kind = kind
        state = worker._connection_state()
        if state.get("fatal_kind") != kind or typeof(state.get("fatal_kind")) != typeof(kind):
            push_error("Native fatal kind was coerced")
            fake.free()
            return -1
        checks += 1
    ui.fatal_kind = "retry"
    for pair in [["fatal_handling","fatal"],["fatal_restart_requested","fatal_restart_requested"],["intentional_shutdown","intentional_shutdown"]]:
        var original = ui.get(pair[0])
        for invalid in [0, 1, "false", null]:
            ui.set(pair[0], invalid)
            state = worker._connection_state()
            if state.get(pair[1]) != invalid or typeof(state.get(pair[1])) != typeof(invalid):
                push_error("Invalid UI state was coerced to boolean")
                fake.free()
                return -1
            checks += 1
        ui.set(pair[0], original)
    for value in [true, false, 0, 1, "false", null]:
        coordinator.retry_pending = value
        state = worker._connection_state()
        if state.get("login_retry_pending") != value or typeof(state.get("login_retry_pending")) != typeof(value):
            push_error("Native retry result was coerced to boolean")
            fake.free()
            return -1
        checks += 1
    worker.host = null
    fake.free()
    return checks
''',
        'res://loading_check.gd':(ROOT/'tools/fixtures/loading_check.gd').read_bytes(),
        'res://.godot/global_script_class_cache.cfg': b'list=[]\n',
    })
    p = subprocess.run([str(engine),'--headless','--main-pack',str(LAB/'syntax.pck'),'--quit-after','3'],capture_output=True,timeout=25,env={**os.environ,"LOCALAPPDATA":str(LAB/"data")})
    text=(p.stdout+p.stderr).decode('utf8',errors='replace')
    (LAB/'validation.log').write_text(text,encoding='utf8')
    print('Engine exit:', p.returncode, text)
    if p.returncode or any(x in text for x in ['SCRIPT ERROR','Parse Error','Failed to load script']):
        raise SystemExit(1)
    if '[WalletHeroesAssistant] loader revision 2' not in text: raise SystemExit('Observer missing')
    if 'const REVISION = 19' not in (ROOT/'bridge/worker.gd').read_text(encoding='utf8'): raise SystemExit('Multi-instance bridge revision missing')
    if '[WalletHeroesAssistant] consumption checks passed: 74' not in text: raise SystemExit('Consumption boundary checks failed')
    if '[WalletHeroesAssistant] connection checks passed: 33' not in text: raise SystemExit('Connection boundary checks failed')
    if '[WalletHeroesAssistant] loading checks passed: 130' not in text: raise SystemExit('Loading boundary checks failed')
    report = {name:int(re.search(r'\[WalletHeroesAssistant\] '+name+r' checks passed: (\d+)', text).group(1)) for name in ('consumption','connection','loading')}
    report['total'] = sum(report.values())
    report['worker_revision'] = 19
    (ROOT/'runtime/bridge-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(f"Isolated observer syntax passed; {report['total']} boundary checks passed.")
