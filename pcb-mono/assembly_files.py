"""Writes the JLCPCB assembly BOM and placement (CPL) for the monoblock board.

assembly_files.py <kicad-cli pos csv> <out dir>
The centre is the middle of each part's pins, in the gerber frame (y up).
JLCPCB draws the ESP32 headers horizontal at 0 degrees; KiCad has them at 90
for that same direction.
"""
import collections
import csv
import os
import sys

import pcbnew

PARTS = {   # ref: (comment, manufacturer, MPN, LCSC)
    "J1": ("Screw terminal 2P 5.08mm 24A 2.5mm2", "Cixi Kefa", "KF128-5.08-2P-AA", "C474952"),
    "J2": ("Screw terminal 2P 5.08mm 24A 2.5mm2", "Cixi Kefa", "KF128-5.08-2P-AA", "C474952"),
    "J3": ("Screw terminal 2P 5.08mm 250V", "Cixi Kefa", "KF128-5.08-2P-AA", "C474952"),
    "J4": ("Screw terminal 6P 5.08mm", "Cixi Kefa", "KF127S-5.08-6P", "C2974928"),
    "J5": ("Screw terminal 4P 5.08mm", "DORABO", "DB128L-5.08-4P-GN-S", "C2827883"),
    "F1": ("Fuse holder 5x20mm, 22.5mm pitch", "Schurter", "0031.8201", "C3204125"),
    "RV1": ("Varistor 10D471K 300VAC", "COV", "10D471K", "C317795"),
    "PS1": ("HLK-10M05 230VAC to 5V 2A", "Hi-Link", "HLK-10M05", "C403745"),
    "K1": ("T92P7D12-5 5VDC 2 form A PCB pins. Not the 12V coil.", "TE Connectivity", "T92P7D12-5", ""),
    "Q1": ("IRLZ44N N-MOSFET TO-220", "Infineon", "IRLZ44NPBF", "C38774"),
    "D1": ("1N4007 DO-41", "JUXING", "1N4007", "C3011149"),
    "R1": ("100R 1/4W", "CCO", "MF1/4W-100\u03a9\u00b11% T", "C119304"),
    "R2": ("100k 1/4W", "CCO", "MF1/4W-100K\u03a9\u00b11% T", "C119369"),
    "R4": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "R5": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "RSA": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "RSM": ("1k 1/4W", "CCO", "MF1/4W-1K\u03a9\u00b11% T", "C119324"),
    "R3": ("330R 1/4W", "CCO", "MF1/4W-330\u03a9\u00b11% T", "C119313"),
    "LED1": ("LED red 3mm", "TOGIALED", "TJ-L3FYTGHRMTCSFLC3R-A5", "C331035"),
    "LED2": ("LED red 3mm", "TOGIALED", "TJ-L3FYTGHRMTCSFLC3R-A5", "C331035"),
    "C1": ("1000uF 16V radial 10x16mm", "Rubycon", "16ZLH1000MEFC10X16", "C338175"),
    "C2": ("100nF 50V X7R disc 5mm", "Vishay", "K104K15X7RF5TH5", "C2167231"),
    "J6": ("Female header 1x15 2.54mm 8.5mm", "HCTL", "PM254-1-15-Z-8.5", "C2897378"),
    "J7": ("Female header 2x15 2.54mm 8.5mm", "BOOMELE", "2.54-2*15P", "C5337168"),
}
NOT_ASSEMBLED = ("H",)
ROTATION = {"J6": 0.0, "J7": 0.0}

pos_csv, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
rows = list(csv.DictReader(open(pos_csv, newline="", encoding="utf-8")))

placed = [r for r in rows if not r["Ref"].startswith(NOT_ASSEMBLED)]
missing = sorted({r["Ref"] for r in placed} - PARTS.keys())
extra = sorted(PARTS.keys() - {r["Ref"] for r in placed})
if missing or extra:
    sys.exit(f"parts table out of date: not in table {missing}, not on board {extra}")

board = pcbnew.LoadBoard(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mono_controller.kicad_pcb"))


def centre(ref):
    fp = board.FindFootprintByReference(ref)
    xs, ys = [], []
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        xs.append(pcbnew.ToMM(p.GetPosition().x))
        ys.append(pcbnew.ToMM(p.GetPosition().y))
    return (min(xs) + max(xs)) / 2, -((min(ys) + max(ys)) / 2)


with open(os.path.join(out, "mono_controller_cpl.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for r in sorted(placed, key=lambda row: row["Ref"]):
        x, y = centre(r["Ref"])
        rot = ROTATION.get(r["Ref"], float(r["Rot"]))
        w.writerow([r["Ref"], f"{x:.3f}mm", f"{y:.3f}mm",
                    "Top" if r["Side"] == "top" else "Bottom", f"{rot:.1f}"])

pkg = {r["Ref"]: r["Package"] for r in placed}
groups = collections.OrderedDict()
for ref, part in PARTS.items():
    groups.setdefault(part, []).append(ref)
with open(os.path.join(out, "mono_controller_bom.csv"), "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Manufacturer", "MPN", "Qty"])
    for (comment, maker, mpn, lcsc), refs in groups.items():
        w.writerow([comment, ",".join(refs), pkg[refs[0]], lcsc, maker, mpn, len(refs)])

print(f"assembly: {len(placed)} parts, {len(groups)} line items -> {out}")
