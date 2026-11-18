extends Node

const REVISION = 20
var data_dir: String
var host: Node
var gateway: Object
var elapsed: float = 0.0
var last_tick_ms: int = 0
var snapshot_write_ms: int = 0
var write_parts: Dictionary = {}
var detail_elapsed: float = 10.0
var sequence: int = 0
var events: Array = []
var catalog_written: bool = false
var services_written: bool = false
var clients: Dictionary = {}
var native_catalog: RefCounted
var selectors: Dictionary = {}
var control: Dictionary = {}
var original_fps: int = -1
var fx_backup: Dictionary = {}
var observed_account_id: int = 0
var request_account_ids: Dictionary = {}

func _dispose_clients() -> void:
	for client in clients.values():
		if client.has_method("dispose"):
			client.call("dispose")
		elif client.has_method("_on_host_exiting"):
			client.call("_on_host_exiting")
	clients.clear()
	selectors.clear()
	native_catalog = null

func _exit_tree() -> void:
	_restore_display()
	_dispose_clients()

func _native_setup() -> void:
	if not clients.is_empty():
		return
	for key in ["craft", "enhancement", "socket", "disassembly"]:
		var client = load("res://scripts/services/workshop_" + key + "_client.gd").new()
		if key == "craft":
			client.call("setup", gateway, Callable(host.get("progression_selectors"), "_inventory_view_snapshot"))
		elif key == "socket":
			client.call("setup", gateway, host.get("store"))
		else:
			client.call("setup", gateway)
		clients[key] = client
	var loot = load("res://scripts/services/pending_battle_loot_controller.gd").new()
	loot.call("setup", host)
	clients["loot"] = loot
	var mail = load("res://scripts/ui/mail_window_controller.gd").new()
	mail.call("setup", host)
	clients["mail"] = mail
	native_catalog = load("res://scripts/ui/workshop/workshop_catalog.gd").new()
	native_catalog.call("setup", host)
	for key in ["craft", "enhancement", "socket", "inventory"]:
		selectors[key] = load("res://scripts/state/workshop_" + key + "_selector.gd")


func setup(directory: String) -> void:
	data_dir = directory.path_join("instances").path_join(str(OS.get_process_id()))
	DirAccess.make_dir_recursive_absolute(data_dir.path_join("commands"))
	DirAccess.make_dir_recursive_absolute(data_dir.path_join("results"))

func _process(delta: float) -> void:
	if data_dir.is_empty():
		return
	var now_ms: int = Time.get_ticks_msec()
	if now_ms - last_tick_ms < 1000:
		return
	last_tick_ms = now_ms
	var export_started: int = Time.get_ticks_msec()
	var control_path = data_dir.path_join("control.json")
	var config_value = JSON.parse_string(FileAccess.get_file_as_string(control_path)) if FileAccess.file_exists(control_path) else {}
	if config_value is Dictionary:
		control = config_value
	detail_elapsed += 1.0
	var scene = get_tree().current_scene
	if scene != null and _has(scene, "world_socket_gateway"):
		host = scene
	if not is_instance_valid(host):
		_write("snapshot.json", {"revision": REVISION, "time_unix": Time.get_unix_time_from_system(), "connected": false, "phase": "waiting_game"})
		return
	_apply_display()
	var current = host.get("world_socket_gateway")
	if current != gateway:
		_dispose_clients()
		if is_instance_valid(gateway):
			if gateway.is_connected("request_completed", _completed):
				gateway.disconnect("request_completed", _completed)
			if gateway.is_connected("request_failed", _failed):
				gateway.disconnect("request_failed", _failed)
		gateway = current
		detail_elapsed = 10.0
		if gateway != null:
			gateway.connect("request_completed", _completed)
			gateway.connect("request_failed", _failed)
	var loading = _continue_loading()
	sequence += 1
	var connected = gateway != null and bool(gateway.get("logged_in"))
	var current_account_id = _account_id(gateway.call("snapshot")) if connected else 0
	if current_account_id > 0 and current_account_id != observed_account_id:
		_dispose_clients()
		observed_account_id = current_account_id
		detail_elapsed = 10.0
	if connected and detail_elapsed >= 5.0:
		detail_elapsed = 0.0
		_export_details()
		_native_setup()
		_skill_previews()
		_export_opportunities()
	var result: Dictionary = {"revision": REVISION, "pid": OS.get_process_id(), "sequence": sequence, "time_unix": Time.get_unix_time_from_system(), "connected": connected, "phase": "ready" if connected else "waiting_session", "deck": host.get("equipped_deck"), "stage_hold": host.get("stage_hold_enabled")}
	result["connection"] = _connection_state()
	result["loading"] = loading
	if gateway != null:
		var pending: Variant = gateway.get("pending_requests")
		result["pending_requests"] = {}
		if pending is Dictionary:
			for id in pending:
				var request: Variant = pending[id]
				result["pending_requests"][str(id)] = {"command": request.get("command", "")} if request is Dictionary else {}
		result["account"] = {"player": {"id": current_account_id}}
	var sim = host.get("sim")
	if sim != null:
		var combat: Dictionary = sim.call("snapshot")
		for key in ["enemies", "fx_events", "install_zones", "player_stone_cooldowns", "player_runtime_buffs"]:
			combat.erase(key)
		result["sim"] = combat
		result["in_dungeon"] = host.call("_is_dungeon_map", int(combat.get("map_id", 0)))
	var selectors = host.get("progression_selectors")
	if selectors != null:
		result["inventory"] = selectors.call("_inventory_view_snapshot").duplicate(true)
		_annotate_steam(result["inventory"])
	result["assistant_display"] = {"target_fps": Engine.max_fps, "minimal_effects": bool(control.get("minimal_effects", false)), "hidden_layers": fx_backup.size()}
	var heroes = host.get("hero_progression_facade")
	if heroes != null:
		result["owned_characters"] = heroes.call("owned_character_keys")
		result["formation_limit"] = heroes.call("formation_slot_limit")
	if not clients.is_empty() and is_instance_valid(host.get("server_runtime_coordinator")):
		result["native_busy"] = {"skill": host.get("server_runtime_coordinator").call("has_pending_skill_request"), "equipment": host.get("server_runtime_coordinator").call("has_pending_equipment_request"), "enhancement": clients.enhancement.get("busy"), "socket": clients.socket.get("busy"), "craft": clients.craft.get("pending"), "disassembly": clients.disassembly.get("pending"), "loot": clients.loot.call("is_busy"), "stones": _stone_operations_busy()}
	result["startup_selection_pending"] = host.get("startup_character_selection_pending")
	result["consumables"] = host.get("combat_consumable_coordinator").call("snapshot")
	result["playable_characters"] = host.get("PLAYABLE_CHARACTERS")
	result["grade_names"] = {}
	var palette = load("res://scripts/ui/shared/grade_palette.gd")
	for grade in range(1, 11):
		result["grade_names"][str(grade)] = palette.call("grade_name", grade)
	result["export_ms"] = Time.get_ticks_msec() - export_started
	result["snapshot_write_ms"] = snapshot_write_ms
	result["write_parts"] = write_parts
	result["time_unix"] = Time.get_unix_time_from_system()
	var write_started: int = Time.get_ticks_msec()
	_write("snapshot.json", result)
	snapshot_write_ms = Time.get_ticks_msec() - write_started
	if connected:
		_process_command()

