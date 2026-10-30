# -*- coding: utf-8 -*-
import hashlib
import json
from Autodesk.Revit import DB
from hdl_openings import geometry as geo
from hdl_openings.config import MM, EPS
from hdl_openings.section_math import passage_interval, swept_range, axis_trace_length, axis_interval

MEP_CATEGORIES = (DB.BuiltInCategory.OST_DuctCurves,
                  DB.BuiltInCategory.OST_PipeCurves,
                  DB.BuiltInCategory.OST_CableTray,
                  DB.BuiltInCategory.OST_Conduit)
HOST_CATEGORIES = (DB.BuiltInCategory.OST_Walls,
                   DB.BuiltInCategory.OST_Floors,
                   DB.BuiltInCategory.OST_Roofs)


def id_value(eid):
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


class Source(object):
    def __init__(self, doc, transform, link=None, reference_point=(0.,0.,0.)):
        self.doc = doc
        self.transform = transform
        self.link = link
        self.key = link.UniqueId if link else 'CURRENT'
        self.reference_point = tuple(reference_point)

    def element_key(self, element):
        return self.key + ':' + element.UniqueId


def sources(doc):
    getter = getattr(DB.BasePoint,'GetProjectBasePoint',None)
    if getter is not None:
        point = getter(doc)
    else:
        points = list(DB.FilteredElementCollector(doc).OfCategory(
            DB.BuiltInCategory.OST_ProjectBasePoint).WhereElementIsNotElementType())
        point = points[0] if len(points)==1 else None
    if point is None:
        raise geo.UnsupportedGeometry('Project Base Point unavailable; no model changes')
    reference_point = (point.Position.X,point.Position.Y,point.Position.Z)
    result = [Source(doc, DB.Transform.Identity,reference_point=reference_point)]
    for link in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance):
        linked = link.GetLinkDocument()
        if linked is not None:
            result.append(Source(linked, link.GetTotalTransform(), link,reference_point))
    return result


def collect(source, categories):
    wanted = set(int(c) for c in categories)
    for element in DB.FilteredElementCollector(source.doc).WhereElementIsNotElementType():
        if element.Category and id_value(element.Category.Id) in wanted:
            yield element


class ModelElement(object):
    def __init__(self, source, element):
        self.source, self.element = source, element
        self.key = source.element_key(element)
        self.solids = geo.solids(element, source.transform)
        if not self.solids:
            raise geo.UnsupportedGeometry('No usable Solid: ' + self.key)
        self.bounds = geo.bbox(self.solids)


