# -*- coding: utf-8 -*-
import math
from Autodesk.Revit import DB
from hdl_openings import geometry as geo
from hdl_openings.config import EPS
from hdl_openings.math_core import merge_intervals, insertion_coordinates, may_extend_group
from hdl_openings.section_math import layer_normal_interval
from hdl_openings.opening_math import ceil_step, choose_round, round_requirement


def xyz(vector):
    return (vector.X, vector.Y, vector.Z)


def layer_range(mep, host, layer, normal):
    return layer_normal_interval(xyz(mep.origin), xyz(mep.axis), xyz(host.normal),
                                 layer['low'], layer['high'], xyz(normal))


def passage_anchor(mep,host,layer):
    mid = (layer['low']+layer['high'])/2.
    denominator = mep.axis.DotProduct(host.normal)
    if abs(denominator)<=EPS:
        return mep.origin.Add(host.normal.Multiply(mid-mep.origin.DotProduct(host.normal)))
    return mep.origin.Add(mep.axis.Multiply((mid-mep.origin.DotProduct(host.normal))/denominator))


def base_rank(passage):
    host,layer = passage['host'],passage['layer']
    anchor = passage.get('anchor',host.normal.Multiply((layer['low']+layer['high'])/2.))
    reference = getattr(host,'reference_point',(0.,0.,0.))
    distance_sq = sum((xyz(anchor)[i]-reference[i])**2 for i in range(3))
    eligible = bool(getattr(host,'is_structural',False)) and layer['index']==host.base_index
    return (not eligible,-layer['width'],distance_sq,anchor.Z,anchor.X,anchor.Y,host.key,layer['index'])


def detect(mep, hosts, cfg):
    gap_limit = cfg.gap
    passages = []
    for host in hosts:
        if not geo.overlaps(mep.bounds, host.bounds):
            continue
        for layer in host.layer_data:
            hits = []
            for a in mep.solids:
                for b in layer['solids']:
                    hit = geo.intersect(a, b)
                    if hit is not None:
                        hits.append(hit)
            if hits:
                passages.append(dict(host=host,layer=layer,hits=hits,anchor=passage_anchor(mep,host,layer)))
    # Separate normal directions: a floor and a wall cannot share a gap coordinate.
    buckets = []
    for passage in sorted(passages, key=base_rank):
        normal = passage['host'].normal
        for reference, items in buckets:
            if abs(abs(normal.DotProduct(reference))-1.) <= 1e-6:
                items.append(passage)
                break
        else:
            buckets.append((normal, [passage]))
    result = []
    for normal, items in buckets:
        records = []
        for passage in items:
            low, high = layer_range(mep, passage['host'], passage['layer'], normal)
            records.append((low, high, passage))
        # EPS is the numeric length tolerance, not an angular gap correction.
        result.extend(merge_intervals(records, gap_limit+EPS))
    return result


