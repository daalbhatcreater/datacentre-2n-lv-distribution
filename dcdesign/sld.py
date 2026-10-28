"""Single-line diagram, generated from the sizing results.

The same node/edge list is written as an editable draw.io file and rendered
to PNG with matplotlib, so the drawing and the calculations cannot drift apart.
Side A is laid out by hand; side B is its mirror image.
"""

from dataclasses import dataclass, replace
from xml.sax.saxutils import escape, quoteattr

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

W, H = 1720, 900

STYLE = {
    # kind: (fill, edge, drawio style extras)
    "src": ("#e8e8e8", "#555555", "rounded=1;"),
    "tx": ("#ffffff", "#1f3864", "shape=ellipse;"),
    "gen": ("#fff2cc", "#7f6000", "shape=ellipse;"),
    "brk": ("#ffffff", "#000000", ""),
    "bus": ("#000000", "#000000", ""),
    "ups": ("#dae8fc", "#1f3864", "rounded=1;"),
    "batt": ("#f8cecc", "#b85450", ""),
    "ats": ("#e1d5e7", "#9673a6", ""),
    "board": ("#d5e8d4", "#82b366", "rounded=1;"),
    "pdu": ("#dae8fc", "#6c8ebf", "rounded=1;"),
    "rack": ("#f5f5f5", "#666666", "rounded=1;"),
    "note": ("none", "none", "text;strokeColor=none;fillColor=none;"),
}


@dataclass
class Node:
    id: str
    label: str
    x: float
    y: float
    w: float
    h: float
    kind: str

    @property
    def cx(self):
        return self.x + self.w / 2


def _side_a(d):
    s, ups, bat, pdu = d["sources"], d["ups"], d["battery"], d["pdus"]
    brk = {b.tag: b for b in d["breakers"]}
    bus = {b["board"]: b for b in d["busbars"]}

    def b(tag):
        x = brk[tag]
        return f"{tag} {x.kind} {x.frame_a} A<br>Ir {x.ir_a:.0f} A"

    nodes = [
        Node("UTIL-A", "11 kV utility feeder A", 60, 20, 170, 36, "src"),
        Node("TX-A", f"TX-A {s['transformer_kva']} kVA<br>11/0.433 kV Dyn11, uk 6.25 %",
             55, 80, 180, 64, "tx"),
        Node("DG-A", f"DG-A {s['dg_kva']} kVA<br>415 V prime, AMF", 290, 80, 170, 64, "gen"),
        Node("QA1", b("QA1"), 95, 175, 100, 40, "brk"),
        Node("QA2", b("QA2"), 325, 175, 100, 40, "brk"),
        Node("IL-A", "QA1 / QA2 mechanically and<br>electrically interlocked<br>(open-transition ATS)",
             470, 170, 200, 50, "note"),
        Node("MSB-A", f"MSB-A {bus['MSB-A']['rating_a']} A, {bus['MSB-A']['icw_ka']} kA 1 s, "
             f"Form 4b, IEC 61439-2", 40, 262, 760, 8, "bus"),
        Node("QA3", b("QA3"), 40, 290, 100, 40, "brk"),
        Node("QA4", b("QA4"), 160, 290, 100, 40, "brk"),
        Node("QA6", b("QA6"), 400, 290, 90, 40, "brk"),
        Node("QA7", b("QA7"), 500, 290, 90, 40, "brk"),
        Node("QA8", b("QA8"), 600, 290, 90, 40, "brk"),
        Node("QA9", b("QA9"), 700, 290, 90, 40, "brk"),
        Node("UPS-A", f"UPS-A {ups['modules']} x {400:.0f} kW<br>double conversion, "
             f"{ups['rating_kw']:.0f} kW", 60, 380, 190, 56, "ups"),
        Node("BAT-A", f"Battery A: {bat['strings']} strings x 40 x 12 V<br>VRLA, 10 min at 1 MW",
             265, 380, 170, 56, "batt"),
        Node("QA10", b("QA10"), 105, 465, 100, 40, "brk"),
        Node("OSB-A", f"UPS-OSB-A {bus['UPS-OSB-A']['rating_a']} A, Form 4b",
             30, 545, 640, 8, "bus"),
    ]
    for i in range(pdu["per_side"]):
        x = 30 + i * 128
        nodes.append(Node(f"QA{11 + i}", b(f"QA{11 + i}"), x, 570, 100, 40, "brk"))
        nodes.append(Node(f"PDU-A{i + 1}", f"PDU-A{i + 1}<br>{pdu['rating_kva']} kVA, 40 ways",
                          x, 650, 100, 46, "pdu"))
    return nodes


SHARED = [
    ("ATS-M1", "ATS-M1 4P", "MDB-M1", "MDB-M1 chillers,<br>pumps, CRAH"),
    ("ATS-M2", "ATS-M2 4P", "MDB-M2", "MDB-M2 chillers,<br>pumps, CRAH"),
    ("ATS-L", "ATS-L 4P", "LDB", "LDB lighting,<br>small power"),
    ("ATS-E", "ATS-E 4P", "ESS-DB", "ESS-DB BMS,<br>fire, security"),
]