func _set_equipment_state(args: Array, view: Dictionary, actions: Object) -> Variant:
	if args.size() < 2 or args.size() > 3 or not args[0] is String or str(args[0]).is_empty():
		return {"ok": false, "error": "invalid_arguments"}
	if not (args[1] is int or args[1] is float) or float(args[1]) != float(int(args[1])) or int(args[1]) <= 0:
		return {"ok": false, "error": "invalid_arguments"}
	if args.size() == 3 and not args[2] is bool:
		return {"ok": false, "error": "invalid_arguments"}
	var owner: String = args[0]
	var item_id: int = int(args[1])
	var desired: bool = args[2] if args.size() == 3 else true
	var by_owner: Variant = view.get("equipped_equipment_ids_by_char")
	if not by_owner is Dictionary or not view.get("items") is Array:
		return {"ok": false, "error": "equipment_state_unknown"}
	var exists: bool = false
	for item in view.items:
		if item is Dictionary and int(item.get("instance_id", item.get("id", 0))) == item_id:
			exists = true
	if not exists:
		return {"ok": false, "error": "equipment_missing"}
	var current: bool = false
	for key in by_owner:
		if not by_owner[key] is Dictionary:
			return {"ok": false, "error": "equipment_state_unknown"}
		for value in by_owner[key].values():
			if int(value) == item_id:
				if str(key) != owner:
					return {"ok": false, "error": "equipment_owner_changed"}
				current = true
	if current == desired:
		return {"ok": true, "already_satisfied": true}
	return actions.call("toggle_equipment_instance", item_id, owner)


func _connection_state() -> Dictionary:
	var out: Dictionary = {"known": false}
	if not is_instance_valid(host):
		return out
	for key in ["server_connection_ui_controller", "server_runtime_coordinator", "world_socket_gateway"]:
		if not _has(host, key) or not is_instance_valid(host.get(key)):
			return out
	var ui = host.get("server_connection_ui_controller")
	var coordinator = host.get("server_runtime_coordinator")
	for key in ["fatal_handling", "fatal_kind", "fatal_restart_requested", "intentional_shutdown"]:
		if not _has(ui, key):
			return out
	if not coordinator.has_method("login_retry_pending"):
		return out
	out["fatal"] = ui.get("fatal_handling")
	out["fatal_kind"] = ui.get("fatal_kind")
	out["fatal_restart_requested"] = ui.get("fatal_restart_requested")
	out["intentional_shutdown"] = ui.get("intentional_shutdown")
	out["login_retry_pending"] = coordinator.call("login_retry_pending")
	out["known"] = true
	return out

# Export only presentation booleans, never the native IPC session or status.
func _loading_state() -> Dictionary:
	var out: Dictionary = {"known": false}
	if not is_instance_valid(host) or not _has(host, "bi_loading_presenter"):
		return out
	var loading = host.get("bi_loading_presenter")
	if not is_instance_valid(loading) or not _has(loading, "process_client"):
		return out
	var client = loading.get("process_client")
	if not is_instance_valid(client) or not client.has_method("refresh_status") or not loading.has_signal("start_requested"):
		return out
	for key in ["active", "content_ready", "native_ready", "presented_complete", "_cancelled", "_completing", "_start_emitted"]:
		if not _has(loading, key):
			return {"known": false}
		out[key.trim_prefix("_")] = loading.get(key)
	for key in ["helper_ready", "rendered_complete", "requires_start_action", "start_requested", "exit_requested", "failed_closed", "_stopped"]:
		if not _has(client, key):
			return {"known": false}
		out[key.trim_prefix("_")] = client.get(key)
	out["start_bound"] = not loading.get_signal_connection_list("start_requested").is_empty()
	out["known"] = true
	return out

