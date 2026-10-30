# -*- coding: utf-8 -*-
"""Bind to an existing parallel planar surface; do not change the opening geometry."""
from Autodesk.Revit import DB


class FaceHostError(Exception):
    pass


def resolve(plan):
    host = plan['host']
    source = host.source
    structural_point = plan['support']
    normal = plan['normal']
    # Top and bottom can differ after shape editing. The structural normal was
    # calculated earlier; the reference side must not redefine that normal.
    sides = [('bottom',DB.HostObjectUtils.GetBottomFaces),('top',DB.HostObjectUtils.GetTopFaces)]
    preferred = 'bottom' if host.variable >= 0 else 'top'
    candidates, diagnostics = [], []
    for side, get_faces in sides:
        references = list(get_faces(host.element))
        diagnostics.append('{} references={}'.format(side,len(references)))
        for reference in references:
            face = host.element.GetGeometryObjectFromReference(reference)
            if not isinstance(face, DB.PlanarFace):
                diagnostics.append('{} nonplanar face'.format(side))
                continue
            world_normal = source.transform.OfVector(face.FaceNormal).Normalize()
            cosine = abs(world_normal.DotProduct(normal))
            if abs(cosine-1.) > 1e-6:
                diagnostics.append('{} normal cosine={:.8f}'.format(side,cosine))
                continue
            world_origin = source.transform.OfPoint(face.Origin)
            signed = structural_point.Subtract(world_origin).DotProduct(world_normal)
            face_point = structural_point.Subtract(world_normal.Multiply(signed))
            local_point = source.transform.Inverse.OfPoint(face_point)
            projection = face.Project(local_point)
            if projection is None or not face.IsInside(projection.UVPoint):
                diagnostics.append('{} insertion projection outside face; skipped'.format(side))
                continue
            target = reference.CreateLinkReference(source.link) if source.link else reference
            candidate = dict(reference=target,point=face_point,
                             structural_point=structural_point,face_normal=world_normal,
                             structural_offset=signed,reference_side=side)
            candidates.append((0 if side==preferred else 1,abs(signed),candidate))
    if candidates:
        return min(candidates,key=lambda item:(item[0],item[1]))[2]
    raise FaceHostError('No original planar host face parallel to base normal. Host: {}. {}. '
                        'No generated plane or changed insertion point.'.format(
                            host.key,'; '.join(diagnostics)))
