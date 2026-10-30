import ast
import copy
import math
import os
import sys
import unittest
from types import SimpleNamespace as NS
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib'))
from hdl_openings import synchronization as sync


def state(x=0,shape='rect'):
    result=dict(insertion=[x,0.,0.],normal=[0.,1.,0.],x=[1.,0.,0.],y=[0.,0.,1.],
        family='wall',symbol_uid='symbol',reference=None,shape=shape,depth=1.)
    if shape=='round':result['diameter']=1.
    else:result.update(width=1.,height=1.)
    return result


def payload(mep='pipe',host='wall',x=0,version=7):
    return dict(version=version,owner=sync.OWNER,mep_source='CURRENT',mep_uid=mep,
        host_source='CURRENT',host_uid=host,layer_index=0,
        opening_guid='55cac59b-01a8-4b68-91e8-d03df45cfd08',run_id='previous',
        state=state(x),participants=[dict(source='CURRENT',uid=host,layer=0,definition='a'*64)])


def old(p=None,identifier=1):
    p=copy.deepcopy(p or payload())
    return dict(element=NS(Id=identifier),payload=p,actual=copy.deepcopy(p.get('state')))


def new(p=None):return dict(plan='plan',payload=copy.deepcopy(p or payload()))


class ReconciliationTests(unittest.TestCase):
    def run_sync(self,olds,news,uncertain=lambda p:None):
        return sync.reconcile(olds,news,uncertain,.001,.0001)
    def test_unchanged_keeps_instance(self):
        self.assertEqual(self.run_sync([old()],[new()])[0]['kind'],'keep')
    def test_move_same_condition_preserves_guid(self):
        o=old();r=self.run_sync([o],[new(payload(x=2))])[0]
        self.assertEqual(r['kind'],'replace')
        self.assertEqual(r['payload']['opening_guid'],o['payload']['opening_guid'])
    def test_dimensions_angle_family_or_reference_change_replaces_same_guid(self):
        for field,value in [('width',2.),('depth',2.),('normal',[.1,.99,0.]),
                            ('symbol_uid','other'),('reference','other')]:
            o=old();n=new();n['payload']['state'][field]=value
            r=self.run_sync([o],[n])[0]
            self.assertEqual(r['kind'],'replace');self.assertEqual(r['payload']['opening_guid'],o['payload']['opening_guid'])
    def test_shape_change_same_condition_preserves_guid(self):
        n=new();n['payload']['state']=state(shape='round')
        r=self.run_sync([old()],[n])[0]
        self.assertEqual(r['kind'],'replace');self.assertEqual(r['payload']['opening_guid'],payload()['opening_guid'])
    def test_manual_edit_is_detected(self):
        o=old();o['actual']['insertion']=[2,0,0]
        self.assertEqual(self.run_sync([o],[new()])[0]['kind'],'replace')
    def test_invalid_actual_geometry_replaced(self):
        o=old();o['actual']=None
        self.assertEqual(self.run_sync([o],[new()])[0]['kind'],'replace')
    def test_small_movement_only_updates_metadata(self):
        self.assertEqual(self.run_sync([old()],[new(payload(x=.0001))])[0]['kind'],'refresh')
    def test_settings_change_same_geometry_refreshes(self):
        o=old();n=new();n['payload']['settings_fingerprint']='new'
        self.assertEqual(self.run_sync([o],[n])[0]['kind'],'refresh')
    def test_new_condition_gets_new_guid(self):
        r=self.run_sync([],[new()])[0]
        self.assertEqual(r['kind'],'create');self.assertNotEqual(r['payload']['opening_guid'],payload()['opening_guid'])
    def test_confirmed_absence_deletes(self):
        self.assertEqual(self.run_sync([old()],[])[0]['kind'],'delete')
    def test_unknown_absence_retains(self):
        self.assertEqual(self.run_sync([old()],[],lambda p:'unavailable')[0]['kind'],'retain')
    def test_added_construction_creates_new_guid_and_deletes_old(self):
        n=new();n['payload']['participants'].append(dict(source='CURRENT',uid='added',layer=0,definition='b'*64))
        r=self.run_sync([old()],[n])
        self.assertEqual([a['kind'] for a in r],['create','delete'])
        self.assertNotEqual(r[0]['payload']['opening_guid'],payload()['opening_guid'])
    def test_removed_construction_creates_new_guid(self):
        o=old();o['payload']['participants'].append(dict(source='CURRENT',uid='removed',layer=0,definition='b'*64))
        self.assertEqual([r['kind'] for r in self.run_sync([o],[new()])],['create','delete'])
    def test_same_uid_changed_assembly_creates_new_guid(self):
        n=new();n['payload']['participants'][0]['definition']='b'*64
        r=self.run_sync([old()],[n])
        self.assertEqual([a['kind'] for a in r],['create','delete'])
        self.assertNotEqual(r[0]['payload']['opening_guid'],payload()['opening_guid'])
    def test_changed_base_is_new_condition_even_if_members_same(self):
        o=old();n=new()
        for record in (o['payload'],n['payload']):
            record['participants'].append(dict(source='CURRENT',uid='other',layer=0,definition='b'*64))
        n['payload']['host_uid']='other'
        self.assertEqual([r['kind'] for r in self.run_sync([o],[n])],['create','delete'])
    def test_changed_layer_index_is_new_condition(self):
        n=new();n['payload']['participants'][0]['layer']=1
        self.assertEqual([r['kind'] for r in self.run_sync([old()],[n])],['create','delete'])
    def test_split_rebuilds_all_children_with_new_guids(self):
        o=old();o['payload']['participants'].append(dict(source='CURRENT',uid='other',layer=0,definition='a'*64))
        r=self.run_sync([o],[new(),new(payload(host='other'))])
        self.assertEqual([a['kind'] for a in r],['create','create','delete'])
        ids=[a['payload']['opening_guid'] for a in r if a['kind']=='create']
        self.assertEqual(len(set(ids)),2);self.assertNotIn(o['payload']['opening_guid'],ids)
    def test_merge_uses_new_guid_and_deletes_both_old(self):
        a=old();b=old(payload(host='other'),2)
        b['payload']['opening_guid']='3954b5b0-1d18-42ef-bcc6-785b45229da6'
        n=new();n['payload']['participants'].append(dict(source='CURRENT',uid='other',layer=0,definition='a'*64))
        r=self.run_sync([a,b],[n])
        self.assertEqual([x['kind'] for x in r],['create','delete','delete'])
        self.assertNotIn(r[0]['payload']['opening_guid'],[a['payload']['opening_guid'],b['payload']['opening_guid']])
    def test_failed_changed_condition_preserves_old(self):
        n=new();n['payload']['participants'][0]['definition']='b'*64;n['uncertain_reason']='outside face'
        self.assertEqual([r['kind'] for r in self.run_sync([old()],[n])],['retain','skip'])
    def test_failed_split_branch_preserves_old(self):
        o=old();o['payload']['participants'].append(dict(source='CURRENT',uid='other',layer=0,definition='a'*64))
        n=new(payload(host='other'));n['uncertain_reason']='bad face'
        self.assertEqual([r['kind'] for r in self.run_sync([o],[new(),n])],['retain','skip','skip'])
    def test_independent_wall_survives_failed_floor_same_mep(self):
        floor=new(payload(host='floor'));floor['uncertain_reason']='bad face'
        self.assertEqual([r['kind'] for r in self.run_sync([],[new(),floor])],['create','skip'])
    def test_legacy_unknown_definition_is_rebuilt_with_new_guid(self):
        for version in (3,4):
            o=old(payload(version=version))
            r=self.run_sync([o],[new()])
            self.assertEqual([a['kind'] for a in r],['create','delete'])
            self.assertNotEqual(r[0]['payload']['opening_guid'],o['payload']['opening_guid'])
    def test_unloaded_source_preserves_old(self):
        o=old();o['payload']['mep_source']='unloaded'
        r=self.run_sync([o],[],lambda p:'unavailable')
        self.assertEqual(r[0]['kind'],'retain')
    def test_link_instances_have_distinct_conditions(self):
        a=payload();b=payload();b['mep_source']='another-instance'
        self.assertNotEqual(sync.condition_key(a),sync.condition_key(b))
    def test_participant_order_does_not_change_condition(self):
        a=payload();a['participants'].append(dict(source='CURRENT',uid='other',layer=0,definition='b'*64))
        b=copy.deepcopy(a);b['participants'].reverse()
        self.assertEqual(sync.condition_key(a),sync.condition_key(b))
    def test_duplicate_guids_are_preserved(self):
        r=self.run_sync([old(),old(payload(mep='other'),2)],[new(),new(payload(mep='other'))])
        self.assertFalse(any(a['kind'] in ('create','delete','replace') for a in r))
    def test_duplicate_calculated_condition_is_preserved(self):
        self.assertEqual([r['kind'] for r in self.run_sync([old()],[new(),new()])],['retain','skip','skip'])
    def test_future_payload_is_preserved(self):
        self.assertEqual(self.run_sync([old(payload(version=99))],[new()])[0]['kind'],'retain')
    def test_nonfinite_state_never_matches(self):
        a=state();a['width']=float('nan');self.assertFalse(sync.same_state(a,state(),.01,.01))
    def test_invalid_payload_is_rejected(self):
        for p in [None,{},dict(payload(),opening_guid='bad'),dict(payload(),participants=[])]:
            with self.assertRaises((ValueError,TypeError,KeyError)):sync.validate_payload(p)
    def test_missing_definition_is_rejected_for_new_version(self):
        p=payload();p['participants'][0].pop('definition')
        with self.assertRaises(ValueError):sync.validate_payload(p)
    def test_known_payloads_validate(self):
        for version in (3,4,5,6,7):self.assertEqual(sync.validate_payload(payload(version=version))['version'],version)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','command.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='coverage_reason']
        namespace={'sync':sync}
        exec(compile(tree,path,'exec'),namespace)
        self.check=namespace['coverage_reason']
        self.element=NS(UniqueId='pipe')
        self.source=NS(doc=NS(GetElement=lambda uid:self.element),element_key=lambda e:'CURRENT:'+e.UniqueId)
        self.sources={'CURRENT':self.source}
        self.bounds={'CURRENT:pipe':[(0,1)]*3}
        self.cfg=NS(gap=.1,clearance=.1,rect_step=.1)
    def reason(self,p=None,failed_meps=None,failed_hosts=None):
        return self.check(p or payload(),self.sources,{'CURRENT:pipe'},failed_meps or set(),
                          failed_hosts or {},self.bounds,self.cfg)
    def test_successful_full_scan_allows_reconciliation(self):
        self.assertIsNone(self.reason())
    def test_linked_mep_is_explicitly_out_of_scope(self):
        p=payload();p['mep_source']='unloaded'
        self.assertIsNone(self.reason(p))
    def test_unloaded_construction_link_retains(self):
        p=payload();p['participants'][0]['source']='unloaded'
        self.assertIn('unavailable',self.reason(p))
    def test_failed_mep_preserves_old(self):
        self.assertIn('uncertain',self.reason(failed_meps={'CURRENT:pipe'}))
    def test_confirmed_deleted_mep_allows_removal_even_with_bad_host(self):
        self.source.doc.GetElement=lambda uid:None
        self.assertIsNone(self.reason(failed_hosts={'bad':None}))
    def test_nearby_failed_host_preserves(self):
        self.assertIn('nearby',self.reason(failed_hosts={'bad':[(.5,2)]*3}))
    def test_far_away_failed_host_does_not_block(self):
        self.assertIsNone(self.reason(failed_hosts={'bad':[(20,30)]*3}))
    def test_unknown_failed_bounds_preserve(self):
        self.assertIn('nearby',self.reason(failed_hosts={'bad':None}))
    def test_source_read_failure_preserves(self):
        def fail(uid):raise RuntimeError('read error')
        self.source.doc.GetElement=fail
        self.assertIn('cannot be checked',self.reason())



