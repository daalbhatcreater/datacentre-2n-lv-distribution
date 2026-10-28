"""Time-step simulation of the source transfer sequence on side A.

Side A changes over between its utility transformer (QA1) and generator (QA2)
with an open-transition, interlocked pair of ACBs. The two mechanical boards,
the lighting board and the ESS board each have a 4-pole ATS with a preferred
source (A or B). UPS-A rides through every break on its battery and then walks
its rectifier in slowly so the generator never sees the full UPS load as a step.

Side B is assumed healthy on utility throughout, and is the alternate source
for the mechanical ATSs and the other cord of every rack.
"""

from dataclasses import dataclass, field

import numpy as np

from . import basis as B


@dataclass
class Settings:
    uv_pickup_pu: float = 0.80        # utility undervoltage
    uv_delay_s: float = 3.0           # rides through an 11 kV auto-reclose
    crank_s: float = 10.0             # one start attempt
    crank_rest_s: float = 10.0
    start_attempts: int = 3
    dg_runup_s: float = 9.0           # crank to rated volts and frequency
    dg_stabilise_s: float = 2.0
    acb_open_s: float = 0.06
    acb_close_s: float = 0.08
    dead_time_s: float = 0.5          # residual voltage decay before reclosing
    utility_stable_s: float = 300.0   # before retransfer
    dg_cooldown_s: float = 300.0
    rectifier_delay_s: float = 5.0
    rectifier_ramp_s: float = 15.0
    mech_ats_delay_s: float = 5.0     # alternate source after preferred is lost
    mech_retransfer_s: float = 300.0
    # mechanical restart after a board is re-energised: (delay s, kW)
    restart_steps: tuple = ((5.0, 54.0), (10.0, 22.5), (30.0, 82.5), (60.0, 82.5))


@dataclass
class Board:
    name: str
    preferred: str
    kw: float                 # running load
    restart: bool             # staged restart (mechanical) or immediate
    source: str = None
    dead_since: float = None
    energised_at: float = -1e9
    down: bool = False
    preferred_ok_since: float = None
    transfer_until: float = -1.0

    def __post_init__(self):
        self.source = self.preferred


@dataclass
class Result:
    t: np.ndarray
    series: dict
    events: list = field(default_factory=list)


