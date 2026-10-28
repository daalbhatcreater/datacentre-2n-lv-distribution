"""Sizing of the A side (the B side is identical) of the 2N power train.

Two operating cases are carried through every calculation:
  normal   both sides healthy, each carries half the IT load and its own
           mechanical board
  failure  the other side is lost: this side carries the whole IT load and,
           through the mechanical ATSs, both mechanical boards
"""

import math
from dataclasses import dataclass

import numpy as np

from . import basis as B

SQRT3 = math.sqrt(3)


def current(kva, v=B.SYSTEM_V):
    return kva * 1e3 / (SQRT3 * v)


def first_at_least(values, x):
    for v in values:
        if v >= x:
            return v
    raise ValueError(f"no standard rating >= {x:.0f}")


def ups_efficiency(load_fraction):
    xs, ys = zip(*B.UPS_EFFICIENCY_CURVE)
    return float(np.interp(load_fraction, xs, ys))


@dataclass
class Breaker:
    tag: str
    duty: str
    kind: str        # ACB / MCCB / MCB
    frame_a: int
    ir_a: float
    load_a: float
    poles: int = 4

    @property
    def loading(self):
        return self.load_a / self.ir_a


def select_breaker(tag, duty, load_a, kind="auto", max_frame_loading=0.9, ir_step=0.05):
    """Frame so that the load is at most 90 % of it, Ir the next 5 % step at
    or above the load current."""
    if kind == "auto":
        kind = "MCCB" if load_a / max_frame_loading <= B.MCCB_FRAMES[-1] else "ACB"
    frames = B.MCCB_FRAMES if kind == "MCCB" else B.ACB_FRAMES
    frame = first_at_least(frames, load_a / max_frame_loading)
    ir = math.ceil(load_a / (frame * ir_step) - 1e-9) * frame * ir_step
    return Breaker(tag, duty, kind, frame, ir, load_a)


def size_ups():
    modules = math.ceil(B.IT_LOAD_KW / (B.UPS_MODULE_KW * B.UPS_MAX_LOADING))
    rating = modules * B.UPS_MODULE_KW
    out = {"modules": modules, "rating_kw": rating}
    for case, load in (("normal", B.IT_LOAD_KW / 2), ("failure", B.IT_LOAD_KW)):
        frac = load / rating
        eff = ups_efficiency(frac)
        p_in = load / eff + B.UPS_RECHARGE_FRACTION * rating
        out[case] = {"load_kw": load, "loading": frac, "efficiency": eff,
                     "losses_kw": load / eff - load,
                     "input_kw": p_in, "input_kva": p_in / B.UPS_INPUT_PF}
    return out


def size_battery(ups):
    """Constant-power sizing of the VRLA strings for full IT load on one side."""
    eff = ups["failure"]["efficiency"]
    p_dc = B.IT_LOAD_KW / eff
    p_design = p_dc * B.BATTERY_AGEING_FACTOR * B.BATTERY_DESIGN_MARGIN
    w_per_cell = p_design * 1e3 / B.CELLS_PER_STRING
    strings = math.ceil(w_per_cell / B.BLOCK_W_PER_CELL_10MIN)
    return {
        "dc_power_kw": p_dc,
        "design_power_kw": p_design,
        "energy_kwh": p_dc * B.AUTONOMY_MIN / 60,
        "w_per_cell_required": w_per_cell,
        "strings": strings,
        "blocks": strings * B.CELLS_PER_STRING // 6,
        "dc_bus_v": B.CELLS_PER_STRING * 2.0,
        "end_v": B.CELLS_PER_STRING * B.END_VOLTAGE_VPC,
        "max_dc_current_a": p_design * 1e3 / (B.CELLS_PER_STRING * B.END_VOLTAGE_VPC),
    }


def mechanical_loads():
    rows = []
    for name, qty, kw, pf, board in B.MECHANICAL:
        p = qty * kw
        q = p * math.tan(math.acos(pf))
        rows.append({"name": name, "qty": qty, "kw_each": kw, "pf": pf,
                     "board": board, "kw": p, "kvar": q})
    return rows


