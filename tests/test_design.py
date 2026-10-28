import xml.dom.minidom

import pytest

from dcdesign import basis as B
from dcdesign import sld
from dcdesign.ats import max_step_kw, simulate
from dcdesign.sizing import design, select_breaker


@pytest.fixture(scope="module")
def d():
    return design()


def test_each_side_carries_the_whole_critical_load(d):
    assert d["ups"]["rating_kw"] >= B.IT_LOAD_KW
    assert d["pdus"]["per_side"] * d["pdus"]["rating_kva"] * B.IT_PF >= B.IT_LOAD_KW
    assert d["ups"]["failure"]["loading"] <= B.UPS_MAX_LOADING


def test_source_loading_limits(d):
    s = d["sources"]
    assert s["transformer_loading_failure"] <= B.TRANSFORMER_MAX_LOADING
    assert s["dg_loading_failure"] <= B.DG_MAX_LOADING
    assert s["transformer_loading_normal"] < 0.5


def test_battery_meets_autonomy(d):
    b = d["battery"]
    assert b["strings"] * B.BLOCK_W_PER_CELL_10MIN >= b["w_per_cell_required"]


def test_breakers_cover_their_loads(d):
    for b in d["breakers"]:
        assert b.ir_a >= b.load_a, b.tag
        assert b.ir_a <= b.frame_a, b.tag


def test_busbars(d):
    for bb in d["busbars"]:
        assert bb["rating_a"] >= bb["incomer_ir_a"]
        assert bb["diversified_a"] <= bb["rating_a"]
    assert d["busbars"][0]["icw_ka"] >= B.MSB_FAULT_KA


def test_breaker_selection_rule():
    b = select_breaker("x", "test", 354.0)
    assert (b.kind, b.frame_a, b.ir_a) == ("MCCB", 400, 360)


def test_utility_failure_sequence():
    r = simulate()
    S = r.series
    assert (S["it_a_kw"] + S["it_b_kw"]).min() == pytest.approx(B.IT_LOAD_KW)
    t_closed = next(t for t, e in r.events if "QA2 generator ACB closed" in e)
    assert t_closed - 10.0 < 30.0           # on generator within 30 s
    assert S["batt_pct"].min() > 90.0
    dg_kw = 0.8 * 2250                       # prime kW
    assert max_step_kw(S["dg_kw"]) < 0.25 * dg_kw
    assert any("returned to preferred source A" in e for _, e in r.events)
    assert any("DG-A stopped" in e for _, e in r.events)


def test_generator_failure_is_carried_by_side_b():
    r = simulate(dg_starts=False, utility_return_s=2400.0, t_end=3000.0)
    S = r.series
    assert (S["it_a_kw"] + S["it_b_kw"]).min() == pytest.approx(B.IT_LOAD_KW)
    assert S["it_b_kw"].max() == pytest.approx(B.IT_LOAD_KW)
    t_end = next(t for t, e in r.events if "end of discharge" in e)
    # half load on side A, so well over the 10 min full-load autonomy
    assert (t_end - 10.0) / 60 > B.AUTONOMY_MIN


def test_sld_is_consistent(d, tmp_path):
    nodes, edges = sld.build(d)
    assert all(a in nodes and b in nodes for a, b, _ in edges)
    for n in range(1, B.PDUS_PER_SIDE + 1):
        assert f"PDU-A{n}" in nodes and f"PDU-B{n}" in nodes
    path = tmp_path / "sld.drawio"
    sld.write_drawio(nodes, edges, path, "test")
    xml.dom.minidom.parse(str(path))
