"""R013 quantity and price limits. Rule text: docs/04_Rulebook.md."""
import unittest,json,copy
from pathlib import Path
from claimguard._pack import config,load_jsonl,make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
ROOT=Path(__file__).resolve().parents[1]

class R013Tests(unittest.TestCase):
    """Clean base claim CG-27BFD8541DEB (EDU-PLUS): L1 SVC-LAB 1 x 140 (max 260/3), L2 SVC-CONSULT 1 x 190 (max 350/1)."""
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.rule=next(r for r in cls.cfg['rules'] if r['rule_id']=='R013');cls.book=PolicyBook(cls.cfg['policies'])
        cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text())[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example);self.l1,self.l2=self.c['lines']
    def evaluate(self,c):
        v=REGISTRY['R013'](RuleContext(c,self.rule,self.book.resolve(c['policy_id']),self.cfg['services'],{}))
        return make_result(c,self.rule,v.status,v.paths,v.message,list(v.line_ids))
    def result(self):return self.evaluate(self.c)
    def status(self):return self.result()['status']

    def test_pass(self):self.assertEqual(self.status(),'PASS')
    def test_limits_inclusive(self):
        self.l1.update(quantity=3,unit_price=260);self.assertEqual(self.status(),'PASS')
        self.l1['unit_price']=260.01;r=self.result();self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],'Price exceeds fictional maximum')
        self.l1.update(unit_price=260,quantity=4);self.assertEqual(self.result()['explanation'],'Quantity exceeds fictional maximum')
    def test_positive_integer(self):
        self.l1['quantity']=-1;r=self.result();self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],'Quantity must be a positive integer')
        self.l1['quantity']=0;self.assertEqual(self.status(),'FAIL')
        self.l1['quantity']=True;self.assertEqual(self.status(),'FAIL')  # DEC-002
        self.l1['quantity']=2.0;self.assertEqual(self.status(),'PASS')  # DEC-001
    def test_fraction_over_max_reports_both(self):
        self.l2['quantity']=1.5;r=self.result()  # CONSULT max 1
        self.assertEqual(r['explanation'],'Quantity exceeds fictional maximum; Quantity must be a positive integer');self.assertEqual(r['affected_line_ids'],['L2'])
    def test_zero_price_fails(self):self.l1['unit_price']=0;self.assertEqual(self.status(),'FAIL')
    def test_missing_price_unknown(self):
        self.l1['unit_price']=None;r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Quantity or price missing')
    def test_unknown_service(self):
        self.l1['service_code']='SVC-UNLISTED';r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Unknown service limits')
        self.l2['unit_price']=400;self.assertEqual(self.status(),'FAIL')  # another line proves a violation
    def test_unknown_policy(self):
        self.c['policy_id']='EDU-NO-POLICY';r=self.result()
        self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual([e['path'] for e in r['evidence']],['/policy_id'])
        self.l1['unit_price']=9999;self.assertEqual(self.status(),'UNABLE_TO_ASSESS')  # max price needs the policy
        self.l1['quantity']=-1;self.assertEqual(self.status(),'FAIL')  # proven without the policy
    def test_non_finite_is_unknown(self):  # DEC-003: json.loads accepts NaN/Infinity
        for k in ('quantity','unit_price'):
            for v in (float('nan'),float('inf'),float('-inf')):
                with self.subTest(field=k,value=v):
                    self.setUp();self.l1[k]=v;r=self.result()
                    self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Quantity or price missing')
        self.l2['unit_price']=400;self.assertEqual(self.status(),'FAIL')  # another line still proves a violation

    def test_matches_gold_on_all_public_splits(self):
        for split in ('development','validation','stress'):
            claims={c['claim_id']:c for c in load_jsonl(ROOT/'data'/split/'claims.jsonl')}
            for g in load_jsonl(ROOT/'data'/split/'expected_results.jsonl'):
                if g['rule_id']=='R013':
                    with self.subTest(split=split,claim=g['claim_id']):self.assertEqual(self.evaluate(claims[g['claim_id']]),g)
if __name__=='__main__':unittest.main()