def simulate(utility_fail_s=10.0, utility_return_s=900.0, dg_starts=True,
             t_end=1600.0, dt=0.1, s: Settings = None):
    s = s or Settings()
    charger_kw = B.UPS_RECHARGE_FRACTION * 1200.0
    # usable energy of the aged battery: rated for the full IT load for the
    # autonomy time, with the design margin
    battery_kwh = B.IT_LOAD_KW * B.AUTONOMY_MIN / 60 / 0.9613 * B.BATTERY_DESIGN_MARGIN
    batt = battery_kwh
    mech_half = sum(q * kw for _, q, kw, _, b in B.MECHANICAL if b == "MDB-M1/M2") / 2
    boards = [
        Board("MDB-M1", "A", mech_half, True),
        Board("MDB-M2", "B", mech_half, True),
        Board("LDB", "A", 30.0, False),
        Board("ESS-DB", "B", 20.0, False),
    ]

    events = []
    def log(t, msg):
        events.append((round(float(t), 1), msg))

    qa1_closed, qa2_closed = True, False
    dg_state, dg_timer, attempts = "stopped", 0.0, 0
    uv_timer = None
    transfer_step, transfer_timer = None, 0.0
    util_ok_since = None
    rect_on_at = 0.0 - s.rectifier_delay_s - s.rectifier_ramp_s
    ups_a_online = True

    n = int(t_end / dt) + 1
    keys = ["util_a", "dg_a", "msb_a", "rect_kw", "batt_kw", "batt_pct",
            "it_a_kw", "it_b_kw", "dg_kw", "msb_a_kw", "m1_on_a", "m2_on_a"]
    out = {k: np.zeros(n) for k in keys}
    t_axis = np.arange(n) * dt

    for k, t in enumerate(t_axis):
        util = 0.0 if utility_fail_s <= t < utility_return_s else 1.0

        # ---- generator ------------------------------------------------------
        if dg_state == "cranking":
            dg_timer += dt
            if dg_starts and dg_timer >= s.dg_runup_s:
                dg_state, dg_timer = "stabilising", 0.0
                log(t, "DG-A at rated voltage and frequency")
            elif not dg_starts and dg_timer >= s.crank_s:
                attempts += 1
                if attempts >= s.start_attempts:
                    dg_state = "failed"
                    log(t, f"DG-A failed to start after {attempts} attempts, alarm")
                else:
                    dg_state, dg_timer = "resting", 0.0
                    log(t, f"DG-A start attempt {attempts} failed")
        elif dg_state == "resting":
            dg_timer += dt
            if dg_timer >= s.crank_rest_s:
                dg_state, dg_timer = "cranking", 0.0
        elif dg_state == "stabilising":
            dg_timer += dt
            if dg_timer >= s.dg_stabilise_s:
                dg_state = "ready"
        elif dg_state == "cooldown":
            dg_timer += dt
            if dg_timer >= s.dg_cooldown_s:
                dg_state = "stopped"
                log(t, "DG-A stopped after cool-down")
        dg_v = 1.0 if dg_state in ("ready", "cooldown") else 0.0

        # ---- utility failure detection and transfer to generator ------------
        if qa1_closed and util < s.uv_pickup_pu:
            if uv_timer is None:
                uv_timer = t
                log(t, "Utility A lost, undervoltage timer started")
            elif t - uv_timer >= s.uv_delay_s and dg_state == "stopped":
                dg_state, dg_timer = "cranking", 0.0
                log(t, "Undervoltage confirmed, DG-A start signal")
        elif qa1_closed:
            if uv_timer is not None:
                log(t, "Utility A restored with QA1 still closed, MSB-A back on utility")
                if dg_state in ("cranking", "resting", "stabilising", "ready", "failed"):
                    dg_state = "stopped"
            uv_timer = None

        if qa1_closed and util < s.uv_pickup_pu and dg_state == "ready" and transfer_step is None:
            transfer_step, transfer_timer = "to_dg", 0.0
            qa1_closed = False
            log(t, "QA1 utility ACB open command")

        # ---- retransfer to utility ------------------------------------------
        if qa2_closed:
            if util >= 0.95:
                util_ok_since = t if util_ok_since is None else util_ok_since
                if util_ok_since == t:
                    log(t, "Utility A restored, stability timer started")
                if t - util_ok_since >= s.utility_stable_s and transfer_step is None:
                    transfer_step, transfer_timer = "to_util", 0.0
                    qa2_closed = False
                    log(t, "QA2 generator ACB open command (retransfer)")
            else:
                util_ok_since = None

        if transfer_step:
            transfer_timer += dt
            if transfer_timer >= s.acb_open_s + s.dead_time_s + s.acb_close_s:
                if transfer_step == "to_dg":
                    qa2_closed = True
                    log(t, "QA2 generator ACB closed, MSB-A on DG")
                else:
                    qa1_closed = True
                    dg_state, dg_timer = "cooldown", 0.0
                    uv_timer = None
                    log(t, "QA1 utility ACB closed, MSB-A on utility; DG-A cooling down")
                transfer_step = None

        msb_v = (util if qa1_closed else 0.0) or (dg_v if qa2_closed else 0.0)
        source_a = msb_v >= s.uv_pickup_pu

        # ---- UPS-A ----------------------------------------------------------
        if not source_a:
            rect_on_at = None
        elif rect_on_at is None:
            rect_on_at = t
        if rect_on_at is None:
            ramp = 0.0
        else:
            ramp = np.clip((t - rect_on_at - s.rectifier_delay_s) / s.rectifier_ramp_s, 0, 1)

        it_a = B.IT_LOAD_KW / 2 if ups_a_online else 0.0
        it_b = B.IT_LOAD_KW - it_a
        eff = 0.9537
        need = it_a / eff
        rect = ramp * need
        batt_kw = need - rect if ups_a_online else 0.0
        # charger runs once the rectifier has fully walked in
        charge_kw = charger_kw if (ramp >= 1 and batt < battery_kwh) else 0.0
        rect += charge_kw
        batt_kw -= 0.9 * charge_kw
        batt = min(max(batt - batt_kw * dt / 3600, 0.0), battery_kwh)
        if ups_a_online and batt <= 0.0:
            ups_a_online = False
            log(t, "UPS-A battery end of discharge, UPS-A output off; "
                   "racks carried by B cords")
        elif not ups_a_online and ramp >= 1:
            ups_a_online = True
            log(t, "UPS-A restarted on restored input, load shared A/B again")

        # ---- mechanical ATSs ------------------------------------------------
        for bd in boards:
            live = {"A": source_a, "B": True}
            alt = "B" if bd.preferred == "A" else "A"
            if t < bd.transfer_until:
                continue
            if not live[bd.source]:
                bd.dead_since = t if bd.dead_since is None else bd.dead_since
                if t - bd.dead_since >= s.mech_ats_delay_s:
                    other = alt if bd.source == bd.preferred else bd.preferred
                    if live[other]:
                        bd.source = other
                        bd.transfer_until = t + 0.3
                        bd.dead_since = None
                        log(t, f"{bd.name} ATS transferred to source {other}")
            else:
                bd.dead_since = None
            if bd.source != bd.preferred and live[bd.preferred]:
                bd.preferred_ok_since = t if bd.preferred_ok_since is None else bd.preferred_ok_since
                if t - bd.preferred_ok_since >= s.mech_retransfer_s:
                    bd.source = bd.preferred
                    bd.transfer_until = t + 0.3
                    bd.preferred_ok_since = None
                    log(t, f"{bd.name} ATS returned to preferred source {bd.preferred}")
            elif bd.source == bd.preferred:
                bd.preferred_ok_since = None

        for bd in boards:
            live_now = t >= bd.transfer_until and {"A": source_a, "B": True}[bd.source]
            if not live_now:
                bd.down = True
            elif bd.down:
                bd.down = False
                bd.energised_at = t

        def board_kw(bd):
            if bd.down:
                return 0.0
            if not bd.restart:
                return bd.kw
            since = t - bd.energised_at
            return sum(kw for delay, kw in s.restart_steps if since >= delay) * bd.kw / sum(
                kw for _, kw in s.restart_steps)

        mech_on_a = sum(board_kw(bd) for bd in boards if bd.source == "A")
        msb_kw = (rect + mech_on_a) if source_a else 0.0

        out["util_a"][k] = util
        out["dg_a"][k] = dg_v
        out["msb_a"][k] = msb_v
        out["rect_kw"][k] = rect
        out["batt_kw"][k] = batt_kw
        out["batt_pct"][k] = 100 * batt / battery_kwh
        out["it_a_kw"][k] = it_a
        out["it_b_kw"][k] = it_b
        out["dg_kw"][k] = msb_kw if qa2_closed else 0.0
        out["msb_a_kw"][k] = msb_kw
        out["m1_on_a"][k] = 1.0 if boards[0].source == "A" else 0.0
        out["m2_on_a"][k] = 1.0 if boards[1].source == "A" else 0.0

    return Result(t_axis, out, events)


def max_step_kw(series, dt=0.1, window_s=1.0):
    """Largest load increase seen by the generator within any window."""
    w = max(int(window_s / dt), 1)
    x = series
    return float(np.max(x[w:] - x[:-w])) if len(x) > w else 0.0
