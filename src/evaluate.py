"""Strict one-record-per-claim-rule scorer; confidence and explanations require separate review."""
import argparse,json
from pathlib import Path
from collections import Counter
from engine_core import load_jsonl, pointer, STATUSES

def index(rows, claims=None):
    out={}
    required={'claim_id','rule_id','rule_version','status','severity','affected_line_ids','evidence','rule_source','explanation','corrective_action','confidence','confidence_kind','requires_human_review','method','review_status'}
    for r in rows:
        if set(r)!=required:raise ValueError('Result keys must match schemas/result.schema.json exactly')
        key=(r['claim_id'],r['rule_id'])
        if key in out:raise ValueError(f'Duplicate result: {key}')
        if r['status'] not in STATUSES:raise ValueError(f'Invalid status: {key}')
        if r['rule_id'] not in {f'R{i:03}' for i in range(1,16)}:raise ValueError(f'Unknown rule: {key}')
        if r['severity'] not in ('high','medium','low'):raise ValueError('Invalid severity')
        if r['rule_version']!='1.0.0' or r['rule_source']!=f'fictional-rulebook/{r["rule_id"]}@1.0.0':raise ValueError('Unknown rule version/source')
        if r['status']!='NOT_IMPLEMENTED' and not r['evidence']:raise ValueError(f'Evidence required: {key}')
        if r['status'] in ('FAIL','UNABLE_TO_ASSESS') and (not r['requires_human_review'] or not r['corrective_action']):raise ValueError('Flag/unknown requires review and corrective action')
        if r['confidence'] is not None and (isinstance(r['confidence'],bool) or not isinstance(r['confidence'],(float,int)) or not 0<=r['confidence']<=1):raise ValueError('Invalid confidence')
        if r['confidence_kind']=='not_probabilistic' and r['confidence'] is not None:raise ValueError('Deterministic confidence must be null')
        if r['confidence_kind'] not in ('not_probabilistic','uncalibrated','calibrated'):raise ValueError('Invalid confidence kind')
        if not isinstance(r['explanation'],str) or not r['explanation'].strip():raise ValueError('Explanation required')
        if claims is not None:
            if r['claim_id'] not in claims:raise ValueError('Unknown claim ID')
            c=claims[r['claim_id']]
            if not set(r['affected_line_ids'])<={x['line_id'] for x in c['lines']}:raise ValueError('Unknown line ID')
            for e in r['evidence']:
                if set(e)!={'path','value'} or not isinstance(e['path'],str) or not e['path'].startswith('/'):raise ValueError('Evidence needs a JSON pointer and value')
                if pointer(c,e['path'])!=e['value']:raise ValueError(f'Evidence value mismatch: {key} {e["path"]}')
        out[key]=r
    return out

def score(gold,pred,claims):
    g=index(gold,claims);p=index(pred,claims)
    if set(g)!=set(p):raise ValueError(f'Prediction coverage mismatch: {len(set(g)-set(p))} missing pairs; {len(set(p)-set(g))} extra pairs. Return all 15 rules for each input claim.')
    expected={(cid,f'R{i:03}') for cid in claims for i in range(1,16)}
    if set(g)!=expected:raise ValueError('Gold coverage is not all 15 rules for every claim')
    def metrics(keys):
        tp=sum(g[k]['status']=='FAIL' and p[k]['status']=='FAIL' for k in keys)
        fp=sum(g[k]['status']!='FAIL' and p[k]['status']=='FAIL' for k in keys)
        fn=sum(g[k]['status']=='FAIL' and p[k]['status']!='FAIL' for k in keys)
        tn=len(keys)-tp-fp-fn
        prec=tp/(tp+fp) if tp+fp else None;rec=tp/(tp+fn) if tp+fn else None
        return {'count':len(keys),'tp':tp,'fp':fp,'fn':fn,'tn':tn,'issue_precision':prec,'issue_recall':rec,'issue_f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,'false_alarm_rate':fp/(fp+tn) if fp+tn else None,'status_accuracy':sum(g[k]['status']==p[k]['status'] for k in keys)/len(keys),'not_implemented':sum(p[k]['status']=='NOT_IMPLEMENTED' for k in keys),'false_abstentions':sum(p[k]['status']=='UNABLE_TO_ASSESS' and g[k]['status']!='UNABLE_TO_ASSESS' for k in keys),'missed_abstentions':sum(g[k]['status']=='UNABLE_TO_ASSESS' and p[k]['status']!='UNABLE_TO_ASSESS' for k in keys)}
    confusion=Counter((g[k]['status'],p[k]['status']) for k in g)
    return {'overall':metrics(list(g)),'by_rule':{r:metrics([k for k in g if k[1]==r]) for r in sorted({k[1] for k in g})},'confusion':[{'expected':a,'predicted':b,'count':n} for (a,b),n in sorted(confusion.items())],'claims_with_all_statuses_correct':sum(all(g[(cid,f'R{i:03}')]['status']==p[(cid,f'R{i:03}')]['status'] for i in range(1,16)) for cid in claims),'note':'Synthetic teaching benchmark only. Evidence pointers/values are checked, but semantic relevance and explanation correctness need human review. NOT_IMPLEMENTED counts as incorrect.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gold',required=True);p.add_argument('--pred',required=True);p.add_argument('--claims',required=True);p.add_argument('--output',default='outputs/metrics.json');a=p.parse_args()
    try:
        rows=load_jsonl(a.claims);claims={c['claim_id']:c for c in rows}
        if len(rows)!=len(claims):raise ValueError('Duplicate claim IDs')
        report=score(load_jsonl(a.gold),load_jsonl(a.pred),claims)
    except (ValueError,KeyError,TypeError,IndexError) as e:p.exit(2,f'Evaluation rejected: {e}\n')
    out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report['overall'],indent=2));print('Report:',out)
if __name__=='__main__':main()