func _loading_can_continue(state: Dictionary) -> bool:
	var enabled = control.get("auto_start")
	if typeof(enabled) != TYPE_BOOL or not enabled:
		return false
	for key in ["known", "active", "content_ready", "native_ready", "presented_complete", "helper_ready", "rendered_complete", "requires_start_action", "start_bound"]:
		var value = state.get(key)
		if typeof(value) != TYPE_BOOL or not value:
			return false
	for key in ["cancelled", "completing", "start_emitted", "start_requested", "exit_requested", "failed_closed", "stopped"]:
		var value = state.get(key)
		if typeof(value) != TYPE_BOOL or value:
			return false
	var connection = _connection_state()
	var fatal_kind = connection.get("fatal_kind")
	if connection.get("known") != true or typeof(fatal_kind) != TYPE_STRING or fatal_kind != "":
		return false
	for key in ["fatal", "fatal_restart_requested", "intentional_shutdown", "login_retry_pending"]:
		var value = connection.get(key)
		if typeof(value) != TYPE_BOOL or value:
			return false
	var current = host.get("world_socket_gateway")
	if not _has(current, "logged_in") or not _has(current, "pending_requests"):
		return false
	var logged_in = current.get("logged_in")
	var pending = current.get("pending_requests")
	return typeof(logged_in) == TYPE_BOOL and not logged_in and pending is Dictionary and pending.is_empty()

func _continue_loading() -> Dictionary:
	var state = _loading_state()
	if not _loading_can_continue(state):
		return state
	# Read the real helper status again before accepting the start choice.
	var loading = host.get("bi_loading_presenter")
	var client = loading.get("process_client")
	client.call("refresh_status")
	state = _loading_state()
	if not _loading_can_continue(state):
		return state
	if not is_instance_valid(host) or not is_instance_valid(loading) or not is_instance_valid(client):
		return state
	if host.get("bi_loading_presenter") != loading or loading.get("process_client") != client:
		return state
	# Let the native presenter emit once and finish its normal login/reveal flow.
	# This is the same flag accepted by the native start button, not an IPC reply.
	client.set("start_requested", true)
	state = _loading_state()
	state["continued"] = true
	print("[WalletHeroesAssistant] continued native loading")
	return state

func _export_details() -> void:
	var store = host.get("store")
	if store != null and not catalog_written:
		var catalog: Dictionary = {}
		for name in ["Items"]:
			catalog[name] = store.call("get_records", name)
		_write("catalog.json", catalog)
		catalog_written = true
	if services_written:
		return
	var services: Dictionary = {}
	for prop in host.get_property_list():
		var key = str(prop.name)
		var value = host.get(key)
		if value is Object and value != null and value.get_script() != null:
			var methods: Array = []
			for method in value.get_script().get_script_method_list():
				methods.append({"name": method.name, "args": method.args, "default_args": method.default_args})
			var state: Dictionary = {}
			if key in ["progression", "world_socket_gateway", "server_runtime_coordinator", "hero_deck_controller", "rune_page_window_controller", "cube_window_controller", "workshop_window_controller", "pending_battle_loot_controller", "item_collection_client"]:
				for field in value.get_property_list():
					var label = str(field.name)
					if label.begins_with("_") or label in ["script", "host", "gateway"]:
						continue
					var field_value = value.get(label)
					if not field_value is Object:
						state[label] = field_value
			services[key] = {"methods": methods, "state": state}
	_write("services.json", services)
	services_written = true

func _skill_previews() -> Array:
	var out: Array = []
	var store = host.get("store")
	var facade = host.get("skill_runtime_facade")
	var heroes = host.get("hero_progression_facade")
	if store == null or facade == null or heroes == null:
		return out
	var owned: Array = heroes.call("owned_character_keys")
	for item in store.call("get_records", "Items"):
		if str(item.get("category", "")) != "Skill":
			continue
		var id = int(item.get("id", 0))
		var owner = str(heroes.call("skill_item_owner_key", id))
		if not owned.has(owner):
			continue
		var level = int(facade.call("level_for_context", id))
		var preview: Dictionary = facade.call("unlock_preview", id, 1) if level == 0 else facade.call("level_preview", id)
		out.append({"id": id, "name": item.get("name", ""), "owner": owner, "level": level, "preview": preview})
	_write("skill-previews.json", {"time_unix": Time.get_unix_time_from_system(), "pid": OS.get_process_id(), "account_id": _account_id(gateway.call("snapshot")), "rows": out})
	return out

func _process_command() -> void:
	_prune_request_accounts()
	var directory = data_dir.path_join("commands")
	var names = DirAccess.get_files_at(directory)
	names.sort()
	for name in names:
		if not str(name).ends_with(".json"):
			continue
		var path = directory.path_join(name)
		var request = JSON.parse_string(FileAccess.get_file_as_string(path))
		if not request is Dictionary:
			DirAccess.rename_absolute(path, path + ".invalid")
			continue
		var id = str(request.get("id", ""))
		if id.is_empty() or id.get_file() != id:
			DirAccess.rename_absolute(path, path + ".invalid")
			continue
		var result_path = "results/" + id + ".json"
		if not FileAccess.file_exists(data_dir.path_join(result_path)):
			# Journal acceptance before native dispatch so a hot reload never blindly replays a spend.
			_write(result_path, {"id": id, "status": "dispatching", "time_unix": Time.get_unix_time_from_system()})
			var command_account_id = _positive_id(request.get("account_id"))
			var before: Array = gateway.get("pending_requests").keys()
			var answer = _execute(request)
			var added: Array = []
			for pending_id in gateway.get("pending_requests"):
				if not before.has(pending_id):
					added.append(pending_id)
					request_account_ids[str(pending_id)] = command_account_id
			_write(result_path, {"id": id, "status": "submitted", "account_id": _positive_id(request.get("account_id")), "action": request.get("action"), "answer": answer, "request_ids": added, "time_unix": Time.get_unix_time_from_system()})
		DirAccess.remove_absolute(path)
		return