def build(d):
    side_a = _side_a(d)
    nodes = list(side_a)
    npdu = d["pdus"]["per_side"]

    def renumber(text):
        # B-side PDUs are numbered from the centre outwards, so that PDU-An
        # and PDU-Bn sit either side of the rows they both feed
        for k in range(1, npdu + 1):
            text = text.replace(f"PDU-B{k}", f"PDU-B#{npdu + 1 - k}")
            text = text.replace(f"QB{10 + k} ", f"QB#{10 + npdu + 1 - k} ")
        return text.replace("#", "")

    for n in side_a:
        label = (n.label.replace("-A", "-B").replace("QA", "QB")
                 .replace("feeder A", "feeder B").replace("Battery A", "Battery B"))
        nid = n.id.replace("-A", "-B").replace("QA", "QB")
        nodes.append(replace(n, id=renumber(nid + " ").strip(), label=renumber(label),
                            x=W - n.x - n.w))

    for i, (ats, ats_label, board, board_label) in enumerate(SHARED):
        x = 690 + i * 88
        nodes.append(Node(ats, ats_label, x, 420, 76, 36, "ats"))
        nodes.append(Node(board, board_label, x - 4, 485, 84, 46, "board"))

    racks = d["pdus"]["per_side"]
    for i in range(racks):
        x = 330 + i * 220
        nodes.append(Node(f"RACKS{i + 1}", f"Rows {2 * i + 1}-{2 * i + 2}: 40 racks<br>"
                          f"dual-corded, 16 A 3-ph rPDU", x, 800, 180, 46, "rack"))

    edges = [("UTIL-A", "TX-A"), ("TX-A", "QA1"), ("DG-A", "QA2"), ("QA1", "MSB-A"),
             ("QA2", "MSB-A"), ("MSB-A", "QA3"), ("MSB-A", "QA4"),
             ("QA3", "UPS-A", {"entry": 0.3}), ("QA4", "UPS-A", {"entry": 0.7}),
             ("UPS-A", "BAT-A"), ("UPS-A", "QA10"), ("QA10", "OSB-A")]
    for t in ("QA6", "QA7", "QA8", "QA9"):
        edges.append(("MSB-A", t))
    for i in range(racks):
        edges += [("OSB-A", f"QA{11 + i}"), (f"QA{11 + i}", f"PDU-A{i + 1}")]
    def to_b(e):
        a, b, *opts = e
        opts = [{**o, "entry": 1 - o["entry"]} if "entry" in o else o for o in opts]
        return (a.replace("-A", "-B").replace("QA", "QB"),
                b.replace("-A", "-B").replace("QA", "QB"), *opts)

    edges += [to_b(e) for e in edges]
    # every A and B feed gets its own entry point and routing level, so no two
    # sources ever appear joined on the drawing
    for i, ((ats, _, board, _), qa, qb) in enumerate(zip(
            SHARED, ("QA6", "QA7", "QA8", "QA9"), ("QB6", "QB7", "QB8", "QB9"))):
        edges += [(qa, ats, {"entry": 0.25, "level": 410 - 20 * i}),
                  (qb, ats, {"entry": 0.75, "level": 400 - 20 * i}),
                  (ats, board)]
    for i in range(racks):
        edges += [(f"PDU-A{i + 1}", f"RACKS{i + 1}", {"entry": 0.3, "level": 786 - 16 * i}),
                  (f"PDU-B{i + 1}", f"RACKS{i + 1}", {"entry": 0.7, "level": 714 + 16 * i})]
    return {n.id: n for n in nodes}, [e if len(e) == 3 else (*e, {}) for e in edges]


def _route(a: Node, b: Node, opts=None):
    """Orthogonal polyline from a to b in drawing coordinates (y down)."""
    opts = opts or {}
    bx = b.x + opts["entry"] * b.w if "entry" in opts else b.cx
    if "level" in opts or "entry" in opts:
        ym = opts.get("level", (a.y + a.h + b.y) / 2)
        return [(a.cx, a.y + a.h), (a.cx, ym), (bx, ym), (bx, b.y)]
    if a.kind == "ups" and b.kind == "batt":
        y = a.y + a.h / 2
        return [(a.x + a.w, y), (b.x, y)]
    if a.kind == "bus":
        x0 = min(max(b.cx, a.x + 4), a.x + a.w - 4)
        return [(x0, a.y + a.h), (x0, b.y)] if abs(x0 - b.cx) < 1 else \
            [(x0, a.y + a.h), (x0, b.y - 10), (b.cx, b.y - 10), (b.cx, b.y)]
    if b.kind == "bus":
        return [(a.cx, a.y + a.h), (a.cx, b.y)]
    if abs(a.cx - b.cx) < 1:
        return [(a.cx, a.y + a.h), (b.cx, b.y)]
    ym = b.y - 14 if b.kind in ("rack", "ats") else (a.y + a.h + b.y) / 2
    return [(a.cx, a.y + a.h), (a.cx, ym), (b.cx, ym), (b.cx, b.y)]


