"""Print pad positions of KiCad library footprints: fp_info.py Lib:Footprint [...]"""
import os
import sys

import pcbnew

LIB = os.path.join(os.path.dirname(os.path.dirname(pcbnew.__file__)), "..", "share", "kicad", "footprints")
LIB = os.environ.get("KICAD_FP_DIR", r"C:\Users\nitee\AppData\Local\Programs\KiCad\10.0\share\kicad\footprints")

for arg in sys.argv[1:]:
    lib, name = arg.split(":", 1)
    fp = pcbnew.FootprintLoad(os.path.join(LIB, lib + ".pretty"), name)
    bb = fp.GetBoundingBox(False)
    mm = pcbnew.ToMM
    print(f"{name}  bbox {mm(bb.GetLeft()):.2f},{mm(bb.GetTop()):.2f} .. {mm(bb.GetRight()):.2f},{mm(bb.GetBottom()):.2f}")
    for p in fp.Pads():
        pos, s, d = p.GetPosition(), p.GetSize(), p.GetDrillSize()
        print(f"   pad {p.GetNumber():>3} at {mm(pos.x):7.2f},{mm(pos.y):7.2f}  size {mm(s.x):.2f}x{mm(s.y):.2f}  drill {mm(d.x):.2f}")