func _execute(request: Dictionary) -> Variant:
	var action = str(request.get("action", ""))
	var args: Array = request.get("args", [])
	if request.has("pid") and int(request.pid) != OS.get_process_id():
		return {"ok": false, "error": "game_session_changed"}
	var requested_account_id = _positive_id(request.get("account_id"))
	if requested_account_id <= 0:
		return {"ok": false, "error": "account_identity_missing"}
	if not is_instance_valid(gateway) or not gateway.has_method("snapshot"):
		return {"ok": false, "error": "account_identity_unavailable"}
	var native_account_id = _account_id(gateway.call("snapshot"))
	if native_account_id <= 0:
		return {"ok": false, "error": "account_identity_unavailable"}
	if int(requested_account_id) != native_account_id:
		return {"ok": false, "error": "account_changed"}
	var view: Dictionary = host.get("progression_selectors").call("_inventory_view_snapshot").duplicate(true)
	_annotate_steam(view)
	if action != "initial_pick" and not bool(view.get("server_inventory_mutation_safe", false)):
		return {"ok": false, "error": "inventory_not_authoritative"}
	var runtime = host.get("server_runtime_coordinator")
	var actions = host.get("progression_actions")
	match action:
		"skill_learn", "skill_level":
			if args.size() != 2:
				return {"ok": false, "error": "invalid_arguments"}
			var facade = host.get("skill_runtime_facade")
			var preview: Dictionary = facade.call("unlock_preview", int(args[1]), 1) if action == "skill_learn" else facade.call("level_preview", int(args[1]))
			var heroes = host.get("hero_progression_facade")
			if heroes == null or str(heroes.call("skill_item_owner_key", int(args[1]))) != str(args[0]) or not heroes.call("owned_character_keys").has(str(args[0])):
				return {"ok": false, "error": "skill_owner_changed"}
			var current_cost_ok: bool = _current_inventory_covers_cost(preview.get("cost", []), view, str(args[0]))
			if not bool(preview.get("ok", false)) or not bool(preview.get("can_afford", false)) or not current_cost_ok:
				return {"ok": false, "error": preview.get("error", "skill_materials_not_ready")}
			return runtime.call("request_skill_learn" if action == "skill_learn" else "request_skill_level_up", str(args[0]), int(args[1]))
		"identify":
			return runtime.call("request_identify_equipments", args)
		"stone_equip":
			if _stone_operations_busy():
				return {"ok": true, "skipped": true, "reason": "native_stone_busy"}
			return actions.callv("equip_stone_instance_to_slot", args)
		"stone_merge":
			if args.size() != 2 or _positive_id(args[0]) <= 0 or _positive_id(args[1]) <= 0 or int(args[0]) == int(args[1]):
				return {"ok": false, "error": "invalid_arguments"}
			if _stone_operations_busy():
				return {"ok": true, "skipped": true, "reason": "native_stone_busy"}
			if _safe_stone_merge_ids(args, view).size() != 2:
				return {"ok": true, "skipped": true, "reason": "stone_candidates_changed"}
			return actions.call("merge_stones_with_ids", args)
		"equipment_equip":
			return _set_equipment_state(args, view, actions)
		"formation":
			return runtime.call("request_formation_save", args)
		"initial_pick":
			host.get("account_bootstrap_coordinator").call("confirm_initial_character_selection", str(args[0]))
			return {"ok": true}
		"character_purchase":
			var preview: Dictionary = runtime.call("character_purchase_preview", str(args[0]))
			if not bool(preview.get("ok", false)):
				return preview
			return runtime.callv("purchase_character", args)
		"rune_level":
			var runes = host.get("rune_page_window_controller")
			var preview: Dictionary = runes.call("_preview", runes.call("_command_page_def"), str(args[0]))
			if not bool(preview.get("ok", false)):
				return preview
			return runes.call("level_up_node_by_key", str(args[0]))
		"skill_equip":
			return host.get("server_skill_loadout_coordinator").callv("request_equip", args)
		"loot_claim":
			clients.loot.call("claim_all")
			return {"ok": clients.loot.call("is_busy")}
		"mail_refresh":
			return {"request_id": gateway.call("send_mail_list")}
		"mail_claim":
			var ids: Array = _mail_claim_ids()
			if ids.is_empty():
				return {"ok": false, "error": "mail_not_ready"}
			return {"request_id": gateway.call("send_mail_read", ids)}
		"consumable_potion":
			var consumables = host.get("combat_consumable_coordinator")
			if consumables.call("is_toggle_active", "potion"):
				return {"ok": false, "error": "already_enabled"}
			return consumables.call("toggle", "potion")
		"consumable_exp":
			return host.get("combat_consumable_coordinator").call("toggle", "exp")
		"mainline_resume":
			if not bool(host.get("stage_hold_enabled")):
				return {"ok": false, "error": "already_advancing"}
			host.set("stage_hold_enabled", false)
			host.call("_mark_local_save_dirty", "settings.stage_hold")
			return {"ok": true}
		"collection_register":
			if not _consumable_instance(int(args[2]), view, false):
				return {"ok": false, "error": "protected_collection_item"}
			return host.get("item_collection_client").callv("register_slot", args)
		"craft":
			clients.craft.call("clear_result")
			var descriptor: Dictionary = native_catalog.call("recipe_descriptor", int(args[0]))
			var plan: Dictionary = selectors.craft.call("material_plan", descriptor, host.get("progression_selectors").call("_inventory_view_snapshot").duplicate(true), bool(args[1]), int(args[2]))
			if not clients.craft.call("can_execute", descriptor, plan):
				return {"ok": false, "error": "craft_not_ready", "plan": plan}
			return clients.craft.call("execute", descriptor, plan, sequence)
		"enhancement_quote":
			return clients.enhancement.call("preview", int(args[0]))
		"enhancement_execute":
			if int(clients.enhancement.get("target_id")) != int(args[0]):
				return {"ok": false, "error": "quote_target_changed"}
			return clients.enhancement.call("execute")
		"socket":
			if args.size() != 4 or _positive_id(args[0]) <= 0 or _positive_id(args[2]) <= 0:
				return {"ok": false, "error": "invalid_arguments"}
			if typeof(args[1]) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(args[1]) or args[1] < 0 or args[1] > 5 or floor(args[1]) != args[1]:
				return {"ok": false, "error": "invalid_arguments"}
			var socket_raw: Dictionary = gateway.call("snapshot")
			var costs: Dictionary = _socket_gold_costs(selectors.inventory.call("rows", socket_raw, host.get("store")), selectors.socket.call("gems", socket_raw, host.get("store")))
			var cost: Variant = costs.get(str(int(args[0])), {}).get(str(int(args[2])), -1)
			if not _socket_budget_allows(cost, args[3], view):
				return {"ok": false, "error": "socket_budget_changed"}
			var plan: Dictionary = {int(args[1]): int(args[2])}
			return clients.socket.call("execute", int(args[0]), plan)
		"salvage_quote":
			var counts: Dictionary = {}
			for id in args:
				if not _consumable_instance(int(id), view, true):
					return {"ok": false, "error": "protected_salvage_item"}
				var count: int = _salvage_count_for_id(int(id), view)
				if count <= 0:
					return {"ok": false, "error": "salvage_quantity_changed"}
				counts[int(id)] = count
			clients.disassembly.call("set_selection", counts)
			return {"ok": int(clients.disassembly.get("pending")) > 0}
		"salvage_execute":
			if not _salvage_quote_matches(args, clients.disassembly.get("selection"), clients.disassembly.get("quote"), view):
				return {"ok": false, "error": "salvage_quote_changed"}
			for row in args[2]:
				var id: int = int(row.get("id", 0))
				if not _consumable_instance(id, view, true) or _salvage_count_for_id(id, view) != int(row.get("count", 0)):
					return {"ok": false, "error": "salvage_protection_changed"}
			return clients.disassembly.call("execute")
		"dungeon_enter":
			var entry = load("res://scripts/ui/portal/dungeon_entry_controller.gd")
			if int(args[0]) > int(host.call("_dungeon_unlocked_floor")) or int(entry.call("key_count", host)) < int(args[0]):
				return {"ok": false, "error": "dungeon_not_ready"}
			if load("res://scripts/services/boss_reward_entry_guard.gd").call("blocked", host, int(args[0])):
				return {"ok": false, "error": "dungeon_rewards_pending"}
			host.call("_enter_dungeon_floor", int(args[0]))
			return {"ok": true, "entered_map_id": int(host.get("sim").get("map_id")), "in_dungeon": host.call("_is_dungeon_map", int(host.get("sim").get("map_id")))}

	return {"ok": false, "error": "unsupported_action"}

