# -*- coding: utf-8 -*-
__title__ = 'Create / Update'
__doc__ = 'Create and synchronize rectangular and round master openings inside a selected Scope Box as one Undo/Redo operation.'
__persistentengine__ = True
from pyrevit import forms, script
from hdl_openings.command import run
try:
    run(__revit__)
except Exception as exc:
    script.get_logger().exception('HDL Openings synchronization failed')
    forms.alert('HDL Openings: {}\nSee output for the traceback. The command did not complete; any active synchronization transaction was rolled back.'.format(exc))
