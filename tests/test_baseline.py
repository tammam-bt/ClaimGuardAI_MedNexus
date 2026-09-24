import unittest,sys,json,copy,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from engine_core import config,base_check,load_jsonl,baseline
from evaluate import score
from audit import append,verify
from llm_adapter import MockExplanationProvider,validate_explanation

class StarterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg=config(ROOT);cls.example=json.loads((ROOT/'examples/worked_cases.json').read_text())[0]['claim']
    def setUp(self):self.c=copy.deepcopy(self.example)
    def result(self,rid):return base_check(self.c,next(r for r in self.cfg['rules'] if r['rule_id']==rid))
    def test_required_null(self):
        self.c['invoice_number']=None;self.assertEqual(self.result('R001')['status'],'FAIL')
    def test_coverage_boundary(self):
        day=self.c['lines'][0]['service_date'];self.c['coverage']['start_date']=day;self.c['coverage']['end_date']=day
        self.assertEqual(self.result('R003')['status'],'PASS')
    def test_unknown_coverage_is_not_pass(self):
        self.c['coverage']['end_date']=None;self.assertEqual(self.result('R003')['status'],'UNABLE_TO_ASSESS')
    def test_known_failure_dominates_unknown(self):
        self.c['coverage']['end_date']=None;self.c['coverage']['status']='cancelled';self.assertEqual(self.result('R003')['status'],'FAIL')
    def test_duplicate_and_modifier(self):
        other=copy.deepcopy(self.c['lines'][0]);other['line_id']='L99';self.c['lines'].append(other)
        self.assertEqual(self.result('R006')['status'],'FAIL');other['modifier']='EDU-SEPARATE';self.assertEqual(self.result('R006')['status'],'PASS')
    def test_unimplemented_is_visible(self):self.assertEqual(sum(r['status']=='NOT_IMPLEMENTED' for r in baseline(self.c,self.cfg)),12)
    def test_scorer_rejects_missing_pair(self):
        gold=load_jsonl(ROOT/'examples/first_10_expected_results.jsonl');claims={c['claim_id']:c for c in load_jsonl(ROOT/'examples/first_10_claims.jsonl')}
        with self.assertRaises(ValueError):score(gold,gold[:-1],claims)
    def test_scorer_rejects_duplicate(self):
        gold=load_jsonl(ROOT/'examples/first_10_expected_results.jsonl');claims={c['claim_id']:c for c in load_jsonl(ROOT/'examples/first_10_claims.jsonl')}
        with self.assertRaises(ValueError):score(gold,gold+[gold[0]],claims)
    def test_scorer_rejects_fabricated_evidence(self):
        gold=load_jsonl(ROOT/'examples/first_10_expected_results.jsonl');pred=copy.deepcopy(gold);pred[0]['evidence'][0]['value']='INVENTED';claims={c['claim_id']:c for c in load_jsonl(ROOT/'examples/first_10_claims.jsonl')}
        with self.assertRaises(ValueError):score(gold,pred,claims)
    def test_audit_detects_edit(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'audit.jsonl';append(p,[dict(claim_id='CG-X',rule_id='R001',action='request_information',actor='tester',reason='Need source invoice')]);self.assertEqual(verify(p)[1],1)
            p.write_text(p.read_text().replace('source invoice','altered invoice'))
            with self.assertRaises(ValueError):verify(p)
    def test_mock_explanation_validates(self):
        r=self.result('R001');out=MockExplanationProvider().explain(r,{});self.assertEqual(validate_explanation(out,r),out)
        out['cited_rule_ids']=['R999']
        with self.assertRaises(ValueError):validate_explanation(out,r)
if __name__=='__main__':unittest.main()