func _socket_gold_costs(rows: Dictionary, gems: Array) -> Dictionary:
	var result: Dictionary = {}
	var policy = load("res://scripts/game/gem_socket_policy.gd")
	for row in rows.values():
		if not row is Dictionary or int(row.get("grade", 0)) < 3 or str(row.get("category_filter", "")) not in ["weapon", "armor", "accessory"]:
			continue
		if not row.get("definition") is Dictionary or _positive_id(row.get("id")) <= 0:
			continue
		var costs: Dictionary = {}
		for gem in gems:
			if not gem is Dictionary or not gem.get("definition") is Dictionary or _positive_id(gem.get("id")) <= 0:
				continue
			var cost: int = policy.call("apply_gold_cost", gem.definition, row.definition)
			if cost >= 0:
				costs[str(int(gem.id))] = cost
		result[str(int(row.id))] = costs
	return result


func _socket_budget_allows(cost: Variant, requested_reserve: Variant, view: Dictionary) -> bool:
	var materials: Variant = view.get("materials", {})
	if not materials is Dictionary:
		return false
	var gold: Variant = materials.get("5", materials.get(5, 0))
	var ratio: Variant = control.get("gold_reserve_ratio", 0.12)
	var minimum: Variant = control.get("gold_reserve_min", 200)
	for value in [cost, requested_reserve, gold, ratio, minimum]:
		if typeof(value) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(value) or value < 0:
			return false
	if floor(cost) != cost or floor(gold) != gold or ratio > 1:
		return false
	return cost <= maxf(0.0, gold - maxf(float(requested_reserve), maxf(float(minimum), gold * ratio)))


func _salvage_quote_matches(args: Array, selection: Dictionary, quote: Dictionary, view: Dictionary) -> bool:
	if args.size() != 3 or not args[2] is Array:
		return false
	if int(args[0]) != OS.get_process_id() or int(args[1]) <= 0 or int(args[1]) != int(quote.get("request_id", 0)):
		return false
	var requested: Dictionary = {}
	for row in args[2]:
		if not row is Dictionary:
			return false
		var id: int = int(row.get("id", 0))
		var count: int = int(row.get("count", 0))
		if id <= 0 or count <= 0 or requested.has(id):
			return false
		requested[id] = count
	var selected: Dictionary = {}
	for id in selection:
		var current_id: int = int(id)
		var count: int = int(selection[id])
		if current_id <= 0 or count <= 0 or selected.has(current_id):
			return false
		selected[current_id] = count
	if requested.is_empty() or requested.size() != selected.size():
		return false
	for id in requested:
		if not selected.has(id) or int(selected[id]) != int(requested[id]) or _salvage_count_for_id(int(id), view) != int(requested[id]):
			return false
	return true

func _salvage_count_for_id(id: int, view: Dictionary) -> int:
	for item in view.get("items", []):
		if int(item.get("instance_id", item.get("id", 0))) == id:
			return 1 if _consumable_instance(id, view, true) else 0
	for record in view.get("material_records", []):
		if int(record.get("record_id", record.get("instance_id", record.get("id", 0)))) == id:
			return int(record.get("count", 0)) if _consumable_instance(id, view, true) else 0
	return 0

func _completed(id: int, response: Dictionary) -> void:
	_receipt(id, response, true)

