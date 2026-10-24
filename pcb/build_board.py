"""Generates tank_controller.kicad_pcb (run with KiCad's bundled python).

All coordinates are board-local millimetres: origin = top-left corner of the board,
x to the right, y downwards. The top strip carries the 230 V terminals and parts,
the lower part is the 5 V / 3.3 V side with the ESP32 sockets. Zones are filled
afterwards by `kicad-cli pcb drc --refill-zones --save-board` (see make.ps1), so the
.kicad_pro net classes and .kicad_dru isolation rules apply to the fill.
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
FP_DIR = os.environ.get("KICAD_FP_DIR", r"C:\Users\nitee\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints")
OUT = os.path.join(HERE, "tank_controller.kicad_pcb")

OX, OY = 30.0, 30.0            # where the board sits on the KiCad sheet
W, H = 100.0, 98.0             # board size (fits the 100 x 100 mm price tier)
MAINS_W, PWR_W, SIG_W = 1.0, 0.8, 0.3


def P(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


def mm(v):
    return pcbnew.FromMM(v)


board = pcbnew.BOARD()
nets = {}


def net(name):
    if name not in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
    return nets[name]


fps = {}


def place(ref, lib, name, x, y, rot=0, value="", pads=None):
    fp = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + ".pretty"), name)
    fp.SetFPIDAsString(f"{lib}:{name}")
    fp.SetReference(ref)
    fp.SetValue(value or name)
    fp.SetPosition(P(x, y))
    fp.SetOrientationDegrees(rot)
    board.Add(fp)
    for num, n in (pads or {}).items():
        pad = fp.FindPadByNumber(str(num))
        if pad is None:
            sys.exit(f"{ref}: no pad {num}")
        pad.SetNet(net(n))
    fp.Value().SetVisible(False)
    fps[ref] = fp
    return fp


def pad_xy(spec):
    ref, num = spec.split(".", 1)
    pos = fps[ref].FindPadByNumber(num).GetPosition()
    return pcbnew.ToMM(pos.x) - OX, pcbnew.ToMM(pos.y) - OY


def pt(p):
    return pad_xy(p) if isinstance(p, str) else p


def track(netname, width, layer, *points):
    pts = [pt(p) for p in points]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(x1, y1))
        t.SetEnd(P(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        board.Add(t)


def via(netname, x, y, size=0.8, drill=0.4):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y))
    v.SetDrill(mm(drill))
    try:
        v.SetWidth(mm(size))
    except TypeError:
        v.SetWidth(pcbnew.F_Cu, mm(size))
    v.SetNet(net(netname))
    # Leave the hole open. A 0.4 mm drill is too big for a reliable solder-mask tent.
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    v.SetBackTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    board.Add(v)


def silk(text, x, y, size=1.1, rot=0, bold=False, layer=pcbnew.F_SilkS):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(P(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.16, size * (0.2 if bold else 0.16))))
    t.SetTextAngleDegrees(rot)
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
    board.Add(t)


def line(x1, y1, x2, y2, layer=pcbnew.F_SilkS, width=0.16):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(P(x1, y1))
    s.SetEnd(P(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def arc(cx, cy, r, a0, a1, layer=pcbnew.F_SilkS, width=0.16):
    """Arc from angle a0 to a1 in degrees, measured clockwise from +x (y points down)."""
    def at(a):
        return P(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))

    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_ARC)
    s.SetArcGeometry(at(a0), at((a0 + a1) / 2), at(a1))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def plus(x, y, arm=0.5):
    line(x - arm, y, x + arm, y, width=0.2)
    line(x, y - arm, x, y + arm, width=0.2)


def _seg_point(x1, y1, x2, y2, px, py):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _seg_seg(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    if orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0:
        return 0.0
    return min(
        _seg_point(*a, *b, *c),
        _seg_point(*a, *b, *d),
        _seg_point(*c, *d, *a),
        _seg_point(*c, *d, *b),
    )


def enlarge_pad(ref, num, diameter):
    pad = fps[ref].FindPadByNumber(str(num))
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(mm(diameter), mm(diameter)))


def gnd_stub(ref, num, width=0.30):
    """Tie a ground pad into the pour with a short radial stub.

    A long track beside the pour edge, or a via parked on the pad, leaves a
    sliver the fab counts as copper spacing. The stub stops on the pad ring
    and ends well inside the pour, with no via of its own.
    """
    pad = fps[ref].FindPadByNumber(str(num))
    cx = pcbnew.ToMM(pad.GetPosition().x) - OX
    cy = pcbnew.ToMM(pad.GetPosition().y) - OY
    hr = pcbnew.ToMM(pad.GetDrillSize().x) / 2
    pr = pcbnew.ToMM(pad.GetSize().x) / 2
    inner = pr - 0.06
    if inner < hr + 0.22 + width / 2:
        sys.exit(f"{ref}.{num}: annular ring too small for a {width} mm stub")
    # Pour starts 0.40 mm from other copper. The round end has to sit 0.20 mm
    # inside that edge, so the centerline stays 0.60 mm off other pads.
    min_outer = pr + 0.40 + width / 2 + 0.40
    keepout = (96.8, 58.5, 100.0, 91.0)

    def inside(x, y):
        if not (1.6 <= x <= 98.2 and 45.6 <= y <= 96.4):
            return False
        return not (keepout[0] <= x <= keepout[2] and keepout[1] <= y <= keepout[3])

    def clear(x1, y1, x2, y2):
        half = width / 2
        for fp in board.GetFootprints():
            for other in fp.Pads():
                if other == pad:
                    continue
                px = pcbnew.ToMM(other.GetPosition().x) - OX
                py = pcbnew.ToMM(other.GetPosition().y) - OY
                rad = max(pcbnew.ToMM(other.GetSize().x), pcbnew.ToMM(other.GetSize().y)) / 2
                if _seg_point(x1, y1, x2, y2, px, py) < rad + half + 0.60:
                    return False
        for item in board.GetTracks():
            if item.GetClass() == "PCB_VIA":
                vx = pcbnew.ToMM(item.GetPosition().x) - OX
                vy = pcbnew.ToMM(item.GetPosition().y) - OY
                if _seg_point(x1, y1, x2, y2, vx, vy) < pcbnew.ToMM(item.GetDrill()) / 2 + 0.25 + half:
                    return False
                continue
            if item.GetNetname() == "GND":
                continue
            a = (pcbnew.ToMM(item.GetStart().x) - OX, pcbnew.ToMM(item.GetStart().y) - OY)
            b = (pcbnew.ToMM(item.GetEnd().x) - OX, pcbnew.ToMM(item.GetEnd().y) - OY)
            if _seg_seg((x1, y1), (x2, y2), a, b) < half + pcbnew.ToMM(item.GetWidth()) / 2 + 0.70:
                return False
        return True

    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0), (-1, -1), (1, -1), (-1, 1), (1, 1)):
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        x1, y1 = cx + ux * inner, cy + uy * inner
        for outer in (pr + 1.50, pr + 1.20, min_outer):
            x2, y2 = cx + ux * outer, cy + uy * outer
            if inside(x1, y1) and inside(x2, y2) and clear(x1, y1, x2, y2):
                track("GND", width, pcbnew.F_Cu, (x1, y1), (x2, y2))
                print(f"stub {ref}.{num} -> ({x2:.2f}, {y2:.2f})")
                return
    sys.exit(f"no clear ground stub for {ref}.{num}")


def extend_ground_stubs():
    """Continue each ground stub to a via that sits well inside the pour.

    The via pad is 0.25 mm larger than the track, so it cannot sit at the
    track end. It goes further in, where the pour still surrounds it.
    """
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    zone = next(z for z in board.Zones() if not z.GetIsRuleArea() and z.GetLayer() == pcbnew.F_Cu and z.GetNetname() == "GND")
    polys = zone.GetFilledPolysList(pcbnew.F_Cu)
    segs = []
    for i in range(polys.OutlineCount()):
        outline = polys.Outline(i)
        pts = [(pcbnew.ToMM(outline.CPoint(j).x) - OX, pcbnew.ToMM(outline.CPoint(j).y) - OY) for j in range(outline.PointCount())]
        segs.extend((pts[j], pts[(j + 1) % len(pts)]) for j in range(len(pts)))
    keepout = (96.8, 58.5, 100.0, 91.0)

    def edge_gap(x, y):
        best = 99.0
        for a, c in segs:
            if min(a[0], c[0]) - 3 > x or max(a[0], c[0]) + 3 < x:
                continue
            if min(a[1], c[1]) - 3 > y or max(a[1], c[1]) + 3 < y:
                continue
            best = min(best, _seg_point(a[0], a[1], c[0], c[1], x, y))
        return best

    def _stub_clear(pad, x1, y1, x2, y2):
        half = 0.15
        for fp in board.GetFootprints():
            for other in fp.Pads():
                if other == pad:
                    continue
                px = pcbnew.ToMM(other.GetPosition().x) - OX
                py = pcbnew.ToMM(other.GetPosition().y) - OY
                rad = max(pcbnew.ToMM(other.GetSize().x), pcbnew.ToMM(other.GetSize().y)) / 2
                if _seg_point(x1, y1, x2, y2, px, py) < rad + half + 0.60:
                    return False
        for item in board.GetTracks():
            if item.GetClass() == "PCB_VIA":
                vx = pcbnew.ToMM(item.GetPosition().x) - OX
                vy = pcbnew.ToMM(item.GetPosition().y) - OY
                if _seg_point(x1, y1, x2, y2, vx, vy) < 0.2 + 0.25 + half:
                    return False
                continue
            if item.GetNetname() == "GND":
                continue
            a = (pcbnew.ToMM(item.GetStart().x) - OX, pcbnew.ToMM(item.GetStart().y) - OY)
            c = (pcbnew.ToMM(item.GetEnd().x) - OX, pcbnew.ToMM(item.GetEnd().y) - OY)
            if _seg_seg((x1, y1), (x2, y2), a, c) < half + pcbnew.ToMM(item.GetWidth()) / 2 + 0.70:
                return False
        return True

    def open_spot(x, y):
        if not (2.0 <= x <= 98.0 and 46.5 <= y <= 96.0):
            return False
        if keepout[0] <= x <= keepout[2] and keepout[1] <= y <= keepout[3]:
            return False
        pt = pcbnew.VECTOR2I(pcbnew.FromMM(x + OX), pcbnew.FromMM(y + OY))
        if not zone.HitTestFilledArea(pcbnew.F_Cu, pt):
            return False
        # Via pad is 0.40 mm, mask opening 0.50 mm. Keep both inside the pour.
        if edge_gap(x, y) < 0.75:
            return False
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                px = pcbnew.ToMM(pad.GetPosition().x) - OX
                py = pcbnew.ToMM(pad.GetPosition().y) - OY
                rad = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2
                if math.hypot(px - x, py - y) < rad + 0.65:
                    return False
        for item in board.GetTracks():
            if item.GetClass() == "PCB_VIA":
                vx = pcbnew.ToMM(item.GetPosition().x) - OX
                vy = pcbnew.ToMM(item.GetPosition().y) - OY
                if math.hypot(vx - x, vy - y) < 1.1:
                    return False
                continue
            if item.GetNetname() == "GND":
                continue
            a = (pcbnew.ToMM(item.GetStart().x) - OX, pcbnew.ToMM(item.GetStart().y) - OY)
            c = (pcbnew.ToMM(item.GetEnd().x) - OX, pcbnew.ToMM(item.GetEnd().y) - OY)
            if _seg_point(a[0], a[1], c[0], c[1], x, y) < pcbnew.ToMM(item.GetWidth()) / 2 + 0.65:
                return False
        return True

    for item in list(board.GetTracks()):
        if item.GetClass() == "PCB_VIA" or item.GetNetname() != "GND" or not item.IsOnLayer(pcbnew.F_Cu):
            continue
        if abs(pcbnew.ToMM(item.GetWidth()) - 0.30) > 0.01:
            continue
        x1 = pcbnew.ToMM(item.GetStart().x) - OX
        y1 = pcbnew.ToMM(item.GetStart().y) - OY
        x2 = pcbnew.ToMM(item.GetEnd().x) - OX
        y2 = pcbnew.ToMM(item.GetEnd().y) - OY
        length = math.hypot(x2 - x1, y2 - y1)
        if length < 0.2:
            continue
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        placed = False
        for step in (0.45, 0.70, 1.00, 1.40):
            vx, vy = x2 + ux * step, y2 + uy * step
            if open_spot(vx, vy):
                via("GND", vx, vy)
                item.SetEnd(P(vx, vy))
                print(f"stub extended to via ({vx:.2f}, {vy:.2f})")
                placed = True
                break
        if placed:
            continue
        # The first direction ran out of pour. Draw the stub the other way,
        # still in a straight line, if that side has room for the via.
        pad = min(
            (p for fp in board.GetFootprints() for p in fp.Pads() if p.GetNetname() == "GND"),
            key=lambda p: (pcbnew.ToMM(p.GetPosition().x) - OX - x1) ** 2 + (pcbnew.ToMM(p.GetPosition().y) - OY - y1) ** 2,
        )
        cx = pcbnew.ToMM(pad.GetPosition().x) - OX
        cy = pcbnew.ToMM(pad.GetPosition().y) - OY
        pr = pcbnew.ToMM(pad.GetSize().x) / 2
        inner = pr - 0.06
        for dx, dy in ((0, 1), (0, -1), (-1, 0), (1, 0), (-1, 1), (1, 1), (-1, -1), (1, -1)):
            el = math.hypot(dx, dy)
            rx, ry = dx / el, dy / el
            sx, sy = cx + rx * inner, cy + ry * inner
            found = None
            for step in (1.15, 1.45, 1.80):
                vx, vy = cx + rx * (pr + step), cy + ry * (pr + step)
                if open_spot(vx, vy) and _stub_clear(pad, sx, sy, vx, vy):
                    found = (vx, vy)
                    break
            if found:
                via("GND", found[0], found[1])
                item.SetStart(P(sx, sy))
                item.SetEnd(P(found[0], found[1]))
                print(f"stub redirected to via ({found[0]:.2f}, {found[1]:.2f})")
                break
        else:
            # J7 pin 3 has the 5 V track on one side and the next socket pin on
            # the other, so the front has no room for a hole. The back layer is
            # clear: run over to the ground via at (30, 48).
            if abs(cx - 62.54) < 0.1 and abs(cy - 62.0) < 0.1:
                board.Remove(item)
                track("GND", 0.30, pcbnew.B_Cu,
                      (cx, cy - inner), (cx, 57.6), (34, 57.6), (34, 53.5), (30, 53.5), (30, 48))
                print("stub J7.3 on back layer -> via (30.00, 48.00)")


def pull_silk(gap):
    """Drop silkscreen that would print on, or within gap of, a pad or an open via."""
    shapes = [(p.GetEffectiveShape(pcbnew.F_Cu), mm(gap)) for fp in board.GetFootprints() for p in fp.Pads()]
    # Via holes are left open, so the mask opening is 0.10 mm past the via pad.
    for item in board.GetTracks():
        if item.GetClass() == "PCB_VIA":
            shapes.append((item.GetEffectiveShape(), mm(gap + 0.10)))

    def close(item):
        if item.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            return False
        try:
            shape = item.GetEffectiveShape()
        except Exception:
            return False
        for other, extra in shapes:
            if shape.Collide(other, extra):
                return True
        return False

    removed = 0
    for fp in board.GetFootprints():
        for item in list(fp.GraphicalItems()):
            if not close(item):
                if item.GetClass() == "PCB_SHAPE" and item.GetWidth() < mm(0.16):
                    item.SetWidth(mm(0.16))
                continue
            if item.GetClass() == "PCB_SHAPE":
                fp.Remove(item)
            else:
                item.SetVisible(False)
            removed += 1
        for item in (fp.Reference(), fp.Value()):
            if item is not None and close(item):
                item.SetVisible(False)
                removed += 1
    for item in list(board.GetDrawings()):
        if not close(item):
            continue
        label = ""
        if item.GetClass() == "PCB_TEXT":
            label = item.GetText()
        print("silk removed board item", item.GetClass(), label)
        board.Remove(item)
        removed += 1
    print("silk moved off pads:", removed)


def rect(x1, y1, x2, y2, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(P(x1, y1))
    s.SetEnd(P(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def polygon_zone(points, layer=None, netname=None, rule_area=False):
    z = pcbnew.ZONE(board)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetLayerSet(pcbnew.LSET.AllCuMask())
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowZoneFills(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetLayer(layer)
        z.SetNet(net(netname))
        z.SetMinThickness(mm(0.25))
        z.SetThermalReliefGap(mm(0.5))
        z.SetThermalReliefSpokeWidth(mm(0.6))
        # No thermal spokes. A spoke is drawn into the pad and the fab checker
        # measures it as copper on the hole wall. Pads join the pour by a short
        # track that stops on the annulus (see gnd_stub).
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_NONE)
        z.SetLocalClearance(mm(0.4))
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in points:
        o.Append(mm(OX + x), mm(OY + y))
    board.Add(z)
    return z


# ================================================================ parts
TB = "TerminalBlock_Phoenix"
TB2 = "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
TB3 = "TerminalBlock_Phoenix_MKDS-1,5-3-5.08_1x03_P5.08mm_Horizontal"
TB4 = "TerminalBlock_Phoenix_MKDS-1,5-4-5.08_1x04_P5.08mm_Horizontal"

# 230 V terminals, turned 180 deg so the wire openings face the top edge (pad 1 is the right-hand screw)
place("J1", TB, TB2, 17.08, 9, 180, "MAINS IN", {2: "L_IN", 1: "N"})
place("J2", TB, TB3, 35.16, 9, 180, "SELECTOR S1", {3: "L_F", 2: "AUTO", 1: "A1"})
place("J3", TB, TB2, 48.08, 9, 180, "KM COIL", {2: "A1", 1: "N"})
place("J4", TB, TB2, 61.08, 9, 180, "LAMP H1", {2: "A1", 1: "N"})

place("F1", "Fuse", "Fuseholder_Cylinder-5x20mm_Schurter_0031_8201_Horizontal_Open", 12, 24, 0, "1A T",
      {1: "L_IN", 2: "L_F"})
place("RV1", "Varistor", "RV_Disc_D12mm_W4.2mm_P7.5mm", 26, 36, 180, "275VAC", {1: "L_F", 2: "N"})
place("PS1", "Converter_ACDC", "Converter_ACDC_Hi-Link_HLK-5Mxx", 58, 22, 270, "HLK-5M05",
      {1: "L_F", 2: "N", 3: "GND", 4: "+5V"})
place("K1", "Relay_THT", "Relay_SPST_Omron_G5NB", 74, 50, 90, "G5NB-1A-E 5VDC",
      {"A1": "+5V", "A2": "COIL_N", "13": "AUTO", "14": "A1"})

# relay driver
place("Q1", "Package_TO_SOT_THT", "TO-92_Inline_Wide", 90, 52, 180, "BC547", {1: "COIL_N", 2: "BASE", 3: "GND"})
place("D1", "Diode_THT", "D_DO-35_SOD27_P7.62mm_Horizontal", 70, 55, 0, "1N4148", {1: "+5V", 2: "COIL_N"})
R = "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
place("R1", "Resistor_THT", R, 77, 58.5, 0, "1k", {1: "RLY", 2: "BASE"})
place("R2", "Resistor_THT", R, 87.5, 58.5, 0, "10k", {1: "BASE", 2: "GND"})
place("R5", "Resistor_THT", R, 83, 45, 0, "1k", {1: "+5V", 2: "LED_RLY"})
place("LED2", "LED_THT", "LED_D3.0mm", 96, 46, 180, "RELAY", {1: "COIL_N", 2: "LED_RLY"})

# 5 V supply side
place("C1", "Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", 37.5, 56, 270, "470uF 16V", {1: "+5V", 2: "GND"})
place("C2", "Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm", 31, 56, 270, "100nF", {1: "+5V", 2: "GND"})
place("R4", "Resistor_THT", R, 23.62, 56, 180, "1k", {1: "+5V", 2: "LED_PWR"})
place("LED1", "LED_THT", "LED_D3.0mm", 10, 56, 0, "PWR", {1: "GND", 2: "LED_PWR"})

# sensor
place("J5", TB, TB4, 12, 90, 0, "SENSOR", {1: "+3V3", 2: "SENS_TX", 3: "GND", 4: "GND"})
place("R3", "Resistor_THT", R, 40, 93.5, 0, "330", {1: "SENS_TX", 2: "RX2"})

# ESP32 DevKit V1 (30 pin), antenna pointing right. Pin n = n-th pin counted from the USB end.
# J7 is one 2x15 socket on the VIN side: pad 2n-1 = pin n on the wide row (25.4 mm from J6),
# pad 2n = pin n on the narrow row (22.86 mm), so both DevKit widths plug in.
X0, YT, YN, YB = 60.0, 62.0, 64.54, 87.4
top = {1: "+5V", 2: "GND", 10: "RLY"}                 # VIN, GND, GPIO32
bottom = {1: "+3V3", 2: "GND", 6: "RX2"}              # 3V3, GND, GPIO16
place("J7", "Connector_PinSocket_2.54mm", "PinSocket_2x15_P2.54mm_Vertical", X0, YT, 90, "ESP32 VIN side",
      {**{2 * n - 1: v for n, v in top.items()}, **{2 * n: v for n, v in top.items()}})
place("J6", "Connector_PinSocket_2.54mm", "PinSocket_1x15_P2.54mm_Vertical", X0, YB, 90, "ESP32 3V3 side", bottom)
fps["J7"].Reference().SetPosition(P(57.6, YT + 1.27))

for i, (x, y) in enumerate([(4, 4), (96, 4), (4, 94), (96, 94)], 1):
    place(f"H{i}", "MountingHole", "MountingHole_3.2mm_M3", x, y).Reference().SetVisible(False)
for ref in ("J1", "J2", "J3", "J4", "J5"):              # the terminal group names on the silkscreen replace these
    fps[ref].Reference().SetVisible(False)
for ref, x, y, rot in [("F1", 5.4, 24, 90), ("RV1", 11, 36.3, 0), ("C1", 37.5, 63, 0), ("C2", 28.2, 56, 0),
                       ("LED2", 95.2, 52.3, 0), ("R5", 86.8, 47.4, 0)]:
    fps[ref].Reference().SetPosition(P(x, y))
    fps[ref].Reference().SetTextAngleDegrees(rot)

def round_pads():
    """Circle pads plot as flashed openings. Rounded rectangles become mask
    polygons, which this fab checker treats as covered holes."""
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                continue
            if pad.GetDrillSize().x <= 0:
                continue
            diameter = max(pad.GetSize().x, pad.GetSize().y)
            pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(diameter, diameter))


round_pads()

# ================================================================ copper: 230 V
F, B = pcbnew.F_Cu, pcbnew.B_Cu
track("L_IN", MAINS_W, F, "J1.2", "F1.1")
track("N", MAINS_W, F, "J1.1", (17.08, 33), "RV1.2")
track("N", MAINS_W, F, (17.08, 14.5), (61.08, 14.5))
track("N", MAINS_W, F, "J3.1", (48.08, 14.5))
track("N", MAINS_W, F, "J4.1", (61.08, 14.5))
track("N", MAINS_W, F, (52, 14.5), "PS1.2")
track("L_F", MAINS_W, F, "F1.2", (34.5, 32), (30.5, 36), "RV1.1")
track("L_F", MAINS_W, B, "J2.3", (25, 18), "F1.2")
track("L_F", MAINS_W, B, "F1.2", (34.5, 27), (56, 27), (58, 25), "PS1.1")
track("AUTO", MAINS_W, B, "J2.2", (30.08, 16.2), (72.8, 16.2), (72.8, 38.5), "K1.13")
track("A1", MAINS_W, B, "J2.1", (35.16, 13), (76.2, 13), (76.2, 31.5), "K1.14")
track("A1", MAINS_W, B, "J3.2", (43, 13))
track("A1", MAINS_W, B, "J4.2", (56, 13))

# ================================================================ copper: 5 V / 3.3 V
track("+5V", PWR_W, F, "PS1.4", (46, 59), (60, 59), "J7.1")
track("+5V", 0.5, F, "J7.1", "J7.2")
track("+5V", PWR_W, F, (46, 56), "R4.1")
track("+5V", PWR_W, F, (60, 59), (68, 59), (70, 57), "D1.1", (70, 52), (72, 50), "K1.A1")
track("+5V", 0.5, F, "K1.A1", (74, 47.5), (83, 47.5), "R5.1")
track("COIL_N", 0.5, F, "K1.A2", (80, 48.7), (96, 48.7), "LED2.1")
track("COIL_N", 0.5, F, "Q1.1", (90, 48.7))
track("COIL_N", 0.5, F, "D1.2", (78.7, 53.9), "K1.A2")
track("LED_RLY", SIG_W, F, "R5.2", "LED2.2")
# The straight line between these pins is 0.35 degrees off vertical, so it met
# the horizontal base track at 89.65 degrees. The corner below is exactly 90.
track("BASE", SIG_W, F, "Q1.2", (87.5, 52), "R2.1")
track("BASE", SIG_W, F, "R1.2", "R2.1")
track("RLY", SIG_W, F, "J7.19", (82.86, 60.6), (79.1, 60.6), "R1.1")
track("RLY", SIG_W, F, "J7.19", "J7.20")
track("LED_PWR", SIG_W, F, "R4.2", "LED1.2")
# Ground pads are not joined pad-centre to pad-centre: that track runs through
# the drills. Each pad gets a short stub onto the pour instead (after the vias).
track("+3V3", 0.5, F, "J5.1", (12, 82), (58, 82), (60, 84), "J6.1")
track("SENS_TX", SIG_W, F, "J5.2", (17.08, 93.5), "R3.1")
track("RX2", SIG_W, F, "R3.2", (72.7, 93.5), "J6.6")

for x, y in [(8, 50), (30, 48), (44, 66), (52, 76), (30, 70), (8, 70), (45, 88), (66, 70), (88, 70),
             (90, 82), (66, 82), (92, 55), (82, 52), (67, 56.3)]:
    via("GND", x, y)

# 1.0 mm drills need a 2.05 mm pad so a 0.30 mm stub can land on the ring and
# still stay 0.25 mm clear of the hole wall. Same idea for the smaller drills.
for ref, num, dia in (
    ("J7", "3", 2.05), ("J7", "4", 2.05), ("J6", "2", 2.05), ("PS1", "3", 2.05),
    ("Q1", "3", 1.90), ("C1", "2", 1.90), ("C2", "2", 1.90), ("R2", "2", 1.90),
    ("LED1", "1", 2.00),
):
    enlarge_pad(ref, num, dia)
for ref, num in (
    ("J7", "3"), ("J7", "4"), ("J6", "2"), ("PS1", "3"), ("Q1", "3"),
    ("C1", "2"), ("C2", "2"), ("R2", "2"), ("LED1", "1"), ("J5", "3"), ("J5", "4"),
):
    gnd_stub(ref, num)

# ground planes on both layers of the low-voltage side; the 6 mm mains rule keeps them back
# Start below the relay slot so the fill does not leave a sliver on its corner.
lv = [(0.5, 44.8), (99.5, 44.8), (99.5, 97.5), (0.5, 97.5)]
polygon_zone(lv, F, "GND")
polygon_zone(lv, B, "GND")
polygon_zone([(96.8, 58.5), (100, 58.5), (100, 91), (96.8, 91)], rule_area=True)     # ESP32 antenna
# The pour edge under the relay slot kinks around the slot corner and leaves a
# speck the fab reads as an island. Keep the slot; just don't pour there.
slot_gap = polygon_zone([(69.5, 44.2), (93.5, 44.2), (93.5, 46.5), (69.5, 46.5)], rule_area=True)
slot_gap.SetDoNotAllowTracks(False)
slot_gap.SetDoNotAllowVias(False)
extend_ground_stubs()

# ================================================================ outline and isolation slot
rect(0, 0, W, H, pcbnew.Edge_Cuts)
rect(71.5, 42.3, 80.8, 44.0, pcbnew.Edge_Cuts)        # slot between relay contacts and coil

# ================================================================ silkscreen
S = pcbnew.F_SilkS
for txt, x in [("MAINS IN", 14.54), ("SELECTOR S1", 30.08), ("KM COIL", 45.54), ("LAMP H1", 58.54)]:
    silk(txt, x, 1.6, 1.0, bold=True)
for txt, x in [("L", 12), ("N", 17.08), ("13", 25), ("14", 30.08), ("24", 35.16),
               ("A1", 43), ("A2", 48.08), ("X1", 56), ("X2", 61.08)]:
    silk(txt, x, 16.5, 1.1, bold=True)
silk("230 V AC  -  DANGER", 22, 41.6, 1.4, bold=True)
silk("FUSE 1 A SLOW", 23, 30.6, 1.0)
for x1, x2, y in [(1, 41.5, 44.6), (68.5, 71, 44.6), (81.5, 99, 43.15)]:
    for xs in range(int(x1 * 2), int(x2 * 2), 3):
        line(xs / 2, y, min(xs / 2 + 1.0, x2), y)
silk("LOW VOLTAGE 5 V / 3.3 V", 20, 46.0, 1.1)
silk("PWR", 11.3, 59.2, 1.0)
silk("RELAY", 94.7, 49.9, 1.0)
silk("SENSOR (CAT6)", 19.6, 80.4, 1.1, bold=True)
for txt, x in [("3V3", 12), ("TX", 17.08), ("MODE", 22.16), ("GND", 27.24)]:
    silk(txt, x, 83.3, 1.0, bold=True)
line(53, 60.4, 99.5, 60.4)
line(53, 89.0, 99.5, 89.0)
line(53, 60.4, 53, 89.0)
silk("ESP32 DevKit V1 (30-pin)", 76, 73.5, 1.3, bold=True)
silk("USB end", 56.5, 75.5, 0.9, rot=90)
silk("ANTENNA ->", 89, 77.8, 0.9)
silk("J7 takes both ESP32 widths (25.4 or 22.86 mm)", 76, 71.8, 0.8)
silk("NK Smart Pumps", 28, 68, 1.4, bold=True)
silk("HLK-5M05 | G5NB relay | ESP32", 28, 72.6, 1.0)
silk("REV 1.1", 28, 75.4, 0.9)

# Polarity marks. The library outlines of Q1 and the LEDs pass within 0.4 mm of
# their pads, so pull_silk() strips them; these are drawn far enough out to stay.
# Q1: the round back of the TO-92 faces the ESP32, the flat face the relay.
arc(87.46, 52.0, 2.6, 55, 125)
for txt, x in [("E", 84.92), ("B", 87.46), ("C", 90.0)]:
    silk(txt, x, 49.0, 0.8)
# LED anodes (long leg).
plus(12.54, 53.6)
plus(93.46, 48.0)

# Mask opening 0.10 mm past the copper, so a polygon pad cannot stick out of its opening.
design = board.GetDesignSettings()
design.m_SolderMaskExpansion = mm(0.10)
pull_silk(0.40)

board.Save(OUT)
print("saved", OUT)
