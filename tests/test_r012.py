"""R012 claim total equals line amounts. Rule text: docs/04_Rulebook.md."""
import unittest,json,copy
from pathlib import Path
from claimguard._pack import config,load_jsonl,make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
ROOT=Path(__file__).resolve().parents[1]

class R012Tests(unittest.TestCase):
    """Clean base claim CG-27BFD8541DEB: lines 140 + 190, total_amount 330."""
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.rule=next(r for r in cls.cfg['rules'] if r['rule_id']=='R012');cls.book=PolicyBook(cls.cfg['policies'])
        cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text())[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example);self.l1,self.l2=self.c['lines']
    def evaluate(self,c):
        v=REGISTRY['R012'](RuleContext(c,self.rule,self.book.resolve(c['policy_id']),self.cfg['services'],{}))
        return make_result(c,self.rule,v.status,v.paths,v.message,list(v.line_ids))
    def result(self):return self.evaluate(self.c)
    def status(self):return self.result()['status']

    # docs/08 Lab 2: exact equality, a difference of 0.01, a difference of 0.02, and a missing amount
    def test_exact(self):self.assertEqual(self.status(),'PASS')
    def test_difference_001_passes(self):self.c['total_amount']=330.01;self.assertEqual(self.status(),'PASS')
    def test_difference_002_fails(self):
        self.c['total_amount']=330.02;r=self.result();self.assertEqual(r['status'],'FAIL');self.assertEqual(r['affected_line_ids'],[])
    def test_missing_amount(self):
        self.c['total_amount']=None;self.assertEqual(self.status(),'UNABLE_TO_ASSESS')
        self.c['total_amount']=330;self.l2['net_amount']=None;self.assertEqual(self.status(),'UNABLE_TO_ASSESS')
    def test_uses_submitted_amounts_not_recomputed(self):
        self.l1['net_amount']=150;self.c['total_amount']=340  # 1 x 140 != 150 is R007's problem, not R012's
        self.assertEqual(self.status(),'PASS')
    def test_non_finite_is_unknown(self):  # DEC-003: json.loads accepts NaN/Infinity
        for v in (float('nan'),float('inf'),float('-inf')):
            with self.subTest(value=v):
                self.setUp();self.c['total_amount']=v;self.assertEqual(self.status(),'UNABLE_TO_ASSESS')
                self.setUp();self.l1['net_amount']=v;self.assertEqual(self.status(),'UNABLE_TO_ASSESS')
    def test_huge_values_are_exact_not_rounded(self):  # DEC-012
        self.l1['net_amount']=1e308;self.c['total_amount']=1e308  # lines sum to 1e308 + 190: 28-digit rounding would hide the 190
        self.assertEqual(self.status(),'FAIL')

    def test_matches_gold_on_all_public_splits(self):
        for split in ('development','validation','stress'):
            claims={c['claim_id']:c for c in load_jsonl(ROOT/'data'/split/'claims.jsonl')}
            for g in load_jsonl(ROOT/'data'/split/'expected_results.jsonl'):
                if g['rule_id']=='R012':
                    with self.subTest(split=split,claim=g['claim_id']):self.assertEqual(self.evaluate(claims[g['claim_id']]),g)
if __name__=='__main__':unittest.main()
