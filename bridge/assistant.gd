extends Node

const REVISION = 2
var data_dir: String
var worker: Node
var worker_stamp: int = -1
var elapsed: float = 0.0

func _ready() -> void:
	if OS.get_cmdline_user_args().has("--bi-loading-helper"):
		set_process(false)
		return
	data_dir = OS.get_environment("LOCALAPPDATA").path_join("WalletHeroesAssistant/runtime")
	DirAccess.make_dir_recursive_absolute(data_dir.path_join("commands"))
	DirAccess.make_dir_recursive_absolute(data_dir.path_join("results"))
	print("[WalletHeroesAssistant] loader revision ", REVISION)
	_reload()

func _process(delta: float) -> void:
	elapsed += delta
	if elapsed >= 2.0:
		elapsed = 0.0
		_reload()

func _reload() -> void:
	var path = get_script().resource_path.get_base_dir().path_join("worker.gd")
	var stamp = FileAccess.get_modified_time(path)
	if stamp == worker_stamp:
		return
	var source = FileAccess.get_file_as_string(path)
	if source.is_empty():
		return
	var script = GDScript.new()
	script.source_code = source
	if script.reload() != OK:
		push_error("[WalletHeroesAssistant] worker parse failed; keeping previous worker")
		return
	if is_instance_valid(worker):
		worker.queue_free()
	worker = Node.new()
	worker.set_script(script)
	add_child(worker)
	worker.call("setup", data_dir)
	worker_stamp = stamp
	print("[WalletHeroesAssistant] worker loaded ", stamp)
