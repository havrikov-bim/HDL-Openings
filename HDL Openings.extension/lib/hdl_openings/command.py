# -*- coding: utf-8 -*-
import uuid
from Autodesk.Revit import DB
from pyrevit import forms, script
from hdl_openings import model, engine, placement, storage, face_host, settings, scope_box, synchronization as sync


class AtomicFailures(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, accessor):
        for failure in accessor.GetFailureMessages():
            if failure.GetSeverity() == DB.FailureSeverity.Error:
                return DB.FailureProcessingResult.ProceedWithRollBack
        return DB.FailureProcessingResult.Continue


def choose_symbols(doc, cfg):
    # Deterministic default, no selection dialog. Selected types are reported.
    available = placement.symbols(doc, cfg)
    return {name: sorted(available[name], key=lambda symbol:
            symbol.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString())[0]
            for name in cfg.families}


def choose_meps(doc):
    available_sources = model.sources(doc)
    raw = [(source, element) for source in available_sources if source.key == 'CURRENT'
           for element in model.collect(source, model.MEP_CATEGORIES)]
    return raw, available_sources


def choose_scope(doc):
    boxes = list(DB.FilteredElementCollector(doc).OfCategory(
        DB.BuiltInCategory.OST_VolumeOfInterest).WhereElementIsNotElementType())
    if not boxes:
        forms.alert('Create a Scope Box in the current model before running Create Openings.')
        return None
    choices = dict((u'{} [{}]'.format(box.Name,model.id_value(box.Id)),box) for box in boxes)
    selected = forms.SelectFromList.show(sorted(choices,key=lambda name:name.lower()),
        title='HDL Openings - Scope Box',multiselect=False,button_name='Create Openings')
    if selected is None:
        return None
    return scope_box.from_element(choices[selected],DB)


def host_category(element):
    if isinstance(element, DB.Wall):
        return 'Walls'
    if isinstance(element, DB.Floor):
        return 'Floors'
    return 'Roofs'


def summary(output, counts, title):
    output.print_md('## ' + title)
    output.print_table(table_data=[[key] + counts[key] for key in ('Walls','Floors','Roofs')],
                       columns=['Category', 'Found', 'Geometry accepted', 'Create / replace'])


def report(output, diagnostics):
    if diagnostics:
        output.print_md('## Diagnostics')
        output.print_table(table_data=diagnostics,
                           columns=['Stage', 'Element / source', 'Reason'])


