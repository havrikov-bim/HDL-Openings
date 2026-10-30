"""Exercise restored command's selection and cross-document numbering."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

PATH = Path(__file__).parents[1] / 'HDL Openings.extension/HDL Openings.tab/Openings.panel/NumberOpenings.pushbutton/script.py'

class Model:
    def __init__(self, title):
        self.Title = title
        self.PathName = title
    def Equals(self, other):
        return self is other

class NumberModelsTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = Model('A'), Model('B')
        self.dialogs, self.writes = [], []
        self.documents = [self.a]
        outer = self
        class Choice:
            def __init__(self, item, checked=False):
                self.item, self.checked = item, checked
        self.Choice = Choice
        def select(choices, **kwargs):
            outer.dialogs.append((choices, kwargs))
            return choices
        tree = ast.parse(PATH.read_text())
        tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('main', 'build_global_plan')]
        self.ns = dict(revit=NS(doc=NS(Application=object())),
                       eligible_documents=lambda app:self.documents,
                       ModelChoice=Choice,
                       forms=NS(alert=lambda *a, **kw:None,
                                SelectFromList=NS(show=select)),
                       collect_plan=lambda doc:([((2 if doc is self.a else 1,0,0),1,doc.Title)],[]),
                       write_plan=lambda docs, plan:self.writes.append((docs,plan)) or {d.Title:1 for d in docs})
        exec(compile(tree,str(PATH),'exec'),self.ns)
    def test_one_model_no_dialog(self):
        self.ns['main']()
        self.assertFalse(self.dialogs)
        self.assertEqual(self.writes[0][1][0][3], 'ID #1')
    def test_multiple_models_checkbox_selection(self):
        self.documents = [self.a,self.b]
        self.ns['main']()
        self.assertTrue(self.dialogs[0][1]['multiselect'])
        plan = self.writes[0][1]
        self.assertIs(plan[0][0],self.b)
        self.assertEqual([r[3] for r in plan], ['ID #1','ID #2'])
    def test_cancel_does_not_write(self):
        self.documents = [self.a,self.b]
        self.ns['forms'].SelectFromList.show = lambda *a, **kw:None
        self.ns['main']()
        self.assertFalse(self.writes)

if __name__ == '__main__':
    unittest.main()