def side_demand(ups, mech):
    """P, Q and S at the MSB of one side for both cases."""
    def pq(kw, pf):
        return kw, kw * math.tan(math.acos(pf))

    shared = [r for r in mech if r["board"] == "MDB-M1/M2"]
    building = [r for r in mech if r["board"] != "MDB-M1/M2"]
    out = {}
    for case, mech_share in (("normal", 0.5), ("failure", 1.0)):
        p_u, q_u = pq(ups[case]["input_kw"], B.UPS_INPUT_PF)
        p_m = sum(r["kw"] for r in shared) * mech_share
        q_m = sum(r["kvar"] for r in shared) * mech_share
        # lighting / small power and the ESS board are dual-fed the same way
        p_b = sum(r["kw"] for r in building) * mech_share
        q_b = sum(r["kvar"] for r in building) * mech_share
        p, q = p_u + p_m + p_b, q_u + q_m + q_b
        s = math.hypot(p, q)
        out[case] = {"ups_kw": p_u, "mech_kw": p_m, "building_kw": p_b,
                     "kw": p, "kvar": q, "kva": s, "pf": p / s, "current_a": current(s)}
    return out


def size_sources(demand):
    worst = demand["failure"]["kva"]
    tx = first_at_least(B.TRANSFORMER_KVA, worst / B.TRANSFORMER_MAX_LOADING)
    dg = first_at_least(B.DG_KVA, worst / B.DG_MAX_LOADING)
    return {
        "transformer_kva": tx, "transformer_loading_failure": worst / tx,
        "transformer_loading_normal": demand["normal"]["kva"] / tx,
        "transformer_in_a": current(tx),
        "dg_kva": dg, "dg_loading_failure": worst / dg, "dg_in_a": current(dg),
    }


def size_pdus():
    per_pdu_failure_kw = B.IT_LOAD_KW / B.PDUS_PER_SIDE
    kva_failure = per_pdu_failure_kw / B.IT_PF
    rating = first_at_least(B.PDU_KVA, kva_failure / B.PDU_MAX_LOADING)
    racks_per_pdu = B.RACKS // B.PDUS_PER_SIDE
    rack_kva = B.RACK_DESIGN_KW / B.IT_PF
    return {
        "per_side": B.PDUS_PER_SIDE, "rating_kva": rating,
        "load_kva_failure": kva_failure, "load_kva_normal": kva_failure / 2,
        "loading_failure": kva_failure / rating,
        "racks_per_pdu": racks_per_pdu,
        "rack_cord_current_a": current(rack_kva),
        "rack_branch_mcb_a": 16,
        "rack_pdu": "3-phase 16 A IEC 60309 (11 kVA)",
    }


def size_switchgear(sources, ups, pdus, demand, mech):
    shared_kw = sum(r["kw"] for r in mech if r["board"] == "MDB-M1/M2")
    shared_kvar = sum(r["kvar"] for r in mech if r["board"] == "MDB-M1/M2")
    mdb_kva = math.hypot(shared_kw, shared_kvar) / 2
    lighting = next(r for r in mech if r["name"].startswith("Lighting"))
    ess = next(r for r in mech if r["name"].startswith("BMS"))

    ups_out_a = current(ups["rating_kw"])  # unity pf output
    brk = [
        # incomers sized on the source rating, not the load
        select_breaker("QA1", "Transformer TX-A incomer", sources["transformer_in_a"], "ACB", 1.0),
        select_breaker("QA2", "Generator DG-A incomer", sources["dg_in_a"], "ACB"),
        select_breaker("QA3", "UPS-A rectifier input", current(ups["failure"]["input_kva"]), "ACB"),
        select_breaker("QA4", "UPS-A static bypass input", ups_out_a, "ACB"),
        select_breaker("QA5", "Maintenance bypass", ups_out_a, "ACB"),
        select_breaker("QA6", "Feeder to MDB-M1 ATS (A source)", current(mdb_kva)),
        select_breaker("QA7", "Feeder to MDB-M2 ATS (A source)", current(mdb_kva)),
        select_breaker("QA8", "Feeder to LDB ATS (A source)", current(lighting["kw"] / lighting["pf"])),
        select_breaker("QA9", "Feeder to ESS-DB ATS (A source)", current(ess["kw"] / ess["pf"])),
        select_breaker("QA10", "UPS-A output to UPS output board", ups_out_a, "ACB"),
    ]
    for n in range(1, B.PDUS_PER_SIDE + 1):
        brk.append(select_breaker(f"QA{10 + n}", f"UPS output board to PDU-A{n}",
                                  current(pdus["rating_kva"])))
    return brk


