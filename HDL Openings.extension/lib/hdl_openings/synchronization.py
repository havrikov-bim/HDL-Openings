# -*- coding: utf-8 -*-
"""Pure reconciliation. Coordinates are state, never passage identity."""
import copy
import math
import uuid

PAYLOAD_VERSION = 7
ALGORITHM_VERSION = '0.8.3'
OWNER = 'HDL Openings'


try:
    STRING_TYPES = (basestring,)
    INTEGER_TYPES = (int, long)
except NameError:
    STRING_TYPES = (str,)
    INTEGER_TYPES = (int,)


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError('Stored payload must be an object')
    version = payload.get('version')
    if isinstance(version,bool) or not isinstance(version,INTEGER_TYPES):
        raise ValueError('Stored payload version missing or invalid')
    for key in ('mep_source','mep_uid','host_source','host_uid'):
        if not isinstance(payload.get(key),STRING_TYPES) or not payload[key]:
            raise ValueError('Stored identity missing: '+key)
    if version in (4,5,6,PAYLOAD_VERSION):
        if payload.get('owner') != OWNER:
            raise ValueError('Stored owner mismatch')
        payload['opening_guid'] = str(uuid.UUID(payload['opening_guid']))
        records = payload.get('participants')
        if not isinstance(records,list) or not records:
            raise ValueError('Stored participants missing')
        for item in records:
            if not isinstance(item,dict):
                raise ValueError('Invalid participant')
            for key in ('source','uid'):
                if not isinstance(item.get(key),STRING_TYPES) or not item[key]:
                    raise ValueError('Invalid participant identity')
            if version == PAYLOAD_VERSION and (not isinstance(item.get('definition'),STRING_TYPES)
                    or len(item['definition'])!=64
                    or any(c not in '0123456789abcdef' for c in item['definition'])):
                raise ValueError('Invalid construction signature')
            if isinstance(item.get('layer'),bool) or not isinstance(item.get('layer'),INTEGER_TYPES):
                raise ValueError('Invalid participant layer')
        if not isinstance(payload.get('state'),dict):
            raise ValueError('Stored state missing')
    # Incompatible versions are identifiable but will be retained without mutation.
    return payload


def finite(value):
    number = float(value)
    if math.isnan(number) or math.isinf(number):
        raise ValueError('Nonfinite geometry')
    return number


def vector(value):
    return [value.X, value.Y, value.Z]


def family_name(plan):
    f = plan['settings'].families
    if plan['shape'] == 'round':
        return f.round_wall if plan['host'].wall else f.round_floor
    return f.rect_wall if plan['host'].wall else f.rect_floor


def desired_payload(plan, symbol_uid, run_id='', opening_guid=None):
    mep, host = plan['mep'], plan['host']
    state = dict(insertion=vector(plan['insertion']), normal=vector(plan['normal']),
                 x=vector(plan['x']), y=vector(plan['y']), shape=plan['shape'],
                 family=family_name(plan), symbol_uid=symbol_uid,
                 depth=plan['depth'], reference=plan.get('reference_key'))
    if plan['shape'] == 'round':
        state['diameter'] = plan['diameter']
    else:
        state.update(width=plan['width'], height=plan['height'])
    return dict(version=PAYLOAD_VERSION, owner=OWNER,
                algorithm_version=ALGORITHM_VERSION, opening_guid=opening_guid,
                key=plan['key'], run_id=run_id, mep_uid=mep.element.UniqueId,
                mep_source=mep.source.key, host_uid=host.element.UniqueId,
                host_source=host.source.key, layer_index=plan['layer'],
                participants=copy.deepcopy(plan['participants']), interaction=copy.deepcopy(plan['interaction']),
                insertion=state['insertion'], host_face_reference=state['reference'],
                shape=plan['shape'], insulation=mep.insulation,
                settings_fingerprint=plan['settings'].fingerprint, state=state,
                units='Revit internal feet; unit direction vectors')


def mep_key(payload):
    return (payload['mep_source'], payload['mep_uid'])


def participants(payload):
    return set((p['source'], p['uid'], p['layer']) for p in payload['participants'])


def host_keys(payload):
    if payload.get('participants'):
        return set((p['source'], p['uid']) for p in payload['participants'])
    return set([(payload['host_source'], payload['host_uid'])])


def distance(a, b):
    return math.sqrt(sum((finite(a[i])-finite(b[i]))**2 for i in range(3)))


def same_state(a, b, length_tolerance, direction_tolerance):
    if not isinstance(a, dict) or not isinstance(b, dict) or set(a) != set(b):
        return False
    try:
        for key in a:
            av, bv = a[key], b[key]
            if key in ('x', 'y', 'normal'):
                if distance(av, bv) > direction_tolerance:
                    return False
            elif key == 'insertion':
                if distance(av, bv) > length_tolerance:
                    return False
            elif key in ('depth', 'width', 'height', 'diameter'):
                if abs(finite(av)-finite(bv)) > length_tolerance:
                    return False
            elif av != bv:
                return False
        return True
    except (TypeError, ValueError, IndexError, OverflowError):
        return False


def passage_components(olds, news):
    """Scope uncertainty to related source constructions only.

    A failed floor passage must not poison an independent wall passage of the
    same MEP. Legacy records know only their base host, so intersecting host
    memberships stay together to protect existing holes after a failed check.
    """
    pending = [('old', item) for item in olds]+[('new', item) for item in news]
    result = []
    while pending:
        kind,item = pending.pop(0)
        group = [(kind,item)]
        hosts = host_keys(item['payload'])
        changed = True
        while changed:
            changed = False
            rest = []
            for candidate_kind,candidate in pending:
                candidate_hosts = host_keys(candidate['payload'])
                if hosts & candidate_hosts:
                    hosts.update(candidate_hosts)
                    group.append((candidate_kind,candidate))
                    changed = True
                else:
                    rest.append((candidate_kind,candidate))
            pending = rest
        result.append(([item for kind,item in group if kind=='old'],
                       [item for kind,item in group if kind=='new']))
    return result


