import ast
import json
import os
import unittest
from types import SimpleNamespace as NS
from test_synchronization import payload
from hdl_openings.synchronization import validate_payload


class Generic:
    def __init__(self,fn):self.fn=fn
    def __getitem__(self,t):return self.fn


class Schema:
    registry={}
    def __init__(self,guid):self.GUID=guid;self.fields={}
    @classmethod
    def Lookup(cls,guid):return cls.registry.get(guid)
    def GetField(self,name):return name


class Builder:
    def __init__(self,guid):self.schema=Schema(guid)
    def SetSchemaName(self,n):pass
    def SetReadAccessLevel(self,n):pass
    def SetWriteAccessLevel(self,n):pass
    def AddSimpleField(self,name,t):self.schema.fields[name]=t
    def Finish(self):Schema.registry[self.schema.GUID]=self.schema;return self.schema


class Entity:
    def __init__(self,s=None):
        self.schema=s;self.data={}
        self.Get=Generic(lambda field:self.data[field])
        self.Set=Generic(lambda field,value:self.data.__setitem__(field,value))
    def IsValid(self):return self.schema is not None


class Element:
    def __init__(self):self.entities={}
    def GetEntity(self,s):return self.entities.get(s.GUID,Entity())
    def SetEntity(self,e):self.entities[e.schema.GUID]=e
    def DeleteEntity(self,s):del self.entities[s.GUID]


class StorageTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','storage.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if not isinstance(n,(ast.Import,ast.ImportFrom))]
        Schema.registry={}
        self.ns=dict(json=json,Guid=str,String=str,Schema=Schema,SchemaBuilder=Builder,
                     Entity=Entity,AccessLevel=NS(Public=1),validate_payload=validate_payload)
        exec(compile(tree,path,'exec'),self.ns)
        self.element=Element()
    def legacy(self,p=None):
        s=Builder(self.ns['LEGACY_SCHEMA_ID']).Finish();e=Entity(s)
        e.data['Payload']=json.dumps(p or payload(version=3));self.element.SetEntity(e)
    def test_roundtrip_with_native_guid_field(self):
        self.ns['write'](self.element,payload())
        s=Schema.Lookup(self.ns['SCHEMA_ID'])
        self.assertIn('OpeningGuid',s.fields)
        self.assertEqual(self.element.GetEntity(s).data['OpeningGuid'],payload()['opening_guid'])
        self.assertEqual(self.ns['read'](self.element),payload())
    def test_legacy_read_then_atomic_schema_migration(self):
        self.legacy();self.assertEqual(self.ns['read'](self.element)['version'],3)
        self.ns['write'](self.element,payload())
        self.assertNotIn(self.ns['LEGACY_SCHEMA_ID'],self.element.entities)
        self.assertEqual(self.ns['read'](self.element)['version'],7)
    def test_no_data_is_not_a_managed_opening(self):
        self.assertIsNone(self.ns['read'](self.element))
    def test_guid_conflict_rejected(self):
        self.ns['write'](self.element,payload())
        self.element.entities[self.ns['SCHEMA_ID']].data['OpeningGuid']='different'
        with self.assertRaises(ValueError):self.ns['read'](self.element)
    def test_corrupt_legacy_json_rejected(self):
        self.legacy();e=self.element.entities[self.ns['LEGACY_SCHEMA_ID']]
        e.data['Payload']='{' 
        with self.assertRaises(ValueError):self.ns['read'](self.element)
    def test_nonfinite_and_duplicate_fields_rejected(self):
        self.legacy();e=self.element.entities[self.ns['LEGACY_SCHEMA_ID']]
        for raw in ['{"version":3,"version":4}','{"x":NaN}']:
            e.data['Payload']=raw
            with self.assertRaises(ValueError):self.ns['read'](self.element)

if __name__=='__main__':unittest.main()
