"""Run the three implemented checks. Extend engine_core.baseline for your MVP."""
import argparse, json
from pathlib import Path
from engine_core import config, load_jsonl, baseline, validate_transport

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',default='data/development/claims.jsonl');p.add_argument('--output',default='outputs/predictions.jsonl');p.add_argument('--limit',type=int)
    a=p.parse_args();cfg=config(Path(__file__).resolve().parents[1]);claims=load_jsonl(a.input)
    if a.limit is not None:claims=claims[:a.limit]
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8') as f:
        for c in claims:
            validate_transport(c)
            for result in baseline(c,cfg):f.write(json.dumps(result,ensure_ascii=False)+'\n')
    print(f'Processed {len(claims)} claims. Implemented: R001, R003, R006. Other rules: NOT_IMPLEMENTED. Output: {out}')
if __name__=='__main__':main()