def run(uiapp):
    doc = uiapp.ActiveUIDocument.Document
    output = script.get_output()
    if doc.IsFamilyDocument or doc.IsReadOnly:
        forms.alert('Run in an editable coordination project.')
        return
    region = choose_scope(doc)
    if region is None:
        output.print_md('No Scope Box selected. No model changes.')
        return
    output.print_md(u'Scope Box: `{}`. Entire opening volume must be inside.'.format(region.name))
    cfg, warning, reloaded = settings.load()
    output.print_md('Settings: `{}`; {}.'.format(cfg.fingerprint[:12], 'reloaded' if reloaded else 'cached'))
    if warning:
        forms.alert(warning)
        output.print_md(warning)
    output.print_md('ThroughAll: **{}**. Base requires Structure [1] + Structural Material=Yes.'.format(int(cfg.through_all)))
    chosen = choose_symbols(doc, cfg)
    if chosen is None:
        return
    raw_meps, all_sources = choose_meps(doc)
    selected_meps = []
    for source,element in raw_meps:
        try:
            if not region.overlaps_bounds(model.element_bounds(source,element)):
                continue
        except Exception:
            pass  # Unknown bounds require normal geometry diagnostics, not omission.
        selected_meps.append((source,element))
    raw_meps = selected_meps
    diagnostics, hosts, plans = [], [], []
    failed_hosts, failed_meps, mep_bounds = {}, set(), {}
    failed_host_records = {}
    counts = {name: [0, 0, 0] for name in ('Walls','Floors','Roofs')}
    output.print_md('Construction sources: **{}**. Current-model MEP elements: **{}**.'.format(
        len(all_sources), len(raw_meps)))
    for name in cfg.families:
        type_name = chosen[name].get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        output.print_md('Family: `{}`; type: `{}`'.format(name, type_name))
    cancelled = False
    with forms.ProgressBar(title='HDL Openings: geometry {value}/{max_value}',
                           cancellable=True) as progress:
        raw_hosts = [(s, e) for s in all_sources for e in model.collect(s, model.HOST_CATEGORIES)]
        for i, (source, element) in enumerate(raw_hosts):
            progress.update_progress(i + 1, max(1, len(raw_hosts)))
            if progress.cancelled:
                cancelled = True
                break
            category = host_category(element)
            counts[category][0] += 1
            try:
                hosts.append(model.Host(source, element))
                counts[category][1] += 1
            except Exception as exc:
                try:
                    failed_bounds = model.element_bounds(source,element)
                except Exception:
                    failed_bounds = None
                failed_hosts[source.element_key(element)] = failed_bounds
                failed_host_records[source.element_key(element)] = (source, element)
                diagnostics.append(['Host ' + category, source.element_key(element), str(exc)])
        if not cancelled:
            for i, (source, element) in enumerate(raw_meps):
                progress.update_progress(i + 1, len(raw_meps))
                if progress.cancelled:
                    cancelled = True
                    break
                try:
                    mep = model.Mep(source, element)
                    mep_bounds[mep.key] = mep.bounds
                    candidates, reasons = engine.plan(mep, hosts, cfg)
                    for candidate in candidates:
                        mep_bounds[mep.key] = sync.combine_bounds(mep_bounds[mep.key],sync.plan_bounds(candidate))
                    plans.extend(candidates)
                    for opening in candidates:
                        selection = opening.get('base_selection')
                        if selection:
                            diagnostics.append(['Base layer',mep.key,
                                'host={}; eligible Structure [1] + Structural Material={}; thickness={:.2f} mm; distance to Project Base Point={:.2f} mm'.format(
                                    opening['host'].key,'Yes' if selection['structural'] else 'No',
                                    selection['width']*304.8,selection['distance_to_pbp']*304.8)])
                        if opening['shape_reason']:
                            diagnostics.append(['Rectangular fallback',mep.key,opening['shape_reason']])
                    for reason in reasons:
                        diagnostics.append(['Rule', mep.key, reason])
                except Exception as exc:
                    failed_meps.add(source.element_key(element))
                    diagnostics.append(['MEP', source.element_key(element), str(exc)])
    if cancelled:
        output.print_md('Cancelled. No model changes.')
        return
    existing = []
    protected_conditions = {}
    unreadable = False
    for fi in DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance):
        try:
            payload = storage.read(fi)
            if not payload:
                continue
        except Exception as error:
            unreadable = True
            diagnostics.append(['Stored data', fi.UniqueId, 'Unreadable managed data: '+str(error)])
            continue
        try:
            wall = payload.get('state', {}).get('family') in (
                cfg.families.rect_wall, cfg.families.round_wall)
            if payload.get('version') == 3:
                wall = fi.Symbol.Family.Name in (cfg.families.rect_wall, cfg.families.round_wall)
            actual = placement.actual_state(fi, wall)
        except Exception as error:
            actual = None
            diagnostics.append(['Existing geometry', fi.UniqueId, str(error)])
        try:
            in_region = region.contains_state(actual,wall)
        except Exception:
            in_region = False
        if not in_region:
            protected_conditions[sync.condition_key(payload)] = 'Existing opening outside Scope Box or geometry unavailable; retained'
        existing.append(dict(element=fi, payload=payload, actual=actual))
    if unreadable:
        report(output, diagnostics)
        forms.alert('Unreadable managed opening data. Synchronization stopped; no model changes.')
        return
    desired = []
    seen = set()
    for opening in plans:
        # Keep an identifiable rejected candidate in reconciliation so only
        # its corresponding old passage is retained, not every hole of the MEP.
        try:
            name = sync.family_name(opening)
            payload = sync.desired_payload(opening,chosen[name].UniqueId)
        except Exception as error:
            failed_meps.add(opening['mep'].key)
            diagnostics.append(['Invalid calculation',opening['mep'].key,str(error)])
            continue
        entry = dict(plan=opening,payload=payload)
        if not region.contains_plan(opening):
            entry['uncertain_reason'] = 'Entire opening volume is not inside selected Scope Box'
            desired.append(entry)
            continue
        if opening['key'] in seen:
            entry['uncertain_reason'] = 'Duplicate calculated passage'
            desired.append(entry)
            diagnostics.append(['Ambiguous calculation',opening['mep'].key,entry['uncertain_reason']])
            continue
        seen.add(opening['key'])
        try:
            if not opening['host'].wall:
                opening['face_host'] = face_host.resolve(opening)
                opening['reference_key'] = opening['face_host']['reference'].ConvertToStableRepresentation(doc)
                opening['interaction']['reference_side'] = opening['face_host']['reference_side']
            else:
                opening['reference_key'] = None
            entry['payload'] = sync.desired_payload(opening,chosen[name].UniqueId)
        except Exception as error:
            entry['uncertain_reason'] = str(error)
            diagnostics.append(['Placement skipped',opening['mep'].key,str(error)])
        desired.append(entry)
    source_by_key = dict((source.key,source) for source in all_sources)
    mep_keys = set(source.element_key(element) for source,element in raw_meps)

    local_coverage = (model.local_host_coverage(failed_host_records, failed_hosts, cfg)
                      if failed_hosts else None)

    def uncertainty(payload):
        protection = protected_conditions.get(sync.condition_key(payload))
        if protection:
            return protection
        return coverage_reason(payload,source_by_key,mep_keys,failed_meps,failed_hosts,mep_bounds,cfg,local_coverage)

    actions = sync.reconcile(existing, desired, uncertainty, cfg.sync_length, cfg.sync_direction)
    totals = dict((kind,0) for kind in ('create','replace','delete','refresh','keep','retain','skip'))
    for action in actions:
        kind = action['kind']
        totals[kind] += 1
        if kind in ('retain','skip'):
            payload = action.get('old',action.get('new'))['payload']
            diagnostics.append([kind, str(sync.mep_key(payload)), action['reason']])
        if kind == 'delete' and action['old']['payload']['mep_source'] != 'CURRENT':
            diagnostics.append(['Out of scope',str(sync.mep_key(action['old']['payload'])),
                                'Linked MEP excluded; managed opening removed'])
        if kind == 'replace':
            old_payload = action['old']['payload']
            new_payload = action['payload']
            diagnostics.append(['Replacement',str(sync.mep_key(new_payload)),
                '{} -> {}; host={}; OpeningGuid={}'.format(
                    old_payload.get('shape','unknown'),new_payload['shape'],
                    action['new']['plan']['host'].key,new_payload['opening_guid'])])
        if kind in ('create','replace'):
            counts[host_category(action['new']['plan']['host'].element)][2] += 1
    summary(output, counts, 'Calculated result')
    report(output, diagnostics)
    output.print_md('Planned: create **{create}**, replace **{replace}**, delete **{delete}**, '
                    'metadata **{refresh}**, unchanged **{keep}**, retained **{retain}**, skipped **{skip}**.'.format(**totals))
    changes = [a for a in actions if a['kind'] in ('create','replace','delete','refresh')]
    if not changes:
        forms.alert('No synchronization changes. See diagnostic output.')
        return
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))
    if not levels and (totals['create'] or totals['replace']):
        forms.alert('Project must contain at least one Level.')
        return
    run_id = str(uuid.uuid4())

    def create(plan,payload):
        level = min(levels,key=lambda l:abs(l.ProjectElevation-plan['insertion'].Z))
        return placement.create(doc,plan,chosen,level,run_id,payload)

    execute_transaction(doc,lambda:sync.apply_actions(doc,changes,create,storage.write,run_id))
    summary(output, counts, 'Committed result')
    output.print_md('Committed: created **{create}**, replaced **{replace}**, deleted **{delete}**, '
                    'metadata updated **{refresh}**. One Undo/Redo operation.'.format(**totals))
    output.print_md('Run `{}`. MEP list initialization and numbering were not performed.'.format(run_id))


