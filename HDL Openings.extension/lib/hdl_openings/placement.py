# -*- coding: utf-8 -*-
import math
from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import StructuralType
from hdl_openings.config import WIDTH, HEIGHT, DEPTH
from hdl_openings import storage, synchronization as sync


class FamilyContractError(Exception):
    pass


def parameter(element, name):
    matches = list(element.GetParameters(name))
    if len(matches) != 1:
        raise FamilyContractError('Expected one parameter: ' + name)
    p = matches[0]
    if p.IsReadOnly or p.StorageType != DB.StorageType.Double:
        raise FamilyContractError('Writable instance Length required: ' + name)
    # Revit 2022+ ForgeTypeId; older versions use ParameterType.
    try:
        is_length = p.Definition.GetDataType() == DB.SpecTypeId.Length
    except AttributeError:
        is_length = p.Definition.ParameterType == DB.ParameterType.Length
    if not is_length:
        raise FamilyContractError('Parameter must have Length specification: ' + name)
    return p


def set_value(element, name, value):
    p = parameter(element, name)
    if abs(p.AsDouble() - value) > 1e-8:
        if not p.Set(value):
            raise FamilyContractError('Parameter.Set failed: ' + name)


def symbols(doc, cfg):
    result = {}
    for name in cfg.families:
        found = [symbol for symbol in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol)
                 if symbol.Family.Name == name]
        if not found:
            raise FamilyContractError('Load family before running: ' + name)
        wall = name in (cfg.families.rect_wall,cfg.families.round_wall)
        expected = DB.FamilyPlacementType.OneLevelBased if wall else DB.FamilyPlacementType.WorkPlaneBased
        for symbol in found:
            if symbol.Family.FamilyPlacementType != expected:
                raise FamilyContractError('Incorrect family placement type: ' + name)
            flag=symbol.Family.get_Parameter(DB.BuiltInParameter.FAMILY_ALWAYS_VERTICAL)
            if flag is not None and flag.AsInteger() != int(wall):
                raise FamilyContractError('Incorrect Always Vertical flag: ' + name)
        result[name] = found
    return result


def align(doc, instance, origin, normal, target_x):
    transform = instance.GetTransform()
    actual = transform.BasisX.Normalize()
    angle = math.atan2(normal.DotProduct(actual.CrossProduct(target_x)),
                       actual.DotProduct(target_x))
    if abs(angle) > 1e-8:
        axis = DB.Line.CreateBound(origin, origin.Add(normal))
        DB.ElementTransformUtils.RotateElement(doc, instance.Id, axis, angle)
        doc.Regenerate()


def insertion_sample(instance, stage):
    p = instance.Location.Point
    return stage, (p.X, p.Y, p.Z)


def insertion_error(plan, family_name, level, origin, samples):
    def mm(values):
        return '({:.3f}, {:.3f}, {:.3f})'.format(*[v*304.8 for v in values])
    target = (origin.X, origin.Y, origin.Z)
    history = []
    for stage, point in samples:
        delta = tuple(a-b for a,b in zip(point,target))
        history.append('{}: actual_mm={}, delta_mm={}'.format(stage,mm(point),mm(delta)))
    return ('Insertion mismatch; family={}; host={}; mep={}; '
            'level_uid={}; level_project_z_mm={:.3f}; target_mm={}; {}').format(
                family_name, plan['host'].key, plan['mep'].key,
                level.UniqueId, level.ProjectElevation*304.8, mm(target), '; '.join(history))


