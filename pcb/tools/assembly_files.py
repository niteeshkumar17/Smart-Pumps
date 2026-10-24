"""Writes the JLCPCB assembly BOM and placement (CPL) files.

assembly_files.py <kicad-cli pos csv> <out dir>
The pos csv comes from `kicad-cli pcb export pos --format csv --units mm --side both`. KiCad reports
the footprint anchor, which for these parts is a pin, while JLCPCB places the centre of the part
there. The centre written below is the middle of each part's pins, in the same coordinate frame.
Part numbers are LCSC / JLCPCB numbers, checked October 2026. K1 and J5 are the in-stock parts
JLCPCB fitted on the October 2026 order.
"""
import collections
import csv
import os
import sys

import pcbnew

PARTS = {   # ref: (comment, manufacturer, MPN, LCSC)
    "J1": ("Screw terminal 2P 5.08mm 250V", "Cixi Kefa", "KF128-5.08-2P-AA", "C474952"),
    "J3": ("Screw terminal 2P 5.08mm 250V", "Cixi Kefa", "KF128-5.08-2P-AA", "C474952"),
    "J4": ("Screw terminal 2P 5.08mm 250V", "Cixi Kefa", "KF128-5.08-2P-AA", "C474952"),
    "J2": ("Screw terminal 3P 5.08mm 250V", "Cixi Kefa", "KF128-5.08-3P-AA", "C474953"),
    "J5": ("Screw terminal 4P 5.08mm", "DORABO", "DB128L-5.08-4P-GN-S", "C2827883"),
    "F1": ("Fuse holder 5x20mm, 22.5mm pitch", "Schurter", "0031.8201", "C3204125"),
    "RV1": ("Varistor 10D471K 300VAC", "COV", "10D471K", "C317795"),
    "PS1": ("HLK-5M05 230VAC to 5V 1A", "Hi-Link", "HLK-5M05", "C209907"),
    "K1": ("Relay G5NB-1A-E 5VDC", "Omron", "G5NB-1A-E-DC5V", "C48746"),
    "Q1": ("BC547B NPN, flat face toward relay K1", "LGE", "BC547B", "C713613"),
    "D1": ("1N4148", "Changzhou Starsea", "1N4148", "C85057"),
    "R1": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "R4": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "R5": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "R2": ("10k 1/4W", "CCO", "MF1/4W-10K\u03a9\u00b11% T", "C119347"),
    "R3": ("330R 1/4W", "CCO", "MF1/4W-330\u03a9\u00b11% T", "C119313"),
    "LED1": ("LED red 3mm", "TOGIALED", "TJ-L3FYTGHRMTCSFLC3R-A5", "C331035"),
    "LED2": ("LED red 3mm", "TOGIALED", "TJ-L3FYTGHRMTCSFLC3R-A5", "C331035"),
    "C1": ("470uF 16V radial 8x12mm", "KNSCHA", "SHG470UF16V03EC0549", "C2943989"),
    "C2": ("100nF 50V X7R disc 5mm", "Vishay", "K104K15X7RF5TH5", "C2167231"),
    "J6": ("Female header 1x15 2.54mm 8.5mm", "HCTL", "PM254-1-15-Z-8.5", "C2897378"),
    "J7": ("Female header 2x15 2.54mm 8.5mm", "BOOMELE", "2.54-2*15P", "C5337168"),
}
NOT_ASSEMBLED = ("H",)      # mounting holes have no part
# JLCPCB draws these headers horizontal at 0 deg. KiCad has them at 90 deg for the same direction.
ROTATION = {"J6": 0.0, "J7": 0.0}

pos_csv, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
rows = list(csv.DictReader(open(pos_csv, newline="", encoding="utf-8")))

placed = [r for r in rows if not r["Ref"].startswith(NOT_ASSEMBLED)]
missing = sorted({r["Ref"] for r in placed} - PARTS.keys())
extra = sorted(PARTS.keys() - {r["Ref"] for r in placed})
if missing or extra:
    sys.exit(f"parts table out of date: not in table {missing}, not on board {extra}")

board = pcbnew.LoadBoard(os.path.join(os.path.dirname(__file__), "..", "tank_controller.kicad_pcb"))


def centre(ref):
    """Middle of the pins, in the position-file frame (y up, same origin as the Gerbers)."""
    fp = board.FindFootprintByReference(ref)
    xs, ys = [], []
    for p in fp.Pads():
        xs.append(pcbnew.ToMM(p.GetPosition().x))
        ys.append(pcbnew.ToMM(p.GetPosition().y))
    return (min(xs) + max(xs)) / 2, -((min(ys) + max(ys)) / 2)


with open(os.path.join(out, "tank_controller_cpl.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in placed:
        x, y = centre(r["Ref"])
        rot = ROTATION.get(r["Ref"], float(r["Rot"]))
        w.writerow([r["Ref"], f"{x:.3f}mm", f"{y:.3f}mm",
                    "Top" if r["Side"] == "top" else "Bottom", f"{rot:.1f}"])

pkg = {r["Ref"]: r["Package"] for r in placed}
groups = collections.OrderedDict()
for ref, part in PARTS.items():
    groups.setdefault(part, []).append(ref)
with open(os.path.join(out, "tank_controller_bom.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Manufacturer", "MPN", "Qty"])
    for (comment, maker, mpn, lcsc), refs in groups.items():
        w.writerow([comment, ",".join(refs), pkg[refs[0]], lcsc, maker, mpn, len(refs)])

print(f"assembly: {len(placed)} parts, {len(groups)} line items -> {out}")
