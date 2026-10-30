# -*- coding: utf-8 -*-
import ast
import copy
import json
import os
import sys
import unittest
from types import SimpleNamespace as NS
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'HDL Openings.extension', 'lib'))
from hdl_openings.mep_labels import Mapping, qualifies
from hdl_openings import mep_excel, settings

CATEGORIES = [('Conduits','Electricity','Electrical'),('Cable Trays','Electricity','Electrical')]
SYSTEMS = [('Supply','SA','HVAC'),('Cooling','CHW','HVAC'),('Water','CW','Plumbing')]
ROOT = os.path.join(os.path.dirname(__file__), '..', 'HDL Openings.extension', 'lib', 'hdl_openings')


class LabelsTests(unittest.TestCase):
    def setUp(self): self.m = Mapping(SYSTEMS, CATEGORIES)
    def test_empty_and_single(self):
        self.assertEqual(self.m.reduce([]), '')
        self.assertEqual(self.m.reduce([('SA','HVAC')]*3), 'SA')
    def test_one_discipline(self):
        self.assertEqual(self.m.reduce([('SA','HVAC'),('CHW','HVAC')]), 'HVAC')
    def test_mixed_and_order(self):
        self.assertEqual(self.m.reduce([('Electricity','Electrical'),('CW','Plumbing'),('SA','HVAC')]), 'HVAC, Plumbing, Electrical')
    def test_equal_labels_different_disciplines(self):
        self.assertEqual(self.m.reduce([('X','Plumbing'),('X','HVAC')]), 'HVAC, Plumbing')
    def test_electricity(self):
        self.assertEqual(self.m.reduce([self.m.resolve(category=c) for c in ('Conduits','Cable Trays')]), 'Electricity')
    def test_hebrew(self):
        m=Mapping([('אספקה','אוויר','מיזוג'),('מים','מים','אינסטלציה')],CATEGORIES)
        self.assertEqual(m.reduce([m.resolve('מים'),m.resolve('אספקה')]), 'מיזוג, אינסטלציה')
    def test_bad_mapping(self):
        for rows in (SYSTEMS+[SYSTEMS[0]], [('Supply','','HVAC')]):
            with self.assertRaises(ValueError):Mapping(rows,CATEGORIES)
        with self.assertRaises(ValueError):self.m.resolve('unknown')
        with self.assertRaises(ValueError):self.m.resolve('')
    def test_threshold_and_exceptions(self):
        self.assertFalse(qualifies(25,100,False,25,.1))
        self.assertFalse(qualifies(24.9,100,False,25,.1))
        self.assertTrue(qualifies(25.001,100,False,25,.1))
        self.assertTrue(qualifies(10,10,False,25,.1))
        self.assertTrue(qualifies(5,100,True,25,.1))


