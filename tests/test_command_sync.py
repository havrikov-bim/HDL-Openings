"""Command orchestration regression with API stand-ins; no Revit process needed."""
import ast
import copy
import json
import os
import sys
import unittest
import uuid
from types import SimpleNamespace as NS
from unittest.mock import Mock
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings import settings,synchronization as sync

class Wall:pass
class Floor:pass
class FamilyInstance:pass
class Level:pass


def v(x=0,y=0,z=0):return NS(X=x,Y=y,Z=z)

class Progress:
    cancelled=False
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def update_progress(self,*args):pass

class CommandTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings')
        with open(os.path.join(path,'..','..','settings.json')) as f:self.cfg=settings.validate(json.load(f),'fingerprint')
        self.doc=NS(IsFamilyDocument=False,IsReadOnly=False)
        self.deleted=[];self.created=[];self.written=[];self.transaction_count=0
        self.doc.Delete=lambda eid:self.deleted.append(eid)
        self.elements={'pipe':NS(UniqueId='pipe')}
        self.doc.GetElement=lambda uid:self.elements.get(uid)
        self.source=NS(key='CURRENT',doc=self.doc,element_key=lambda e:'CURRENT:'+e.UniqueId)
        self.mep=NS(key='CURRENT:pipe',source=self.source,element=self.elements['pipe'],
                    insulation=0,bounds=[(0,1)]*3)
        self.host=NS(key='CURRENT:wall',wall=True,source=self.source,element=Wall())
        self.host.element.UniqueId='wall'
        self.plan=dict(key='old-coordinate-key',mep=self.mep,host=self.host,layer=0,
            participants=[dict(source='CURRENT',uid='wall',layer=0,definition='a'*64)],interaction={},
            shape='rect',shape_reason=None,diameter=None,settings=self.cfg,
            insertion=v(),center=v(0,0,.5),normal=v(0,1,0),x=v(1,0,0),y=v(0,0,1),
            width=1.,height=1.,depth=1.)
        self.plans=[self.plan];self.existing=[];self.raw=[(self.source,self.elements['pipe'])]
        self.symbols=dict((name,NS(UniqueId='symbol',get_Parameter=lambda p:NS(AsString=lambda:'Standard')))
                          for name in self.cfg.families)
        outer=self
        class Collector:
            def __init__(self,doc):pass
            def OfClass(self,cls):return outer.existing if cls is FamilyInstance else [NS(ProjectElevation=0)]
        db=NS(FilteredElementCollector=Collector,FamilyInstance=FamilyInstance,Level=Level,Wall=Wall,Floor=Floor,
              BuiltInParameter=NS(SYMBOL_NAME_PARAM=1))
        self.region=NS(name='Test Scope',contains_plan=lambda p:True,
                       contains_state=lambda state,wall:True,overlaps_bounds=lambda bounds:True)
        self.forms=NS(alert=Mock(),ProgressBar=lambda **kw:Progress())
        self.storage=NS(read=lambda fi:fi.payload,write=lambda fi,p:self.written.append((fi,p)))
        def create(doc,plan,chosen,level,run,payload):self.created.append((plan,payload))
        self.face_host=NS(resolve=Mock(side_effect=ValueError('outside face')))
        self.ns=dict(DB=db,uuid=uuid,sync=sync,forms=self.forms,choose_scope=lambda doc:self.region,
            settings=NS(load=lambda:(self.cfg,None,False)),
            script=NS(get_output=lambda:NS(print_md=lambda *a:None,print_table=lambda **kw:None)),
            choose_symbols=lambda doc,cfg:self.symbols,choose_meps=lambda doc:(self.raw,[self.source]),
            model=NS(HOST_CATEGORIES=(),collect=lambda *args:[],Mep=lambda s,e:self.mep),
            engine=NS(plan=lambda *args:(self.plans,[])),
            placement=NS(actual_state=lambda fi,wall:fi.actual,create=create),
            storage=self.storage,face_host=self.face_host)
        def transaction(doc,callback):self.transaction_count+=1;callback()
        self.ns['execute_transaction']=transaction
        with open(os.path.join(path,'command.py')) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in
                   ('run','coverage_reason','host_category','report','summary')]
        exec(compile(tree,'command.py','exec'),self.ns)
    def add_existing(self,version=7):
        p=sync.desired_payload(self.plan,'symbol','previous','55cac59b-01a8-4b68-91e8-d03df45cfd08')
        p['version']=version
        fi=NS(Id=10,UniqueId='existing-opening',payload=p,actual=copy.deepcopy(p['state']),
              Symbol=NS(Family=NS(Name=sync.family_name(self.plan))))
        self.existing.append(fi)
        return fi
    def run_command(self):self.ns['run'](NS(ActiveUIDocument=NS(Document=self.doc)))
    def test_unchanged_run_does_not_start_transaction(self):
        self.add_existing();self.run_command()
        self.assertEqual(self.transaction_count,0)
        self.assertFalse(self.created);self.assertFalse(self.deleted)
    def test_moved_pipe_replaces_old_and_preserves_guid(self):
        old=self.add_existing();self.plan['insertion']=v(2);self.plan['center']=v(2,0,.5)
        self.plan['key']='new-coordinate-key'
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])
        self.assertEqual(self.transaction_count,1)
    def test_deleted_last_mep_still_cleans_up(self):
        self.add_existing();self.raw=[];self.elements.clear();self.plans=[]
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertFalse(self.created)
        self.assertEqual(self.transaction_count,1)
    def test_no_longer_intersects_deletes_old(self):
        self.add_existing();self.plans=[];self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertFalse(self.created)
    def test_unplaceable_floor_keeps_old(self):
        self.host.wall=False;self.host.element=Floor();self.host.element.UniqueId='floor'
        self.plan['participants'][0]['uid']='floor'
        self.add_existing();self.run_command()
        self.assertEqual(self.transaction_count,0)
        self.assertFalse(self.created);self.assertFalse(self.deleted)
    def test_legacy_instance_without_definition_is_rebuilt(self):
        fi=self.add_existing(version=3);fi.payload.pop('state');fi.payload.pop('participants');fi.payload.pop('opening_guid')
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertTrue(self.created[0][1]['opening_guid'])
    def test_bad_stored_data_blocks_changes(self):
        self.add_existing()
        def fail(fi):raise ValueError('invalid stored data')
        self.storage.read=fail;self.run_command()
        self.assertEqual(self.transaction_count,0)
        self.assertFalse(self.created);self.assertFalse(self.deleted)

    def floor_plan(self):
        floor=Floor();floor.UniqueId='floor'
        result=dict(self.plan)
        result.update(key='floor-key',host=NS(key='CURRENT:floor',wall=False,source=self.source,element=floor),
                      participants=[dict(source='CURRENT',uid='floor',layer=0,definition='a'*64)],interaction={})
        return result
    def add_floor_existing(self):
        floor=self.floor_plan()
        p=sync.desired_payload(floor,'symbol','previous','a698b67f-d750-49c3-a92f-42df8dfd1110')
        fi=NS(Id=11,UniqueId='floor-opening',payload=p,actual=copy.deepcopy(p['state']))
        self.existing.append(fi)
        return fi
    def test_rejected_floor_does_not_block_new_wall_same_mep(self):
        self.plans=[self.plan,self.floor_plan()]
        self.run_command()
        self.assertEqual(len(self.created),1)
        self.assertTrue(self.created[0][0]['host'].wall)
        self.assertFalse(self.deleted)
        self.assertEqual(self.transaction_count,1)
    def test_rejected_floor_retains_old_floor_and_creates_wall(self):
        self.add_floor_existing()
        self.plans=[self.plan,self.floor_plan()]
        self.run_command()
        self.assertEqual(len(self.created),1)
        self.assertTrue(self.created[0][0]['host'].wall)
        self.assertFalse(self.deleted)
    def test_rejected_floor_allows_wall_replacement_same_mep(self):
        old_wall=self.add_existing();self.add_floor_existing()
        self.plan['insertion']=v(2);self.plan['center']=v(2,0,.5)
        self.plans=[self.plan,self.floor_plan()]
        self.run_command()
        self.assertEqual(self.deleted,[10])
        self.assertEqual(len(self.created),1)
        self.assertEqual(self.created[0][1]['opening_guid'],old_wall.payload['opening_guid'])
    def test_floor_rule_rejection_alone_does_not_block_wall(self):
        self.add_floor_existing()
        self.ns['engine'].plan=lambda *args:([self.plan],['K_slope exceeded: ratio=2.0, limit=1.5'])
        self.run_command()
        self.assertEqual(len(self.created),1)
        self.assertTrue(self.created[0][0]['host'].wall)
        self.assertEqual(self.deleted,[11])

    def test_rectangular_to_round_replaces_family_and_preserves_guid(self):
        old=self.add_existing()
        self.plan.update(shape='round',diameter=.4)
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertEqual(self.created[0][1]['state']['family'],self.cfg.families.round_wall)
        self.assertEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])
    def test_round_to_rectangular_replaces_family_and_preserves_guid(self):
        self.plan.update(shape='round',diameter=.4)
        old=self.add_existing()
        self.plan.update(shape='rect',diameter=None)
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertEqual(self.created[0][1]['state']['family'],self.cfg.families.rect_wall)
        self.assertEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])

    def test_moved_construction_with_changed_layer_set_replaces(self):
        old=self.add_existing()
        self.plan['insertion']=v(0,2,0);self.plan['center']=v(0,2,.5)
        self.plan['depth']=1.2
        self.plan['participants'].append(dict(source='CURRENT',uid='additional-layer-host',layer=0,definition='a'*64))
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertNotEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])
        self.assertEqual(self.created[0][1]['state']['insertion'],[0,2,0])
        self.assertEqual(self.created[0][1]['state']['depth'],1.2)

    def test_added_wall_becomes_base_and_existing_hole_is_replaced(self):
        old=self.add_existing()
        new_wall=Wall();new_wall.UniqueId='new-wall'
        self.plan['host']=NS(key='CURRENT:new-wall',wall=True,source=self.source,element=new_wall)
        self.plan['participants'].append(dict(source='CURRENT',uid='new-wall',layer=0,definition='a'*64))
        self.plan['insertion']=v(0,2,0);self.plan['center']=v(0,2,.5)
        self.plan['depth']=3.
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertEqual(self.created[0][1]['host_uid'],'new-wall')
        self.assertNotEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])
        self.assertEqual(self.created[0][1]['state']['depth'],3.)

    def test_assembly_change_same_wall_uid_creates_fresh_guid(self):
        old=self.add_existing()
        self.plan['participants'][0]['definition']='b'*64
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertNotEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])
    def test_switching_base_inside_same_group_creates_fresh_guid(self):
        self.plan['participants'].append(dict(source='CURRENT',uid='other-wall',layer=0,definition='a'*64))
        old=self.add_existing()
        other=Wall();other.UniqueId='other-wall'
        self.plan['host']=NS(key='CURRENT:other-wall',wall=True,source=self.source,element=other)
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertEqual(len(self.created),1)
        self.assertNotEqual(self.created[0][1]['opening_guid'],old.payload['opening_guid'])

    def test_existing_linked_mep_opening_is_removed_even_if_link_unloaded(self):
        old=self.add_existing();old.payload['mep_source']='unloaded-link'
        self.plans=[];self.raw=[]
        self.run_command()
        self.assertEqual(self.deleted,[10]);self.assertFalse(self.created)
    def test_mep_collection_uses_current_model_only_but_preserves_host_sources(self):
        root=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings')
        with open(os.path.join(root,'command.py')) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='choose_meps']
        current=NS(key='CURRENT');link=NS(key='link')
        calls=[]
        def collect(source,categories):
            calls.append(source.key)
            if source is link:raise AssertionError('Must not scan linked MEP')
            return ['native-pipe']
        ns=dict(model=NS(sources=lambda doc:[current,link],collect=collect,MEP_CATEGORIES='mep'))
        exec(compile(tree,'command.py','exec'),ns)
        raw,sources=ns['choose_meps'](self.doc)
        self.assertEqual(calls,['CURRENT'])
        self.assertEqual(raw,[(current,'native-pipe')])
        self.assertEqual(sources,[current,link])

    def test_cancel_scope_selection_makes_no_changes(self):
        self.add_existing();self.region=None
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.created);self.assertFalse(self.deleted)
    def test_new_opening_outside_scope_not_created(self):
        self.region.contains_plan=lambda plan:False
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.created)
    def test_old_outside_scope_not_deleted(self):
        self.add_existing();self.plans=[];self.region.contains_state=lambda state,wall:False
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.deleted)
    def test_old_outside_scope_not_replaced_when_new_plan_inside(self):
        self.add_existing();self.plan['insertion']=v(2);self.region.contains_state=lambda state,wall:False
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.created);self.assertFalse(self.deleted)
    def test_inside_old_preserved_when_new_plan_crosses_scope_boundary(self):
        self.add_existing();self.plan['insertion']=v(2);self.region.contains_plan=lambda plan:False
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.created);self.assertFalse(self.deleted)
    def test_outside_linked_mep_opening_is_preserved(self):
        old=self.add_existing();old.payload['mep_source']='link'
        self.plans=[];self.raw=[];self.region.contains_state=lambda state,wall:False
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.deleted)
    def test_outside_floor_does_not_block_independent_inside_wall(self):
        self.plans=[self.plan,self.floor_plan()]
        self.region.contains_plan=lambda plan:plan['host'].wall
        self.run_command()
        self.assertEqual(len(self.created),1);self.assertTrue(self.created[0][0]['host'].wall)
        self.face_host.resolve.assert_not_called()
    def test_mep_prefilter_does_not_turn_unknown_coverage_into_deletion(self):
        self.add_existing();self.ns['model'].element_bounds=lambda *args:[(10,11)]*3
        self.region.overlaps_bounds=lambda bounds:False
        self.run_command()
        self.assertEqual(self.transaction_count,0);self.assertFalse(self.deleted)

if __name__=='__main__':unittest.main()