def execute_transaction(doc,apply_changes):
    transaction = DB.Transaction(doc,'HDL Create Openings')
    try:
        transaction.Start()
        failures = AtomicFailures()
        options = transaction.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(failures)
        options.SetClearAfterRollback(True)
        transaction.SetFailureHandlingOptions(options)
        apply_changes()
        status = transaction.Commit()
        if status != DB.TransactionStatus.Committed:
            raise RuntimeError('Synchronization was not committed: '+str(status))
    except Exception:
        if transaction.GetStatus() == DB.TransactionStatus.Started:
            transaction.RollBack()
        raise


def coverage_reason(payload,source_by_key,mep_keys,failed_meps,failed_hosts,mep_bounds,cfg,local_coverage=None):
    if payload['mep_source'] != 'CURRENT':
        return None  # Linked MEP are explicitly outside the command scope.
    source = source_by_key.get(payload['mep_source'])
    if source is None:
        return 'MEP source unavailable; existing opening retained'
    try:
        mep = source.doc.GetElement(payload['mep_uid'])
    except Exception:
        return 'MEP source cannot be checked'
    if mep is None:
        return None  # Confirmed deletion in an available document.
    key = source.element_key(mep)
    if key not in mep_keys or key in failed_meps:
        return 'MEP calculation or placement uncertain; existing opening retained'
    bounds = mep_bounds.get(key)
    for host_key,failed_bounds in failed_hosts.items():
        if local_coverage is not None:
            reason = local_coverage(payload, host_key)
            if reason:
                return reason
            continue
        if bounds is None or failed_bounds is None or sync.bounds_overlap(
                bounds,failed_bounds,cfg.gap+cfg.clearance+cfg.rect_step):
            return 'Incomplete nearby host geometry: '+host_key
    for host_source, host_uid in sync.host_keys(payload):
        if host_source not in source_by_key:
            return 'Construction source unavailable; existing opening retained'
    return None
