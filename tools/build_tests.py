"""Offline release-report validation; no executable or account is started."""
from pathlib import Path
import json
import tempfile

def run(check):
    from tools.build_release import verified_report
    valid = {'passed':1,'tests':[{'name':'fixture','passed':True}]}
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/'report.json'
        path.write_text(json.dumps(valid),encoding='utf8')
        check('发布报告完整成功才通过',verified_report(path)==valid)
        variants = [[],{}, {'passed':0,'tests':[]}, {'passed':2,'tests':valid['tests']},
            {'passed':True,'tests':valid['tests']}, {'passed':1,'tests':[{'name':'fixture','passed':1}]},
            {'passed':1,'tests':[{'name':'fixture','passed':False}]},
            {'passed':1,'tests':[{'name':'','passed':True}]}, {'passed':1,'tests':['invalid']}]
        for index, value in enumerate(variants):
            path.write_text(json.dumps(value),encoding='utf8')
            try:
                verified_report(path)
            except ValueError:
                check('发布拒绝不完整或失败报告：'+str(index), True)
            else:
                check('发布拒绝不完整或失败报告：'+str(index), False)
        changed={'passed':1,'tests':[{'name':'omitted real case','passed':True}]}
        path.write_text(json.dumps(changed),encoding='utf8')
        try:
            verified_report(path, valid)
        except ValueError:
            check('包内自检遗漏或换用场景时禁止发布摘要', True)
        else:
            check('包内自检遗漏或换用场景时禁止发布摘要', False)
