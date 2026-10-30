# Identify MEP v0.9.6

Install `HDL Openings.extension` into your pyRevit extensions directory and reload pyRevit. The panel order is Create / Update, Identify MEP, Number Openings. This package includes Number Openings from the previously supplied separate extension. Remove/disable the old `HDL_NumberOpenings.extension` when installing this combined package to avoid duplicate Number Openings buttons.

## Excel configuration

Copy `HDL_MEP_Mapping.xlsx` to a permanent editable location. Fill the Systems sheet with exact Revit system TYPE names, output labels and disciplines. Matching is case-sensitive after trimming leading/trailing whitespace and Unicode NFC normalization. Identical type names in different source documents share one row. A physical SP_OP_System_Label parameter in Revit is not required.

Systems columns: `System Type`, `SP_OP_System_Label`, `Discipline`.
Categories columns: `Category`, `SP_OP_System_Label`, `Discipline`.

Category keys are exactly `Conduits` and `Cable Trays`. Their output labels and disciplines are editable. Initial values are Electricity / Electrical. Examples is explanatory and is ignored by the command. Systems is intentionally empty because the exact project type names have not been supplied. Copy suitable example rows and replace their type names with the real project names. Use literal text, without Excel formulas. Hebrew and other Unicode text are supported in every mapping column.

On first click, select the workbook. The path is remembered. Shift-click chooses a different workbook and then runs identification with it. The complete XLSX is reread and validated on each execution. Excel and Office are not required on the workstation. Changes in an open Excel workbook must be saved before running the command.

Discipline order is the first occurrence in Systems, followed by Categories. Each label/discipline is compared as explicit text from Excel. No discipline is guessed from a system name. Different spellings or languages therefore represent different disciplines.

## Classification

- No qualifying MEP: write the empty string and replace the saved element list with an empty list.
- One discipline, one distinct label: write that label, irrespective of element count.
- One discipline, multiple distinct labels: write the discipline name.
- Multiple disciplines: write their unique names, joined by comma and space. Example: HVAC, Plumbing, Electrical. Discipline reduction takes priority even if the labels happen to be identical.

Duplicate mapping keys, incomplete nonempty rows and formulas are errors. A malformed workbook stops the command before model changes. Missing type mappings or unassigned systems in geometrically qualifying MEP preserve that opening's previous label AND its previous saved list, with a diagnostic.

## Geometry and sources

All instances of the four configured BL Opening families in the active project are processed, including manually placed instances without synchronization metadata. Only the current model's openings are edited. Pipes, ducts, conduits and cable trays are searched in the active document and directly loaded Revit links, with each link instance's total transform. Fittings, equipment, flexible categories and nested links are outside this command's collection scope.

The void is reconstructed from actual instance dimensions, LocationPoint and transform, following the accepted family contract:

- Rect Wall: Width centered on local X, Height from insertion along local +Z, Depth along local +Y.
- Round Wall: circle centered at insertion, Depth along local +Y.
- Rect Floor: Width/Height centered on local X/Y, Depth along local -Z.
- Round Floor: circle centered at insertion, Depth along local -Z.

Visible family geometry is not treated as the void. Family insertion conventions must match these definitions. No structural-host geometry is required for identification.

Positive actual solid overlap is required, including pipe/duct insulation. The qualifying cases are a passage through the full normal depth, partial penetration strictly greater than touch_mm (default 25 mm) measured along the opening normal, or the entire MEP LocationCurve segment lying inside the void. A wholly contained short segment or passage through an opening thinner than 25 mm is accepted independently of that threshold. Touch without positive volume is rejected. Partial entry exactly 25 mm is rejected. Full-segment containment is defined by the LocationCurve, not by an equipment or fitting body.

As in the existing geometric utilities, projected ranges use the Revit kernel solid bounding boxes aligned with the normal; curved trimmed intersections can have conservative bounds. Geometry/Boolean errors preserve the affected opening. Unloaded direct links are skipped and listed in the report. Identification uses the current model and loaded direct links only. Previous labels and metadata are recalculated from those available sources, including clearing a label when no matching MEP remains. Load all relevant MEP links before running when a complete identification is required. Stored payloads include source_scope and unavailable_links.

## Stored data and updates

SP_OP_MEP_Elements must already exist as one writable instance Text parameter. The command does not create parameters. Invalid or read-only targets are reported and preserved.

A separate public Extensible Storage schema is used: e803865b-9aec-4e1f-9fad-2e3789b23e76, HDLOpeningsMEPIdentificationV1. The Payload JSON contains an ordered elements list, output value, configuration path and SHA-256, schema version and depth threshold. Each element records its source, element UniqueId, link-instance UniqueId (null for CURRENT), source document title, system type, label, discipline, entry depth and qualifying rule. Two instances of the same linked model remain distinct.

