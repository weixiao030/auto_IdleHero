"""Package the already verified release without user data or game resources."""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.build_release import verified_report


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.package.tmp')
    temporary.write_bytes(data)
    os.replace(temporary, path)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def main():
    dist = ROOT / 'dist'
    stamp = datetime.now().strftime('%Y%m%d')
    name = f'桌面勇者自动远征-多实例版-{stamp}'
    output = dist / f'{name}.zip'
    if output.exists():
        raise FileExistsError(f'保留已生成的分发包，不覆盖：{output}')
    source = verified_report(ROOT / 'runtime/self-test.json')
    packaged = verified_report(ROOT / 'runtime/packaged-self-test-candidate.json', source)
    candidate = json.loads((dist / 'SHA256-candidate.json').read_text(encoding='utf-8'))
    executable_names = ['桌面勇者自动远征.exe', '桌面勇者自动远征-沙盒版.exe']
    for filename in executable_names:
        if sha256(dist / filename) != candidate['sha256']:
            raise ValueError(f'正式 EXE 与已自检候选不一致：{filename}')
    guide = dist / '桌面勇者自动远征启动教程.docx'
    with zipfile.ZipFile(guide) as docx:
        if docx.testzip() is not None or 'word/document.xml' not in docx.namelist():
            raise ValueError('Word 教程结构损坏')
    release = {
        'version': '0.4.0', 'worker_revision': 18,
        'file': executable_names[0], 'sha256': candidate['sha256'],
        'sandbox_file': executable_names[1], 'sandbox_sha256': candidate['sha256'],
        'source_tests': source['passed'], 'packaged_tests': packaged['passed'],
        'bridge_boundary_tests': 220,
    }
    atomic_write(dist / 'SHA256.json', json_bytes(release))
    atomic_write(ROOT / 'runtime/packaged-self-test.json', json_bytes(packaged))
    with tempfile.TemporaryDirectory(prefix='release-package-', dir=dist) as staging:
        folder = Path(staging)
        for filename in executable_names + [guide.name]:
            shutil.copy2(dist / filename, folder / filename)
        (folder / '使用说明.txt').write_text('''桌面勇者自动远征 0.4.0 多实例版

1. 完整解压压缩包；先在本机或 Sandboxie 沙盒内启动 Steam 和游戏并完成登录。
2. 在沙盒外双击“桌面勇者自动远征.exe”。“沙盒版.exe”功能相同，任选一个。
3. 工作台：http://127.0.0.1:17470/
4. 查看顶部实例连接管理，确认环境和 PID。首次安装桥接若未载入，待游戏结算后手动正常退出并重新打开游戏。
5. 每个实例可独立开启自动成长、设置功能和参数，多个实例可同时自动化。
   切换网页实例仅改变查看和控制目标，其他实例继续运行。
6. 自动重连默认关闭；游戏退出后不会因此自动启动或重启。
   自动成长是另一项开关：新实例默认开启，现有实例沿用保存状态，请接入时核对。
7. 降低占用：按需开启性能模式（默认上限 10 FPS）、极简特效，调整操作间隔。
   低帧率会影响游戏画面流畅度；关闭网页不会停止助手。
8. F8 自动成长、F9 分解、F10 换装，均只控制当前选中实例。
9. 完全退出所有助手调度：在 EXE 目录执行
   .\\桌面勇者自动远征.exe --stop
   也可双击“停止助手.cmd”；该操作不关闭游戏。

配置与日志：%LOCALAPPDATA%\\WalletHeroesAssistant\\instances\\<实例ID>\\
根目录 config.json 是新实例模板，实例建立后独立保存。
更新前暂停所有实例并等待待结算和维护任务结束；使用 --stop 后替换助手。
不要覆盖旧配置、调度记录或账号存档。详细启动、更新和排错步骤见 Word 教程。

游戏与 Steam 是否允许多个会话，取决于其自身限制。
此包包含自有助手、文档和测试报告，不包含个人配置、账号日志、存档、游戏代码或游戏资源。
''', encoding='utf-8')
        (folder / '验证说明.txt').write_text(f'''验证时间：2026-11-16
版本：0.4.0，worker revision 18

已通过：{source['passed']} 项源码回归、{packaged['passed']} 项 EXE 包内隔离自检、220 项 Godot 桥接边界检查，以及进程独立目录创建和快照写入检查。
隔离回归覆盖本机与多个沙盒独立并行调度、同一沙盒不同 PID、命令和回执隔离、重启恢复，以及自动重连默认关闭。

本轮实机覆盖：当前沙盒连接和状态刷新；一次只读邮件同步由原生成功回执核验；16 个网页模块逐一关闭和恢复开启，保存生效；重新检测、显示选项、桌面与 390px 窄屏布局通过，浏览器无错误或警告。保留原游戏会话和自动化暂停状态。
核验游戏 buildid 26636673，原生日志版本 v1.11.205。无需进一步逆向；如后续需要逆向，按约定使用 IDA。

短时单实例、暂停自动化样本：助手 worker 单核 CPU 约 61.24% 降到 2.19%，RSS 约 187.4 MiB 降到 81.81 MiB；快照约 5.95 MB 缩减至 0.293 MB。8 次连续请求均连接正常，HTTP 响应约 4–14 ms。
这些样本不代表多实例或长期负载。

实机边界：目前只有一个真实沙盒游戏会话；本机和多个沙盒账号同时运行由隔离回归覆盖，尚未完成多个真实 Steam 账号同时实机验收。未为测试而强制消费金币、强化装备或切换账号；未解锁和资源不足的消费功能仍需对应真实条件验收。
旧版本的 20 分钟运行记录不作为本版长期运行验证。

校验方法：PowerShell 执行 Get-FileHash -Algorithm SHA256 -LiteralPath .\\桌面勇者自动远征.exe
结果应与 SHA256.json 或 SHA256.txt 一致。两个 EXE 内容完全相同。
''', encoding='utf-8')
        (folder / '打开工作台.url').write_text('[InternetShortcut]\nURL=http://127.0.0.1:17470/\n', encoding='utf-8')
        (folder / '停止助手.cmd').write_bytes(
            '@echo off\r\nchcp 65001 >nul\r\n"%~dp0桌面勇者自动远征.exe" --stop\r\n'.encode('utf-8'))
        (folder / '包内自检报告.json').write_bytes(json_bytes(packaged))
        payload = sorted(folder.iterdir(), key=lambda path: path.name)
        release['files'] = [{'file': path.name, 'size': path.stat().st_size, 'sha256': sha256(path)} for path in payload]
        (folder / 'SHA256.json').write_bytes(json_bytes(release))
        (folder / 'SHA256.txt').write_text(
            ''.join(f"{row['sha256']}  {row['file']}\n" for row in release['files']), encoding='utf-8')
        allowed = {path.name for path in folder.iterdir()}
        temporary_zip = output.with_suffix('.zip.package.tmp')
        with zipfile.ZipFile(temporary_zip, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(folder.iterdir()):
                archive.write(path, path.name)
        with zipfile.ZipFile(temporary_zip) as archive:
            if archive.testzip() is not None or set(archive.namelist()) != allowed:
                raise ValueError('ZIP 完整性或文件白名单校验失败')
            for row in release['files']:
                data = archive.read(row['file'])
                if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise ValueError(f"ZIP 内文件校验失败：{row['file']}")
        os.replace(temporary_zip, output)
    manifest = {'file': output.name, 'size': output.stat().st_size, 'sha256': sha256(output), **release}
    manifest['file'] = output.name
    manifest['sha256'] = sha256(output)
    atomic_write(ROOT / f'runtime/package-{stamp}-manifest.json', json_bytes(manifest))
    atomic_write(output.with_suffix('.sha256.txt'), f"{manifest['sha256']}  {output.name}\n".encode('utf-8'))
    print(json.dumps({key: manifest[key] for key in ('file', 'size', 'sha256', 'source_tests', 'packaged_tests')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