def condition_key(payload):
    """Source identities and composition define a condition; geometry is state."""
    if payload.get('version') != PAYLOAD_VERSION:
        # Prior releases lack the complete composition snapshot. They cannot
        # claim equivalence with a newly computed condition.
        return ('legacy',payload.get('version'),payload.get('opening_guid') or payload.get('key'),
                payload['mep_source'],payload['mep_uid'],payload['host_source'],payload['host_uid'])
    members = tuple(sorted((p['source'],p['uid'],p['layer'],p['definition'])
                           for p in payload['participants']))
    return ('condition',payload['mep_source'],payload['mep_uid'],
            payload['host_source'],payload['host_uid'],payload['layer_index'],members)


def reconcile(existing, desired, uncertainty, length_tolerance, direction_tolerance):
    """existing records: element, payload, actual; desired records: plan, payload.

    uncertainty(payload) returns a retention reason, or None after a successful
    absence check. Unknown/ambiguous memberships never cause deletion.
    """
    actions = []
    old_groups, new_groups = {}, {}
    guid_counts = {}
    for old in existing:
        payload = old['payload']
        old_groups.setdefault(mep_key(payload), []).append(old)
        guid = payload.get('opening_guid')
        if guid:
            guid_counts[guid] = guid_counts.get(guid, 0)+1
    for new in desired:
        new_groups.setdefault(mep_key(new['payload']), []).append(new)
    for key in sorted(set(old_groups) | set(new_groups)):
        olds, news = old_groups.get(key, []), new_groups.get(key, [])
        for olds,news in passage_components(olds,news):
            reasons = [uncertainty(item['payload']) for item in olds+news]
            reasons.extend(item.get('uncertain_reason') for item in news)
            if any(guid_counts.get(o['payload'].get('opening_guid'), 0)>1 for o in olds):
                reasons.append('Duplicate OpeningGuid; identity requires review')
            if any(o['payload'].get('version') not in (3,4,5,6,PAYLOAD_VERSION) for o in olds):
                reasons.append('Unsupported stored payload version')
            reason = next((r for r in reasons if r), None)
            if reason:
                actions.extend(dict(kind='retain', old=o, reason=reason) for o in olds)
                actions.extend(dict(kind='skip', new=n, reason=reason) for n in news)
                continue
            old_by_condition, new_by_condition = {},{}
            for old in olds:
                old_by_condition.setdefault(condition_key(old['payload']),[]).append(old)
            for new in news:
                new_by_condition.setdefault(condition_key(new['payload']),[]).append(new)
            if any(len(items)>1 for items in list(old_by_condition.values())+list(new_by_condition.values())):
                reason = 'Duplicate stored/calculated condition; preserved for review'
                actions.extend(dict(kind='retain',old=o,reason=reason) for o in olds)
                actions.extend(dict(kind='skip',new=n,reason=reason) for n in news)
                continue
            pairs = [(old_by_condition[key][0],new_by_condition[key][0])
                     for key in sorted(set(old_by_condition)&set(new_by_condition))]
            unmatched_old = [o for o in olds if condition_key(o['payload']) not in new_by_condition]
            unmatched_new = [n for n in news if condition_key(n['payload']) not in old_by_condition]
            for old,new in pairs:
                payload = dict(new['payload'])
                op = old['payload']
                payload['opening_guid'] = op.get('opening_guid') or str(uuid.uuid4())
                payload['run_id'] = op.get('run_id', '')
                unchanged = same_state(old.get('actual'), payload['state'], length_tolerance, direction_tolerance)
                if op.get('state') is not None:
                    unchanged = unchanged and same_state(op['state'], payload['state'], length_tolerance, direction_tolerance)
                if not unchanged:
                    kind = 'replace'
                elif payload != op:
                    kind = 'refresh'
                else:
                    kind = 'keep'
                actions.append(dict(kind=kind,old=old,new=new,payload=payload))
            for new in unmatched_new:
                payload = dict(new['payload'])
                payload['opening_guid'] = str(uuid.uuid4())
                actions.append(dict(kind='create',new=new,payload=payload))
            actions.extend(dict(kind='delete',old=o) for o in unmatched_old)
    return actions


def apply_actions(doc, actions, create, write, run_id):
    """Caller owns the single atomic transaction; no partial commit here."""
    for action in actions:
        kind = action['kind']
        if kind in ('create', 'replace', 'refresh'):
            payload = dict(action['payload'])
            payload['run_id'] = run_id
            if kind == 'refresh':
                write(action['old']['element'], payload)
            else:
                # Validate replacement creation before removing its predecessor.
                create(action['new']['plan'], payload)
        if kind in ('replace', 'delete'):
            doc.Delete(action['old']['element'].Id)


def plan_bounds(plan):
    center = vector(plan['center'])
    x,y,n = vector(plan['x']),vector(plan['y']),vector(plan['normal'])
    w,h = ((plan['diameter'],plan['diameter']) if plan['shape']=='round'
           else (plan['width'],plan['height']))
    half = [(abs(x[i])*w+abs(y[i])*h+abs(n[i])*plan['depth'])/2. for i in range(3)]
    return [(center[i]-half[i],center[i]+half[i]) for i in range(3)]


def combine_bounds(a,b):
    return [(min(a[i][0],b[i][0]),max(a[i][1],b[i][1])) for i in range(3)]


def bounds_overlap(a,b,margin=0.):
    return all(a[i][0]-margin <= b[i][1] and b[i][0] <= a[i][1]+margin for i in range(3))