Identification never overwrites synchronization entities or numbering. It plans the complete run before writing and commits accepted updates as one Undo/Redo transaction. Cancellation during planning makes no model changes. Repeating an unchanged result avoids writing. Errors preserve prior data per opening. A transaction failure rolls back every planned write.

Create / Update may replace an opening instance when its geometry changes; the identification entity belongs to the old instance and must be regenerated by rerunning Identify MEP after such replacement. No live updating is enabled.

The report includes opening counts, old/new values and reasons for preservation, followed by the qualifying element UniqueIds, source IDs, mappings and geometric rules.

## Validation

270 automated tests passed in the supplied package. New tests exercise classification, Hebrew, ordering, missing and duplicate mappings, the 25 mm boundary, short-segment and through exceptions, linked identifiers, empty results, preservation on errors, rollback orchestration and all four family void conventions with rotated instances. The exported XLSX was read successfully by the command's reader and all three sheets were rendered and inspected.

Revit is unavailable in the build environment. Actual Revit Boolean operations, linked model geometry, Extensible Storage writes and ribbon behavior require verification in a Revit project. Recommended first check: one known through pipe, one partially entering segment, one fully contained short segment and an empty opening. Inspect the report and Undo once to verify the batch.

## v0.9.1 compatibility fix

XML entries from XLSX are explicitly decoded to Unicode before ElementTree parsing. This addresses IronPython parsers that reject bytes with "expected str, got bytes". UTF-8 and BOM-marked UTF-16/32 are supported. Eight additional regression tests cover a text-only XML parser, Hebrew text, BOM variants, DTD rejection and the exported template. Revit runtime confirmation remains pending. Create / Update code and settings are unchanged from v0.8.3.

## v0.9.2 diagnostic release

The reported bytes/str failure is not yet localized in the actual runtime. This release adds an independent WinForms error dialog with full traceback, a Copy full error report button and an automatic UTF-8 log at %TEMP%/HDL_IdentifyMEP_error.log. Startup imports are inside the diagnostic boundary. The pyRevit output window is not required. Core detection behavior is unchanged.

## v0.9.3 ZIP reader fix

The actual v0.9.2 traceback localizes the failure in IronPython zipfile.ZipFile(BytesIO(raw)), before XML parsing. Under IronPython, XLSX now uses System.IO.Compression.ZipArchive on a .NET MemoryStream of the same immutable input snapshot. XML entries are decoded by a BOM-aware StreamReader with strict UTF-8 fallback. CPython retains its standard zipfile backend. Archive, entry-reader and memory-stream resources are disposed explicitly. File and expanded-size limits and snapshot hashing are retained. Full traceback diagnostics remain enabled.

274 tests pass. The new tests verify runtime dispatch without invoking stdlib zipfile in the IronPython branch, full template reading through a simulated .NET adapter, Hebrew XML and resource disposal. The actual .NET adapter still requires execution in Revit; this environment does not contain IronPython/Revit.

## v0.9.4 Unicode XML parser fix

The v0.9.3 runtime traceback confirmed successful ZIP reading followed by an ASCII encoding failure inside IronPython ElementTree.feed on Hebrew. IronPython now parses XML with System.Xml.XmlDocument.LoadXml and traverses nodes using namespace-aware XPath. A small adapter preserves the existing reader interfaces. No ElementTree parsing occurs in the IronPython branch. Text and namespaced attributes remain Unicode. DTD/entity declarations remain rejected and XmlResolver is disabled. CPython parsing is unchanged.

278 tests pass, including tests that prohibit ElementTree parsing while checking Hebrew rich strings, inline cells, namespaced relationship attributes, XML traversal and the full exported template. The .NET interfaces are simulated in these local tests; actual Revit runtime confirmation is pending. Create / Update remains unchanged.

## v0.9.5 per-opening Unicode handling

The v0.9.4 report confirms Excel reading now succeeds. Most openings reported an ASCII conversion failure containing U+200E; the per-opening report did not include a traceback, so the exact failing line was not established. The identification path now uses Unicode literals, explicitly converts CLR names/titles to native Unicode and serializes metadata with a dedicated ASCII JSON writer. Non-ASCII characters, including U+200E and Hebrew, are escaped in stored JSON and round-trip unchanged. This bypasses implicit string encoding in the runtime JSON encoder.

Every preserved opening and candidate now records its processing stage and full traceback in %TEMP%/HDL_IdentifyMEP_preserved.log. The report displays the log path. Missing Excel mappings remain an explicit preservation reason; no output labels or disciplines are guessed. The observed missing types מים חמים and מים קרים must be added to the user workbook.

284 tests pass, including Unicode JSON round trips, invisible direction marks, rich XML and preservation/rollback orchestration. Actual Revit validation remains pending. Create / Update is unchanged.
