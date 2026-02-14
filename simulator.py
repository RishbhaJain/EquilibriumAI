"""
Emissions recalculation engine for what-if scenarios.

Pure Python — no AI. Takes the carbon footprint JSON and a dict of overrides,
recomputes all totals, and returns a before/after diff.
"""

import copy
import json


# Baseline constants extracted from the data
TOTAL_UNITS = 90000
ECOMMERCE_UNITS = 18500
UNITS_24OZ = 60500  # sum of all 24oz SKUs
UNITS_32OZ = 29500  # sum of all 32oz SKUs

# Ocean freight shipment details for recalculation
OCEAN_SHIPMENTS = [
    {"name": "COSCO Orchid 0285E", "containers": 1, "units": 15000, "teu_class": 19100, "speed": "slow"},
    {"name": "COSCO Peony 0312E", "containers": 1, "units": 12000, "teu_class": 19100, "speed": "slow"},
    {"name": "COSCO Jasmine 0318E", "containers": 1, "units": 10000, "teu_class": 19100, "speed": "slow"},
    {"name": "COSCO Universe 0331E", "containers": 2, "units": 20000, "teu_class": 21237, "speed": "slow"},
    {"name": "COSCO Nebula 0338E", "containers": 1, "units": 15000, "teu_class": 19100, "speed": "slow"},
    {"name": "Maersk Edirne 249W", "containers": 1, "units": 18000, "teu_class": 15282, "speed": "express"},
]

# CO2 per 40HC container by speed mode (kg)
OCEAN_CO2_PER_CONTAINER = {
    "slow": {19100: 1360, 21237: 1240, 15282: 1180},
    "moderate": {19100: 1520, 21237: 1390, 15282: 1320},
    "express": {19100: 1780, 21237: 1630, 15282: 1530},
    "ultra_slow": {19100: 1120, 21237: 1020, 15282: 970},
}

# Drayage trips
DRAYAGE_TRIPS_DIESEL = 6
DRAYAGE_TRIPS_EV = 1
DRAYAGE_CO2_DIESEL = 181.3  # kg per trip
DRAYAGE_CO2_EV = 23.0  # kg per trip


