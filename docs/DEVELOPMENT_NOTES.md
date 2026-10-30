# HDL Openings — Development Notes

English technical overview for **v0.9.8**. [Original development notes in Russian](DEVELOPMENT_NOTES.ru.md) · [Installation](../README.md) · [Identify MEP guide](../IDENTIFY_MEP_README.md)

The original notes preserve detailed implementation history. This overview describes the current package and distinguishes implemented behavior from historical notes.

## Architecture and command scope

HDL Openings is a pyRevit extension for creating and synchronizing editable opening instances in the active Revit project. Linked construction models provide read-only context; the extension does not modify or cut them.

| Command | Edited data | Geometry sources |
| --- | --- | --- |
| Create / Update | Managed openings and synchronization metadata in the active project | MEP in the active project; walls, floors and roofs in the active project and loaded direct links |
| Identify MEP | Opening identification data in the active project | Pipes, ducts, conduits and cable trays in the active project and loaded direct links |
| Number Openings | `SP_OP_Id` in selected editable open projects | Shared coordinates of eligible elements in those projects |

Commands run explicitly. There is no `DocumentChanged` handler or background elevation updater in this package. Runtime shared-parameter calculation and Tag Openings are separate projects.

## Family and parameter contract

RFA files are not included. Load the four configured families before using Create / Update.

| Family | Writable instance dimensions | Local geometry convention | Placement |
| --- | --- | --- | --- |
| `BL Opening Rect Wall` | `Width`, `Height`, `Depth` | Width centered on X; Height starts at Ref Level along +Z; Depth extends along +Y | OneLevelBased; Work Plane-Based off; Always Vertical on |
| `BL Opening Round Wall` | `Diameter`, `Depth` | Circle centered at Ref Level; Depth extends along +Y | OneLevelBased; Work Plane-Based off; Always Vertical on |
| `BL Opening Rect Floor` | `Width`, `Height`, `Depth` | Width/Height centered on X/Y; top of Depth at Ref Level, extending along −Z | Work Plane-Based on; Always Vertical off |
| `BL Opening Round Floor` | `Diameter`, `Depth` | Circle centered on the reference plane; Depth extends along −Z | Work Plane-Based on; Always Vertical off |

Dimensions must be writable instance Length parameters; they need not be shared. Duplicate names and type parameters substituted for the required instance parameters are rejected. If several family types exist, the first by name is selected and reported. Roof openings use the floor families.

Create / Update does not write `SP_BOM_*` values: dimensional values are handled by family formulas. `SP_BOM_Absolute_Elevation` is excluded from this command; its runtime service is external to the package.

Floor and roof openings use existing source faces, with `CreateLinkReference` for linked faces. No ReferencePlane or SketchPlane is created. Suitable top/bottom planar faces must be parallel to the calculated normal. A parallel external face with an offset can support placement at an internal base-layer boundary. The projected insertion point must belong to the actual face region. Failed hosting retains the corresponding existing opening and is reported.

## Cross-sections and insulation

Create / Update supports straight MEP with constant Round, Rectangular or Oval profiles. Oval ducts are treated as flat ovals with straight central sections and semicircular ends, rather than ellipses. Connector vectors account for profile rotation.

Pipe and duct insulation is obtained through `InsulationLiningBase.GetInsulationIds` in the active document. Insulation solids participate in intersection detection, including insulation-only entry. Internal duct lining is not added to the outside envelope. Conduits use their actual outside diameter; separate custom coverings are not automatically treated as insulation.

Missing insulation thickness/geometry and multiple separate insulation elements on one MEP element are reported rather than silently calculating from the bare element.

## Circular and rectangular sizing

Only pipes and conduits can produce circular openings. Ducts of every profile and cable trays produce rectangular openings.

1. Read the actual outside diameter using `RBS_PIPE_OUTER_DIAMETER` or `RBS_CONDUIT_OUTER_DIAM_PARAM`, not nominal DN or Trade Size.
2. Include insulation on both sides: `D_e = D_out + 2s`.
3. Select the first configured core strictly larger than `D_0 = D_e + 2t`. An exact match advances to the next size.
4. Check the complete oblique penetration envelope: `D_required = D_e / cos(α) + L × tan(α) + 2t`.
5. Accept the circular shape when `D_required ≤ D_core` and `L ≤ MaxCoreDepth`. The center lies halfway along the lateral axis displacement through construction. Actual depth is rechecked against the accepted layers, with up to eight center/depth refinement iterations and a convergence check.
6. If the core is unavailable, the envelope does not fit, depth exceeds the limit or refinement fails, use a rectangular opening and report why. A further enlarged core is not selected merely to accommodate inclination.

Here, `s` is insulation thickness, `t` is clearance on each side, `α` is the angle from the penetration normal and `L` is normal penetration depth.

Default core sizes: **1, 1¼, 1½, 2, 3, 4, 5, 6, 8, 10 and 12 inches**. The initial series excludes 2½ and 3½ inches. One inch is 25.4 mm. Default maximum core depth is 1000 mm inclusive; this is an algorithm setting, not a universal equipment limit.