func _failed(id: int, response: Dictionary) -> void:
	_receipt(id, response, false)

func _receipt(id: int, response: Dictionary, success: bool) -> void:
	var account_id = _receipt_account(id)
	var event: Dictionary = {"request_id": id, "ok": success, "response": response, "time_unix": Time.get_unix_time_from_system()}
	if account_id > 0:
		event["account_id"] = account_id
	if account_id > 0:
		_write("receipt-" + str(OS.get_process_id()) + "-" + str(account_id) + "-" + str(id) + ".json", event)
		request_account_ids.erase(str(id))

func _receipt_account(id: int) -> int:
	return _positive_id(request_account_ids.get(str(id), 0))

func _prune_request_accounts() -> void:
	if not is_instance_valid(gateway):
		return
	var native_pending: Variant = gateway.get("pending_requests")
	if not native_pending is Dictionary:
		return
	var active: Dictionary = {}
	for id in native_pending:
		active[str(id)] = true
	for id in request_account_ids.keys():
		if not active.has(str(id)):
			request_account_ids.erase(id)

func _has(object: Object, key: String) -> bool:
	for prop in object.get_property_list():
		if str(prop.name) == key:
			return true
	return false

func _safe(value: Variant, depth: int = 0) -> Variant:
	if depth > 18:
		return null
	if value is Dictionary:
		var clean: Dictionary = {}
		for key in value:
			var label = str(key)
			if label.to_lower().contains("token") or label.to_lower().contains("ticket") or label.to_lower().contains("password") or label.to_lower().contains("secret"):
				continue
			clean[label] = _safe(value[key], depth + 1)
		return clean
	if value is Array:
		var clean: Array = []
		for item in value.slice(0, 25000):
			clean.append(_safe(item, depth + 1))
		return clean
	if typeof(value) in [TYPE_NIL, TYPE_BOOL, TYPE_INT, TYPE_FLOAT, TYPE_STRING]:
		return value
	return str(value) if typeof(value) in [TYPE_STRING_NAME, TYPE_NODE_PATH] else null

func _account_id(account: Variant) -> int:
	if not account is Dictionary:
		return 0
	var player: Variant = account.get("player")
	if not player is Dictionary:
		return 0
	var value: Variant = player.get("id")
	return _positive_id(value)

func _positive_id(value: Variant) -> int:
	if typeof(value) == TYPE_INT:
		return int(value) if int(value) > 0 else 0
	# Godot JSON numbers are floats. Only exact positive integers are identities.
	if typeof(value) == TYPE_FLOAT and is_finite(value) and value > 0 and value <= 9007199254740991.0 and floor(value) == value:
		return int(value)
	return 0

func _write(name: String, value: Dictionary) -> void:
	var start: int = Time.get_ticks_msec()
	var serialized: String = JSON.stringify(value if name == "snapshot.json" else _safe(value))
	var encoded: int = Time.get_ticks_msec()
	var path = data_dir.path_join(name)
	var file = FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null:
		return
	# Snapshot fields are explicitly selected above; pending requests carry only
	# command names. Keep full sanitization for diagnostic and receipt exports.
	var opened: int = Time.get_ticks_msec()
	file.store_string(serialized)
	file.close()
	var stored: int = Time.get_ticks_msec()
	DirAccess.rename_absolute(path + ".tmp", path)
	if name == "snapshot.json":
		write_parts = {"encode": encoded-start, "open": opened-encoded, "store": stored-opened, "rename": Time.get_ticks_msec()-stored}


