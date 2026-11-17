"""Build an own-code-only single-file Windows release."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parent.parent

def verified_report(path, expected=None):
    report = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(report, dict): raise ValueError('Self-test report must be an object')
    rows = report.get('tests')
    if (not isinstance(rows, list) or not rows or type(report.get('passed')) is not int
            or report['passed'] != len(rows)
            or any(not isinstance(row, dict) or row.get('passed') is not True
                   or not isinstance(row.get('name'), str) or not row['name'] for row in rows)):
        raise ValueError('Self-test report is incomplete or contains failures')
    if expected is not None and rows != expected['tests']:
        raise ValueError('Packaged test coverage does not match the source report')
    return report

def atomic_json(path, value):
    temporary = path.with_name(path.name+'.build.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')
    os.replace(temporary,path)
def main():
    parser = argparse.ArgumentParser(description='Build the single-file Windows release.')
    parser.add_argument('--candidate', action='store_true', help='Write a side-by-side candidate without replacing the live EXE.')
    parser.add_argument('--output-name', default='', help='Override the executable base name.')
    args = parser.parse_args()
    output_name = args.output_name or ('桌面勇者自动远征-候选' if args.candidate else '桌面勇者自动远征')
    subprocess.run([sys.executable,'-X','utf8','tools/self_test.py'],cwd=ROOT,check=True)
    subprocess.run([sys.executable,'-X','utf8','tools/validate_bridge.py'],cwd=ROOT,check=True)
    subprocess.run(['npm.cmd','run','build'],cwd=ROOT/'web',check=True)
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed',
        '--name',output_name,'--add-data','web/dist;web/dist','--add-data','bridge;bridge',
        '--hidden-import','tools.self_test','desktop_entry.py'],cwd=ROOT,check=True)
    exe=ROOT/'dist'/f'{output_name}.exe'
    source_report = verified_report(ROOT/'runtime/self-test.json')
    # A successful PyInstaller process alone is not a verified release. Use a
    # unique report and isolated account data, and publish the digest only after
    # the packaged executable passes exactly the same regression scenarios.
    with tempfile.TemporaryDirectory(prefix='package-self-test-') as temporary:
        report_path = Path(temporary)/'report.json'
        subprocess.run([str(exe),'--self-test',str(report_path)],cwd=ROOT,check=True,timeout=120,
            env={**os.environ,'WALLET_ASSISTANT_DATA':str(Path(temporary)/'account')},
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        packaged = verified_report(report_path, source_report)
    report_name = 'packaged-self-test-candidate.json' if args.candidate else 'packaged-self-test.json'
    atomic_json(ROOT/'runtime'/report_name, packaged)
    digest = {'file':exe.name,'sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),
              'source_tests':source_report['passed'],'packaged_tests':packaged['passed']}
    hash_name = 'SHA256-candidate.json' if args.candidate else 'SHA256.json'
    atomic_json(ROOT/'dist'/hash_name, digest)
    print(json.dumps(digest,ensure_ascii=False))
if __name__=='__main__':main()
