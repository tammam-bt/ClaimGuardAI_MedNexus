"""R014 submission window. Rule text: docs/04_Rulebook.md. Undecided combinations: DEC-009."""
import unittest,json,copy
from pathlib import Path
from claimguard._pack import config,load_jsonl,make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
ROOT=Path(__file__).resolve().parents[1]

class R014Tests(unittest.TestCase):
    """Clean base claim CG-27BFD8541DEB (EDU-PLUS, 60 days): both lines served 2026-05-25, submitted 2026-06-06 (lag 12)."""
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.rule=next(r for r in cls.cfg['rules'] if r['rule_id']=='R014');cls.book=PolicyBook(cls.cfg['policies'])
        cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text(encoding='utf-8'))[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example);self.l1,self.l2=self.c['lines']
    def evaluate(self,c):
        v=REGISTRY['R014'](RuleContext(c,self.rule,self.book.resolve(c['policy_id']),self.cfg['services'],{}))
        return make_result(c,self.rule,v.status,v.paths,v.message,list(v.line_ids))
    def result(self):return self.evaluate(self.c)
    def status(self):return self.result()['status']

    def test_pass(self):
        r=self.result();self.assertEqual(r['status'],'PASS')
        self.assertEqual([e['path'] for e in r['evidence']],['/submission_date','/policy_id','/lines/0/service_date','/lines/1/service_date'])
    def test_window_is_inclusive_plus(self):
        self.c['submission_date']='2026-07-24';self.assertEqual(self.status(),'PASS')  # lag 60 = EDU-PLUS window
        self.c['submission_date']='2026-07-25';r=self.result()  # lag 61
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],'Submission exceeds fictional window')
        self.assertEqual(r['affected_line_ids'],[])  # claim-level defect, as in all gold failures
    def test_window_is_inclusive_basic(self):
        self.c['policy_id']='EDU-BASIC'
        self.c['submission_date']='2026-06-24';self.assertEqual(self.status(),'PASS')  # lag 30
        self.c['submission_date']='2026-06-25';self.assertEqual(self.status(),'FAIL')  # lag 31
    def test_lag_counts_from_the_latest_service_date(self):
        self.l1['service_date']='2026-01-01';self.assertEqual(self.status(),'PASS')  # L1 alone would be 156 days late
    def test_same_day_submission_passes(self):
        self.c['submission_date']='2026-05-25';self.assertEqual(self.status(),'PASS')  # lag 0 is not negative
    def test_negative_lag_is_not_applicable(self):
        self.c['submission_date']='2026-05-24';r=self.result()  # R002's problem, not R014's
        self.assertEqual(r['status'],'NOT_APPLICABLE');self.assertEqual(r['explanation'],'Rule does not apply to the supplied claim.')
    def test_missing_date_is_unknown(self):
        self.l2['service_date']=None;r=self.result()
        self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Date missing')
        self.assertEqual(len(r['evidence']),4)  # still cites every date, including the null one
    def test_missing_date_never_proves_a_failure(self):  # DEC-009 (3)
        self.l1['service_date']='2026-01-01';self.l2['service_date']=None  # the known date is 156 days late...
        self.assertEqual(self.status(),'UNABLE_TO_ASSESS')  # ...but L2 may be the latest
    def test_no_policy_cites_only_policy_id(self):
        self.c['policy_id']='EDU-NO-POLICY';r=self.result()
        self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'No policy is supplied for this policy_id.')
        self.assertEqual([e['path'] for e in r['evidence']],['/policy_id'])
    def test_no_policy_wins_over_negative_lag_and_missing_date(self):  # DEC-009 (1) and (2)
        self.c['policy_id']='EDU-NO-POLICY'
        self.c['submission_date']='2026-05-24';self.assertEqual(self.result()['explanation'],'No policy is supplied for this policy_id.')
        self.c['submission_date']='2026-06-06';self.l2['service_date']=None
        self.assertEqual(self.result()['explanation'],'No policy is supplied for this policy_id.')

    def test_matches_gold_on_all_public_splits(self):
        for split in ('development','validation','stress'):
            claims={c['claim_id']:c for c in load_jsonl(ROOT/'data'/split/'claims.jsonl')}
            for g in load_jsonl(ROOT/'data'/split/'expected_results.jsonl'):
                if g['rule_id']=='R014':
                    with self.subTest(split=split,claim=g['claim_id']):self.assertEqual(self.evaluate(claims[g['claim_id']]),g)
if __name__=='__main__':unittest.main()