def render_png(nodes, edges, path, title):
    fig = plt.figure(figsize=(W / 80, H / 80))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    for a, b, opts in edges:
        pts = _route(nodes[a], nodes[b], opts)
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color="#333333", lw=0.9, zorder=1)
    for n in nodes.values():
        fill, edge, _ = STYLE[n.kind]
        text = n.label.replace("<br>", "\n")
        if n.kind == "bus":
            ax.add_patch(Rectangle((n.x, n.y), n.w, n.h, color="black", zorder=2))
            ax.text(n.x, n.y - 4, text, fontsize=7.5, weight="bold", va="bottom", zorder=3)
            continue
        if n.kind == "note":
            ax.text(n.x, n.y + n.h / 2, text, fontsize=6.5, va="center", style="italic",
                    color="#444444")
            continue
        box = FancyBboxPatch((n.x, n.y), n.w, n.h,
                             boxstyle="round,pad=0,rounding_size=6" if "rounded" in STYLE[n.kind][2]
                             or n.kind in ("tx", "gen") else "square,pad=0",
                             facecolor=fill, edgecolor=edge, lw=1.0, zorder=2)
        ax.add_patch(box)
        ax.text(n.cx, n.y + n.h / 2, text, fontsize=6.3 if n.kind != "brk" else 5.8,
                ha="center", va="center", zorder=3)
    ax.text(W / 2, H - 12, title, ha="center", fontsize=9, weight="bold")
    fig.savefig(path, dpi=110)
    plt.close(fig)


def write_drawio(nodes, edges, path, title):
    cells = ['<mxCell id="0"/>', '<mxCell id="1" parent="0"/>']
    for n in nodes.values():
        fill, edge, extra = STYLE[n.kind]
        if n.kind == "bus":
            style = ("fillColor=#000000;strokeColor=#000000;labelPosition=center;"
                     "verticalLabelPosition=top;align=left;verticalAlign=bottom;"
                     "fontStyle=1;fontSize=11;html=1;")
        elif n.kind == "note":
            style = extra + "align=left;fontStyle=2;fontSize=9;html=1;"
        else:
            style = f"{extra}whiteSpace=wrap;html=1;fillColor={fill};strokeColor={edge};fontSize=9;"
        cells.append(
            f'<mxCell id={quoteattr(n.id)} value={quoteattr(n.label)} style={quoteattr(style)} '
            f'vertex="1" parent="1"><mxGeometry x="{n.x:g}" y="{n.y:g}" width="{n.w:g}" '
            f'height="{n.h:g}" as="geometry"/></mxCell>')
    for k, (a, b, opts) in enumerate(edges):
        na, nb = nodes[a], nodes[b]
        style = "edgeStyle=orthogonalEdgeStyle;rounded=0;endArrow=none;html=1;"
        points = ""
        if opts:
            pts = _route(na, nb, opts)[1:-1]
            points = '<Array as="points">' + "".join(
                f'<mxPoint x="{x:g}" y="{y:g}"/>' for x, y in pts) + "</Array>"
            style += f"exitX=0.5;exitY=1;entryX={opts.get('entry', 0.5):g};entryY=0;"
        elif na.kind == "bus":
            ex = (min(max(nb.cx, na.x + 4), na.x + na.w - 4) - na.x) / na.w
            style += f"exitX={ex:.4f};exitY=1;exitDx=0;exitDy=0;entryX=0.5;entryY=0;"
        elif nb.kind == "bus":
            ex = (na.cx - nb.x) / nb.w
            style += f"exitX=0.5;exitY=1;entryX={ex:.4f};entryY=0;entryDx=0;entryDy=0;"
        elif na.kind == "ups" and nb.kind == "batt":
            style += "exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
        else:
            style += "exitX=0.5;exitY=1;entryX=0.5;entryY=0;"
        cells.append(f'<mxCell id="e{k}" style={quoteattr(style)} edge="1" parent="1" '
                     f'source={quoteattr(a)} target={quoteattr(b)}>'
                     f'<mxGeometry relative="1" as="geometry">{points}</mxGeometry></mxCell>')
    xml = (f'<mxfile host="drawio"><diagram name={quoteattr(escape(title))}>'
           f'<mxGraphModel dx="{W}" dy="{H}" grid="1" gridSize="10" page="1" '
           f'pageWidth="{W}" pageHeight="{H}"><root>' + "".join(cells) +
           '</root></mxGraphModel></diagram></mxfile>\n')
    with open(path, "w") as fh:
        fh.write(xml)
