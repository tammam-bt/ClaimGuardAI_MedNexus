"""R009 authorization record matches service. Rule text: docs/04_Rulebook.md.
Wordings the gold never shows: DEC-005. Aggregation: DEC-006. Dependency on R008: DEC-007."""
import unittest,json,copy
from pathlib import Path
from claimguard._pack import config,load_jsonl,make_result
from claimguard.engine.context import RuleContext
from claimguard.engine.policy import PolicyBook
from claimguard.engine.registry import REGISTRY
import claimguard.rules  # noqa: F401  registers every rule module
ROOT=Path(__file__).resolve().parents[1]
NO_ID='Cannot inspect authorization without an ID'
UNKNOWN='Unknown service prevents authorization requirement lookup'
AGGREGATE='Aggregate quantity exceeds authorization'

class R009Tests(unittest.TestCase):
    """Base claim CG-27BFD8541DEB (EDU-PLUS): L1 SVC-LAB, L2 SVC-CONSULT, both 2026-05-25, quantity 1, no authorizations.
    Neither service needs authorization (NOT_APPLICABLE). therapy() turns L1 into SVC-THERAPY under AUTH-T-1:
    approved, same patient, valid 2026-05-20..2026-05-30, max_quantity 4."""
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.rules={r['rule_id']:r for r in cls.cfg['rules']};cls.book=PolicyBook(cls.cfg['policies'])
        cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text(encoding='utf-8'))[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example);self.l1,self.l2=self.c['lines']
    def evaluate(self,c,rid='R009'):
        rule=self.rules[rid];v=REGISTRY[rid](RuleContext(c,rule,self.book.resolve(c['policy_id']),self.cfg['services'],{}))
        return make_result(c,rule,v.status,v.paths,v.message,list(v.line_ids))
    def result(self):return self.evaluate(self.c)
    def status(self):return self.result()['status']
    def therapy(self,line=None,auth='AUTH-T-1',**record):
        (line or self.l1).update(service_code='SVC-THERAPY',authorization_id=auth)
        if not any(a['authorization_id']==auth for a in self.c['authorizations']):
            self.c['authorizations'].append({'authorization_id':auth,'patient_id':self.c['patient_id'],'service_code':'SVC-THERAPY',
                                             'status':'approved','valid_from':'2026-05-20','valid_to':'2026-05-30','max_quantity':4,**record})
        return self.c['authorizations'][-1]

    def test_no_required_service_is_not_applicable(self):
        r=self.result();self.assertEqual(r['status'],'NOT_APPLICABLE')
        self.assertEqual([e['path'] for e in r['evidence']],['/lines/0/service_code','/lines/0/authorization_id','/lines/1/service_code','/lines/1/authorization_id'])
    def test_matching_record_passes(self):
        self.therapy();r=self.result();self.assertEqual(r['status'],'PASS')
        self.assertEqual([e['path'] for e in r['evidence']],['/lines/0/service_code','/lines/0/authorization_id','/authorizations/0',
                                                             '/lines/0/service_date','/lines','/lines/1/service_code','/lines/1/authorization_id'])

    # R008 -> R009 (DEC-007)
    def test_missing_reference_cascades_to_unknown(self):
        self.therapy(auth=None);self.c['authorizations']=[];r=self.result()
        self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],NO_ID);self.assertEqual(r['affected_line_ids'],[])
        self.assertEqual(self.evaluate(self.c,'R008')['status'],'FAIL')  # R008 owns this defect; R009 must not fail it again
    def test_cascade_is_per_line(self):
        self.therapy(auth=None);self.c['authorizations']=[];self.therapy(line=self.l2,auth='AUTH-T-2',status='denied');r=self.result()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['affected_line_ids'],['L2'])
        self.assertEqual(r['explanation'],'Authorization status mismatch; Additional unknown inputs: '+NO_ID)
    def test_unknown_service_is_unknown(self):
        self.l1['service_code']='SVC-UNLISTED';r=self.result()
        self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],UNKNOWN)

    # Resolution and the four matches (DEC-005 for wordings the gold never shows)
    def test_record_absent_from_the_complete_list_fails(self):
        self.therapy();self.l1['authorization_id']='AUTH-NOT-SUPPLIED';r=self.result()
        self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],'Authorization record not found');self.assertEqual(r['affected_line_ids'],['L1'])
    def test_reference_is_case_sensitive(self):
        self.therapy();self.l1['authorization_id']='auth-t-1';self.assertEqual(self.result()['explanation'],'Authorization record not found')
    def test_patient_mismatch_fails(self):
        self.therapy(patient_id='PAT-SOMEONE-ELSE');r=self.result()
        self.assertEqual(r['explanation'],'Authorization patient mismatch')
        self.assertIn('/authorizations/0/patient_id',[e['path'] for e in r['evidence']])
    def test_service_mismatch_fails(self):
        self.therapy(service_code='SVC-IMAGE');self.assertEqual(self.result()['explanation'],'Authorization service mismatch')
    def test_status_must_be_exactly_approved(self):
        for status in ('denied','Approved','pending'):
            with self.subTest(status=status):
                self.setUp();self.therapy(status=status);r=self.result()
                self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],'Authorization status mismatch')
                self.assertIn('/authorizations/0/status',[e['path'] for e in r['evidence']])
    def test_validity_dates_are_inclusive(self):
        for valid_from,valid_to,expected in (('2026-05-25','2026-05-30','PASS'),('2026-05-20','2026-05-25','PASS'),
                                             ('2026-05-26','2026-05-30','FAIL'),('2026-05-20','2026-05-24','FAIL')):
            with self.subTest(valid_from=valid_from,valid_to=valid_to):
                self.setUp();self.therapy(valid_from=valid_from,valid_to=valid_to);self.assertEqual(self.status(),expected)
        self.assertEqual(self.result()['explanation'],'Service date outside authorization validity')
    def test_missing_date_is_unknown(self):
        for where in ('line','valid_from','valid_to'):
            with self.subTest(missing=where):
                self.setUp();a=self.therapy()
                if where=='line':self.l1['service_date']=None
                else:a[where]=None
                r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Authorization date input missing')
    def test_null_record_field_is_unknown(self):
        for field in ('patient_id','service_code','status'):
            with self.subTest(field=field):
                self.setUp();self.therapy(**{field:None});self.assertEqual(self.result()['explanation'],'Authorization input missing')
    def test_duplicate_records_are_ambiguous(self):
        self.therapy();self.c['authorizations'].append(dict(self.c['authorizations'][0],status='denied'))
        r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Authorization record ambiguous')

    # Aggregate quantity (DEC-006)
    def test_single_line_over_the_maximum_fails(self):
        self.therapy();self.l1['quantity']=5;r=self.result();self.assertEqual(r['explanation'],AGGREGATE);self.assertEqual(r['affected_line_ids'],['L1'])
    def test_quantity_is_summed_across_lines_sharing_the_authorization(self):
        self.therapy();self.therapy(line=self.l2);self.l1['quantity']=2;self.l2['quantity']=3  # each within 4, together 5
        r=self.result();self.assertEqual(r['status'],'FAIL');self.assertEqual(r['explanation'],AGGREGATE);self.assertEqual(r['affected_line_ids'],['L1','L2'])
    def test_sum_equal_to_the_maximum_passes_and_is_not_double_counted(self):
        self.therapy();self.therapy(line=self.l2);self.l1['quantity']=2;self.l2['quantity']=2  # counting per line would give 8
        self.assertEqual(self.status(),'PASS')
    def test_a_non_required_line_sharing_the_reference_counts(self):
        self.therapy();self.l1['quantity']=3;self.l2.update(authorization_id='AUTH-T-1',quantity=2)  # L2 stays SVC-CONSULT
        self.assertEqual(self.result()['affected_line_ids'],['L1','L2'])
    def test_separate_authorizations_are_summed_separately(self):
        self.therapy();self.therapy(line=self.l2,auth='AUTH-T-2');self.l1['quantity']=4;self.l2['quantity']=4
        self.assertEqual(self.status(),'PASS')
    def test_missing_quantity_makes_the_aggregate_unknown(self):
        for q in (None,float('nan')):
            with self.subTest(quantity=q):
                self.setUp();self.therapy();self.therapy(line=self.l2);self.l2['quantity']=q
                r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Authorization quantity input missing')

    # Hostile inputs the transport check lets through (DEC-012)
    def test_huge_quantity_is_a_real_excess_not_a_crash(self):
        self.therapy();self.l1['quantity']=1e308;self.assertEqual(self.result()['explanation'],AGGREGATE)
    def test_sum_is_exact_so_rounding_cannot_hide_an_excess(self):
        self.therapy();self.therapy(line=self.l2);self.c['lines'].append(dict(self.l2,line_id='L3'))
        for line,q in zip(self.c['lines'],(1e30,5,-1e30)):line['quantity']=q  # exact sum 5 > 4; 28 digits would give 0
        self.assertEqual(self.result()['explanation'],AGGREGATE)
    def test_unreadable_entry_never_proves_a_record_absent(self):
        for junk in ('not an object',None,7,['AUTH-T-1']):
            with self.subTest(junk=junk):
                self.setUp();self.therapy();self.l1['authorization_id']='AUTH-NOT-SUPPLIED';self.c['authorizations'].append(junk)
                r=self.result();self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual(r['explanation'],'Authorization inventory unreadable')
    def test_unreadable_entry_does_not_hide_a_readable_match(self):
        self.therapy();self.c['authorizations'].append(None);self.assertEqual(self.status(),'PASS')
        self.c['authorizations'][0]['status']='denied';self.assertEqual(self.result()['explanation'],'Authorization status mismatch')

    def test_no_policy_cites_only_policy_id(self):
        self.therapy();self.c['policy_id']='EDU-NO-POLICY';r=self.result()
        self.assertEqual(r['status'],'UNABLE_TO_ASSESS');self.assertEqual([e['path'] for e in r['evidence']],['/policy_id'])

    def test_agrees_with_r008_on_all_public_claims(self):
        """DEC-007: R008 FAILs a missing ID exactly where R009 cascades, and both report an unknown service alike."""
        for split in ('development','validation','stress'):
            for c in load_jsonl(ROOT/'data'/split/'claims.jsonl'):
                with self.subTest(split=split,claim=c['claim_id']):
                    r8,r9=self.evaluate(c,'R008'),self.evaluate(c,'R009')
                    self.assertEqual(r8['status']=='FAIL',NO_ID in r9['explanation'])
                    self.assertEqual(UNKNOWN in r8['explanation'],UNKNOWN in r9['explanation'])
                    self.assertEqual(r8['status']=='NOT_APPLICABLE',r9['status']=='NOT_APPLICABLE')
    def test_matches_gold_on_all_public_splits(self):
        for split in ('development','validation','stress'):
            claims={c['claim_id']:c for c in load_jsonl(ROOT/'data'/split/'claims.jsonl')}
            for g in load_jsonl(ROOT/'data'/split/'expected_results.jsonl'):
                if g['rule_id']=='R009':
                    with self.subTest(split=split,claim=g['claim_id']):self.assertEqual(self.evaluate(claims[g['claim_id']]),g)
if __name__=='__main__':unittest.main()
