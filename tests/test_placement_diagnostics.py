"""Diagnostic coordinates remain snapshots after the API moves an instance."""
import ast
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

class PlacementDiagnosticTests(unittest.TestCase):
    def test_snapshot_and_report_preserve_each_stage_and_coordinate_frame(self):
        path=Path(__file__).parents[1]/'HDL Openings.extension/lib/hdl_openings/placement.py'
        tree=ast.parse(path.read_text())
        funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('insertion_sample','insertion_error')]
        scope={}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),str(path),'exec'),scope)
        point=NS(X=1.,Y=2.,Z=3.)
        instance=NS(Location=NS(Point=point))
        before=scope['insertion_sample'](instance,'wall created')
        point.Z=4.
        after=scope['insertion_sample'](instance,'set Depth')
        report=scope['insertion_error'](dict(host=NS(key='LINK:wall'),mep=NS(key='CURRENT:pipe')),
            'BL Opening Rect Wall',NS(UniqueId='level',ProjectElevation=2.),NS(X=1.,Y=2.,Z=3.),[before,after])
        self.assertIn('wall created: actual_mm=(304.800, 609.600, 914.400), delta_mm=(0.000, 0.000, 0.000)',report)
        self.assertIn('set Depth: actual_mm=(304.800, 609.600, 1219.200), delta_mm=(0.000, 0.000, 304.800)',report)
        self.assertIn('host=LINK:wall; mep=CURRENT:pipe',report)
        self.assertIn('level_project_z_mm=609.600',report)

class Vec:
    def __init__(self,x,y,z):self.X,self.Y,self.Z=x,y,z
    def Add(self,b):return Vec(self.X+b.X,self.Y+b.Y,self.Z+b.Z)
    def CrossProduct(self,b):return Vec(self.Y*b.Z-self.Z*b.Y,self.Z*b.X-self.X*b.Z,self.X*b.Y-self.Y*b.X)
    def DotProduct(self,b):return self.X*b.X+self.Y*b.Y+self.Z*b.Z
    def Normalize(self):return self
    def DistanceTo(self,b):return ((self.X-b.X)**2+(self.Y-b.Y)**2+(self.Z-b.Z)**2)**.5

class WallPlacementTests(unittest.TestCase):
    def test_real_create_path_converts_model_z_to_level_z_for_both_shapes(self):
        import math
        from unittest.mock import Mock
        path=Path(__file__).parents[1]/'HDL Openings.extension/lib/hdl_openings/placement.py'
        tree=ast.parse(path.read_text())
        funcs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('create','insertion_sample','insertion_error')]
        Vec.BasisZ=Vec(0,0,1)
        class Location:
            def __init__(self,point):self.Point=point
        for shape in ('round','rect'):
            for height_mm in (29500.,0.,-3500.):
                with self.subTest(shape=shape,level_mm=height_mm):
                    origin=Vec(96722.332/304.8,-207586.550/304.8,27941.320/304.8)
                    level=NS(ProjectElevation=height_mm/304.8,UniqueId='level')
                    # Shared/displayed elevation must never enter model-Z arithmetic.
                    level.Elevation=level.ProjectElevation+1234.
                    tf=NS(BasisX=Vec(1,0,0),BasisY=Vec(0,1,0),BasisZ=Vec.BasisZ)
                    def factory(point,symbol,selected_level,structural):
                        return NS(Location=Location(Vec(point.X,point.Y,point.Z+selected_level.ProjectElevation)),
                                  GetTransform=lambda:tf,Id=1)
                    create=Mock(side_effect=factory)
                    doc=NS(Create=NS(NewFamilyInstance=create),Regenerate=Mock())
                    families=NS(round_wall='RoundWall',rect_wall='RectWall')
                    plan=dict(host=NS(wall=True,key='LINK:wall'),mep=NS(key='CURRENT:pipe'),
                        settings=NS(families=families,sync_length=.001,sync_direction=.001),shape=shape,
                        insertion=origin,normal=tf.BasisY,x=tf.BasisX,y=tf.BasisZ,
                        width=1.,height=1.,diameter=1.,depth=.5)
                    state={}
                    write=Mock()
                    scope=dict(DB=NS(XYZ=Vec,LocationPoint=Location,
                        Line=NS(CreateBound=Mock()),ElementTransformUtils=NS(RotateElement=Mock())),
                        StructuralType=NS(NonStructural=0),math=math,WIDTH='Width',HEIGHT='Height',DEPTH='Depth',
                        FamilyContractError=RuntimeError,set_value=Mock(),
                        actual_state=lambda *args:state,sync=NS(same_state=lambda *args:True),storage=NS(write=write))
                    exec(compile(ast.Module(body=funcs,type_ignores=[]),str(path),'exec'),scope)
                    result=scope['create'](doc,plan,{'RoundWall':NS(IsActive=True),'RectWall':NS(IsActive=True)},level,'run',{'state':state})
                    self.assertLess(result.Location.Point.DistanceTo(origin),1e-8)
                    self.assertAlmostEqual(create.call_args.args[0].Z,(27941.320-height_mm)/304.8)
                    write.assert_called_once()
