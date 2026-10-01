"""R008 required authorization reference. Rule text: docs/04_Rulebook.md. Shared predicate and unknown service: DEC-007."""
import unittest,json,copy
from pathlib import Path
from claimguard._pack import config,load_jsonl,make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
ROOT=Path(__file__).resolve().parents[1]
MISSING='Required authorization ID missing'
UNKNOWN='Unknown service prevents authorization requirement lookup'

class R008Tests(unittest.TestCase):
    """Base claim CG-27BFD8541DEB (EDU-PLUS): L1 SVC-LAB, L2 SVC-CONSULT, no authorization IDs.
    Neither service needs authorization, so the base claim is NOT_APPLICABLE; tests switch lines to SVC-IMAGE / SVC-THERAPY."""
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.rule=next(r for r in cls.cfg['rules'] if r['rule_id']=='R008');cls.book=PolicyBook(cls.cfg['policies'])
        cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text(encoding='utf-8'))[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example);self.l1,self.l2=self.c['lines']
    def evaluate(self,c):
        v=REGISTRY['R008'](RuleContext(c,self.rule,self.book.resolve(c['policy_id']),self.cfg['services'],{}))
        return make_result(c,self.rule,v.status,v.paths,v.message,list(v.line_ids))
    def result(self):return self.evaluate(self.c)
    def status(self):return self.result()['status']

    def test_no_required_service_is_not_applicable(self):
        r=self.result();self.assertEqual(r['status'],'NOT_APPLICABLE');self.assertEqual(r['explanation'],'Rule does not apply to the supplied claim.')
        self.assertEqual([e['path'] for e in r['evidence']],['/lines/0/service_code','/lines/0/authorization_id','/lines/1/service_code','/lines/1/authorization_id'])
    def test_reference_present_passes(self):
        for code in ('SVC-IMAGE','SVC-THERAPY'):
            with self.subTest(code=code):
                self.l1.update(service_code=code,authorization_id='AUTH-X-1');self.assertEqual(self.status(),'PASS')
    def test_only_presence_is_checked(self):
        self.l1.update(service_code='SVC-IMAGE',authorization_id='AUTH-NOT-IN-THE-LIST')
        self.assertEqual(self.status(),'PASS')  # resolving the record is R009's job
    def test_empty_reference_fails(self):
        for ref in (None,'','   '):
            with self.subTest(ref=ref):
                self.l1.update(service_code='SVC-IMAGE',authorization_id=ref);r=self.result()
                self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],MISSING);self.assertEqual(r['affected_line_ids'],['L1'])
    def test_every_missing_line_is_reported_in_claim_order(self):
        self.l1['service_code']='SVC-THERAPY';self.l2['service_code']='SVC-IMAGE'
        self.assertEqual(self.result()['affected_line_ids'],['L1','L2'])
    def test_one_good_line_does_not_hide_a_missing_one(self):
        self.l1.update(service_code='SVC-IMAGE',authorization_id='AUTH-X-1');self.l2['service_code']='SVC-THERAPY'
        self.assertEqual(self.result()['affected_line_ids'],['L2'])
    def test_unknown_service_is_unknown(self):  # DEC-007
        for code in ('SVC-UNLISTED',None,'svc-image'):  # case-sensitive: svc-image is not SVC-IMAGE
            with self.subTest(code=code):
                self.l1['service_code']=code;r=self.result()
                self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],UNKNOWN)
    def test_unknown_service_with_a_passing_required_line_is_unknown(self):
        self.l1['service_code']='SVC-UNLISTED';self.l2.update(service_code='SVC-IMAGE',authorization_id='AUTH-X-1')
        self.assertEqual(self.status(),'UNABLE_TO_ASSESS')
    def test_failure_dominates_unknown_service(self):
        self.l1['service_code']='SVC-UNLISTED';self.l2['service_code']='SVC-IMAGE';r=self.result()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['affected_line_ids'],['L2'])
        self.assertEqual(r['explanation'],MISSING+'; Additional unknown inputs: '+UNKNOWN)
    def test_no_policy_cites_only_policy_id(self):
        self.c['policy_id']='EDU-NO-POLICY';self.l1['service_code']='SVC-IMAGE'  # even an empty reference proves nothing without the policy
        r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'No policy is supplied for this policy_id.')
        self.assertEqual([e['path'] for e in r['evidence']],['/policy_id'])

    def test_matches_gold_on_all_public_splits(self):
        for split in ('development','validation','stress'):
            claims={c['claim_id']:c for c in load_jsonl(ROOT/'data'/split/'claims.jsonl')}
            for g in load_jsonl(ROOT/'data'/split/'expected_results.jsonl'):
                if g['rule_id']=='R008':
                    with self.subTest(split=split,claim=g['claim_id']):self.assertEqual(self.evaluate(claims[g['claim_id']]),g)
if __name__=='__main__':unittest.main()
