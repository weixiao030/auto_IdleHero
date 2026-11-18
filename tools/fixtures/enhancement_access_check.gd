extends RefCounted

# Own fixture: the only native call modeled here is the metadata request.
class Gateway extends RefCounted:
    var access: Dictionary = {"highest_cleared_map_id": 500137}
    var requests = 0
    var next_request = 71
    func snapshot():
        return {"player": {"id": 501}}
    func enhancement_access_snapshot():
        return access.duplicate(true)
    func send_enhancement_access():
        requests += 1
        return next_request

class Unsupported extends RefCounted:
    func snapshot():
        return {"player": {"id": 501}}

class Inventory extends RefCounted:
    var safe = true
    func _inventory_view_snapshot():
        return {"server_inventory_mutation_safe": safe, "items": []}

class Host extends Node:
    var progression_selectors = Inventory.new()
    var steam_inventory_coordinator = null
    var server_runtime_coordinator = RefCounted.new()
    var progression_actions = RefCounted.new()

func run(worker) -> int:
    var old_host = worker.host
    var old_gateway = worker.gateway
    var host = Host.new()
    var gateway = Gateway.new()
    worker.host = host
    worker.gateway = gateway
    var checks: Array = []
    var state = worker._enhancement_access_opportunities()
    checks.append(["export advertises native metadata query", state.enhancement_access_query_supported and state.enhancement_access.highest_cleared_map_id == 500137])
    checks.append(["export never sends background requests", gateway.requests == 0])
    var request = {"action": "enhancement_access", "args": [], "account_id": 501}
    var answer = worker._execute(request)
    checks.append(["explicit query submits native metadata request", answer.ok and answer.request_id == 71 and gateway.requests == 1])
    request.args = [100]
    checks.append(["query rejects item arguments", worker._execute(request).error == "invalid_arguments" and gateway.requests == 1])
    request.args = []
    for unlocked in [false, true]:
        gateway.access = {"required_clear_map_id": 500150, "unlocked": unlocked}
        answer = worker._execute(request)
        checks.append(["known condition is not queried again " + str(unlocked), answer.error == "enhancement_access_already_known" and gateway.requests == 1])
    gateway.access = {}
    gateway.next_request = 0
    answer = worker._execute(request)
    checks.append(["no native request does not count success", not answer.ok and answer.request_id == 0 and gateway.requests == 2])
    host.progression_selectors.safe = false
    answer = worker._execute(request)
    checks.append(["authority gate still applies", answer.error == "inventory_not_authoritative" and gateway.requests == 2])
    host.progression_selectors.safe = true
    request.account_id = 502
    checks.append(["account identity gate still applies", worker._execute(request).error == "account_changed" and gateway.requests == 2])
    request.account_id = 501
    worker.gateway = Unsupported.new()
    checks.append(["unsupported gateway is not advertised", not worker._enhancement_access_opportunities().enhancement_access_query_supported])
    checks.append(["unsupported native query is rejected", worker._execute(request).error == "enhancement_access_unavailable"])
    worker.gateway = null
    checks.append(["missing gateway is not advertised", not worker._enhancement_access_opportunities().enhancement_access_query_supported])
    worker.host = old_host
    worker.gateway = old_gateway
    host.free()
    for check in checks:
        if not check[1]:
            push_error("Enhancement access: " + check[0])
            return -1
    return checks.size()