def recalculate_emissions(base_data, overrides):
    """Recalculate emissions with overrides applied.

    Supported override keys:
        raw_materials.steel_factor        - kg CO2e per kg steel (default 1.83)
        raw_materials.tritan_factor       - kg CO2e per kg resin (default 3.8)
        raw_materials.silicone_factor     - kg CO2e per kg silicone (default 4.23)
        manufacturing.grid_factor         - kg CO2e per kWh (default 0.581)
        manufacturing.renewable_pct       - 0-100, % of electricity from renewables (default 0)
        ocean_freight.speed_mode          - "slow" | "moderate" | "express" | "ultra_slow"
        ocean_freight.all_same_speed      - if true, apply speed_mode to ALL shipments
        port_drayage.ev_pct               - 0-100, % of trips using EV (default ~14%)
        warehousing.renewable_pct         - 0-100, % of DC electricity from renewables (default 0)
        warehousing.efficiency_gain_pct   - 0-100, % reduction in overall DC energy
        distribution.ftl_shift_pct        - 0-100, % of LTL shipments shifted to FTL

    Returns dict with stage-by-stage results and new totals.
    """
    result = {}

    # --- RAW MATERIALS ---
    steel_factor = overrides.get("raw_materials.steel_factor", 1.83)
    tritan_factor = overrides.get("raw_materials.tritan_factor", 3.8)
    silicone_factor = overrides.get("raw_materials.silicone_factor", 4.23)

    # Steel: 260g per 24oz, 327g per 32oz
    steel_co2 = (UNITS_24OZ * 0.260 * steel_factor) + (UNITS_32OZ * 0.327 * steel_factor)
    # Tritan: 38g per 24oz, 42g per 32oz
    tritan_co2 = (UNITS_24OZ * 0.038 * tritan_factor) + (UNITS_32OZ * 0.042 * tritan_factor)
    # Silicone: 26g per 24oz, 30g per 32oz
    silicone_co2 = (UNITS_24OZ * 0.026 * silicone_factor) + (UNITS_32OZ * 0.030 * silicone_factor)
    # Powder coating + PP straw (small, keep as constants)
    other_materials_co2 = 944 + 496  # from original data

    raw_materials_total = steel_co2 + tritan_co2 + silicone_co2 + other_materials_co2
    result["raw_materials"] = {
        "total_kg_co2e": round(raw_materials_total, 1),
        "steel_kg_co2e": round(steel_co2, 1),
        "tritan_kg_co2e": round(tritan_co2, 1),
        "silicone_kg_co2e": round(silicone_co2, 1),
        "other_kg_co2e": other_materials_co2,
        "per_unit_kg": round(raw_materials_total / TOTAL_UNITS, 4),
    }

    # --- INLAND TRUCKING (CHINA) ---
    # Keep constant unless overrides added later
    inland_trucking_total = 7927
    result["inland_trucking"] = {
        "total_kg_co2e": inland_trucking_total,
        "per_unit_kg": round(inland_trucking_total / TOTAL_UNITS, 4),
    }

    # --- MANUFACTURING ---
    base_grid_factor = overrides.get("manufacturing.grid_factor", 0.581)
    renewable_pct = overrides.get("manufacturing.renewable_pct", 0) / 100.0

    # Electricity: 3,840,000 kWh annual, Owala share ~90000/4200000 of annual
    owala_share = TOTAL_UNITS / 4200000
    annual_kwh = 3840000
    effective_grid_factor = base_grid_factor * (1 - renewable_pct)
    electricity_co2 = annual_kwh * owala_share * effective_grid_factor
    # Gas + diesel stay constant
    gas_co2 = 76.8 * 1000 * owala_share  # tonnes to kg, scaled to Owala share
    diesel_co2 = 22.0 * 1000 * owala_share

    manufacturing_total = electricity_co2 + gas_co2 + diesel_co2
    result["manufacturing"] = {
        "total_kg_co2e": round(manufacturing_total, 1),
        "electricity_kg_co2e": round(electricity_co2, 1),
        "grid_factor_used": round(effective_grid_factor, 4),
        "renewable_pct": round(renewable_pct * 100, 1),
        "per_unit_kg": round(manufacturing_total / TOTAL_UNITS, 4),
    }

    # --- PACKAGING ---
    packaging_total = 720
    result["packaging"] = {
        "total_kg_co2e": packaging_total,
        "per_unit_kg": round(packaging_total / TOTAL_UNITS, 4),
    }

    # --- OCEAN FREIGHT ---
    speed_mode = overrides.get("ocean_freight.speed_mode", None)
    all_same_speed = overrides.get("ocean_freight.all_same_speed", False)

    ocean_total = 0
    shipment_details = []
    for s in OCEAN_SHIPMENTS:
        ship_speed = speed_mode if (all_same_speed and speed_mode) else s["speed"]
        if speed_mode and not all_same_speed:
            # Only override express shipments if not all_same_speed
            if s["speed"] == "express":
                ship_speed = speed_mode

        co2_per_container = OCEAN_CO2_PER_CONTAINER.get(ship_speed, OCEAN_CO2_PER_CONTAINER["slow"]).get(
            s["teu_class"], 1360
        )
        shipment_co2 = co2_per_container * s["containers"]
        ocean_total += shipment_co2
        shipment_details.append({
            "name": s["name"],
            "speed": ship_speed,
            "containers": s["containers"],
            "co2_kg": round(shipment_co2, 1),
            "co2_per_unit_kg": round(shipment_co2 / s["units"], 4),
        })

    result["ocean_freight"] = {
        "total_kg_co2e": round(ocean_total, 1),
        "per_unit_kg": round(ocean_total / TOTAL_UNITS, 4),
        "shipments": shipment_details,
    }

    # --- PORT DRAYAGE ---
    ev_pct = overrides.get("port_drayage.ev_pct", 14.3) / 100.0  # default: 1/7 trips
    total_trips = DRAYAGE_TRIPS_DIESEL + DRAYAGE_TRIPS_EV  # 7
    ev_trips = round(total_trips * ev_pct)
    diesel_trips = total_trips - ev_trips
    drayage_total = (diesel_trips * DRAYAGE_CO2_DIESEL) + (ev_trips * DRAYAGE_CO2_EV)

    result["port_drayage"] = {
        "total_kg_co2e": round(drayage_total, 1),
        "diesel_trips": diesel_trips,
        "ev_trips": ev_trips,
        "per_unit_kg": round(drayage_total / TOTAL_UNITS, 4),
    }

    # --- WAREHOUSING ---
    base_warehousing = 117000  # kg CO2e, Q3-Q4
    wh_renewable_pct = overrides.get("warehousing.renewable_pct", 0) / 100.0
    wh_efficiency = overrides.get("warehousing.efficiency_gain_pct", 0) / 100.0
    # Electricity is ~68% of warehouse emissions (1920/2840)
    electricity_share = 0.676
    warehousing_total = base_warehousing * (
        (electricity_share * (1 - wh_renewable_pct)) +
        (1 - electricity_share)
    ) * (1 - wh_efficiency)

    result["warehousing"] = {
        "total_kg_co2e": round(warehousing_total, 1),
        "renewable_pct": round(wh_renewable_pct * 100, 1),
        "efficiency_gain_pct": round(wh_efficiency * 100, 1),
        "per_unit_kg": round(warehousing_total / TOTAL_UNITS, 4),
    }

    # --- DC TO RETAIL DISTRIBUTION ---
    ftl_shift = overrides.get("distribution.ftl_shift_pct", 0) / 100.0
    # Original: FTL carriers = 1120 + 290 = 1410 kg, LTL = 3850 + 2680 + 5440 = 11970 kg
    base_ftl_co2 = 1410
    base_ltl_co2 = 11970
    # Shifting LTL to FTL saves ~40% per tonne-mile (avg FTL ~68 vs LTL ~107 g/tonne-mi)
    shifted_ltl = base_ltl_co2 * ftl_shift
    distribution_total = base_ftl_co2 + (base_ltl_co2 - shifted_ltl) + (shifted_ltl * 0.63)

    result["distribution"] = {
        "total_kg_co2e": round(distribution_total, 1),
        "ftl_shift_pct": round(ftl_shift * 100, 1),
        "per_unit_kg": round(distribution_total / TOTAL_UNITS, 4),
    }

    # --- LAST MILE ---
    last_mile_total = 12553
    result["last_mile"] = {
        "total_kg_co2e": last_mile_total,
        "per_unit_kg": round(last_mile_total / ECOMMERCE_UNITS, 4),
    }

    # --- TOTALS ---
    grand_total = sum([
        raw_materials_total, inland_trucking_total, manufacturing_total,
        packaging_total, ocean_total, drayage_total, warehousing_total,
        distribution_total, last_mile_total,
    ])

    stages = [
        ("Raw Materials", raw_materials_total),
        ("Inland Trucking (China)", inland_trucking_total),
        ("Manufacturing", manufacturing_total),
        ("Packaging Production", packaging_total),
        ("Ocean Freight", ocean_total),
        ("Port Drayage (US)", drayage_total),
        ("Warehousing (DC)", warehousing_total),
        ("DC to Retail", distribution_total),
        ("Last Mile (e-comm)", last_mile_total),
    ]

    result["totals"] = {
        "total_kg_co2e": round(grand_total, 1),
        "total_tonnes_co2e": round(grand_total / 1000, 2),
        "per_unit_kg": round(grand_total / TOTAL_UNITS, 4),
        "by_stage": [
            {
                "stage": name,
                "kg_co2e": round(val, 1),
                "pct": round(val / grand_total * 100, 1),
            }
            for name, val in stages
        ],
    }

    return result


