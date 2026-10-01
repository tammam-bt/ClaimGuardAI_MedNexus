"""R007 line arithmetic. Rule text: docs/04_Rulebook.md."""
import unittest,json,copy
from pathlib import Path
from claimguard._pack import config,load_jsonl,make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
ROOT=Path(__file__).resolve().parents[1]

class R007Tests(unittest.TestCase):
    """Clean base claim CG-27BFD8541DEB: L1 SVC-LAB 1 x 140 = 140, L2 SVC-CONSULT 1 x 190 = 190."""
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.rule=next(r for r in cls.cfg['rules'] if r['rule_id']=='R007');cls.book=PolicyBook(cls.cfg['policies'])
        cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text())[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example);self.l1,self.l2=self.c['lines']
    def evaluate(self,c):
        v=REGISTRY['R007'](RuleContext(c,self.rule,self.book.resolve(c['policy_id']),self.cfg['services'],{}))
        return make_result(c,self.rule,v.status,v.paths,v.message,list(v.line_ids))
    def result(self):return self.evaluate(self.c)
    def status(self):return self.result()['status']

    def test_pass(self):self.assertEqual(self.status(),'PASS')
    def test_tolerance_is_inclusive(self):
        self.l1['net_amount']=140.01;self.assertEqual(self.status(),'PASS')
        self.l1['net_amount']=140.02;r=self.result();self.assertEqual(r['status'],'FAIL');self.assertEqual(r['affected_line_ids'],['L1'])
    def test_rounds_exact_product_half_up(self):
        self.l1.update(quantity=3,unit_price=0.335,net_amount=1.00)  # exact product 1.005 -> 1.01 (HALF_UP)
        self.assertEqual(self.status(),'PASS')  # rounding factors first would give 3 x 0.34 = 1.02 -> FAIL
        self.l1['net_amount']=0.99
        self.assertEqual(self.status(),'FAIL')  # HALF_EVEN would give 1.00 -> diff 0.01 -> wrong PASS
    def test_missing_input_is_unknown(self):
        self.l1['unit_price']=None;r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['affected_line_ids'],[])
    def test_failure_dominates_missing(self):
        self.l1['unit_price']=None;self.l2['net_amount']=999;r=self.result()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['affected_line_ids'],['L2']);self.assertIn('unknown',r['explanation'])
    def test_invalid_quantities_are_arithmetic_only(self):
        self.l1.update(quantity=-1,net_amount=-140);self.l2.update(quantity=1.5,net_amount=285.0)
        self.assertEqual(self.status(),'PASS')  # R013 judges validity
    def test_non_finite_is_unknown(self):  # DEC-003: json.loads accepts NaN/Infinity
        for k in ('quantity','unit_price','net_amount'):
            for v in (float('nan'),float('inf'),float('-inf')):
                with self.subTest(field=k,value=v):
                    self.setUp();self.l1[k]=v;self.assertEqual(self.status(),'UNABLE_TO_ASSESS')
        self.l2['net_amount']=999;self.assertEqual(self.status(),'FAIL')  # another line still proves a failure
    def test_huge_values_are_exact_not_a_crash(self):  # DEC-012: decimal context beyond 28 digits
        self.l1.update(quantity=1e308,unit_price=10,net_amount=1e308);self.assertEqual(self.status(),'FAIL')
        self.l1.update(quantity=1e20,unit_price=1e20,net_amount=1e40);self.assertEqual(self.status(),'PASS')

    def test_matches_gold_on_all_public_splits(self):
        for split in ('development','validation','stress'):
            claims={c['claim_id']:c for c in load_jsonl(ROOT/'data'/split/'claims.jsonl')}
            for g in load_jsonl(ROOT/'data'/split/'expected_results.jsonl'):
                if g['rule_id']=='R007':
                    with self.subTest(split=split,claim=g['claim_id']):self.assertEqual(self.evaluate(claims[g['claim_id']]),g)
if __name__=='__main__':unittest.main()
