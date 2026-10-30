# -*- coding: utf-8 -*-
"""Renumber every instance with SP_OP_Id in the active document."""
from pyrevit import DB, forms, revit, script
import math

__title__ = u'Number\nOpenings'
__doc__ = u'Renumber selected open models together by shared Z, X, Y. Starts at ID #1.'
__version__ = '2.0.1'
PARAMETER = 'SP_OP_Id'


def element_id(element):
    try:
        return element.Id.Value
    except AttributeError:
        return element.Id.IntegerValue


def position(element, doc):
    location = element.Location
    if isinstance(location, DB.LocationPoint):
        point = location.Point
    elif isinstance(location, DB.LocationCurve):
        point = location.Curve.Evaluate(0.5, True)
    else:
        box = element.get_BoundingBox(None)
        if box is None:
            raise ValueError(u'No placement point or bounding box')
        point = box.Transform.OfPoint((box.Min + box.Max) * 0.5)
    shared = doc.ActiveProjectLocation.GetProjectPosition(point)
    coordinates = (shared.Elevation, shared.EastWest, shared.NorthSouth)
    if any(math.isnan(v) or math.isinf(v) for v in coordinates):
        raise ValueError(u'Invalid coordinates')
    return coordinates


def collect_plan(doc):
    plan, errors = [], []
    for element in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        parameters = list(element.GetParameters(PARAMETER))
        if not parameters:
            continue
        eid = element_id(element)
        try:
            if len(parameters) != 1:
                raise ValueError(u'Multiple SP_OP_Id parameters found')
            parameter = parameters[0]
            if parameter.StorageType != DB.StorageType.String:
                raise ValueError(u'SP_OP_Id must be a text parameter')
            if parameter.IsReadOnly:
                raise ValueError(u'SP_OP_Id is read-only')
            plan.append((position(element, doc), eid, parameter))
        except Exception as error:
            errors.append((eid, str(error)))
    # ElementId makes equal coordinates deterministic within this document.
    plan.sort(key=lambda row: (row[0], row[1]))
    return plan, errors


class ModelChoice(forms.TemplateListItem):
    @property
    def name(self):
        doc = self.item
        path = doc.PathName or 'Unsaved project'
        return u'{0} | {1} | Site: {2}'.format(
            doc.Title, path, doc.ActiveProjectLocation.Name)


def eligible_documents(application):
    return [d for d in application.Documents
            if not d.IsLinked and not d.IsFamilyDocument
            and not d.IsReadOnly and not d.IsModifiable]


def build_global_plan(documents):
    rows, errors = [], []
    # Stable document order is used only to break identical-coordinate ties.
    ordered = sorted(documents, key=lambda d: (d.PathName or '', d.Title))
    for model_index, doc in enumerate(ordered):
        plan, model_errors = collect_plan(doc)
        for eid, message in model_errors:
            errors.append(u'{0} / ElementId {1}: {2}'.format(doc.Title, eid, message))
        for coordinates, eid, parameter in plan:
            rows.append((coordinates, model_index, eid, doc, parameter))
    rows.sort(key=lambda row: (row[0], row[1], row[2]))
    return [(row[3], row[4], row[2], 'ID #{0}'.format(index + 1))
            for index, row in enumerate(rows)], errors


def write_plan(documents, plan):
    groups, finalized, changed = [], [], {}
    try:
        # Keep each model's group open until all model transactions succeed.
        for doc in documents:
            group = DB.TransactionGroup(doc, 'Number Openings')
            groups.append((doc, group))
            if group.Start() != DB.TransactionStatus.Started:
                raise RuntimeError('Could not start group: ' + doc.Title)
        for doc in documents:
            rows = [row for row in plan if row[0].Equals(doc)]
            changed[doc.Title] = 0
            transaction = DB.Transaction(doc, 'Number Openings SP_OP_Id')
            try:
                if transaction.Start() != DB.TransactionStatus.Started:
                    raise RuntimeError('Could not start transaction: ' + doc.Title)
                options = transaction.GetFailureHandlingOptions()
                options.SetClearAfterRollback(True)
                options.SetForcedModalHandling(True)
                transaction.SetFailureHandlingOptions(options)
                for _, parameter, eid, target in rows:
                    if parameter.AsString() != target:
                        if not parameter.Set(target):
                            raise RuntimeError('Could not write ElementId {0}'.format(eid))
                        changed[doc.Title] += 1
                if transaction.Commit() != DB.TransactionStatus.Committed:
                    raise RuntimeError('Transaction not committed: ' + doc.Title)
            finally:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
                transaction.Dispose()
        for doc, group in groups:
            if group.Assimilate() != DB.TransactionStatus.Committed:
                raise RuntimeError('Could not finalize model: ' + doc.Title)
            finalized.append(doc.Title)
        return changed
    except Exception as error:
        rollback_errors = []
        for doc, group in reversed(groups):
            try:
                if group.GetStatus() == DB.TransactionStatus.Started:
                    if group.RollBack() != DB.TransactionStatus.RolledBack:
                        rollback_errors.append(doc.Title)
            except Exception:
                rollback_errors.append(doc.Title)
        message = u'Numbering failed: {0}'.format(error)
        if finalized:
            message += u'\nAlready finalized models (use Undo in each): ' + ', '.join(finalized)
        if rollback_errors:
            message += u'\nRollback could not be confirmed: ' + ', '.join(rollback_errors)
        if not finalized and not rollback_errors:
            message += u'\nAll numbering changes were rolled back.'
        raise RuntimeError(message)
    finally:
        for _, group in reversed(groups):
            group.Dispose()


def main():
    active = revit.doc
    if active is None:
        forms.alert('Open a project document first.')
        return
    documents = eligible_documents(active.Application)
    if not documents:
        forms.alert('No editable project documents are open.')
        return
    documents.sort(key=lambda d: (d.Title, d.PathName or ''))
    if len(documents) > 1:
        choices = [ModelChoice(d, checked=d.Equals(active)) for d in documents]
        selected = forms.SelectFromList.show(
            choices, title='Number Openings - Select Open Models',
            button_name='Number from ID #1', multiselect=True, width=950,
            height=550)
        if not selected:
            return
        documents = [item.item if isinstance(item, ModelChoice) else item
                     for item in selected]
    try:
        plan, errors = build_global_plan(documents)
        if errors:
            forms.alert('Numbering cancelled. No changes made.\n\n' + '\n'.join(errors))
            return
        if not plan:
            forms.alert('No instances with SP_OP_Id found in the selected models.')
            return
        changed = write_plan(documents, plan)
    except Exception as error:
        forms.alert(u'{0}'.format(error), title='Number Openings - Error')
        return
    lines = ['Number Openings v2.0.1',
             'Assigned: {0} | Range: ID #1 - ID #{0}'.format(len(plan)),
             'Shared coordinates: Z > X > Y', '']
    for doc in documents:
        count = sum(1 for row in plan if row[0].Equals(doc))
        lines.append('{0}: {1} assigned, {2} changed'.format(
            doc.Title, count, changed[doc.Title]))
    lines += ['', 'Save each model to keep the changes.',
              'Undo is separate in each model.']
    forms.alert('\n'.join(lines), title='Number Openings - Complete')


if __name__ == '__main__':
    main()
