"""Independent check of the 230 V isolation: smallest copper gap between any 230 V net and
any low-voltage copper (pads, tracks, filled zones), per copper layer."""
import math
import sys

import pcbnew

MAINS = {"L_IN", "L_F", "N", "AUTO", "A1"}
board = pcbnew.LoadBoard(sys.argv[1] if len(sys.argv) > 1 else "tank_controller.kicad_pcb")


def shapes(layer):
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.IsOnLayer(layer) and p.GetNetname():
                ps = pcbnew.SHAPE_POLY_SET()
                p.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
                out.append((p.GetNetname(), f"{fp.GetReference()}.{p.GetNumber()}", ps))
    for t in board.GetTracks():
        if t.IsOnLayer(layer):
            ps = pcbnew.SHAPE_POLY_SET()
            t.TransformShapeToPolygon(ps, layer, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
            out.append((t.GetNetname(), "track", ps))
    for z in board.Zones():
        if not z.GetIsRuleArea() and z.IsOnLayer(layer):
            out.append((z.GetNetname(), "zone", z.GetFilledPolysList(layer)))
    return out


def vertices(ps):
    for i in range(ps.OutlineCount()):
        o = ps.Outline(i)
        for j in range(o.PointCount()):
            yield o.CPoint(j)


def gap(a, b):
    best = min((b.SquaredDistance(v) for v in vertices(a)), default=float("inf"))
    best = min(best, min((a.SquaredDistance(v) for v in vertices(b)), default=float("inf")))
    return pcbnew.ToMM(int(math.sqrt(best)))


for layer, name in ((pcbnew.F_Cu, "F.Cu"), (pcbnew.B_Cu, "B.Cu")):
    s = shapes(layer)
    hv = [x for x in s if x[0] in MAINS]
    lv = [x for x in s if x[0] not in MAINS and x[2].OutlineCount()]
    g, pair = min(((gap(h[2], l[2]), (f"{h[0]} {h[1]}", f"{l[0]} {l[1]}")) for h in hv for l in lv), key=lambda r: r[0])
    print(f"{name}: smallest 230 V to low-voltage gap = {g:.2f} mm  ({pair[0]}  <->  {pair[1]})")
