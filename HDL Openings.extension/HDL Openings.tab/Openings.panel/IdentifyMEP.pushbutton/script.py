# -*- coding: utf-8 -*-
__title__ = 'Identify MEP'
__doc__ = 'Identify pipes, ducts, conduits and cable trays inside existing openings. Shift-click to select another Excel mapping.'
import traceback
from pyrevit import forms, script

VERSION = '0.9.6'
try:
    # Imports belong inside the error boundary so startup errors are shown too.
    from hdl_openings.identify_command import run
    run(__revit__, globals().get('__shiftclick__', False))
except Exception:
    trace = traceback.format_exc()
    try:
        from hdl_openings.error_report import show
        show(trace, VERSION, forms)
    except Exception:
        forms.alert(u'Identify MEP v{}\n\n{}'.format(VERSION, trace),
                    title='Identify MEP - full error report')
    try:
        script.get_logger().error(trace)
    except Exception:
        pass
