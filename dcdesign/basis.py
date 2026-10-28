"""Design basis for a 1 MW critical-load data hall with 2N power paths.

Each side (A and B) has its own 11 kV utility feeder, transformer, diesel
generator, main LV switchboard (MSB), UPS system, UPS output board and PDUs.
Every rack is dual-corded, one cord to an A-side PDU and one to a B-side PDU,
so either side alone must carry the whole critical load.
"""

SYSTEM_V = 415.0
FREQ_HZ = 50

# ---- IT load -----------------------------------------------------------------
IT_LOAD_KW = 1000.0
RACKS = 200
RACK_DESIGN_KW = 6.0          # per-rack design maximum (average is 5 kW)
IT_PF = 0.98
ROWS = 10                     # 20 racks per row
PDUS_PER_SIDE = 5             # each PDU serves two rows

# ---- UPS -----------------------------------------------------------------------
UPS_MODULE_KW = 400.0         # unity pf modules
UPS_MAX_LOADING = 0.90        # with one side carrying everything
UPS_INPUT_PF = 0.99
UPS_RECHARGE_FRACTION = 0.10  # charger power as a fraction of UPS rating
# double-conversion efficiency against load fraction, from a typical maker curve
UPS_EFFICIENCY_CURVE = [(0.25, 0.945), (0.50, 0.958), (0.75, 0.962), (1.00, 0.960)]
AUTONOMY_MIN = 10.0
BATTERY_AGEING_FACTOR = 1.25  # end-of-life capacity 80 %
BATTERY_DESIGN_MARGIN = 1.10
CELLS_PER_STRING = 240        # 40 x 12 V blocks, 480 V nominal
END_VOLTAGE_VPC = 1.67
# constant-power rating of the selected 12 V block at 10 min to 1.67 V/cell,
# W per cell, read from the battery maker's discharge table
BLOCK_W_PER_CELL_10MIN = 600.0

# ---- Mechanical and building loads (running, kW, pf) --------------------------
# Mechanical boards MDB-M1 and MDB-M2 each have a 4-pole ATS fed from MSB-A
# and MSB-B, so either MSB may end up carrying both.
MECHANICAL = [
    # name, quantity running, kW each, pf, board
    ("Air-cooled chiller (VFD)", 3, 110.0, 0.95, "MDB-M1/M2"),
    ("Chilled water pump (VFD)", 3, 15.0, 0.95, "MDB-M1/M2"),
    ("CRAH fan (EC)", 18, 6.0, 0.95, "MDB-M1/M2"),
    ("Lighting and small power", 1, 30.0, 0.90, "LDB"),
    ("BMS, fire and security (own UPS)", 1, 20.0, 0.90, "ESS-DB"),
]

# ---- Standard ratings ---------------------------------------------------------
TRANSFORMER_KVA = [1000, 1250, 1600, 2000, 2500, 3150]
TRANSFORMER_MAX_LOADING = 0.90      # worst single contingency
DG_KVA = [1250, 1500, 2000, 2250, 2500, 3000]
DG_MAX_LOADING = 0.85               # of prime rating
ACB_FRAMES = [800, 1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000, 6300]
MCCB_FRAMES = [100, 160, 250, 400, 630, 800, 1000, 1250]
BUSBAR_RATINGS = [800, 1000, 1250, 1600, 2000, 2500, 3200, 4000, 5000, 6300]
PDU_KVA = [100, 150, 200, 250, 300, 400]
PDU_MAX_LOADING = 0.85

# prospective fault at the MSB from the short-circuit study of the same
# 2000 kVA transformer (lv-short-circuit-selectivity-study)
MSB_FAULT_KA = 40.5
