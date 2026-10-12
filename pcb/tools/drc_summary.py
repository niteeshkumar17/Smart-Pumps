"""Summarise a kicad-cli DRC json report: drc_summary.py out/drc.json"""
import collections
import json
import sys

OX = OY = 30.0
d = json.load(open(sys.argv[1]))
v, u = d.get("violations", []), d.get("unconnected_items", [])
print("violations", len(v), "unconnected", len(u))
print(dict(collections.Counter(f"{x['severity']}:{x['type']}" for x in v)))


def where(i):
    return f"{i['description'][:55]} @{i['pos']['x'] - OX:.1f},{i['pos']['y'] - OY:.1f}"


skip = set(sys.argv[2:])
for x in v:
    if x["type"] in skip:
        continue
    print(f"{x['type']} | {x['description'][:70]} | " + " / ".join(where(i) for i in x["items"]))
for x in u:
    print("UNCONNECTED | " + " / ".join(where(i) for i in x["items"]))
