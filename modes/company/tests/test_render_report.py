import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; spec=importlib.util.spec_from_file_location('renderer',ROOT/'scripts/render_report.py'); r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
class TestRenderer(unittest.TestCase):
 def setUp(self): self.m=json.loads((ROOT/'examples/example_report.json').read_text())
 def test_invalid_audience_route(self):
  self.m["presentation"]={"primary_audience":"popular","secondary_policy":"collapsed","reason":"猜测"}
  with self.assertRaisesRegex(ValueError,"invalid primary_audience"): r.validate(self.m)
 def test_choice_outputs(self):
  r.validate(self.m); page=r.render_html(self.m); md=r.render_markdown(self.m)
  self.assertIn('type=radio',page); self.assertIn('type=checkbox',page); self.assertIn('数据健康度',page); self.assertIn('不适用',page); self.assertNotIn('>not_applicable<',page); self.assertIn('关键事实',page); self.assertIn('数据健康度',md); self.assertIn('可继续追问',md); self.assertIn('通过（PASS）',page); self.assertIn('不等于建议买入',md); self.assertNotIn('textarea',page)
 def test_invalid_single(self):
  self.m['quiz_cards'][0]['correct_option_ids']=['A','B']
  with self.assertRaises(ValueError): r.validate(self.m)
 def test_fact_unknown_source(self):
  self.m['facts'][0]['source_ids']=['missing']
  with self.assertRaises(ValueError): r.validate(self.m)
 def test_old_model_is_compatible(self):
  self.m.pop('facts'); self.m.pop('data_health'); r.validate(self.m)
 def test_learning_and_deep_sections_are_folded(self):
  self.m['sections'].extend([{'title':'底稿一','body':'x'},{'title':'底稿二','body':'y'}])
  page=r.render_html(self.m); md=r.render_markdown(self.m)
  self.assertIn('class=learning',page); self.assertIn('class=deep',page)
  self.assertIn('<summary><strong>可选理解检查',md)
 def test_interview_questions_require_ten(self):
  self.m['interview_questions']=[{'id':'1','dimension':'x','question':'q','ask_to':'a','green':'g','yellow':'y','red':'r'}]
  with self.assertRaises(ValueError): r.validate(self.m)
if __name__=='__main__': unittest.main()