class Mep(ModelElement):
    def __init__(self, source, element):
        ModelElement.__init__(self, source, element)
        loc = element.Location
        if not isinstance(loc, DB.LocationCurve) or not isinstance(loc.Curve, DB.Line):
            raise geo.UnsupportedGeometry('Current test requires straight MEP: ' + self.key)
        self.axis = source.transform.OfVector(loc.Curve.Direction).Normalize()
        self.origin = source.transform.OfPoint(loc.Curve.GetEndPoint(0))
        self.length = loc.Curve.Length
        connectors = list(element.ConnectorManager.Connectors)
        ends = [c for c in connectors if c.ConnectorType == DB.ConnectorType.End]
        if not ends:
            raise geo.UnsupportedGeometry('No end connector for section: ' + self.key)
        connector = min(ends, key=lambda c: source.transform.OfPoint(c.Origin).DistanceTo(self.origin))
        self.u = source.transform.OfVector(connector.CoordinateSystem.BasisX).Normalize()
        self.v = source.transform.OfVector(connector.CoordinateSystem.BasisY).Normalize()
        self.circular = connector.Shape == DB.ConnectorProfileType.Round
        self.round_eligible = id_value(element.Category.Id) in (
            int(DB.BuiltInCategory.OST_PipeCurves), int(DB.BuiltInCategory.OST_Conduit))
        if self.circular:
            self.hw = self.hh = connector.Radius
        elif connector.Shape == DB.ConnectorProfileType.Oval:
            self.circular = 'oval'
            self.hw, self.hh = connector.Width/2., connector.Height/2.
        elif connector.Shape == DB.ConnectorProfileType.Rectangular:
            self.hw, self.hh = connector.Width/2., connector.Height/2.
        else:
            raise geo.UnsupportedGeometry('Unsupported connector section: ' + self.key)
        if self.round_eligible:
            outside_parameter = (DB.BuiltInParameter.RBS_PIPE_OUTER_DIAMETER
                if id_value(element.Category.Id) == int(DB.BuiltInCategory.OST_PipeCurves)
                else DB.BuiltInParameter.RBS_CONDUIT_OUTER_DIAM_PARAM)
            parameter = element.get_Parameter(outside_parameter)
            if parameter is None or parameter.AsDouble() <= 0:
                raise geo.UnsupportedGeometry('Actual outside diameter unavailable: ' + self.key)
            self.hw = self.hh = parameter.AsDouble()/2.
        self.insulation = 0.
        insulated_categories = (int(DB.BuiltInCategory.OST_PipeCurves),
                                 int(DB.BuiltInCategory.OST_DuctCurves))
        if id_value(element.Category.Id) in insulated_categories:
            insulation_ids = list(DB.InsulationLiningBase.GetInsulationIds(source.doc, element.Id))
            if len(insulation_ids) > 1:
                raise geo.UnsupportedGeometry('Multiple insulation elements require explicit layer handling: ' + self.key)
            for insulation_id in insulation_ids:
                insulation = source.doc.GetElement(insulation_id)
                if insulation is None or insulation.Thickness < 0:
                    raise geo.UnsupportedGeometry('Invalid insulation data: ' + self.key)
                self.insulation = insulation.Thickness
                extra = geo.solids(insulation, source.transform)
                if self.insulation > 0 and not extra:
                    raise geo.UnsupportedGeometry('Insulation geometry unavailable: ' + self.key)
                self.solids.extend(extra)
        self.hw += self.insulation
        self.hh += self.insulation
        self.bounds = geo.bbox(self.solids)
        if abs(self.u.DotProduct(self.axis)) > 1e-6 or abs(self.v.DotProduct(self.axis)) > 1e-6:
            raise geo.UnsupportedGeometry('Connector frame not perpendicular to MEP axis')

    def section_data(self):
        xyz = lambda v: (v.X, v.Y, v.Z)
        return (xyz(self.origin), xyz(self.axis), xyz(self.u), xyz(self.v),
                self.hw, self.hh, self.circular)

    def passage(self, normal, low, high):
        origin, axis, u, v, hw, hh, circular = self.section_data()
        return passage_interval(origin, axis, self.length, u, v, hw, hh, circular,
                                (normal.X, normal.Y, normal.Z), low, high)

    def grouping_interval(self, normal, low, high):
        return axis_interval((self.origin.X, self.origin.Y, self.origin.Z),
                             (self.axis.X, self.axis.Y, self.axis.Z), self.length,
                             (normal.X, normal.Y, normal.Z), low, high)

    def axis_trace(self, normal, low, high):
        return axis_trace_length((self.origin.X, self.origin.Y, self.origin.Z),
                                 (self.axis.X, self.axis.Y, self.axis.Z), self.length,
                                 (normal.X, normal.Y, normal.Z), low, high)

    def sweep(self, normal, low, high, direction):
        return swept_range(*(self.section_data() +
                           ((normal.X, normal.Y, normal.Z), low, high,
                            (direction.X, direction.Y, direction.Z))))



def eligible_layer_indices(cs,layers):
    index = int(cs.StructuralMaterialIndex)
    if (0<=index<len(layers) and layers[index].Width>EPS and
            layers[index].Function==DB.MaterialFunctionAssignment.Structure):
        return [index]
    return []


