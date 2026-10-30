# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import time
import traceback
from hdl_openings.error_report import save_run_log
from Autodesk.Revit import DB
from hdl_openings.mep_labels import text_type
from pyrevit import forms, script
from hdl_openings import settings, geometry as geo, mep_excel, mep_storage
from hdl_openings.mep_geometry import Opening, gather
from hdl_openings.model import id_value

PARAMETER = 'SP_OP_MEP_Elements'


def target_parameter(element):
    values = list(element.GetParameters(PARAMETER))
    if len(values) != 1:
        raise ValueError('Expected one instance parameter: ' + PARAMETER)
    p = values[0]
    if p.IsReadOnly or p.StorageType != DB.StorageType.String:
        raise ValueError('Writable instance Text required: ' + PARAMETER)
    return p


def choose_excel(shift):
    config = script.get_config()
    path = getattr(config, 'mep_excel_path', '')
    if shift or not path or not os.path.isfile(path):
        path = forms.pick_file(file_ext='xlsx', title='Select MEP system mapping')
        if not path:
            return None
    # Validate before remembering; a broken workbook must not replace the last path.
    mapping, fingerprint = mep_excel.load(path)
    config.mep_excel_path = path
    script.save_config()
    return path, mapping, fingerprint


def run(uiapp, shift=False):
    started = time.time()
    doc = uiapp.ActiveUIDocument.Document
    if doc.IsFamilyDocument:
        forms.alert('Identify MEP requires a project document.')
        return
    chosen = choose_excel(shift)
    if chosen is None:
        return
    path, mapping, fingerprint = chosen
    cfg, warning, _ = settings.load()
    if warning:
        raise ValueError(warning)
    openings = [e for e in DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance)
                if e.Symbol.Family.Name in cfg.families]
    output = script.get_output()
    if not openings:
        forms.alert('No accepted opening families found in the current model.')
        return
    candidates, unavailable = gather(doc)
    plans, rows, detail_rows = [], [], []
    diagnostics = []
    counts = dict(updated=0, unchanged=0, preserved=0)
    # No model changes occur during detection or classification.
    with forms.ProgressBar(title='Identify MEP: {value}/{max_value}', cancellable=True) as progress:
        for index, element in enumerate(openings):
            if progress.cancelled:
                output.print_md('Identify MEP cancelled. No model changes.')
                return
            progress.update_progress(index+1, len(openings))
            eid = str(id_value(element.Id))
            stage = 'Sources and target parameter'
            try:
                p = target_parameter(element)
                stage = 'Opening volume'
                volume = Opening(element, cfg.families)
                hits, errors = [], []
                stage = 'MEP geometry and classification'
                try:
                    for candidate in candidates:
                        if candidate.bounds is not None and not geo.overlaps(candidate.bounds, volume.bounds):
                            continue
                        try:
                            match = candidate.inside(volume, cfg.touch, cfg.sync_length)
                            if match is not None:
                                item = candidate.classification(mapping)
                                item.update(match)
                                hits.append(item)
                        except Exception as error:
                            diagnostics.append('Opening {} / candidate {}\n{}'.format(eid, candidate.key, text_type(traceback.format_exc())))
                            errors.append(text_type(candidate.key) + ': ' + text_type(error))
                finally:
                    volume.solid.Dispose()
                if errors:
                    raise ValueError('; '.join(errors))
                stage = 'Sort and label reduction'
                hits.sort(key=lambda x: (x['source'], x['element_unique_id']))
                value = mapping.reduce((h['label'], h['discipline']) for h in hits)
                payload = dict(version=1, elements=hits, value=value,
                               mapping_sha256=fingerprint, mapping_path=os.path.abspath(path),
                               threshold_mm=cfg.touch*304.8,
                               source_scope='Current model and loaded direct links',
                               unavailable_links=sorted(text_type(uid) for uid in unavailable))
                stage = 'Serialize identification metadata'
                raw = mep_storage.serialized(payload)
                stage = 'Read previous label and metadata'
                old = text_type(p.AsString() or '')
                changed = old != value or not mep_storage.matches(element, raw)
                plans.append((element, value, raw, changed))
                for hit in hits:
                    detail_rows.append([eid, hit['source'], hit['element_unique_id'],
                                        hit.get('system_type', ''), hit['label'], hit['discipline'],
                                        hit['rule'], hit['entry_mm']])
                rows.append([eid, str(len(hits)), old, value,
                             'Update' if changed else 'Unchanged', ''])
            except Exception as error:
                counts['preserved'] += 1
                diagnostics.append('Opening {} / stage {}\n{}'.format(eid, stage, text_type(traceback.format_exc())))
                rows.append([eid, '', '', '', 'Preserved', stage + ': ' + text_type(error)])
    diagnostic_path = ''
    if diagnostics:
        try:
            diagnostic_path = save_run_log(diagnostics)
        except Exception as error:
            diagnostic_path = 'Log could not be saved: ' + text_type(error)
    transaction = DB.Transaction(doc, 'HDL Openings - Identify MEP')
    pending = [p for p in plans if p[3]]
    if pending:
        try:
            if transaction.Start() != DB.TransactionStatus.Started:
                raise ValueError('Could not start transaction')
            options = transaction.GetFailureHandlingOptions()
            options.SetClearAfterRollback(True)
            options.SetForcedModalHandling(True)
            transaction.SetFailureHandlingOptions(options)
            for element, value, raw, _ in pending:
                p = target_parameter(element)
                if (p.AsString() or '') != value and not p.Set(value):
                    raise ValueError('Parameter.Set failed: ' + str(id_value(element.Id)))
                mep_storage.write(element, raw)
            if transaction.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Identify MEP transaction did not commit')
        except Exception:
            if transaction.GetStatus() == DB.TransactionStatus.Started:
                transaction.RollBack()
            output.print_md('Identify MEP failed. Planned updates were not committed.')
            raise
        finally:
            transaction.Dispose()
    counts['updated'] = len(pending)
    counts['unchanged'] = len(plans)-len(pending)
    output.print_md('## Identify MEP v0.9.6')
    output.print_md('Found: **{}** | Updated: **{}** | Unchanged: **{}** | Preserved: **{}** | Time: **{:.1f} s**'.format(
        len(openings), counts['updated'], counts['unchanged'], counts['preserved'], time.time()-started))
    output.print_md('Mapping SHA-256: `{}`'.format(fingerprint))
    if unavailable:
        output.print_md('Skipped unloaded links: **{}**. Results use the current model and loaded links only; previous values are recalculated from these available sources.'.format(len(unavailable)))
        output.print_table(table_data=[[text_type(uid)] for uid in unavailable],
                           columns=['Skipped Link Instance UniqueId'])
    if diagnostic_path:
        output.print_md('Diagnostic log: `{}`'.format(diagnostic_path))
    for row in rows:
        row[4] = 'Updated' if row[4] == 'Update' else row[4]
    output.print_table(table_data=rows, columns=['Opening', 'MEP count', 'Old value', 'Result', 'Status', 'Reason'])

    if detail_rows:
        output.print_table(table_data=detail_rows, columns=['Opening', 'Source / Link UniqueId',
            'MEP UniqueId', 'System Type', 'Label', 'Discipline', 'Rule', 'Entry mm'])