def create(doc, plan, chosen, level, run_id, payload=None):
    host = plan['host']
    families = plan['settings'].families
    family_name = ((families.round_wall if host.wall else families.round_floor)
                   if plan['shape'] == 'round' else
                   (families.rect_wall if host.wall else families.rect_floor))
    symbol = chosen[family_name]
    if not symbol.IsActive:
        symbol.Activate()
        doc.Regenerate()
    origin, normal, x = plan['insertion'], plan['normal'], plan['x']
    support_reference = None
    samples = []
    if host.wall:
        # The level-based overload adds the level elevation to the input Z.
        # Plans and synchronization remain in current-document model coordinates.
        level_point = DB.XYZ(origin.X, origin.Y, origin.Z-level.ProjectElevation)
        instance = doc.Create.NewFamilyInstance(level_point, symbol, level,
                                                StructuralType.NonStructural)
        doc.Regenerate()
        samples.append(insertion_sample(instance,'wall created'))
        # Local +Y is depth and local +Z is vertical for the wall family.
        actual = instance.GetTransform().BasisY.Normalize()
        angle = math.atan2(DB.XYZ.BasisZ.DotProduct(actual.CrossProduct(normal)),
                           actual.DotProduct(normal))
        DB.ElementTransformUtils.RotateElement(
            doc, instance.Id, DB.Line.CreateBound(origin, origin.Add(DB.XYZ.BasisZ)), angle)
        doc.Regenerate()
        samples.append(insertion_sample(instance,'wall rotated'))
    else:
        face_host = plan['face_host']
        point = face_host['point']
        reference = face_host['reference']
        instance = doc.Create.NewFamilyInstance(reference, point, x, symbol)
        doc.Regenerate()
        samples.append(insertion_sample(instance,'face hosted'))
        if instance.GetTransform().BasisZ.Normalize().DotProduct(normal) < 0:
            if not instance.CanFlipWorkPlane:
                raise FamilyContractError('Floor family cannot invert the bottom-face work plane')
            instance.IsWorkPlaneFlipped = not instance.IsWorkPlaneFlipped
            doc.Regenerate()
        support_reference = reference.ConvertToStableRepresentation(doc)
        offset = instance.get_Parameter(DB.BuiltInParameter.INSTANCE_FREE_HOST_OFFSET_PARAM)
        if offset is None or offset.IsReadOnly:
            raise FamilyContractError('Floor family requires writable work-plane offset')
        offset.Set(origin.Subtract(point).DotProduct(face_host['face_normal']))
        doc.Regenerate()
        samples.append(insertion_sample(instance,'face offset'))
        align(doc, instance, origin, normal, x)
    doc.Regenerate()
    tf = instance.GetTransform()
    depth_axis = tf.BasisY if host.wall else tf.BasisZ
    if depth_axis.Normalize().DotProduct(normal) < .99999:
        raise FamilyContractError('Family depth axis differs from required normal')
    height_axis = tf.BasisZ if host.wall else tf.BasisY
    if height_axis.Normalize().DotProduct(plan['y']) < .99999:
        raise FamilyContractError('Family height axis differs from required axis')
    if tf.BasisX.Normalize().DotProduct(x) < .99999:
        raise FamilyContractError('Family width axis differs from required axis')
    dimensions = [('Diameter',plan['diameter'])] if plan['shape']=='round' else [(WIDTH,plan['width']),(HEIGHT,plan['height'])]
    dimensions.append((DEPTH,plan['depth']))
    for name, value in dimensions:
        set_value(instance, name, value)
        doc.Regenerate()
        samples.append(insertion_sample(instance,'set '+name))
    doc.Regenerate()
    location = instance.Location
    if not isinstance(location, DB.LocationPoint):
        raise FamilyContractError('Point-based family required')
    if location.Point.DistanceTo(origin) > 1e-5:
        raise FamilyContractError(insertion_error(plan,family_name,level,origin,samples))
    if payload is None:
        raise FamilyContractError('Synchronization payload required')
    if not sync.same_state(actual_state(instance,host.wall),payload['state'],
                           plan['settings'].sync_length,plan['settings'].sync_direction):
        raise FamilyContractError('Created instance differs from synchronization target')
    storage.write(instance, payload)
    return instance


def actual_state(instance, wall):
    """Read actual geometry so manual edits cannot hide behind stored metadata."""
    tf = instance.GetTransform()
    def xyz(v):
        return [v.X, v.Y, v.Z]
    shape = 'round' if list(instance.GetParameters('Diameter')) else 'rect'
    state = dict(insertion=xyz(instance.Location.Point), x=xyz(tf.BasisX.Normalize()),
        y=xyz((tf.BasisZ if wall else tf.BasisY).Normalize()),
        normal=xyz((tf.BasisY if wall else tf.BasisZ).Normalize()),
        shape=shape, family=instance.Symbol.Family.Name,
        symbol_uid=instance.Symbol.UniqueId, reference=None,
        depth=parameter(instance, DEPTH).AsDouble())
    if not wall:
        reference = instance.HostFace
        if reference is not None:
            state['reference'] = reference.ConvertToStableRepresentation(instance.Document)
    for name in (('Diameter',) if shape=='round' else (WIDTH, HEIGHT)):
        state[name.lower()] = parameter(instance, name).AsDouble()
    return state