Rectangular sizing accounts for outside profile, insulation, inclination, rotation and clearance. Width and Height are rounded up to `rect_size_step_mm`, initially 50 mm, with the increase distributed symmetrically about the section center: 312 → 350 mm, 400 → 400 mm. Depth is not rounded.

## Structural base layer and ThroughAll

A base layer must satisfy **both** `Function = Structure [1]` and the Structural Material designation represented by `CompoundStructure.StructuralMaterialIndex`. The instance-level Structural parameter is not used. Without an eligible, actually intersected layer, no opening is created; there is no fallback to a nonstructural layer.

Select the thickest eligible layer, rather than the construction with the greatest total thickness. For equal thicknesses, compare the 3D distance from the active project's Project Base Point to the penetration center on each layer's mid-plane. Linked geometry is transformed to the same coordinates. Stable coordinates and UniqueId resolve exact ties.

Layers are reconstructed from homogeneous CompoundStructure definitions and source solids by half-space clipping along the normal. Material physical properties do not determine eligibility. Vertically heterogeneous walls, folded undersides and variable structural base-layer thickness require separate handling. A variable upper layer over a constant base is permitted.

Penetrations of the **same MEP element** are grouped along compatible normals when `Gap ≤ T_gap`, initially 50 mm. Opposite normals are aligned; nonparallel directions remain separate. Different MEP elements are **not merged into a common opening**.

| `ThroughAll` | Resulting depth |
| --- | --- |
| `0` | Selected base layer only |
| `1` (default) | Accepted adjacent construction/layer group, including finishes and gaps |

Both modes require an eligible base layer. For a straight assembly with a 20 mm finish and marked 100 mm structural layer, the depths are 100 mm and 120 mm respectively. Entry and `K_slope` checks apply to the base layer; dimensions and core fit are recalculated over the final ThroughAll volume.

## Settings and cache

`settings.json` is located in `HDL Openings.extension`; its path is resolved relative to the extension, not the working directory.

| Key | Default | Accepted values |
| --- | --- | --- |
| `schema_version` | `1` | Integer 1 only |
| `ThroughAll` | `1` | Integer 0 or 1 |
| `clearance_mm` | `25` | 0–1000 mm |
| `gap_mm` | `50` | 0–10000 mm |
| `touch_mm` | `25` | 0–1000 mm |
| `k_slope` | `1.5` | 1–100 |
| `max_core_depth_mm` | `1000` | 0.1–10000 mm |
| `rect_size_step_mm` | `50` | 0.1–1000 mm |
| `core_diameters_inch` | Series above | 1–256 unique numbers; each 0.01–120 inches |
| `families` | Four family names | Distinct nonempty strings, at most 200 characters each |
| `sync_length_tolerance_mm` | `0.1` | 0.0001–10 mm |
| `sync_angle_tolerance_deg` | `0.01` | 0.000001–1 degree |

Required family keys: `rect_wall`, `rect_floor`, `round_wall`, `round_floor`. Core sizes are sorted after validation. `ThroughAll` and `sync_*` keys can be omitted for compatibility with older settings; defaults apply. Synchronization tolerances compare state and do not replace geometric clearances or rounding steps.

Files are limited to 65536 bytes and nesting depth 16. UTF-8 with optional BOM is accepted. Unknown/duplicate keys, missing required fields, unsupported versions, invalid numeric types, NaN/Infinity and out-of-range values are rejected. JSON contains data only.

The persistent engine checks file metadata once per run. Unchanged settings are not reread or reparsed. Changed files are read into a temporary structure, checked for concurrent changes and fully validated before atomically replacing the cache. One immutable snapshot is used throughout the run. SHA-256 identifies the settings used in reports and instance metadata.

Invalid, missing or inaccessible settings retain the last valid snapshot and produce a warning. If no valid snapshot exists, the command stops before a model transaction. Edits preserving all tracked metadata may not be detected.

## Scope Box

Create / Update requires one Scope Box from the active project. The picker displays its name and ElementId. Cancellation, no boxes or unreadable box geometry produces no changes; processing does not automatically switch to the whole model.

The complete final opening volume must fit inside the box in all three dimensions. Checks account for box rotation, opening orientation, final rounded dimensions and depth. Circular openings are checked as cylinders, with a small boundary tolerance. Partially outside openings are skipped.

An oriented region is reconstructed from Scope Box line geometry, rather than substituting a world-axis-aligned bounding box. Preliminary MEP bounding-box filtering preserves long elements whose endpoints are outside but whose penetration is inside. Construction is analyzed without clipping to avoid changing layer groups or depth.

Existing openings not fully inside are not deleted, replaced or assigned new synchronization metadata. If either the old or new position lies outside, the existing opening is retained for review; choose a box containing both positions to synchronize that movement. Scope Box selection does not itself change OpeningGuid.

## Identity, storage and transactions

Each managed FamilyInstance stores an Extensible Storage entity. Schema `HDLOpeningsSynchronizationV2` contains `OpeningGuid` (`System.Guid`) and JSON `Payload`. No document-level DataStorage is used. The schema GUID is common; OpeningGuid belongs to a penetration condition. Replacing an instance changes its Revit UniqueId.