func _export_opportunities() -> void:
	var projection: Dictionary = host.get("progression_selectors").call("_inventory_view_snapshot").duplicate(true)
	_annotate_steam(projection)
	var raw: Dictionary = gateway.call("snapshot")
	var store = host.get("store")
	var out: Dictionary = {"time_unix": Time.get_unix_time_from_system(), "pid": OS.get_process_id(), "account_id": _account_id(raw)}
	var rune_controller = host.get("rune_page_window_controller")
	var rune_page: Dictionary = rune_controller.call("_command_page_def")
	var rune_snapshot: Dictionary = rune_controller.call("_rune_snapshot")
	var rune_previews: Array = []
	for node in rune_page.get("nodes", []):
		rune_previews.append(rune_controller.call("_server_rune_preview", rune_page, str(node.key), rune_snapshot))
	out["runes"] = rune_previews
	var roster: Array = []
	for key in host.get("PLAYABLE_CHARACTERS"):
		roster.append(host.get("server_runtime_coordinator").call("character_purchase_preview", str(key)))
	out["recruitment"] = roster
	out["collections"] = host.get("item_collection_client").call("projection")
	out["loot"] = clients.loot.call("state")
	out["skill_slot_count"] = host.get("server_skill_loadout_coordinator").call("authoritative_skill_slot_count")
	out["stone_slots"] = {}
	for key in host.get("hero_progression_facade").call("owned_character_keys"):
		out["stone_slots"][str(key)] = host.get("progression").call("stone_slot_count_for_char", str(key))
	out["stone_merge_recipes"] = {}
	for item in projection.get("items", []):
		if item.get("tags", []).has("StoneWeapon"):
			var id = int(item.get("item_data_id", 0))
			out["stone_merge_recipes"][str(id)] = host.get("progression_selectors").call("_progression_stone_merge_result_item_data_id", id)
	var members: Array = host.get("progression_selectors").call("_progression_manual_stone_merge_member_ids")
	var merge_ids: Array = host.get("progression_selectors").call("_progression_manual_stone_merge_ids", members)
	out["stone_merge_ids"] = _safe_stone_merge_ids(merge_ids, projection)
	out["in_dungeon"] = host.call("_is_dungeon_map", int(host.get("sim").call("current_map_id")))
	out["mail_ids"] = _mail_claim_ids()
	var candidates: Array = []
	var progress: Dictionary = projection.get("character_progress_by_char", {})
	for item in projection.get("items", []):
		if str(item.get("category", "")) not in ["Equipment", "Weapon"] or item.get("tags", []).has("StoneWeapon"):
			continue
		var owners: Array = []
		for key in progress:
			if native_catalog.call("can_equip", int(item.get("item_data_id", 0)), str(key), int(progress[key].get("level", 1))):
				owners.append(key)
		if not owners.is_empty():
			candidates.append({"instance_id": item.get("instance_id"), "owners": owners})
	out["equipment_eligibility"] = candidates
	var descriptors: Array = native_catalog.get("recipe_entries")
	var plans: Array = selectors.craft.call("material_plans", descriptors, projection)
	var recipes: Array = []
	for index in range(descriptors.size()):
		var descriptor: Dictionary = descriptors[index]
		recipes.append({"recipe_id": descriptor.recipe_id, "target_id": descriptor.target_id, "target": descriptor.target, "required_level": descriptor.required_level, "category": descriptor.category, "subtype": descriptor.subtype, "plan": plans[index], "executable": clients.craft.call("can_execute", descriptor, plans[index])})
	out["recipes"] = recipes
	out["salvage"] = selectors.inventory.call("rows", raw, store)
	out["salvage_can_execute"] = clients.disassembly.call("can_execute")
	out["salvage_quote"] = clients.disassembly.get("quote")
	out["salvage_selection"] = clients.disassembly.get("selection")
	out["enhancement_items"] = selectors.enhancement.call("equipment", raw, store)
	out["enhancement_quote"] = clients.enhancement.get("quote")
	out["enhancement_ready"] = clients.enhancement.call("ready")
	out["enhancement_access"] = gateway.call("enhancement_access_snapshot") if gateway.has_method("enhancement_access_snapshot") else {}
	out["socket_items"] = selectors.socket.call("equipment", raw, store)
	out["socket_gems"] = selectors.socket.call("gems", raw, store)
	out["socket_ready"] = clients.socket.call("ready")
	out["socket_gold_costs"] = _socket_gold_costs(out.salvage, out.socket_gems)
	var entry = load("res://scripts/ui/portal/dungeon_entry_controller.gd")
	var unlocked_floor = int(host.call("_dungeon_unlocked_floor"))
	var keys = int(entry.call("key_count", host))
	var selected_floor = mini(unlocked_floor, maxi(0, keys - int(control.get("dungeon_key_reserve", 0))))
	out["dungeon"] = {"unlocked_floor": unlocked_floor, "keys": keys, "entry_blocked": selected_floor > 0 and load("res://scripts/services/boss_reward_entry_guard.gd").call("blocked", host, selected_floor), "session_required": host.call("_server_session_required")}
	_write("opportunities.json", out)

func _mail_claim_ids() -> Array:
	var out: Array = []
	var mail = clients.get("mail")
	if mail == null:
		return out
	var bag: int = mail.call("_bag_free_slots")
	var stones: int = mail.call("_stone_free_slots")
	var room: Dictionary = {}
	for entry in mail.call("_mail_entries", "reward"):
		if mail.call("_server_mail_expired", entry) or entry.get("attachments", []).is_empty():
			continue
		var next_room = room.duplicate()
		var cost: int = mail.call("_bag_slot_cost", entry, next_room)
		var stone_cost: int = mail.call("_stone_slot_cost", entry)
		if (bag >= 0 and cost > bag) or (stones >= 0 and stone_cost > stones):
			continue
		room = next_room
		bag -= cost
		stones -= stone_cost
		out.append(int(entry.get("id", 0)))
	return out.slice(0, 100)


func _annotate_steam(view: Dictionary) -> void:
	var coordinator = host.get("steam_inventory_coordinator")
	if coordinator != null:
		coordinator.call("prewarm_catalog")
	var ready: bool = coordinator != null and bool(coordinator.call("is_catalog_ready"))
	view["steam_trade_ready"] = ready
	for item in view.get("items", []):
		item["steam_trade_protected"] = true
		if ready:
			var definition: Dictionary = coordinator.call("exportable_definition", int(item.get("item_data_id", 0)), int(item.get("variant_id", 0)), int(item.get("tier", 1)), int(item.get("grade", 1)), int(item.get("level", 1)))
			item["steam_trade_protected"] = not definition.is_empty()


func _consumable_instance(id: int, view: Dictionary, salvage: bool) -> bool:
	if salvage:
		var by_owner: Variant = view.get("equipped_equipment_ids_by_char", {})
		if not by_owner is Dictionary:
			return false
		for loadout in by_owner.values():
			if not loadout is Dictionary:
				return false
			for worn_id in loadout.values():
				if int(worn_id) == id:
					return false
		for worn_id in view.get("equipped_stone_instance_ids", []):
			if int(worn_id) == id:
				return false
	for item in view.get("items", []):
		if int(item.get("instance_id", item.get("id", 0))) != id:
			continue
		var trade_permission: bool = salvage and bool(control.get("salvage_allow_tradeable", false)) and bool(view.get("steam_trade_ready", false)) and typeof(item.get("steam_trade_protected")) == TYPE_BOOL
		if (bool(item.get("steam_trade_protected", true)) and not trade_permission) or bool(item.get("stored", false)) or bool(item.get("unidentified", false)):
			return false
		if int(item.get("state_flag", 0)) & (1 | 2 | 4 | 8 | 32 | 64):
			return false
		if salvage:
			if str(item.get("category", "")) == "Material" and not bool(control.get("salvage_include_materials", false)):
				return false
			if not _salvage_grade_allowed(int(item.get("grade", 1))):
				return false
			if int(item.get("level", 1)) > 1 or int(item.get("enhance_level", 0)) > 0 or not item.get("socket_stats", []).is_empty() or _has_socket_materials(item):
				return false
		return true
	# Collection slots can consume material records (for example, gems),
	# which are not present in the equipment `items` array. They are never
	# salvage targets, but still need the same lock/state protection.
	if not salvage:
		for record in view.get("material_records", []):
			if int(record.get("record_id", record.get("instance_id", record.get("id", 0)))) != id:
				continue
			if int(record.get("count", 0)) <= 0 or bool(record.get("stored", false)):
				return false
			if int(record.get("state_flag", 0)) & (1 | 2 | 4 | 8 | 32 | 64):
				return false
			return true
	else:
		if not bool(control.get("salvage_include_materials", false)):
			return false
		for record in view.get("material_records", []):
			if int(record.get("record_id", record.get("instance_id", record.get("id", 0)))) != id:
				continue
			if int(record.get("count", 0)) <= 0 or bool(record.get("stored", false)):
				return false
			if int(record.get("state_flag", 0)) & (1 | 2 | 4 | 8 | 32 | 64):
				return false
			return _salvage_grade_allowed(int(record.get("grade", 1)))
	return false


