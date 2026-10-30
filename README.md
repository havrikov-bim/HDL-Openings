# HDL Openings

pyRevit tools for creating, updating, identifying and numbering MEP openings in Autodesk Revit.

**Version: 0.9.8** · Author: Dmytro Havrikov

## Commands

| Command | Purpose |
| --- | --- |
| **Create / Update** | Create and synchronize openings from MEP geometry in the active model, using walls, floors and roofs in the active model and loaded direct links as construction context. |
| **Identify MEP** | Identify pipes, ducts, conduits and cable trays passing through openings; classify systems and disciplines using an editable Excel mapping. Searches the active model and loaded direct links. |
| **Number Openings** | Renumber elements with the writable Text instance parameter `SP_OP_Id`, starting at `ID #1`, in shared Z → X → Y order. Multiple editable open projects can be selected and numbered together. |

Create / Update calculates opening dimensions with insulation, clearance and penetration geometry. Pipes and conduits can produce circular openings when the configured core diameter and depth conditions are met; otherwise a rectangular opening is used. Ducts and cable trays produce rectangular openings. Rectangular width and height are rounded up using the configured step.

## Download and installation

1. [Download the v0.9.8 installation ZIP](https://github.com/havrikov-bim/HDL-Openings/raw/refs/heads/main/downloads/HDL_Openings_v0.9.8.zip), or use **Code → Download ZIP** for the repository source.
2. Extract the package and copy the entire `HDL Openings.extension` folder into your pyRevit extensions directory, normally `%APPDATA%\pyRevit\Extensions`.
3. Fully replace an earlier copy of this extension. Remove or disable the old standalone `HDL_NumberOpenings.extension` to avoid duplicate buttons.
4. Reload pyRevit. The **HDL Openings** tab contains **Create / Update**, **Identify MEP** and **Number Openings**.
5. Load the required opening families and configure their names in `HDL Openings.extension/settings.json`.
6. Copy `HDL_MEP_Mapping.xlsx` to an editable location and fill the **Systems** sheet with the exact system type names used in your project. Select the workbook on the first Identify MEP run; Shift-click selects a different workbook.

Requires Autodesk Revit with pyRevit. Revit and pyRevit are not included. A supported-version compatibility matrix has not yet been established.

**Opening family RFA files are not included.** Installation of the extension alone is insufficient for Create / Update. The expected families and placement conventions are described below and in the technical notes.

## Required families

| Family | Writable instance dimensions | Placement |
| --- | --- | --- |
| `BL Opening Rect Wall` | `Width`, `Height`, `Depth` | OneLevelBased, Work Plane-Based off, Always Vertical on |
| `BL Opening Round Wall` | `Diameter`, `Depth` | OneLevelBased, Work Plane-Based off, Always Vertical on |
| `BL Opening Rect Floor` | `Width`, `Height`, `Depth` | Work Plane-Based on, Always Vertical off |
| `BL Opening Round Floor` | `Diameter`, `Depth` | Work Plane-Based on, Always Vertical off |

Dimension parameters must be writable instance Length parameters. Roof openings use the floor families. Family origins, local axes and depth direction must match the contract in [Development notes](docs/DEVELOPMENT_NOTES.md#family-and-parameter-contract).

Number Openings requires a writable Text instance parameter named `SP_OP_Id`. Identify MEP requires a writable Text instance parameter named `SP_OP_MEP_Elements`; see its detailed documentation for the stored value and metadata.

## Workflow and settings

1. Run **Create / Update** and select the processing Scope Box. Review the generated report.
2. Run **Identify MEP** after creation or replacement of openings to refresh identification data.
3. Run **Number Openings** to assign the required numbering across the selected open models. This command renumbers all eligible elements in those models, independently of the Create / Update Scope Box.

`settings.json` controls family names, clearance, touching and gap thresholds, core diameters, maximum core depth, rectangular rounding and synchronization tolerances. Saved valid changes are read on the next command run.

The structural base layer must have both `Function = Structure [1]` and `Structural Material = Yes`. Construction without a qualifying layer is skipped.

## Scope and limitations

- Create / Update uses MEP in the **active model**, rather than linked MEP. Identify MEP additionally reads **loaded direct links**.
- Nearby penetrations from different MEP elements are **not merged into a common opening** in this version.
- Identification is command-driven. Run it again after relevant changes. Unloaded links are skipped and reported; their missing geometry can affect or clear previous identification results.
- Runtime calculation of shared parameters, including absolute elevation, is a separate project and is not bundled here. Tag Openings is also outside this package.
- Review opening placement, dimensions and reports in the target Revit project before issuing documentation.

## Validation

The supplied Python test suite passes **300 tests**. Run it from the repository root:

```bash
python -m unittest discover -s tests -q
```

These tests cover calculation and orchestration logic using Revit API substitutes. They do not establish compatibility with every Revit/pyRevit version or replace checks of geometry, family placement and transactions inside Revit.

## Documentation

- [Identify MEP: mapping, geometry and stored data](IDENTIFY_MEP_README.md)
- [Development notes in English](docs/DEVELOPMENT_NOTES.md) — technical overview, geometry, settings, synchronization and version history.
- [Original development notes in Russian](docs/DEVELOPMENT_NOTES.ru.md) — preserved implementation history; historical statements refer to their respective releases.

Report reproducible problems in [Issues](https://github.com/havrikov-bim/HDL-Openings/issues), including command version, Revit/pyRevit versions, expected result, actual result and a relevant diagnostic report.
