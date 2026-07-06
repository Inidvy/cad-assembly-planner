"""Tessellate OCC shapes into triangle meshes (world coordinates) for the viewer."""

from __future__ import annotations


def tessellate(shape, deflection: float = 0.4) -> tuple[list[tuple[float, float, float]],
                                                        list[tuple[int, int, int]]]:
    """Return (vertices, triangles) for `shape` in world space.

    vertices: list of (x, y, z) in mm. triangles: list of (i, j, k) vertex
    indices. `deflection` controls mesh fineness (smaller = finer, slower).
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    BRepMesh_IncrementalMesh(shape, deflection)
    verts: list[tuple[float, float, float]] = []
    tris: list[tuple[int, int, int]] = []

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face_s(exp.Current())
        reversed_face = face.Orientation() == TopAbs_REVERSED
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            trsf = loc.Transformation()
            base = len(verts)
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                verts.append((p.X(), p.Y(), p.Z()))
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Value(1), tri.Triangle(i).Value(2), \
                    tri.Triangle(i).Value(3)
                # Respect face orientation so outward normals are consistent
                # (needed for correct signed volume / watertight meshes).
                if reversed_face:
                    b, c = c, b
                tris.append((base + a - 1, base + b - 1, base + c - 1))
        exp.Next()
    return verts, tris