Payload version 7 includes source/UniqueId identifiers, construction layer indices and fingerprints, selected base, MEP axis/profile/insulation, interaction intervals, opening axes and source face, final dimensions/shape/placement/type, algorithm version, settings fingerprint and run identifier. Lengths use Revit internal feet; directions use unit vectors.

The condition key uses the MEP source/UniqueId, selected base and exact set of construction sources/UniqueIds/layer indices/definition fingerprints. Enumeration order does not matter. Coordinates, angles and sizes are state, rather than permanent identity.

| Situation | Action |
| --- | --- |
| Same condition and same state | Keep the instance; refresh metadata if needed |
| Same condition; changed position, orientation, shape, type or sizes | Replace the instance, preserving OpeningGuid |
| Changed participants, base or layer definitions | Create a new OpeningGuid; remove the predecessor after successful verification |
| Confirmed deleted MEP or successfully checked MEP no longer requiring a passage | Delete the obsolete managed opening |
| Calculation, link availability or hosting uncertainty | Retain the corresponding opening and report the reason |
| Duplicate identity or unreadable/incompatible entity | Do not resolve by arbitrary identity inheritance |

Unmanaged instances are not modified by synchronization. Old Payload versions 3–6 are migrated by recreating successfully checked penetrations inside the Scope Box with new GUIDs; uncertain or out-of-scope instances remain.

Actions are planned before writing and committed in one `HDL Create Openings` transaction. New instances are verified before predecessors are deleted. Creation, deletion or metadata-write failure rolls back the run. Undo/Redo applies to the whole transaction. Reports distinguish create, replace, delete, refresh, keep, retain and skip.

## Passage-local unsupported-host checks

The v0.9.6 correction checks unsupported construction against each individual opening volume, including clearance. A distant unsupported host intersecting the full MEP bounding box no longer blocks unrelated passages.

Bounding boxes are preliminary filters; transformed physical construction solids determine final overlap. Failed-host solids are extracted lazily and cached per run. Local overlap, unavailable local solids or Boolean failure preserves existing openings and skips affected new passages. Diagnostics identify the link, host, MEP and check stage. Variable structural base layers still require separate local-thickness support.

## Identification and numbering

Identify MEP processes the four configured opening families, including manually placed instances. The Excel mapping defines system labels and disciplines. Results are written to `SP_OP_MEP_Elements`; detailed provenance is saved in a separate Extensible Storage entity. Synchronization metadata and numbering are not overwritten. See the [Identify MEP guide](../IDENTIFY_MEP_README.md) for exact qualification and mapping rules.

Unloaded links are skipped and reported. Results are recalculated from available geometry; previous values can change or clear if their only source is unloaded. Load all required links before a complete run. Rerun identification after Create / Update replaces an opening instance.

Number Openings v2.0.1 processes eligible elements with writable Text instance parameter `SP_OP_Id`. One editable open project runs without a model picker; multiple projects show a checkbox selection. Selected models are numbered together by shared Z → X → Y from `ID #1`. Their shared coordinates must be coordinated. Numbering is independent of the Create / Update Scope Box.

## Limitations

- Create / Update supports straight MEP with constant profiles; fittings are not analyzed.
- Walls must be straight and vertical. Floors need a coplanar flat underside; overall slope is permitted. Folded undersides are reported. Roofs follow equivalent geometry/base-layer requirements.
- Section dimensions are analytical. Entry/depth use conservative bounds from Revit Boolean solids; complex trimmed surfaces can add allowance. Arbitrary nonparallel surfaces are not claimed as fully supported.
- Create / Update uses active-model MEP only. Linked construction is limited to loaded direct links, without nested-link traversal.
- Different MEP elements are not combined into one opening. Annotation transfer and runtime elevation calculation are outside synchronization scope.

## Version history

| Version | Change |
| --- | --- |
| 0.9.8 | Restored Number Openings v2.0.1 with multi-model selection and shared-coordinate numbering; other commands unchanged from 0.9.7 |
| 0.9.7 | Identify MEP skips unloaded links, recalculates from available sources and records unavailable links |
| 0.9.6 | Localized unsupported-host checks to each opening volume |
| 0.8.3 | Added Create / Update ribbon placement and light/dark icons; standalone numbering described in historical notes is now bundled |
| 0.8.2 | Corrected wall OneLevelBased insertion Z to model Z minus `Level.ProjectElevation`; calculated geometry and synchronization data remain in active-model coordinates |
| 0.8.0 | Introduced revised penetration-condition identity and Payload 7 migration |

## Verification

The v0.9.8 package passed **300 local automated tests** during repository preparation:

```bash
python -m unittest discover -s tests -q
```

Coverage includes sizing, core selection, insulation, structural layers, ThroughAll, Scope Box, settings, synchronization, passage-local coverage, identification and multi-model numbering. API-dependent tests use substitutes. They do not verify Revit's actual geometry kernel, family hosting, ribbon or transaction execution. Target-project runtime verification remains necessary. Earlier test counts and runtime status in the original notes refer to historical releases.