class TransactionTests(unittest.TestCase):
    def setUp(self):
        path=os.path.join(os.path.dirname(__file__),'..','HDL Openings.extension','lib','hdl_openings','command.py')
        with open(path) as f:tree=ast.parse(f.read())
        tree.body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='execute_transaction']
        self.doc=NS(items={1:'old',2:'another'},commits=0,rollbacks=0)
        self.doc.Delete=lambda eid:self.doc.items.pop(eid)
        doc=self.doc
        class Transaction:
            def __init__(self,*args):self.status='new'
            def Start(self):self.before=copy.deepcopy(doc.items);self.status='started'
            def GetFailureHandlingOptions(self):return self
            def SetFailuresPreprocessor(self,p):pass
            def SetClearAfterRollback(self,b):pass
            def SetFailureHandlingOptions(self,p):pass
            def Commit(self):self.status='committed';doc.commits+=1;return self.status
            def GetStatus(self):return self.status
            def RollBack(self):doc.items=self.before;doc.rollbacks+=1;self.status='rolledback'
        namespace={'DB':NS(Transaction=Transaction,TransactionStatus=NS(Started='started',Committed='committed')),
                   'AtomicFailures':lambda:None}
        exec(compile(tree,path,'exec'),namespace)
        self.execute=namespace['execute_transaction']
    def test_mixed_batch_one_commit(self):
        actions=sync.reconcile([old()],[new(payload(x=2)),new(payload(mep='new',host='other'))],lambda p:None,.001,.001)
        def create(plan,p):self.doc.items[len(self.doc.items)+100]=p['opening_guid']
        self.execute(self.doc,lambda:sync.apply_actions(self.doc,actions,create,lambda e,p:None,'run'))
        self.assertNotIn(1,self.doc.items);self.assertIn(2,self.doc.items)
        self.assertEqual(self.doc.commits,1);self.assertEqual(self.doc.rollbacks,0)
    def test_late_creation_failure_restores_all_old_instances(self):
        actions=[dict(kind='delete',old=old()),dict(kind='create',new=new(),payload=payload())]
        def fail(plan,p):raise RuntimeError('creation failed')
        with self.assertRaises(RuntimeError):
            self.execute(self.doc,lambda:sync.apply_actions(self.doc,actions,fail,lambda e,p:None,'run'))
        self.assertEqual(self.doc.items,{1:'old',2:'another'})
        self.assertEqual(self.doc.commits,0);self.assertEqual(self.doc.rollbacks,1)
    def test_metadata_failure_also_rolls_back_deletion(self):
        actions=[dict(kind='delete',old=old()),dict(kind='refresh',old=old(identifier=2),payload=payload())]
        def fail(e,p):raise RuntimeError('metadata write failed')
        with self.assertRaises(RuntimeError):
            self.execute(self.doc,lambda:sync.apply_actions(self.doc,actions,lambda p,v:None,fail,'run'))
        self.assertEqual(self.doc.items,{1:'old',2:'another'});self.assertEqual(self.doc.rollbacks,1)
    def test_replacement_creation_failure_does_not_delete_predecessor(self):
        actions=[dict(kind='replace',old=old(),new=new(),payload=payload())]
        def fail(plan,p):raise RuntimeError('fail')
        with self.assertRaises(RuntimeError):sync.apply_actions(self.doc,actions,fail,None,'run')
        self.assertEqual(self.doc.items[1],'old')

if __name__=='__main__':unittest.main()