def plan_group(mep, group, all_hosts, other_layers, cfg):
    CLEARANCE, GAP, TOUCH, K_SLOPE = cfg.clearance, cfg.gap, cfg.touch, cfg.k_slope
    passages = group[2]
    candidates = [p for p in passages
                  if p['host'].is_structural and p['layer']['index'] == p['host'].base_index]
    if not candidates:
        return None, 'No layer with Function=Structure [1] AND Structural Material=Yes; opening not created'
    for candidate in candidates:
        candidate['anchor'] = passage_anchor(mep,candidate['host'],candidate['layer'])
    base = sorted(candidates,key=base_rank)[0]
    host, layer = base['host'], base['layer']
    normal = host.normal
    entry = geo.combined_range(base['hits'], normal)
    if entry[1] - entry[0] <= TOUCH + EPS:
        return None, 'Touch only'
    trace_length = mep.axis_trace(normal, layer['low'], layer['high'])
    if trace_length > K_SLOPE * layer['width'] + EPS:
        return None, ('K_slope exceeded: axis trace={:.2f} mm, base={:.2f} mm, '
                      'ratio={:.4f}, limit={:.4f}').format(
                          trace_length * 304.8, layer['width'] * 304.8,
                          trace_length / layer['width'], K_SLOPE)
    x, y = geo.frame(normal, host.wall)
    # Work with layer solids, never whole hosts: a host can contain separated layers.
    selected_passages = passages if cfg.through_all else [base]
    selected = {(p['host'].key,p['layer']['index']):p['layer'] for p in selected_passages}
    selected_interactions = dict(((p['host'].key,p['layer']['index']),
        ('MEP',list(geo.combined_range(p['hits'],normal)))) for p in selected_passages)

    def envelope(layers):
        solids = [solid for item in layers for solid in item['solids']]
        nr = geo.combined_range(solids, normal)
        xr = mep.sweep(normal, nr[0], nr[1], x)
        yr = mep.sweep(normal, nr[0], nr[1], y)
        cx, cy = (xr[0]+xr[1])/2., (yr[0]+yr[1])/2.
        w = ceil_step(xr[1]-xr[0]+2*CLEARANCE,cfg.rect_step)
        h = ceil_step(yr[1]-yr[0]+2*CLEARANCE,cfg.rect_step)
        xr, yr = (cx-w/2.,cx+w/2.), (cy-h/2.,cy+h/2.)
        return solids, nr, xr, yr

    host_solids, nr, xr, yr = envelope(list(selected.values()))
    # The probe can discover layers missed by the original MEP cross-section.
    # Its padding is search-only; candidate layers must still satisfy T_gap.
    probe = geo.prism(x, y, normal, xr, yr, (nr[0]-GAP, nr[1]+GAP))
    probe_bounds = geo.bbox([probe])
    for candidate_host in (all_hosts if cfg.through_all else []):
        if abs(abs(candidate_host.normal.DotProduct(normal))-1.) > 1e-6:
            continue
        if not geo.overlaps(candidate_host.bounds, probe_bounds):
            continue
        for candidate_layer in candidate_host.layer_data:
            layer_key = (candidate_host.key, candidate_layer['index'])
            if layer_key in selected or layer_key in other_layers:
                continue
            hits = []
            for solid in candidate_layer['solids']:
                hit = geo.intersect(probe, solid)
                if hit is not None:
                    hits.append(hit)
            if not hits:
                continue
            interval = layer_range(mep, candidate_host, candidate_layer, normal)
            selected_solids = [solid for item in selected.values() for solid in item['solids']]
            selected_range = geo.combined_range(selected_solids, normal)
            if may_extend_group(selected_range, interval, GAP+EPS, False):
                selected[layer_key] = candidate_layer
                selected_interactions[layer_key] = ('opening_probe',list(geo.combined_range(hits,normal)))
    host_solids, nr, xr, yr = envelope(list(selected.values()))
    width, height = xr[1]-xr[0], yr[1]-yr[0]
    temporary = geo.prism(x, y, normal, xr, yr, (nr[0]-EPS, nr[1]+EPS))
    actual = []
    for solid in host_solids:
        hit = geo.intersect(temporary, solid)
        if hit is not None:
            actual.append(hit)
    if not actual:
        raise geo.UnsupportedGeometry('Second-pass intersection is empty')
    nr = geo.combined_range(actual, normal)
    shape, diameter, shape_reason = 'rect', None, None
    round_check = None
    if mep.round_eligible and mep.circular is True:
        # Select one core from insulated OD+2t; never upsize to fit a tilted passage.
        core, shape_reason = choose_round(2*mep.hw,1.,0.,CLEARANCE,cfg.cores,cfg.max_core_depth)
        cosine = min(1.,abs(mep.axis.DotProduct(normal)))
        round_check = dict(effective_diameter=2*mep.hw, clearance=CLEARANCE,
            initial_diameter=2*mep.hw+2*CLEARANCE, selected_core=core,
            cosine=cosine, angle_deg=math.degrees(math.acos(cosine)),
            depth=nr[1]-nr[0], depth_source='rectangular_probe',
            required_diameter=(round_requirement(2*mep.hw,cosine,nr[1]-nr[0],CLEARANCE) if cosine>0 else None),
            hit_count=0,iterations=0)
        if core is not None:
            trial_nr = nr
            round_hits = []
            for unused in range(8):
                round_check['iterations'] = unused+1
                rx = mep.sweep(normal,trial_nr[0],trial_nr[1],x)
                ry = mep.sweep(normal,trial_nr[0],trial_nr[1],y)
                axis_center = x.Multiply(sum(rx)/2.).Add(y.Multiply(sum(ry)/2.))
                full_nr = geo.combined_range(host_solids,normal)
                volume = geo.cylinder(x,y,normal,axis_center,core,
                                      (full_nr[0]-EPS,full_nr[1]+EPS))
                round_hits = []
                for solid in host_solids:
                    hit = geo.intersect(volume,solid)
                    if hit is not None:
                        round_hits.append(hit)
                round_check['hit_count'] = len(round_hits)
                round_check['probe_center'] = list(xyz(axis_center.Add(normal.Multiply(sum(full_nr)/2.))))
                if not round_hits:
                    shape_reason = 'Circular volume has no construction intersection'
                    break
                next_nr = geo.combined_range(round_hits,normal)
                round_check.update(depth=next_nr[1]-next_nr[0],depth_source='circular_intersection',
                    required_diameter=(round_requirement(2*mep.hw,cosine,next_nr[1]-next_nr[0],CLEARANCE) if cosine>0 else None))
                if max(abs(next_nr[i]-trial_nr[i]) for i in (0,1)) <= EPS:
                    actual_core, shape_reason = choose_round(
                        2*mep.hw,abs(mep.axis.DotProduct(normal)),next_nr[1]-next_nr[0],
                        CLEARANCE,cfg.cores,cfg.max_core_depth)
                    if actual_core is not None:
                        shape,diameter,nr = 'round',actual_core,next_nr
                        xr = (sum(rx)/2.-diameter/2.,sum(rx)/2.+diameter/2.)
                        yr = (sum(ry)/2.-diameter/2.,sum(ry)/2.+diameter/2.)
                    break
                trial_nr = next_nr
            else:
                shape_reason = 'Circular depth did not converge; rectangular fallback'
    if shape_reason and round_check:
        core_text = ('none' if round_check['selected_core'] is None else
                     '{:.2f} mm ({:.3f} in)'.format(round_check['selected_core']*304.8,
                                                  round_check['selected_core']*12.))
        shape_reason += ('; host={}; D_e={:.2f} mm; D_0={:.2f} mm; core={}; '
                         'D_required={}; depth={:.2f} mm [{}]; angle={:.4f} deg; '
                         'circular_hits={}; iterations={}').format(
            host.key,round_check['effective_diameter']*304.8,round_check['initial_diameter']*304.8,
            core_text,('undefined' if round_check['required_diameter'] is None else
                       '{:.2f} mm'.format(round_check['required_diameter']*304.8)),round_check['depth']*304.8,
            round_check['depth_source'],round_check['angle_deg'],round_check['hit_count'],
            round_check['iterations'])
        if not round_check['hit_count'] and 'probe_center' in round_check:
            shape_reason += '; probe_center_mm=({:.2f}, {:.2f}, {:.2f})'.format(
                *[c*304.8 for c in round_check['probe_center']])
    center = (x.Multiply((xr[0]+xr[1])/2.)
              .Add(y.Multiply((yr[0]+yr[1])/2.))
              .Add(normal.Multiply((nr[0]+nr[1])/2.)))
    if shape == 'round':
        insertion = (x.Multiply((xr[0]+xr[1])/2.)
                     .Add(y.Multiply((yr[0]+yr[1])/2.))
                     .Add(normal.Multiply(nr[0] if host.wall else nr[1])))
    else:
        ix, iy, iz = insertion_coordinates(xr,yr,nr,host.wall)
        insertion = x.Multiply(ix).Add(y.Multiply(iy)).Add(normal.Multiply(iz))
    support_coordinate = host.support(layer['index'])
    support_point = center.Add(normal.Multiply(support_coordinate - center.DotProduct(normal)))
    sweep_key = geo.combined_range(host_solids, normal)
    key = '{}|{}|{}|{:.8f}|{:.8f}'.format(
        mep.key, host.key, layer['index'], sweep_key[0], sweep_key[1])
    host_by_key = dict((h.key, h) for h in all_hosts)
    participants = []
    for (host_key, layer_index), selected_layer in sorted(selected.items()):
        selected_host = host_by_key[host_key]
        interval = layer_range(mep, selected_host, selected_layer, normal)
        participants.append(dict(source=selected_host.source.key,
            uid=selected_host.element.UniqueId, layer=layer_index, definition=selected_host.definition,
            normal_interval=list(interval),
            function_structure=selected_layer.get('function_structure',layer_index==selected_host.base_index),
            structural_material=selected_layer.get('structural_material',layer_index==selected_host.base_index),
            width=selected_layer['width'],
            detection=selected_interactions[(host_key,layer_index)][0],
            intersection_range=selected_interactions[(host_key,layer_index)][1]))
    interaction = dict(axis_origin=list(xyz(mep.origin)), axis=list(xyz(mep.axis)),
        axis_length=mep.length, u=list(xyz(mep.u)), v=list(xyz(mep.v)),
        half_width=mep.hw, half_height=mep.hh, profile=mep.circular,
        insulation=mep.insulation, normal=list(xyz(normal)),
        normal_range=list(nr), x_range=list(xr), y_range=list(yr),
        support=list(xyz(support_point)), reference_side=None, round_check=round_check,
        through_all=cfg.through_all,project_base_point=list(getattr(host,'reference_point',(0.,0.,0.))))
    return dict(key=key, mep=mep, host=host, layer=layer['index'],
                participants=participants, interaction=interaction,
                base_selection=dict(structural=bool(getattr(host,'is_structural',False)),
                    width=layer['width'],rank=list(base_rank(base)),distance_to_pbp=math.sqrt(base_rank(base)[2])),
                shape=shape, diameter=diameter, shape_reason=shape_reason, round_check=round_check,
                settings=cfg, center=center, insertion=insertion, support=support_point, normal=normal,
                x=x, y=y, width=width, height=height, depth=nr[1] - nr[0]), None


def plan(mep, hosts, cfg):
    result, reasons = [], []
    groups = detect(mep, hosts, cfg)
    for index, group in enumerate(groups):
        other_layers = set((p['host'].key, p['layer']['index'])
                           for j, other in enumerate(groups) if j != index
                           for p in other[2])
        opening, reason = plan_group(mep, group, hosts, other_layers, cfg)
        if opening:
            result.append(opening)
        else:
            reasons.append(reason)
    return result, reasons