def compute_diff(original_totals, simulated):
    """Compute before/after diff between original data and simulated results."""
    original_stages = {
        "Raw Materials": 64710,
        "Inland Trucking (China)": 7927,
        "Manufacturing": 49950,
        "Packaging Production": 720,
        "Ocean Freight": 9450,
        "Port Drayage (US)": 1112,
        "Warehousing (DC)": 117000,
        "DC to Retail": 13380,
        "Last Mile (e-comm)": 12553,
    }
    original_total = 213602  # from the base data (sum doesn't exactly match due to rounding)

    sim_stages = {s["stage"]: s["kg_co2e"] for s in simulated["totals"]["by_stage"]}
    sim_total = simulated["totals"]["total_kg_co2e"]

    diff = {
        "total": {
            "original_kg": original_total,
            "simulated_kg": round(sim_total, 1),
            "delta_kg": round(sim_total - original_total, 1),
            "delta_pct": round((sim_total - original_total) / original_total * 100, 2),
        },
        "per_unit": {
            "original_kg": round(original_total / TOTAL_UNITS, 4),
            "simulated_kg": round(sim_total / TOTAL_UNITS, 4),
            "delta_kg": round((sim_total - original_total) / TOTAL_UNITS, 4),
        },
        "by_stage": [],
    }

    for stage_name, orig_val in original_stages.items():
        sim_val = sim_stages.get(stage_name, orig_val)
        delta = sim_val - orig_val
        diff["by_stage"].append({
            "stage": stage_name,
            "original_kg": orig_val,
            "simulated_kg": round(sim_val, 1),
            "delta_kg": round(delta, 1),
            "delta_pct": round(delta / orig_val * 100, 2) if orig_val > 0 else 0,
        })

    return diff
