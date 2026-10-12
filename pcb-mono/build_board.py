"""Monoblock controller board. Run with KiCad's python.

Motor live and neutral are switched on the board by a TE T92 (5 V DC coil,
two normally-open poles). The 1 A fuse feeds only the HLK-10M05. Pump current
does not go through that fuse. Coordinates are board-local millimetres,
origin at the top-left, x right, y down.
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
FP_DIR = os.environ.get("KICAD_FP_DIR", r"C:\Users\nitee\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints")
OUT = os.path.join(HERE, "mono_controller.kicad_pcb")

OX, OY = 30.0, 30.0
W, H = 200.0, 164.0
# 4 mm on 2 oz copper carries the 10 A motor current. The last few millimetres
# into a terminal neck down so the track end does not reach the neighbouring screw.
MOTOR_W, NECK_W, BRANCH_W, PWR_W, SIG_W = 4.0, 1.5, 1.2, 0.8, 0.3
MAINS = ("L_IN", "L_F", "N_IN", "L_OUT", "N_OUT")
# Recorded geometry for the clearance check at the end of this script.
SEGS = []  # (net, layer, x1, y1, x2, y2, width)
VIAS = []  # (net, x, y, size)

board = pcbnew.BOARD()
nets = {}
fps = {}


def P(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


def mm(v):
    return pcbnew.FromMM(v)


def net(name):
    if name not in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        nets[name] = ni
    return nets[name]


def place(ref, lib, name, x, y, rot=0, value="", pads=None):
    fp = pcbnew.FootprintLoad(os.path.join(FP_DIR, lib + ".pretty"), name)
    if fp is None:
        sys.exit(f"missing footprint {lib}:{name}")
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


def add_pad(fp, num, x, y, drill, size):
    pad = pcbnew.PAD(fp)
    pad.SetNumber(str(num))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    pad.SetSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    pad.SetDrillSize(pcbnew.VECTOR2I(mm(drill), mm(drill)))
    pad.SetLayerSet(pad.PTHMask())
    pad.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.Add(pad)
    return pad


def make_t92(x, y):
    """TE T92 code 1, 2 form A. Local origin is terminal 2.

    Datasheet centre distances: contact columns 7.85 mm, contact rows
    16.00 mm, coil row 25.40 mm beyond the near contact row, coil pair
    4.70 mm and centred on that pair. Body 52.32 x 34.54 mm. Round holes
    are the datasheet's 1.93 mm alternate, drilled 1.9 mm. Confirm the
    coil-pair centring on a 1:1 print before any board is ordered.
    """
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPIDAsString("Relay_TE_T92")
    fp.SetReference("K1")
    fp.SetValue("T92P7D12-5")
    board.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(0, 0))
    coil_y = 16.00 + 25.40
    coil_x0 = 7.85 / 2 - 4.70 / 2
    for num, px, py, drill, size in (
        ("2", 0.00, 0.00, 1.9, 4.0),
        ("4", 7.85, 0.00, 1.9, 4.0),
        ("6", 0.00, 16.00, 1.9, 4.0),
        ("8", 7.85, 16.00, 1.9, 4.0),
        ("0", coil_x0, coil_y, 1.9, 3.2),
        ("1", coil_x0 + 4.70, coil_y, 1.9, 3.2),
    ):
        add_pad(fp, num, px, py, drill, size)
    # Body centred on the contact pair, with equal end margins on the 52.32 mm length.
    x1, x2 = 3.925 - 17.27 - 0.25, 3.925 + 17.27 + 0.25
    y1, y2 = -5.46 - 0.25, coil_y + 5.46 + 0.25
    for layer in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
        s = pcbnew.PCB_SHAPE(fp)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
        s.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
        s.SetLayer(layer)
        s.SetWidth(mm(0.05))
        fp.Add(s)
    fp.SetPosition(P(x, y))
    ref = fp.Reference()
    ref.SetPosition(P(188, 40))
    ref.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
    ref.SetTextThickness(mm(0.16))
    fps["K1"] = fp
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
        if abs(x1 - x2) < 1e-6 and abs(y1 - y2) < 1e-6:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(x1, y1))
        t.SetEnd(P(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        board.Add(t)
        SEGS.append((netname, layer, x1, y1, x2, y2, width))


def via(netname, x, y, size=0.8, drill=0.4):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y))
    v.SetDrill(mm(drill))
    try:
        v.SetWidth(mm(size))
    except TypeError:
        v.SetWidth(pcbnew.F_Cu, mm(size))
    v.SetNet(net(netname))
    v.SetFrontTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    v.SetBackTentingMode(pcbnew.TENTING_MODE_NOT_TENTED)
    board.Add(v)
    VIAS.append((netname, x, y, size))


def silk(text, x, y, size=1.1, rot=0, bold=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(P(x, y))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.16, size * (0.18 if bold else 0.15))))
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


def rect(x1, y1, x2, y2, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(P(x1, y1))
    s.SetEnd(P(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def zone(points, layer, netname):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(netname))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetLocalClearance(mm(0.5))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    o = z.Outline()
    o.NewOutline()
    for x, y in points:
        o.Append(mm(OX + x), mm(OY + y))
    board.Add(z)
    return z


TB = "TerminalBlock_Phoenix"
TB_M = "TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal"
TB2 = "TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal"
TB4 = "TerminalBlock_Phoenix_MKDS-1,5-4-5.08_1x04_P5.08mm_Horizontal"
TB6 = "TerminalBlock_Phoenix_MKDS-1,5-6-5.08_1x06_P5.08mm_Horizontal"
R = "R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"

# Wire openings face the top edge. At rotation 180, pad 2 is the left screw.
place("J1", TB, TB_M, 72, 16, 180, "MAINS", {2: "L_IN", 1: "N_IN"})
place("J2", TB, TB_M, 104, 16, 180, "MOTOR", {2: "L_OUT", 1: "N_OUT"})
place("J3", TB, TB2, 132, 16, 180, "LAMP", {2: "L_OUT", 1: "N_OUT"})
place("F1", "Fuse", "Fuseholder_Cylinder-5x20mm_Schurter_0031_8201_Horizontal_Open", 18, 14, 0, "1A T",
      {1: "L_IN", 2: "L_F"})
fps["F1"].Reference().SetVisible(False)
place("RV1", "Varistor", "RV_Disc_D12mm_W4.2mm_P7.5mm", 90, 38, 0, "275VAC", {1: "L_F", 2: "N_IN"})
place("PS1", "Converter_ACDC", "Converter_ACDC_Hi-Link_HLK-10Mxx", 32, 28, 270, "HLK-10M05",
      {1: "L_F", 2: "N_IN", 3: "GND", 4: "+5V"})
make_t92(155, 30)
for num, name in (("2", "L_IN"), ("4", "L_OUT"), ("6", "N_IN"), ("8", "N_OUT"), ("0", "DRAIN"), ("1", "COIL")):
    fps["K1"].FindPadByNumber(num).SetNet(net(name))

# Live on the front, neutral on the back, so the two can cross without sharing a surface.
# The 1 A fuse is a branch: the motor bus does not go through it.
track("L_IN", NECK_W, pcbnew.F_Cu, "J1.2", (66.92, 30))
track("L_IN", MOTOR_W, pcbnew.F_Cu, (50, 30), "K1.2")
track("L_IN", BRANCH_W, pcbnew.F_Cu, "F1.1", (10, 14), (10, 52))
track("L_IN", BRANCH_W, pcbnew.B_Cu, (10, 52), (20, 52), (20, 24), (50, 24), (50, 30))
via("L_IN", 10, 52, 1.0, 0.6)
via("L_IN", 50, 30, 1.0, 0.6)
track("L_F", BRANCH_W, pcbnew.F_Cu, "F1.2", (40.5, 28), "PS1.1")
track("L_F", BRANCH_W, pcbnew.F_Cu, (40.5, 28), (40.5, 38), "RV1.1")
track("L_OUT", NECK_W, pcbnew.F_Cu, "J2.2", (98.92, 22))
track("L_OUT", NECK_W, pcbnew.F_Cu, "J3.2", (126.92, 22))
track("L_OUT", MOTOR_W, pcbnew.F_Cu, (98.92, 22), (182, 22), (182, 30), "K1.4")
track("N_IN", NECK_W, pcbnew.B_Cu, "J1.1", (72, 46))
track("N_IN", MOTOR_W, pcbnew.B_Cu, (48, 46), "K1.6")
track("N_IN", BRANCH_W, pcbnew.B_Cu, "PS1.2", (24.2, 34), (48, 34), (48, 46))
track("N_IN", BRANCH_W, pcbnew.B_Cu, "RV1.2", (97.5, 46))
track("N_OUT", NECK_W, pcbnew.B_Cu, "J2.1", (104, 22))
track("N_OUT", NECK_W, pcbnew.B_Cu, "J3.1", (132, 22))
track("N_OUT", MOTOR_W, pcbnew.B_Cu, (104, 22), (182, 22), (182, 46), "K1.8")

# Coil driver. IRLZ44N, front view, pins left to right: gate, drain, source.
place("Q1", "Package_TO_SOT_THT", "TO-220-3_Vertical", 168, 112, 0, "IRLZ44N",
      {1: "GATE", 2: "DRAIN", 3: "GND"})
fps["Q1"].Reference().SetPosition(P(186, 118))
place("D1", "Diode_THT", "D_DO-41_SOD81_P10.16mm_Horizontal", 140, 92, 0, "1N4007",
      {1: "COIL", 2: "DRAIN"})
place("R1", "Resistor_THT", R, 148, 112, 0, "100", {1: "RLY", 2: "GATE"})
place("R2", "Resistor_THT", R, 132, 118, 0, "100k", {1: "GATE", 2: "GND"})
place("R5", "Resistor_THT", R, 150, 120, 0, "1k", {1: "+5V", 2: "LED_RLY"})
place("LED2", "LED_THT", "LED_D3.0mm", 164, 120, 0, "RELAY", {1: "DRAIN", 2: "LED_RLY"})
place("C1", "Capacitor_THT", "CP_Radial_D10.0mm_P5.00mm", 70, 90, 0, "1000uF 16V", {1: "+5V", 2: "GND"})
place("C2", "Capacitor_THT", "C_Disc_D5.0mm_W2.5mm_P5.00mm", 86, 90, 0, "100nF", {1: "+5V", 2: "GND"})
place("R4", "Resistor_THT", R, 104, 90, 0, "1k", {1: "+5V", 2: "LED_PWR"})
place("LED1", "LED_THT", "LED_D3.0mm", 116, 90, 0, "PWR", {1: "GND", 2: "LED_PWR"})
place("J4", TB, TB6, 108, 146, 0, "SELECTOR",
      {1: "+5V", 2: "COIL", 3: "GND", 4: "DRAIN", 5: "SA", 6: "SM"})
place("RSA", "Resistor_THT", R, 144, 126, 0, "1k", {1: "SA", 2: "SEL_A"})
place("RSM", "Resistor_THT", R, 144, 136, 0, "1k", {1: "SM", 2: "SEL_M"})
place("J5", TB, TB4, 48, 146, 0, "SENSOR", {1: "+3V3", 2: "SENS_TX", 3: "GND", 4: "GND"})
place("R3", "Resistor_THT", R, 36, 136, 0, "330", {1: "SENS_TX", 2: "RX2"})

X0, YT = 22.0, 98.0
top = {1: "+5V", 2: "GND", 8: "SEL_M", 9: "SEL_A", 10: "RLY"}
bottom = {1: "+3V3", 2: "GND", 6: "RX2"}
place("J7", "Connector_PinSocket_2.54mm", "PinSocket_2x15_P2.54mm_Vertical", X0, YT, 90, "ESP32 VIN side",
      {**{2 * n - 1: v for n, v in top.items()}, **{2 * n: v for n, v in top.items()}})
place("J6", "Connector_PinSocket_2.54mm", "PinSocket_1x15_P2.54mm_Vertical", X0, YT + 25.4, 90, "ESP32 3V3 side", bottom)

for i, (x, y) in enumerate(((5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5)), 1):
    place(f"H{i}", "MountingHole", "MountingHole_3.2mm_M3", x, y).Reference().SetVisible(False)
for ref in ("J1", "J2", "J3", "J4", "J5"):
    fps[ref].Reference().SetVisible(False)

# 5 V rail stops before the coil copper. The selector, not this rail, feeds the coil.
track("+5V", PWR_W, pcbnew.F_Cu, "PS1.4", (16.8, 84), (145, 84))
track("+5V", PWR_W, pcbnew.F_Cu, (22, 84), "J7.1", "J7.2")
track("+5V", PWR_W, pcbnew.F_Cu, (70, 84), "C1.1")
track("+5V", PWR_W, pcbnew.F_Cu, (86, 84), "C2.1")
track("+5V", PWR_W, pcbnew.F_Cu, (104, 84), "R4.1")
track("+5V", PWR_W, pcbnew.F_Cu, (108, 84), (108, 140), (108, 146), "J4.1")
track("+5V", PWR_W, pcbnew.F_Cu, (145, 84), (186, 84), (186, 128), (150, 128), "R5.1")
track("LED_PWR", SIG_W, pcbnew.F_Cu, "R4.2", (111.62, 94), (118.54, 94), "LED1.2")
track("COIL", PWR_W, pcbnew.F_Cu, "K1.1", (190, 71.4), (190, 132), (113.08, 132), "J4.2")
track("COIL", PWR_W, pcbnew.F_Cu, (190, 130), (130, 130), (130, 92), "D1.1")
track("DRAIN", PWR_W, pcbnew.B_Cu, "K1.0", (148, 71.4), (148, 92), "D1.2")
track("DRAIN", PWR_W, pcbnew.B_Cu, (148, 104), (170.54, 104), (170.54, 120), "Q1.2")
track("DRAIN", PWR_W, pcbnew.B_Cu, (148, 92), (148, 104))
track("DRAIN", PWR_W, pcbnew.B_Cu, (170.54, 120), (170.54, 124), (164, 124), "LED2.1")
track("DRAIN", PWR_W, pcbnew.B_Cu, (100, 96), (170.54, 96), (170.54, 104))
via("DRAIN", 100, 96, 0.8, 0.4)
track("DRAIN", PWR_W, pcbnew.F_Cu, (100, 96), (100, 158), (123.24, 158), "J4.4")
track("LED_RLY", SIG_W, pcbnew.F_Cu, "R5.2", (157.62, 116), (166.54, 116), "LED2.2")
track("GATE", SIG_W, pcbnew.F_Cu, "R1.2", (155.62, 108), (168, 108), "Q1.1")
track("GATE", SIG_W, pcbnew.F_Cu, (155.62, 108), (132, 108), "R2.1")
# Three socket signals go down the left gutter, across under the selector, then up.
track("SEL_M", SIG_W, pcbnew.B_Cu, "J7.15", (39.78, 103), (10, 103), (10, 156), (151.62, 156), "RSM.2")
track("SEL_M", SIG_W, pcbnew.F_Cu, "J7.15", "J7.16")
track("SEL_A", SIG_W, pcbnew.B_Cu, "J7.17", (42.32, 107), (14, 107), (14, 153), (148, 153), (148, 126), "RSA.2")
track("SEL_A", SIG_W, pcbnew.F_Cu, "J7.17", "J7.18")
track("RLY", SIG_W, pcbnew.B_Cu, "J7.19", (44.86, 111), (18, 111), (18, 150), (146, 150), (146, 108), (148, 108), "R1.1")
track("RLY", SIG_W, pcbnew.F_Cu, "J7.19", "J7.20")
track("SA", SIG_W, pcbnew.B_Cu, "J4.5", (128.32, 130), (132, 130), (132, 126), "RSA.1")
track("SM", SIG_W, pcbnew.B_Cu, "J4.6", (138, 146), (138, 136), "RSM.1")
track("+3V3", PWR_W, pcbnew.F_Cu, "J6.1", (22, 142), (48, 142), "J5.1")
track("RX2", SIG_W, pcbnew.B_Cu, "J6.6", (34.7, 132), (43.62, 132), "R3.2")
track("SENS_TX", SIG_W, pcbnew.F_Cu, "J5.2", (53.08, 140), (36, 140), "R3.1")

lv = [(3, 66), (W - 3, 66), (W - 3, H - 3), (3, H - 3)]
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    gnd = zone(lv, layer, "GND")
    gnd.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    gnd.SetThermalReliefGap(mm(0.45))
    gnd.SetThermalReliefSpokeWidth(mm(0.6))
    gnd.SetLocalClearance(mm(0.4))

# Antenna of the DevKit, past the last header pin. No copper here.
zone_keep = pcbnew.ZONE(board)
zone_keep.SetIsRuleArea(True)
zone_keep.SetLayerSet(pcbnew.LSET.AllCuMask())
zone_keep.SetDoNotAllowTracks(True)
zone_keep.SetDoNotAllowVias(True)
zone_keep.SetDoNotAllowZoneFills(True)
zone_keep.SetDoNotAllowPads(False)
zone_keep.SetDoNotAllowFootprints(False)
ko = zone_keep.Outline()
ko.NewOutline()
for x, y in ((60, 100), (78, 100), (78, 132), (60, 132)):
    ko.Append(mm(OX + x), mm(OY + y))
board.Add(zone_keep)

rect(0, 0, W, H, pcbnew.Edge_Cuts, 0.05)
rect(142, 55, 178, 58, pcbnew.Edge_Cuts, 0.05)

silk("NK Smart Pumps", 100, 60, 1.8, bold=True)
silk("MONOBLOCK  1.5 HP MAX", 100, 63.2, 1.2, bold=True)
silk("ORDER 2 OZ COPPER", 100, 52, 1.0, bold=True)
silk("MAINS", 68, 8, 1.1, bold=True)
silk("MOTOR", 100, 8, 1.1, bold=True)
silk("LAMP", 128, 8, 1.1, bold=True)
silk("L", 64, 26, 1.0, bold=True)
silk("N", 74, 26, 1.0, bold=True)
silk("L", 96, 26, 1.0, bold=True)
silk("N", 106, 26, 1.0, bold=True)
silk("1A", 48, 8, 0.9, bold=True)
silk("HLK-10M05", 24, 48, 0.9)
silk("T92 5V  1.5HP", 168, 26, 0.9, bold=True)
silk("pin2 L in", 150, 26, 0.8)
silk("K stripe", 140, 88, 0.8)
silk("G D S", 168, 108, 0.8)
silk("+", 68, 86, 1.0, bold=True)
silk("SELECTOR", 108, 140, 1.0, bold=True)
silk("+5V COIL GND MAN SA SM", 120, 154, 0.9)
silk("SENSOR", 48, 140, 1.0, bold=True)
silk("ESP32 DevKit V1", 40, 92, 1.0, bold=True)
silk("USB", 18, 94, 0.9)
silk("CONFIRM T92 PINS ON A 1:1 PRINT", 100, 70, 0.9, bold=True)

def _seg_point(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 < 1e-12:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def _seg_seg(a, b, c, d):
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    c1, c2 = cross(a, b, c), cross(a, b, d)
    c3, c4 = cross(c, d, a), cross(c, d, b)
    if c1 * c2 < 0 and c3 * c4 < 0:
        return 0.0
    return min(_seg_point(*c, *a, *b), _seg_point(*d, *a, *b), _seg_point(*a, *c, *d), _seg_point(*b, *c, *d))


def _need(na, nb):
    am, bm = na in MAINS, nb in MAINS
    if am and bm:
        return 2.0
    if am or bm:
        return 8.0
    return 0.2


PADS = []
for fp in board.GetFootprints():
    for pad in fp.Pads():
        x = pcbnew.ToMM(pad.GetPosition().x) - OX
        y = pcbnew.ToMM(pad.GetPosition().y) - OY
        r = max(pcbnew.ToMM(pad.GetSize().x), pcbnew.ToMM(pad.GetSize().y)) / 2
        PADS.append((fp.GetReference(), pad.GetNumber(), pad.GetNetname(), x, y, r, pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH))

problems = []
items = []
for netname, layer, x1, y1, x2, y2, width in SEGS:
    items.append((netname, layer, (x1, y1), (x2, y2), width / 2))
for netname, x, y, size in VIAS:
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        items.append((netname, layer, (x, y), (x, y), size / 2))
for ref, num, netname, x, y, r, npth in PADS:
    if npth or not netname:
        continue
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        items.append((netname, layer, (x, y), (x, y), r))

for i, a in enumerate(items):
    for b in items[i + 1:]:
        if a[0] == b[0]:
            continue
        if a[1] != b[1] and not (a[0] in MAINS or b[0] in MAINS):
            continue
        need = _need(a[0], b[0]) if a[1] == b[1] or (a[0] in MAINS or b[0] in MAINS) else 0
        if a[1] != b[1] and a[0] in MAINS and b[0] in MAINS:
            continue
        dist = _seg_seg(a[2], a[3], b[2], b[3]) - a[4] - b[4]
        if dist < need - 0.02:
            problems.append(
                f"clear {a[0]}/{b[0]} {dist:.2f}<{need:.1f} "
                f"({a[2][0]:.1f},{a[2][1]:.1f})-({a[3][0]:.1f},{a[3][1]:.1f}) vs "
                f"({b[2][0]:.1f},{b[2][1]:.1f})-({b[3][0]:.1f},{b[3][1]:.1f})"
            )

for netname, layer, x1, y1, x2, y2, width in SEGS:
    for x, y in ((x1, y1), (x2, y2)):
        edge = min(x, y, W - x, H - y) - width / 2
        limit = 2.0 if netname in MAINS else 0.5
        if edge < limit - 0.02:
            problems.append(f"edge {netname} {edge:.2f} at ({x:.1f},{y:.1f})")

# Pads of one part inside another part's courtyard.
boxes = []
for fp in board.GetFootprints():
    try:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
    except Exception:
        continue
    boxes.append((fp.GetReference(), pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY,
                  pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY))
for ref, num, netname, x, y, r, npth in PADS:
    for owner, x1, y1, x2, y2 in boxes:
        if owner == ref or owner.startswith("H"):
            continue
        if x1 < x < x2 and y1 < y < y2:
            problems.append(f"pad {ref}.{num} inside {owner} courtyard")

print(f"geometry {len(problems)} problems")
for row in problems[:40]:
    print(" ", row)

design = board.GetDesignSettings()
design.m_SolderMaskExpansion = mm(0.10)
design.m_CopperEdgeClearance = mm(0.5)
try:
    design.m_SolderMaskMinWidth = mm(0.08)
except Exception:
    pass
try:
    design.m_MinClearance = mm(0)
    design.m_NetSettings.GetDefaultNetclass().SetClearance(mm(0))
except Exception as exc:
    print("clearance setting:", exc)

board.Save(OUT)
print("saved", OUT)

