# -*- coding: utf-8 -*-
import math
from Autodesk.Revit import DB
from System.Collections.Generic import List
from hdl_openings.config import EPS, VOLUME_EPS


class UnsupportedGeometry(Exception):
    pass


def solids(element, transform):
    options = DB.Options()
    options.DetailLevel = DB.ViewDetailLevel.Fine
    options.IncludeNonVisibleObjects = False
    def visit(geo):
        for item in geo:
            if isinstance(item, DB.Solid) and item.Volume > VOLUME_EPS:
                yield DB.SolidUtils.CreateTransformed(item, transform)
            elif isinstance(item, DB.GeometryInstance):
                for solid in visit(item.GetInstanceGeometry()):
                    yield solid
    geo = element.get_Geometry(options)
    return list(visit(geo)) if geo else []


def solid_range(solid, direction):
    """Revit kernel bounds in a frame aligned with direction; no edge access.

    Used only for host/Boolean depth and broad-phase bounds, not MEP section sizing.
    Kernel bounding boxes are conservative, including at trimmed curved faces.
    """
    z = direction.Normalize()
    x, y = frame(z, False)
    transform = DB.Transform.Identity
    transform.BasisX, transform.BasisY, transform.BasisZ = x, y, z
    aligned = DB.SolidUtils.CreateTransformed(solid, transform.Inverse)
    try:
        box = aligned.GetBoundingBox()
        values = [box.Transform.OfPoint(DB.XYZ(xx, yy, zz)).Z
                  for xx in (box.Min.X, box.Max.X)
                  for yy in (box.Min.Y, box.Max.Y)
                  for zz in (box.Min.Z, box.Max.Z)]
        return min(values), max(values)
    finally:
        aligned.Dispose()


def combined_range(items, direction):
    rr = [solid_range(s, direction) for s in items]
    if not rr:
        raise UnsupportedGeometry('Empty geometry range')
    return min(r[0] for r in rr), max(r[1] for r in rr)


def intersect(a, b):
    # Boolean failures propagate to diagnostic report, never interpreted as no clash.
    result = DB.BooleanOperationsUtils.ExecuteBooleanOperation(
        a, b, DB.BooleanOperationsType.Intersect)
    return result if result.Volume > VOLUME_EPS else None


def clip(solid, normal, low, high):
    a = DB.Plane.CreateByNormalAndOrigin(normal, normal.Multiply(low))
    b = DB.Plane.CreateByNormalAndOrigin(normal.Negate(), normal.Multiply(high))
    first = DB.BooleanOperationsUtils.CutWithHalfSpace(solid, a)
    if first is None or first.Volume <= VOLUME_EPS:
        return None
    second = DB.BooleanOperationsUtils.CutWithHalfSpace(first, b)
    return second if second is not None and second.Volume > VOLUME_EPS else None


def frame(normal, wall):
    if wall:
        y = DB.XYZ.BasisZ
        x = normal.CrossProduct(y).Normalize()
    else:
        trial = DB.XYZ.BasisX
        if abs(trial.DotProduct(normal)) > .95:
            trial = DB.XYZ.BasisY
        x = trial.Subtract(normal.Multiply(trial.DotProduct(normal))).Normalize()
        y = normal.CrossProduct(x).Normalize()
    return x, y


def prism(x, y, normal, xr, yr, nr):
    # Ensure right handed profile independent of wall frame orientation.
    p = [x.Multiply(xr[0]).Add(y.Multiply(yr[0])).Add(normal.Multiply(nr[0])),
         x.Multiply(xr[1]).Add(y.Multiply(yr[0])).Add(normal.Multiply(nr[0])),
         x.Multiply(xr[1]).Add(y.Multiply(yr[1])).Add(normal.Multiply(nr[0])),
         x.Multiply(xr[0]).Add(y.Multiply(yr[1])).Add(normal.Multiply(nr[0]))]
    loop = DB.CurveLoop()
    for i in range(4):
        loop.Append(DB.Line.CreateBound(p[i], p[(i + 1) % 4]))
    loops = List[DB.CurveLoop]()
    loops.Add(loop)
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(
        loops, normal, nr[1] - nr[0])


def bbox(items):
    axes = [DB.XYZ.BasisX, DB.XYZ.BasisY, DB.XYZ.BasisZ]
    return [combined_range(items, axis) for axis in axes]


def overlaps(a, b):
    return all(a[i][0] <= b[i][1] + EPS and b[i][0] <= a[i][1] + EPS
               for i in range(3))


def cylinder(x, y, normal, center, diameter, nr):
    origin = center.Add(normal.Multiply(nr[0]-center.DotProduct(normal)))
    radius = diameter/2.
    a = origin.Add(x.Multiply(radius))
    b = origin.Subtract(x.Multiply(radius))
    loop = DB.CurveLoop()
    loop.Append(DB.Arc.Create(a,b,origin.Add(y.Multiply(radius))))
    loop.Append(DB.Arc.Create(b,a,origin.Subtract(y.Multiply(radius))))
    loops = List[DB.CurveLoop]()
    loops.Add(loop)
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(loops,normal,nr[1]-nr[0])


def opening_volume(state):
    """Physical opening envelope, including the clearance already in its size.

    Reconstruct from stored or desired state, never from the full pipe extent.
    Wall rectangles start at bottom/start depth; floor origins are top/centre.
    """
    point = DB.XYZ(*state['insertion'])
    x, y, normal = [DB.XYZ(*state[name]) for name in ('x','y','normal')]
    wall = state['family'].endswith('Wall')
    depth = float(state['depth'])
    n = point.DotProduct(normal)
    nr = (n,n+depth) if wall else (n-depth,n)
    if depth <= EPS:
        raise UnsupportedGeometry('Invalid local opening depth')
    if state['shape'] == 'round':
        return cylinder(x,y,normal,point,float(state['diameter']),nr)
    width, height = float(state['width']), float(state['height'])
    cx, cy = point.DotProduct(x), point.DotProduct(y)
    yr = (cy,cy+height) if wall else (cy-height/2.,cy+height/2.)
    return prism(x,y,normal,(cx-width/2.,cx+width/2.),yr,nr)
