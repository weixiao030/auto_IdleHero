"""Compact method retrieval from external analysis files. Never distributes game code."""
from pathlib import Path
import argparse,json

ANALYSIS=Path.home()/'DesktopWalletHeroes-analysis'
ROOT=ANALYSIS/'recovered/scripts'

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('query')
    parser.add_argument('--source',action='store_true')
    parser.add_argument('--limit',type=int,default=30)
    args=parser.parse_args()
    index=json.loads((ANALYSIS/'method-index.json').read_text(encoding='utf8'))
    hits=0
    for relative,methods in index.items():
        selected=[x for x in methods if args.query.casefold() in (relative+' '+x['signature']).casefold()]
        if not selected: continue
        lines=None
        for method in selected:
            if hits>=args.limit: break
            print(relative+':'+str(method['line'])+' '+method['signature'])
            if args.source:
                if lines is None: lines=(ROOT/relative).read_text(encoding='utf8').splitlines()
                start=method['line']
                end=next((x['line']-1 for x in methods if x['line']>start),len(lines))
                print('\n'.join(lines[start:end])[:12000])
            hits+=1
        if hits>=args.limit: break