class Progress:
    cancelled=False
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def update_progress(self,*a):pass


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.doc=NS(IsFamilyDocument=False)
        self.written=[];self.events=[];self.hit=True;self.mapping_error=False
        self.unavailable=[];self.cancel=False
        self.parameter=NS(AsString=lambda:'old',Set=lambda value:self.events.append(('set',value)) or True)
        self.element=NS(Id=1,Symbol=NS(Family=NS(Name='BL Opening Rect Wall')))
        self.messages=[];self.tables=[]
        self.output=NS(print_md=lambda msg:self.messages.append(msg),print_table=lambda **kw:self.tables.append(kw))
        outer=self
        class Collector:
            def __init__(self,doc):pass
            def OfClass(self,cls):return [outer.element]
        class Tx:
            def __init__(self,*args):self.state='New'
            def Start(self):self.state='Started';outer.events.append('start');return self.state
            def GetFailureHandlingOptions(self):return NS(SetClearAfterRollback=lambda v:None,SetForcedModalHandling=lambda v:None)
            def SetFailureHandlingOptions(self,options):pass
            def GetStatus(self):return self.state
            def Commit(self):
                if outer.commit_error:raise ValueError('commit error')
                self.state='Committed';return self.state
            def RollBack(self):self.state='RolledBack';outer.events.append('rollback')
            def Dispose(self):pass
        self.commit_error=False
        class Candidate:
            bounds=[(0,1)]*3;key='link:pipe'
            def inside(self,*args):return {'rule':'Through','entry_mm':100} if outer.hit else None
            def classification(self,mapping):
                if outer.mapping_error:raise ValueError('missing type')
                return dict(source='link',element_unique_id='pipe',label='SA',discipline='HVAC')
        self.candidate=Candidate()
        self.cfg=NS(families=NS(),touch=25/304.8,sync_length=.1/304.8)
        self.cfg.families=['BL Opening Rect Wall']
        self.m=Mapping(SYSTEMS,CATEGORIES)
        self.ns=dict(traceback=__import__('traceback'),save_run_log=lambda records:'test.log',text_type=str,os=os,time=__import__('time'),DB=NS(FilteredElementCollector=Collector,FamilyInstance=object,
           Transaction=Tx,TransactionStatus=NS(Started='Started',Committed='Committed')),
           forms=NS(alert=lambda *a:None,ProgressBar=lambda **kw:Progress()),
           script=NS(get_output=lambda:self.output),settings=NS(load=lambda:(self.cfg,None,False)),
           choose_excel=lambda shift:('/tmp/mapping.xlsx',self.m,'hash'),target_parameter=lambda e:self.parameter,
           Opening=lambda *a:NS(bounds=[(0,1)]*3,solid=NS(Dispose=lambda:None)),
           gather=lambda doc:([self.candidate],self.unavailable),geo=NS(overlaps=lambda *a:True),
           id_value=lambda eid:eid,mep_storage=NS(serialized=lambda p:json.dumps(p),matches=lambda *a:False,
           write=lambda e,raw:self.written.append(json.loads(raw))))
        path=os.path.join(ROOT,'identify_command.py')
        with open(path) as stream:tree=ast.parse(stream.read())
        # Execute the real orchestration function with deterministic Revit stand-ins.
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run']
        exec(compile(tree,path,'exec'),self.ns)
    def run_command(self):self.ns['run'](NS(ActiveUIDocument=NS(Document=self.doc)))
    def test_identified_linked_ids_saved(self):
        self.run_command();self.assertEqual(self.written[0]['elements'][0]['element_unique_id'],'pipe')
        self.assertIn(('set','SA'),self.events)
    def test_empty_clears(self):
        self.hit=False;self.run_command();self.assertIn(('set',''),self.events)
        self.assertEqual(self.written[0]['elements'],[])
    def test_unknown_mapping_preserves(self):
        self.mapping_error=True;self.run_command();self.assertFalse(self.written);self.assertFalse(self.events)
    def test_unavailable_link_does_not_block_available_mep(self):
        self.unavailable=['unloaded-link'];self.run_command()
        self.assertIn(('set','SA'),self.events)
        self.assertEqual(self.written[0]['unavailable_links'],['unloaded-link'])
        self.assertTrue(any('Skipped unloaded links' in msg for msg in self.messages))
        self.assertTrue(any(t['table_data']==[['unloaded-link']] for t in self.tables))
    def test_only_unavailable_source_recalculates_empty(self):
        self.unavailable=['unloaded-link'];self.hit=False;self.run_command()
        self.assertIn(('set',''),self.events)
        self.assertEqual(self.written[0]['elements'],[])
    def test_complete_source_metadata(self):
        self.run_command()
        self.assertEqual(self.written[0]['unavailable_links'],[])
        self.assertFalse(any('Skipped unloaded links' in msg for msg in self.messages))
    def test_geometry_failure_preserves(self):
        self.candidate.inside=lambda *a:(_ for _ in ()).throw(ValueError('Boolean'))
        self.run_command();self.assertFalse(self.written);self.assertFalse(self.events)
    def test_commit_failure_rollback(self):
        self.commit_error=True
        with self.assertRaises(ValueError):self.run_command()
        self.assertIn('rollback',self.events)


if __name__=='__main__':unittest.main()