def size_busbars(sources, ups, breakers):
    """Busbar rating from the largest incomer, checked against the outgoing
    sum with the IEC 61439-1 rated diversity factor."""
    def rdf(n):
        return 0.9 if n <= 3 else 0.8 if n <= 5 else 0.7 if n <= 9 else 0.6

    msb_in = max(b.ir_a for b in breakers if b.tag in ("QA1", "QA2"))
    msb_out = [b for b in breakers if b.tag in ("QA3", "QA4", "QA6", "QA7", "QA8", "QA9")]
    osb_out = [b for b in breakers if b.duty.startswith("UPS output board to PDU")]
    msb = first_at_least(B.BUSBAR_RATINGS, msb_in)
    osb = first_at_least(B.BUSBAR_RATINGS, current(ups["rating_kw"]))
    icw = first_at_least([50, 65, 80, 100], B.MSB_FAULT_KA)
    return [
        {"board": "MSB-A", "rating_a": msb, "incomer_ir_a": msb_in,
         "outgoing_sum_a": sum(b.ir_a for b in msb_out), "rdf": rdf(len(msb_out)),
         "diversified_a": sum(b.ir_a for b in msb_out) * rdf(len(msb_out)),
         "icw_ka": icw, "form": "Form 4b"},
        {"board": "UPS-OSB-A", "rating_a": osb, "incomer_ir_a": current(ups["rating_kw"]),
         "outgoing_sum_a": sum(b.ir_a for b in osb_out), "rdf": rdf(len(osb_out)),
         "diversified_a": sum(b.ir_a for b in osb_out) * rdf(len(osb_out)),
         "icw_ka": 50, "form": "Form 4b"},
    ]


METERING = [
    # point, meter, purpose
    ("TX-A incomer (QA1)", "Class 0.5S multifunction, power quality", "Utility energy, demand, THD"),
    ("DG-A incomer (QA2)", "Class 1 multifunction", "Generator kWh, run hours, loading"),
    ("UPS-A input (QA3)", "Class 0.5S multifunction", "UPS input energy, for UPS losses"),
    ("UPS-A output (QA10)", "Class 0.5S multifunction", "Critical energy, UPS efficiency"),
    ("PDU-A1..A5 incomers", "Class 1 multifunction", "IT energy per PDU, PUE numerator/denominator"),
    ("PDU branch circuits", "Branch circuit monitoring, CT per way", "Rack-level current, capacity planning"),
    ("MDB-M1, MDB-M2 incomers", "Class 1 multifunction", "Cooling energy, partial PUE"),
    ("LDB, ESS-DB incomers", "Class 1 multifunction", "Building and life-safety energy"),
]


def pue(ups, demand):
    """Design PUE in normal operation, from the metered quantities."""
    it = B.IT_LOAD_KW
    facility = 2 * demand["normal"]["kw"] - 2 * B.UPS_RECHARGE_FRACTION * ups["rating_kw"]
    return facility / it


def design():
    ups = size_ups()
    battery = size_battery(ups)
    mech = mechanical_loads()
    demand = side_demand(ups, mech)
    sources = size_sources(demand)
    pdus = size_pdus()
    breakers = size_switchgear(sources, ups, pdus, demand, mech)
    busbars = size_busbars(sources, ups, breakers)
    return {"ups": ups, "battery": battery, "mech": mech, "demand": demand,
            "sources": sources, "pdus": pdus, "breakers": breakers,
            "busbars": busbars, "pue": pue(ups, demand), "metering": METERING}