class Host(ModelElement):
    """Base eligibility requires BOTH Structure [1] and Structural Material."""
    def __init__(self, source, element):
        ModelElement.__init__(self, source, element)
        self.wall = isinstance(element, DB.Wall)
        typ = source.doc.GetElement(element.GetTypeId())
        cs = typ.GetCompoundStructure()
        if cs is None or not cs.IsVerticallyHomogeneous():
            raise geo.UnsupportedGeometry('No homogeneous compound structure: '+self.key)
        self.layers = list(cs.GetLayers())
        eligible = eligible_layer_indices(cs,self.layers)
        self.base_index = eligible[0] if eligible else None
        # This internal flag denotes eligible layers, never the instance checkbox.
        self.is_structural = bool(eligible)
        self.reference_point = getattr(source,'reference_point',(0.,0.,0.))
        self.variable = -1
        if self.wall:
            curve = element.Location.Curve
            if not isinstance(curve, DB.Line):
                raise geo.UnsupportedGeometry('Curved wall: '+self.key)
            self.normal = source.transform.OfVector(element.Orientation).Normalize()
            if abs(self.normal.Z)>1e-6:
                raise geo.UnsupportedGeometry('Slanted wall: '+self.key)
        else:
            bottom = [f for solid in self.solids for f in solid.Faces
                      if isinstance(f,DB.PlanarFace) and f.FaceNormal.Z<-.1]
            if not bottom:
                raise geo.UnsupportedGeometry('No planar bottom surface: '+self.key)
            bottom.sort(key=lambda face:face.Area,reverse=True)
            self.normal = bottom[0].FaceNormal.Negate().Normalize()
            coordinate = bottom[0].Origin.DotProduct(self.normal)
            for face in bottom[1:]:
                if (abs(face.FaceNormal.DotProduct(self.normal)+1)>1e-6 or
                        abs(face.Origin.DotProduct(self.normal)-coordinate)>.5*MM):
                    raise geo.UnsupportedGeometry('Folded/noncoplanar bottom: '+self.key)
            top = [face for solid in self.solids for face in solid.Faces
                   if isinstance(face,DB.PlanarFace) and face.FaceNormal.DotProduct(self.normal)>.1]
            # Existing face geometry determines the placement side.
            if top:
                top_coordinate = top[0].Origin.DotProduct(self.normal)
                if any(abs(face.FaceNormal.DotProduct(self.normal)-1)>1e-6 or
                       abs(face.Origin.DotProduct(self.normal)-top_coordinate)>.5*MM for face in top):
                    self.variable = 0
        low,high = geo.combined_range(self.solids,self.normal)
        if high-low<=EPS:
            raise geo.UnsupportedGeometry('Construction has no positive normal thickness: '+self.key)
        self.outer_high = high
        total = sum(float(item.Width) for item in self.layers)
        variable_index = int(cs.VariableLayerIndex)
        if self.wall and variable_index>=0:
            raise geo.UnsupportedGeometry('Variable wall layer unsupported: '+self.key)
        if variable_index not in (-1,0):
            raise geo.UnsupportedGeometry('Only uppermost variable layer is supported: '+self.key)
        if self.base_index is not None and self.base_index==variable_index:
            raise geo.UnsupportedGeometry('Variable base layer requires local thickness calculation: '+self.key)
        if variable_index<0 and abs(high-low-total)>.5*MM:
            raise geo.UnsupportedGeometry('Physical thickness differs from compound layers: '+self.key)
        self.variable = variable_index
        self.layer_data = []
        for index,item in enumerate(self.layers):
            layer_high = low+total-sum(float(v.Width) for v in self.layers[:index])
            layer_low = layer_high-float(item.Width)
            if index==variable_index:
                layer_high=high
            solids = []
            if item.Width>EPS:
                for solid in self.solids:
                    piece=geo.clip(solid,self.normal,layer_low,layer_high)
                    if piece is not None:
                        solids.append(piece)
            self.layer_data.append(dict(index=index,low=layer_low,high=layer_high,
                width=float(item.Width),solids=solids,
                function_structure=item.Function==DB.MaterialFunctionAssignment.Structure,
                structural_material=index==int(cs.StructuralMaterialIndex)))
        signature = dict(layers=[(str(item.Function),float(item.Width)) for item in self.layers],
                         structural_material=int(cs.StructuralMaterialIndex),variable=variable_index)
        self.definition = hashlib.sha256(json.dumps(signature,sort_keys=True).encode('utf-8')).hexdigest()

    def support(self, layer_index):
        member = self.layer_data[layer_index]
        return member['low'] if not self.wall and self.variable>=0 else member['high']


def element_bounds(source,element):
    """Broad-phase fallback for a host whose detailed geometry is unsupported."""
    box = element.get_BoundingBox(None)
    if box is None:
        return None
    points = [source.transform.OfPoint(box.Transform.OfPoint(DB.XYZ(x,y,z)))
              for x in (box.Min.X,box.Max.X)
              for y in (box.Min.Y,box.Max.Y)
              for z in (box.Min.Z,box.Max.Z)]
    return [(min(getattr(p,axis) for p in points),max(getattr(p,axis) for p in points))
            for axis in ('X','Y','Z')]


def local_host_coverage(records, failed_bounds, cfg):
    """Return a passage-local uncertainty check; solids already use root coordinates.

    A failed layer interpretation does not imply that the physical Solid is bad.
    Extract it lazily, once per failed host, only after the local broad phase.
    """
    from hdl_openings import synchronization as sync
    cache = {}

    def check(payload, host_key):
        state = payload.get('state')
        source, element = records[host_key]
        link_name = source.link.Name if source.link is not None else 'CURRENT'
        try:
            mep_id = str(int(payload['mep_uid'].rsplit('-',1)[-1],16))
        except (ValueError, TypeError):
            mep_id = payload['mep_uid']
        label = 'link={}; host Id={}; MEP Id={}; stage=Local Solid'.format(
            link_name, id_value(element.Id), mep_id)
        if not state:
            # Legacy records cannot define a local volume. Preserve only their
            # own failed host memberships, rather than blocking the whole MEP.
            if host_key in [s+':'+u for s,u in sync.host_keys(payload)]:
                return 'Local coverage unavailable (legacy state); '+label
            return None
        try:
            probe = geo.opening_volume(state)
            try:
                bounds = geo.bbox([probe])
                host_bounds = failed_bounds[host_key]
                if host_bounds is not None and not sync.bounds_overlap(bounds, host_bounds):
                    return None
                if host_key not in cache:
                    try:
                        items = geo.solids(element, source.transform)
                        cache[host_key] = (items, None if items else 'No usable Solid')
                    except Exception as error:
                        cache[host_key] = ([], str(error))
                items, error = cache[host_key]
                if error:
                    return 'Local Solid unavailable; {}; {}'.format(label, error)
                for solid in items:
                    overlap = geo.intersect(probe, solid)
                    if overlap is not None:
                        overlap.Dispose()
                        return 'Local opening volume intersects unsupported host; '+label
                return None
            finally:
                probe.Dispose()
        except Exception as error:
            return 'Local geometry check uncertain; {}; {}'.format(label, error)
    return check
