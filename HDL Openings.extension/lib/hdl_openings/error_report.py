# -*- coding: utf-8 -*-
"""Self-contained diagnostics; never depends on the pyRevit output webview."""
import io
import os
import tempfile
from hdl_openings.mep_labels import text_type


def show(trace, version, forms):
    report = u'HDL Openings Identify MEP v{}\n\n{}'.format(version, text_type(trace))
    try:
        path = os.path.join(tempfile.gettempdir(), 'HDL_IdentifyMEP_error.log')
        with io.open(path, 'w', encoding='utf-8') as stream:
            stream.write(report)
        report += u'\n\nLog file: ' + text_type(path)
    except Exception as error:
        report += u'\n\nCould not save log: ' + text_type(error)
    try:
        import clr
        clr.AddReference('System.Windows.Forms')
        clr.AddReference('System.Drawing')
        from System.Drawing import Font, Size
        from System.Windows.Forms import (Form, TextBox, Button, DockStyle,
            ScrollBars, FormStartPosition, Clipboard)
        window = Form()
        try:
            window.Text = 'Identify MEP - error details v' + version
            window.Size = Size(1000, 650)
            window.MinimumSize = Size(650, 400)
            window.StartPosition = FormStartPosition.CenterScreen
            text = TextBox()
            text.Multiline = True
            text.ReadOnly = True
            text.WordWrap = False
            text.ScrollBars = ScrollBars.Both
            text.Dock = DockStyle.Fill
            text.Font = Font('Consolas', 10)
            text.Text = report.replace(u'\r\n', u'\n').replace(u'\n', u'\r\n')
            button = Button()
            button.Text = 'Copy full error report'
            button.Height = 38
            button.Dock = DockStyle.Bottom
            def copy_report(sender, args):
                try:
                    Clipboard.SetText(report)
                    button.Text = 'Copied'
                except Exception:
                    text.Focus()
                    text.SelectAll()
                    button.Text = 'Press Ctrl+C to copy'
            button.Click += copy_report
            window.Controls.Add(text)
            window.Controls.Add(button)
            window.ShowDialog()
        finally:
            window.Dispose()
    except Exception:
        # The full text is still available if WinForms cannot be initialized.
        forms.alert(report, title='Identify MEP - full error report')


def save_run_log(records):
    path = os.path.join(tempfile.gettempdir(), 'HDL_IdentifyMEP_preserved.log')
    with io.open(path, 'w', encoding='utf-8') as stream:
        stream.write(u'HDL Identify MEP per-opening diagnostics\n\n')
        stream.write(u'\n\n'.join(text_type(record) for record in records))
    return text_type(path)
