"""Stage 1 — Loader.

Read a STEP assembly into LoadedParts (named solids + centroid + bbox), with:
  - unit normalization to mm (OpenCASCADE converts to the target unit on read),
  - a validation GATE: at least 2 separable solids, else fail loud.

    STEP file ──STEPCAFControl_Reader──▶ XCAF doc
                                          │  walk assembly tree → leaf parts
                                          ▼
                                    LoadedAssembly(parts[], source_unit)

We use the CAF reader (not the plain STEPControl_Reader) so part NAMES survive —
the classifier depends on them.
"""

from __future__ import annotations

from pathlib import Path

from asmplan.geometry import LoadedAssembly, LoadedPart


class AssemblyLoadError(ValueError):
    """Raised when a STEP file cannot be used as an assembly (fused, flat,
    single-body, or otherwise below the >=2-solid bar)."""


def _centroid_and_bbox(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    c = props.CentreOfMass()
    centroid = (c.X(), c.Y(), c.Z())

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return centroid, (xmin, ymin, zmin), (xmax, ymax, zmax)


def _name_of(label) -> str | None:
    from OCP.TDataStd import TDataStd_Name

    attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attr):
        return attr.Get().ToExtString()
    return None


def _collect_leaf_parts(shape_tool, label, out: list) -> None:
    """Recurse the assembly tree; append (name, shape) for each leaf solid."""
    from OCP.TDF import TDF_Label, TDF_LabelSequence

    if shape_tool.IsAssembly_s(label):
        comps = TDF_LabelSequence()
        shape_tool.GetComponents_s(label, comps)
        for i in range(1, comps.Length() + 1):
            comp = comps.Value(i)
            referred = TDF_Label()
            if shape_tool.GetReferredShape_s(comp, referred):
                name = _name_of(comp) or _name_of(referred)
                if shape_tool.IsAssembly_s(referred):
                    _collect_leaf_parts(shape_tool, referred, out)
                else:
                    out.append((name, shape_tool.GetShape_s(comp)))
            else:
                out.append((_name_of(comp), shape_tool.GetShape_s(comp)))
    else:
        out.append((_name_of(label), shape_tool.GetShape_s(label)))


def load_step(path: str | Path) -> LoadedAssembly:
    """Load a STEP assembly. Raises AssemblyLoadError on unusable input."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    path = Path(path)
    if not path.exists():
        raise AssemblyLoadError(f"STEP file not found: {path}")

    doc = TDocStd_Document(TCollection_ExtendedString("MDTV-XCAF"))
    reader = STEPCAFControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise AssemblyLoadError(f"OpenCASCADE could not read STEP file: {path}")
    reader.Transfer(doc)

    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    shape_tool.GetFreeShapes(free)

    collected: list = []
    for i in range(1, free.Length() + 1):
        _collect_leaf_parts(shape_tool, free.Value(i), collected)

    # Validation gate: assembly planning needs >= 2 separable solids.
    if len(collected) < 2:
        raise AssemblyLoadError(
            f"expected >=2 separable solids, found {len(collected)} in {path.name}. "
            "The file may be fused, flat, or a single body — not an assembly."
        )

    parts: list[LoadedPart] = []
    for idx, (name, shape) in enumerate(collected):
        centroid, bbmin, bbmax = _centroid_and_bbox(shape)
        parts.append(
            LoadedPart(
                part_id=f"p{idx}",
                name=name,
                shape=shape,
                centroid=centroid,
                bbox_min=bbmin,
                bbox_max=bbmax,
            )
        )

    # OpenCASCADE normalizes geometry to its target unit (mm) on read. True
    # source-unit extraction + fail-loud-if-absent is a P2-full refinement; STEP
    # files essentially always declare a unit, and geometry here is in mm.
    return LoadedAssembly(parts=parts, source_unit="mm")
