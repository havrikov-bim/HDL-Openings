"""Exercise actual parameter adapter functions without loading Revit."""
import ast
import os
import unittest
from types import SimpleNamespace

path = os.path.join(os.path.dirname(__file__), '..', 'HDL Openings.extension',
                    'lib', 'hdl_openings', 'placement.py')
with open(path) as stream:
    tree = ast.parse(stream.read())
tree.body = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
             and n.name in ('FamilyContractError', 'parameter', 'set_value')]
DB = SimpleNamespace(StorageType=SimpleNamespace(Double='Double'),
                     SpecTypeId=SimpleNamespace(Length='Length'))
ns = {'DB': DB}
exec(compile(tree, path, 'exec'), ns)


class Param:
    # Intentionally no IsShared: ordinary family parameters must be accepted.
    IsReadOnly = False
    StorageType = 'Double'
    Definition = SimpleNamespace(GetDataType=lambda: 'Length')
    def __init__(self):
        self.value = 1.0
    def AsDouble(self):
        return self.value
    def Set(self, value):
        self.value = value
        return True


class Element:
    def __init__(self, params):
        self.params = params
    def GetParameters(self, name):
        return self.params.get(name, [])


class ParameterTests(unittest.TestCase):
    def test_ordinary_parameters_are_written(self):
        for name in ('Width', 'Height', 'Depth'):
            p = Param()
            e = Element({name: [p]})
            ns['set_value'](e, name, 2.0)
            self.assertEqual(p.value, 2.0)

    def test_readonly_formula_parameter_rejected(self):
        p = Param()
        p.IsReadOnly = True
        with self.assertRaises(ns['FamilyContractError']):
            ns['parameter'](Element({'Width': [p]}), 'Width')

    def test_type_parameter_not_used_as_fallback(self):
        with self.assertRaises(ns['FamilyContractError']):
            ns['parameter'](Element({}), 'Width')

    def test_duplicate_names_rejected(self):
        with self.assertRaises(ns['FamilyContractError']):
            ns['parameter'](Element({'Width': [Param(), Param()]}), 'Width')

    def test_wrong_specification_rejected(self):
        p = Param()
        p.Definition = SimpleNamespace(GetDataType=lambda: 'Area')
        with self.assertRaises(ns['FamilyContractError']):
            ns['parameter'](Element({'Width': [p]}), 'Width')

if __name__ == '__main__':
    unittest.main()
