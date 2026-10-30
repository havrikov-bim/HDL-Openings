# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""Volumes follow the four accepted BL family insertion conventions."""
from Autodesk.Revit import DB
from hdl_openings.mep_labels import text_type
from hdl_openings import geometry as geo
from hdl_openings.model import Source, collect, MEP_CATEGORIES, id_value, element_bounds
from hdl_openings.mep_labels import qualifies
from hdl_openings.config import MM, EPS


def length(element, name):
    parameters = list(element.GetParameters(name))
    if len(parameters) != 1 or parameters[0].StorageType != DB.StorageType.Double:
        raise ValueError('Expected one instance length: ' + name)
    value = parameters[0].AsDouble()
    if value <= EPS:
        raise ValueError('Nonpositive opening dimension: ' + name)
    return value


class Opening(object):
    def __init__(self, element, families):
        self.element = element
        name = element.Symbol.Family.Name
        wall = name in (families.rect_wall, families.round_wall)
        circular = name in (families.round_wall, families.round_floor)
        tf = element.GetTransform()
        x = tf.BasisX.Normalize()
        y = (tf.BasisZ if wall else tf.BasisY).Normalize()
        self.normal = (tf.BasisY if wall else tf.BasisZ).Normalize()
        if not isinstance(element.Location, DB.LocationPoint):
            raise ValueError('Opening requires LocationPoint')
        origin = element.Location.Point
        self.depth = length(element, 'Depth')
        z0 = origin.DotProduct(self.normal)
        nr = (z0, z0+self.depth) if wall else (z0-self.depth, z0)
        self.low, self.high = nr
        if circular:
            self.solid = geo.cylinder(x, y, self.normal, origin, length(element, 'Diameter'), nr)
        else:
            width, height = length(element, 'Width'), length(element, 'Height')
            xx, yy = origin.DotProduct(x), origin.DotProduct(y)
            yr = (yy, yy+height) if wall else (yy-height/2., yy+height/2.)
            self.solid = geo.prism(x, y, self.normal, (xx-width/2., xx+width/2.), yr, nr)
        self.bounds = geo.bbox([self.solid])


class Candidate(object):
    def __init__(self, source, element):
        self.source, self.element = source, element
        self.key = source.element_key(element)
        self.solids = None
        self.error = None
        self.curve = None
        self.bounds = None
        try:
            self.bounds = element_bounds(source, element)
            cat = id_value(element.Category.Id)
            self.insulation = []
            if cat in (int(DB.BuiltInCategory.OST_PipeCurves), int(DB.BuiltInCategory.OST_DuctCurves)):
                for eid in DB.InsulationLiningBase.GetInsulationIds(source.doc, element.Id):
                    item = source.doc.GetElement(eid)
                    if item is None or item.Thickness < 0:
                        raise ValueError('Insulation data unavailable')
                    self.insulation.append(item)
                    # Includes envelope, even when the primary element bbox excludes it.
                    other = element_bounds(source, item)
                    if other is None:
                        self.bounds = None
                        break
                    if self.bounds is not None:
                        self.bounds = [(min(a[0],b[0]),max(a[1],b[1])) for a,b in zip(self.bounds,other)]
        except Exception as error:
            self.error = text_type(error)
            self.bounds = None

    def geometry(self):
        if self.error:
            raise ValueError(self.error)
        if self.solids is None:
            try:
                self.solids = geo.solids(self.element, self.source.transform)
                if not self.solids:
                    raise ValueError('No usable MEP solid')
                for insulation in self.insulation:
                    extra = geo.solids(insulation, self.source.transform)
                    if insulation.Thickness > 0 and not extra:
                        raise ValueError('Insulation geometry unavailable')
                    self.solids.extend(extra)
                location = self.element.Location
                if not isinstance(location, DB.LocationCurve):
                    raise ValueError('MEP requires LocationCurve')
                self.curve = location.Curve.CreateTransformed(self.source.transform)
                self.bounds = geo.bbox(self.solids)
            except Exception as error:
                self.error = text_type(error)
                raise

    def inside(self, opening, threshold, tolerance):
        self.geometry()
        if not geo.overlaps(self.bounds, opening.bounds):
            return None
        pieces = []
        try:
            for solid in self.solids:
                piece = geo.intersect(solid, opening.solid)
                if piece is not None:
                    pieces.append(piece)
            if not pieces:
                return None
            # Each connected solid must independently satisfy the normal-depth rule.
            entry = 0.
            for piece in pieces:
                low, high = geo.solid_range(piece, opening.normal)
                entry = max(entry, min(high, opening.high)-max(low, opening.low))
            options = DB.SolidCurveIntersectionOptions()
            intersection = None
            try:
                intersection = opening.solid.IntersectWithCurve(self.curve, options)
                total = sum(intersection.GetCurveSegment(i).Length for i in range(intersection.SegmentCount))
                full_segment = abs(total-self.curve.Length) <= tolerance
            finally:
                if intersection is not None:
                    intersection.Dispose()
                options.Dispose()
            if not qualifies(entry, opening.depth, full_segment, threshold, tolerance):
                return None
            reason = ('Full segment' if full_segment else
                      'Through' if entry >= opening.depth-tolerance else 'Entry > threshold')
            return dict(entry_mm=round(entry/MM, 6), rule=reason)
        finally:
            for piece in pieces:
                piece.Dispose()

    def classification(self, mapping):
        cat = id_value(self.element.Category.Id)
        category = ('Conduits' if cat == int(DB.BuiltInCategory.OST_Conduit) else
                    'Cable Trays' if cat == int(DB.BuiltInCategory.OST_CableTray) else None)
        type_name = ''
        if category:
            label, discipline = mapping.resolve(category=category)
        else:
            system = self.element.MEPSystem
            if system is None:
                raise ValueError('MEP system not assigned: ' + self.key)
            typ = self.source.doc.GetElement(system.GetTypeId())
            if typ is None:
                raise ValueError('System type not available: ' + self.key)
            type_name = text_type(DB.Element.Name.GetValue(typ))
            label, discipline = mapping.resolve(system_type=type_name)
        return dict(source=text_type(self.source.key), element_unique_id=text_type(self.element.UniqueId),
                    link_instance_unique_id=text_type(self.source.link.UniqueId) if self.source.link else None,
                    source_title=text_type(self.source.doc.Title),
                    category=text_type(category or self.element.Category.Name),
                    system_type=type_name, label=label, discipline=discipline)


def gather(doc):
    sources = [Source(doc, DB.Transform.Identity)]
    unavailable = []
    for link in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance):
        linked = link.GetLinkDocument()
        if linked is None:
            unavailable.append(link.UniqueId)
        else:
            sources.append(Source(linked, link.GetTotalTransform(), link))
    candidates = []
    for source in sources:
        for element in collect(source, MEP_CATEGORIES):
            candidates.append(Candidate(source, element))
    return candidates, unavailable