func _has_socket_materials(item: Dictionary) -> bool:
	var layers: Variant = item.get("socket_materials", {})
	if not layers is Dictionary:
		return true
	for slots in layers.values():
		if not slots is Array:
			return true
		for material in slots:
			if not material is Dictionary or not material.is_empty():
				return true
	return false


func _current_inventory_covers_cost(cost: Variant, view: Dictionary, owner: String = "") -> bool:
	if not cost is Array or cost.is_empty():
		return false
	var materials: Variant = view.get("materials", {})
	if not materials is Dictionary:
		return false
	var totals: Dictionary = {}
	for row in cost:
		if not row is Dictionary:
			return false
		var item_id: int = _positive_id(row.get("item_data_id", row.get("item_id", 0)))
		var required: int = _positive_id(row.get("count", row.get("required", 0)))
		if item_id <= 0 or required <= 0:
			return false
		totals[item_id] = int(totals.get(item_id, 0)) + required
	for item_id in totals:
		var available: int = int(materials.get(str(item_id), materials.get(item_id, 0)))
		if item_id == 200501:
			var progress: Dictionary = view.get("character_progress_by_char", {}).get(owner, {})
			var points: Variant = progress.get("skill_points")
			if owner.is_empty() or typeof(points) not in [TYPE_INT, TYPE_FLOAT] or not is_finite(points) or points < 0 or floor(points) != points:
				return false
			available = int(points)
		if available < int(totals[item_id]):
			return false
	return true


func _stone_operations_busy() -> bool:
	if not is_instance_valid(host):
		return true
	for key in ["server_stone_merge_request_id", "server_stone_loadout_coordinator", "progression_actions"]:
		if not _has(host, key):
			return true
	if int(host.get("server_stone_merge_request_id")) > 0:
		return true
	var loadout = host.get("server_stone_loadout_coordinator")
	if not is_instance_valid(loadout) or not loadout.has_method("has_pending_requests") or bool(loadout.call("has_pending_requests")):
		return true
	var actions = host.get("progression_actions")
	if not is_instance_valid(actions) or not _has(actions, "manual_batch"):
		return true
	var batch = actions.get("manual_batch")
	return not is_instance_valid(batch) or not _has(batch, "active") or bool(batch.get("active"))


func _safe_stone_merge_ids(candidate_ids: Array, view: Dictionary) -> Array:
	var equipped_ids: Dictionary = {}
	var equipped: Dictionary = view.get("equipped_stone_ids_by_char", {})
	for values in equipped.values():
		if values is Array:
			for value in values:
				equipped_ids[int(value)] = true
	var items: Dictionary = {}
	for item in view.get("items", []):
		var id: int = int(item.get("instance_id", item.get("id", 0)))
		if id > 0:
			items[id] = item
	var out: Array = []
	var seen: Dictionary = {}
	var data_id: int = -1
	for raw_id in candidate_ids:
		var id: int = int(raw_id)
		if id <= 0 or seen.has(id) or equipped_ids.has(id) or not items.has(id):
			return []
		if not _consumable_instance(id, view, false):
			return []
		var current: Dictionary = items[id]
		var current_data_id: int = int(current.get("item_data_id", 0))
		if data_id < 0:
			data_id = current_data_id
		elif current_data_id != data_id:
			return []
		seen[id] = true
		out.append(id)
	return out if out.size() >= 2 else []


func _salvage_grade_allowed(grade: int) -> bool:
	# JSON numbers are floats; Array.has(int) rejects an equal float in Godot.
	for allowed in control.get("salvage_grades", [1, 2, 3]):
		if int(allowed) == grade:
			return true
	return false


func _apply_display() -> void:
	if bool(control.get("performance_mode", false)):
		if original_fps < 0:
			original_fps = Engine.max_fps
		Engine.max_fps = clampi(int(control.get("performance_fps", 10)), 10, 60)
	elif original_fps >= 0:
		Engine.max_fps = original_fps
		original_fps = -1
	if bool(control.get("minimal_effects", false)):
		for key in ["combat_layer", "combat_ground_fx_layer"]:
			var layer = host.get("generated_runtime_nodes").get(key)
			if layer is CanvasItem and is_instance_valid(layer):
				var id: int = layer.get_instance_id()
				if not fx_backup.has(id):
					fx_backup[id] = {"ref": weakref(layer), "color": layer.modulate}
				var color: Color = layer.modulate
				color.a = 0.0
				layer.modulate = color
	else:
		_restore_fx()


func _restore_fx() -> void:
	for entry in fx_backup.values():
		var layer = entry.ref.get_ref()
		if is_instance_valid(layer):
			layer.modulate = entry.color
	fx_backup.clear()


func _restore_display() -> void:
	_restore_fx()
	if original_fps >= 0:
		Engine.max_fps = original_fps
		original_fps = -1
