extends RefCounted

class Client extends RefCounted:
    var helper_ready = true
    var rendered_complete = true
    var requires_start_action = true
    var start_requested = false
    var exit_requested = false
    var failed_closed = false
    var _stopped = false
    var refresh_calls = 0
    var on_refresh = Callable()
    var session = {"token":"PRIVATE_SENTINEL"}
    var status = {"token":"PRIVATE_SENTINEL"}
    func refresh_status():
        refresh_calls += 1
        if on_refresh.is_valid():
            on_refresh.call()

class Presenter extends RefCounted:
    signal start_requested
    var process_client = Client.new()
    var active = true
    var content_ready = true
    var native_ready = true
    var presented_complete = true
    var _cancelled = false
    var _completing = false
    var _start_emitted = false
    var emissions = 0
    func _init():
        start_requested.connect(_on_start)
    func _on_start():
        emissions += 1

class UI extends RefCounted:
    var fatal_handling = false
    var fatal_kind = ""
    var fatal_restart_requested = false
    var intentional_shutdown = false

class Coordinator extends RefCounted:
    var pending = false
    func login_retry_pending():
        return pending

class Gateway extends RefCounted:
    var logged_in = false
    var pending_requests = {}

class Host extends Node:
    var bi_loading_presenter = Presenter.new()
    var world_socket_gateway = Gateway.new()
    var server_connection_ui_controller = UI.new()
    var server_runtime_coordinator = Coordinator.new()

class NoRefresh extends RefCounted:
    var helper_ready = true

func run(worker) -> int:
    var checks = 0
    worker.control = {"auto_start":true}
    worker.host = null
    if worker._continue_loading() != {"known":false}:
        push_error("Absent loading host accepted")
        return -1
    checks += 1
    var host = Host.new()
    worker.host = host
    var loading = host.bi_loading_presenter
    var client = loading.process_client
    var state = worker._loading_state()
    if not state.get("known") or state.size() != 16 or JSON.stringify(state).contains("PRIVATE_SENTINEL"):
        push_error("Loading export whitelist failed")
        host.free()
        return -1
    checks += 1
    for enabled in [false, 0, 1, "true", null]:
        worker.control = {"auto_start":enabled}
        if worker._continue_loading().get("continued",false) or client.start_requested or client.refresh_calls:
            push_error("Disabled or invalid automation continued loading")
            host.free()
            return -1
        checks += 1
    worker.control = {"auto_start":true}
    for pair in [[loading,"active"],[loading,"content_ready"],[loading,"native_ready"],[loading,"presented_complete"],
            [loading,"_cancelled"],[loading,"_completing"],[loading,"_start_emitted"],
            [client,"helper_ready"],[client,"rendered_complete"],[client,"requires_start_action"],
            [client,"start_requested"],[client,"exit_requested"],[client,"failed_closed"],[client,"_stopped"]]:
        var original = pair[0].get(pair[1])
        for invalid in [not original, 0, 1, "false", null]:
            pair[0].set(pair[1],invalid)
            if worker._continue_loading().get("continued",false) or client.refresh_calls:
                push_error("Unsafe or invalid loading state accepted: " + pair[1])
                host.free()
                return -1
            checks += 1
        pair[0].set(pair[1],original)
    loading.start_requested.disconnect(loading._on_start)
    if worker._continue_loading().get("continued",false) or client.start_requested:
        push_error("Unbound native start accepted")
        host.free()
        return -1
    checks += 1
    loading.start_requested.connect(loading._on_start)
    for key in ["bi_loading_presenter","world_socket_gateway","server_connection_ui_controller","server_runtime_coordinator"]:
        var original = host.get(key)
        for invalid in [null, RefCounted.new()]:
            host.set(key,invalid)
            if worker._continue_loading().get("continued",false) or client.start_requested:
                push_error("Missing native object accepted: " + key)
                host.free()
                return -1
            checks += 1
        host.set(key,original)
    for invalid in [null, RefCounted.new(), NoRefresh.new()]:
        loading.process_client = invalid
        if worker._continue_loading().get("continued",false):
            push_error("Missing client contract accepted")
            host.free()
            return -1
        checks += 1
    loading.process_client = client
    for pair in [[host.server_connection_ui_controller,"fatal_handling"],
            [host.server_connection_ui_controller,"fatal_restart_requested"],
            [host.server_connection_ui_controller,"intentional_shutdown"],
            [host.server_runtime_coordinator,"pending"],[host.world_socket_gateway,"logged_in"]]:
        for invalid in [true, 0, 1, "false", null]:
            pair[0].set(pair[1],invalid)
            if worker._continue_loading().get("continued",false) or client.start_requested:
                push_error("Unsafe connection state accepted: " + pair[1])
                host.free()
                return -1
            checks += 1
        pair[0].set(pair[1],false)
    for invalid in ["retry","quit","sanction",null,1]:
        host.server_connection_ui_controller.fatal_kind = invalid
        if worker._continue_loading().get("continued",false) or client.start_requested:
            push_error("Fatal kind accepted during loading")
            host.free()
            return -1
        checks += 1
    host.server_connection_ui_controller.fatal_kind = ""
    for invalid in [{"1":{}},null,[],false]:
        host.world_socket_gateway.pending_requests = invalid
        if worker._continue_loading().get("continued",false) or client.start_requested:
            push_error("Pending or invalid request collection accepted")
            host.free()
            return -1
        checks += 1
    host.world_socket_gateway.pending_requests = {}
    client.on_refresh = func(): client.exit_requested = true
    if worker._continue_loading().get("continued",false) or client.start_requested or client.refresh_calls != 1:
        push_error("Fresh native exit choice ignored")
        host.free()
        return -1
    checks += 1
    client.exit_requested = false
    client.on_refresh = func(): client.failed_closed = true
    if worker._continue_loading().get("continued",false) or client.start_requested:
        push_error("Fresh helper failure ignored")
        host.free()
        return -1
    checks += 1
    client.failed_closed = false
    var replacement = Client.new()
    client.on_refresh = func(): loading.process_client = replacement
    if worker._continue_loading().get("continued",false) or client.start_requested or replacement.start_requested:
        push_error("Replaced client accepted after refresh")
        host.free()
        return -1
    checks += 1
    loading.process_client = client
    var replacement_loading = Presenter.new()
    client.on_refresh = func(): host.bi_loading_presenter = replacement_loading
    if worker._continue_loading().get("continued",false) or client.start_requested or replacement_loading.process_client.start_requested:
        push_error("Replaced presenter accepted after refresh")
        host.free()
        return -1
    checks += 1
    host.bi_loading_presenter = loading
    client.on_refresh = Callable()
    var refreshed = client.refresh_calls
    var accepted = worker._continue_loading()
    if not accepted.get("continued",false) or not client.start_requested or loading.emissions or client.refresh_calls != refreshed+1:
        push_error("Native start was not accepted once through presenter state")
        host.free()
        return -1
    checks += 1
    if worker._continue_loading().get("continued",false) or client.refresh_calls != refreshed+1 or loading.emissions:
        push_error("Native start was repeated")
        host.free()
        return -1
    checks += 1
    var reloaded = Node.new()
    reloaded.set_script(worker.get_script())
    reloaded.host = host
    reloaded.control = {"auto_start":true}
    var repeated = reloaded._continue_loading()
    reloaded.host = null
    reloaded.free()
    if repeated.get("continued",false) or client.refresh_calls != refreshed+1 or loading.emissions:
        push_error("Worker reload repeated native start")
        host.free()
        return -1
    checks += 1
    client.on_refresh = Callable()
    worker.host = null
    host.free()
    return checks
