extends RefCounted

# A small lifecycle fixture, with no native recipe or receipt implementation.
class Client extends RefCounted:
	var pending = 0
	var result: Dictionary = {}
	var uncertain = false
	var acknowledgements = 0
	var legacy_clears = 0
	var executions = 0
	func has_uncertain_operation():
		return uncertain
	func reconcile_correlated_sources():
		acknowledgements += 1
		if pending != 0 or not result.get("source_set_correlated", false):
			return false
		result.clear()
		return true
	func clear_settled_error():
		pass
	func clear_result():
		legacy_clears += 1
		result.clear()
	func can_execute(_descriptor, plan):
		return pending == 0 and result.is_empty() and plan.get("complete", false)
	func execute(_descriptor, _plan, _sequence):
		executions += 1
		result = {"source_set_correlated": true}
		return true

class Catalog extends RefCounted:
	var recipe_entries = [{"recipe_id": 10, "target_id": 20, "target": {}, "required_level": 30, "category": "equipment", "subtype": "Head"}]
	func recipe_descriptor(_id):
		return recipe_entries[0]

class Selector extends RefCounted:
	var complete = true
	func material_plans(_descriptors, _projection):
		return [{"recipe_id":10, "complete":complete}]
	func material_plan(_descriptor, _projection, _lock, _grade):
		return {"recipe_id":10, "complete":complete}

class InventoryView extends RefCounted:
	func _inventory_view_snapshot():
		return {"server_inventory_mutation_safe":true, "items":[]}

class Host extends Node:
	var progression_selectors = InventoryView.new()
	var server_runtime_coordinator = RefCounted.new()
	var progression_actions = RefCounted.new()
	var steam_inventory_coordinator = null

func run(worker) -> int:
	var previous_host = worker.host
	var previous_clients = worker.clients
	var previous_catalog = worker.native_catalog
	var previous_selectors = worker.selectors
	var host = Host.new()
	var client = Client.new()
	var selector = Selector.new()
	worker.host = host
	worker.clients = {"craft":client}
	worker.native_catalog = Catalog.new()
	worker.selectors = {"craft":selector}
	var checks: Array = []
	var request = {"account_id":501, "action":"craft", "args":[10,false,0]}
	client.result = {"source_set_correlated":true}
	var opportunity = worker._craft_opportunities({})
	checks.append(["settled result no longer blocks export", opportunity.craft_state.ready and opportunity.recipes[0].executable and client.acknowledgements == 1])
	worker._craft_opportunities({})
	checks.append(["empty result is not repeatedly acknowledged", client.acknowledgements == 1])
	checks.append(["first craft dispatches", worker._execute(request) == true and client.executions == 1])
	opportunity = worker._craft_opportunities({})
	checks.append(["successful craft exposes next opportunity", opportunity.recipes[0].executable and client.acknowledgements == 2])
	checks.append(["second craft dispatches without helper restart", worker._execute(request) == true and client.executions == 2])
	for reason in ["pending", "outcome_unknown", "result_unconfirmed"]:
		client.pending = 7 if reason == "pending" else 0
		client.uncertain = reason == "outcome_unknown"
		client.result = {"source_set_correlated":reason != "result_unconfirmed"}
		opportunity = worker._craft_opportunities({})
		checks.append([reason + " blocks exported opportunities", not opportunity.craft_state.ready and opportunity.craft_state.reason == reason and not opportunity.recipes[0].executable and not client.result.is_empty()])
		checks.append([reason + " blocks actual spending", worker._execute(request).get("ok") == false and client.executions == 2 and not client.result.is_empty()])
	client.pending = 0
	client.uncertain = true
	client.result.clear()
	checks.append(["uncertain empty result is preserved", worker._execute(request).get("error") == "craft_outcome_unknown" and client.executions == 2])
	client.uncertain = false
	selector.complete = false
	checks.append(["insufficient materials still block export", not worker._craft_opportunities({}).recipes[0].executable])
	checks.append(["insufficient materials still block spending", worker._execute(request).get("error") == "craft_not_ready" and client.executions == 2])
	request.args = [10,false,-1]
	checks.append(["invalid grade is rejected", worker._execute(request).get("error") == "invalid_arguments"])
	checks.append(["legacy unconditional clear is never called", client.legacy_clears == 0])
	worker.clients = {"craft":RefCounted.new()}
	checks.append(["unsupported lifecycle waits", worker._prepare_craft_client().reason == "unavailable"])
	worker.host = previous_host
	worker.clients = previous_clients
	worker.native_catalog = previous_catalog
	worker.selectors = previous_selectors
	host.free()
	for check in checks:
		if not check[1]:
			push_error("Craft lifecycle: " + check[0])
			return -1
	return checks.size()
