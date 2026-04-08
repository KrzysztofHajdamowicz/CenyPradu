#!/usr/bin/env python3
"""
Solar/Battery Investment Optimizer

Determines the most profitable split of a budget between additional PV panels
and battery storage, based on real Home Assistant consumption/price data and
a physics-based clear-sky PV model.

Usage:
    python scripts/solar_investment_optimizer.py
"""

import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

BUDGET = 16_660  # PLN
PV_COST_PER_WP = 1.0  # PLN/Wp
PV_PANEL_WP = 400  # Wp per new panel
PV_PANEL_COST = PV_PANEL_WP * PV_COST_PER_WP  # 400 PLN
BATTERY_COST_PER_KWH = 8_000 / 15  # ~533 PLN/kWh
BATTERY_UNIT_KWH = 15.0
BATTERY_UNIT_COST = 8_000  # PLN

# Existing installation (baseline after microinverter fix)
EXISTING_PANELS = [
    # (azimuth_from_south_deg, tilt_deg, watts_peak)
    (0, 45, 575),  # South
    (33, 45, 575),  # SSW
    (98, 45, 575),  # West
    (135, 45, 575),  # NW
]
EXISTING_BATTERY_KWH = 15.0

# New panels
NEW_PANEL_AZ = 45  # SW (degrees from south, positive=west)
NEW_PANEL_TILT = 20  # degrees from horizontal
NEW_PANEL_WP = 400

# Battery parameters
BATTERY_EFFICIENCY = 0.92  # round-trip
CHARGE_EFF = math.sqrt(BATTERY_EFFICIENCY)
DISCHARGE_EFF = math.sqrt(BATTERY_EFFICIENCY)
BATTERY_C_RATE = 0.5  # C/2 charge/discharge rate
MIN_SOC_FRAC = 0.05  # 5% minimum SoC

# Location
LAT = 51.1
LON = 17.0
TZ = ZoneInfo("Europe/Warsaw")

# Cloud factor for Poland (annual average clear-sky to real ratio)
CLOUD_FACTOR = 0.50  # conservative for Poland; clear-sky overestimates

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CSV_PATH = BASE_DIR / "HomeAssistant-history.csv"
TARIFF_PATH = BASE_DIR / "data" / "tariffs" / "tauron-g13s.json"
PRICES_DIR = BASE_DIR / "data" / "prices"

# ---------------------------------------------------------------------------
# SOLAR POSITION & PANEL POWER MODEL (from generate_pv_svgs.py)
# ---------------------------------------------------------------------------


def solar_declination(doy):
    return 23.45 * math.sin(math.radians(360 / 365 * (284 + doy)))


def equation_of_time(doy):
    B = math.radians(360 / 365 * (doy - 81))
    return 9.87 * math.sin(2 * B) - 7.53 * math.cos(B) - 1.5 * math.sin(B)


def solar_position(doy, local_hour, tz_offset):
    lat_r = math.radians(LAT)
    decl_r = math.radians(solar_declination(doy))
    eot = equation_of_time(doy)
    tc = 4 * (LON - tz_offset * 15) + eot
    solar_time = local_hour + tc / 60
    ha_r = math.radians(15 * (solar_time - 12))
    sin_alt = math.sin(lat_r) * math.sin(decl_r) + math.cos(lat_r) * math.cos(
        decl_r
    ) * math.cos(ha_r)
    sin_alt = max(-1, min(1, sin_alt))
    altitude = math.degrees(math.asin(sin_alt))
    if math.cos(math.radians(altitude)) < 0.001:
        return altitude, 0.0
    cos_az = (sin_alt * math.sin(lat_r) - math.sin(decl_r)) / (
        math.cos(math.radians(altitude)) * math.cos(lat_r)
    )
    cos_az = max(-1, min(1, cos_az))
    azimuth = math.degrees(math.acos(cos_az))
    if 15 * (solar_time - 12) < 0:
        azimuth = -azimuth
    return altitude, azimuth


def clear_sky_dni(alt_deg):
    if alt_deg <= 1:
        return 0
    zenith = 90 - alt_deg
    AM = 1 / (
        math.sin(math.radians(alt_deg))
        + 0.50572 * max(0.001, (96.07995 - zenith)) ** (-1.6364)
    )
    return 1361 * (0.7 ** (max(1, AM) ** 0.678))


def clear_sky_dhi(alt_deg, dni):
    if alt_deg <= 1:
        return 0
    sin_a = math.sin(math.radians(alt_deg))
    return max(0, 0.10 * dni * sin_a + 15 * sin_a)


def panel_power_w(alt_deg, az_deg, panel_az, panel_tilt, panel_wp):
    """Returns instantaneous power in watts for a single panel."""
    if alt_deg <= 1:
        return 0
    dni = clear_sky_dni(alt_deg)
    dhi = clear_sky_dhi(alt_deg, dni)
    tilt_r = math.radians(panel_tilt)
    alt_r = math.radians(alt_deg)
    delta_az_r = math.radians(az_deg - panel_az)
    # Front side: beam + diffuse + ground reflected
    cos_aoi = math.sin(alt_r) * math.cos(tilt_r) + math.cos(alt_r) * math.sin(
        tilt_r
    ) * math.cos(delta_az_r)
    beam_poa = dni * max(0, cos_aoi)
    diffuse_poa = dhi * (1 + math.cos(tilt_r)) / 2
    ghi = dni * math.sin(alt_r) + dhi
    ground_poa = 0.2 * ghi * (1 - math.cos(tilt_r)) / 2
    # Rear side: bifacial
    cos_wall_aoi = math.cos(alt_r) * math.cos(delta_az_r)
    wall_beam = dni * max(0, cos_wall_aoi)
    wall_total = wall_beam + dhi * 0.5
    rear = wall_total * 0.35 * 0.35
    rear += 0.04 * ghi
    total = beam_poa + diffuse_poa + ground_poa + rear * 0.70
    power = panel_wp * (total / 1000) * 0.95
    return max(0, power)


def compute_hourly_pv_kwh(panels, doy, tz_offset):
    """Compute total kWh for each hour (0-23) for a list of panels on a given day."""
    hourly = []
    for hour in range(24):
        # Integrate over 4 sub-steps per hour for accuracy
        total_wh = 0.0
        for sub in range(4):
            t = hour + sub * 0.25 + 0.125  # midpoint of 15-min interval
            alt, az = solar_position(doy, t, tz_offset)
            for panel_az, panel_tilt, panel_wp in panels:
                total_wh += (
                    panel_power_w(alt, az, panel_az, panel_tilt, panel_wp) * 0.25
                )
        hourly.append(total_wh / 1000.0)  # convert Wh to kWh
    return hourly


# ---------------------------------------------------------------------------
# POLISH HOLIDAYS (ported from holidays.js)
# ---------------------------------------------------------------------------

FIXED_HOLIDAYS_MMDD = [
    (1, 1),
    (5, 1),
    (5, 3),
    (8, 15),
    (11, 1),
    (11, 11),
    (12, 25),
    (12, 26),
]


def easter_date(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_polish_holidays(year):
    holidays = set()
    for m, d in FIXED_HOLIDAYS_MMDD:
        holidays.add(date(year, m, d))
    e = easter_date(year)
    holidays.add(e)
    holidays.add(e + timedelta(days=1))  # Easter Monday
    holidays.add(e + timedelta(days=49))  # Whit Sunday
    holidays.add(e + timedelta(days=60))  # Corpus Christi
    return holidays


def get_day_type(d, holidays_set):
    if d in holidays_set:
        return "holiday"
    dow = d.weekday()  # 0=Mon, 6=Sun
    if dow == 6:
        return "sunday"
    if dow == 5:
        return "saturday"
    return "weekday"


# ---------------------------------------------------------------------------
# TARIFF & PRICE ENGINE
# ---------------------------------------------------------------------------


def load_tariff(path):
    with open(path) as f:
        return json.load(f)


def get_distribution_rate(wall_hour, day_type, tariff, month):
    rates = tariff["variable_rates_pln_kwh"]
    if rates["type"] == "flat":
        return rates["rate"]
    # TOU with seasons
    if rates.get("seasonal"):
        for season in rates["seasons"]:
            if month in season["months"]:
                periods = season["periods"]
                break
        else:
            raise ValueError(f"No season for month {month}")
    else:
        periods = rates["periods"]

    for period in periods:
        schedule = period["schedule"].get(day_type, [])
        for rng in schedule:
            start_str, end_str = rng.split("-")
            start = int(start_str.split(":")[0])
            end = int(end_str.split(":")[0])
            if start == 0 and end == 24:
                return period["rate"]
            if start < end:
                if start <= wall_hour < end:
                    return period["rate"]
            elif start > end:
                if wall_hour >= start or wall_hour < end:
                    return period["rate"]
    raise ValueError(f"No rate for hour={wall_hour}, day={day_type}, month={month}")


def compute_buy_price_brutto(tge_pln_mwh, wall_hour, day_type, tariff, month):
    """All-in buy price in PLN/kWh (brutto = with VAT)."""
    spot = tge_pln_mwh / 1000.0
    dist = get_distribution_rate(wall_hour, day_type, tariff, month)
    sys_charges = sum(tariff["system_charges_pln_kwh"].values())
    excise = tariff["excise_pln_kwh"]
    netto = spot + dist + sys_charges + excise
    return netto * (1 + tariff["vat_rate"])


# ---------------------------------------------------------------------------
# DATA LOADING
# ---------------------------------------------------------------------------


def load_csv_sensors(csv_path):
    """Load CSV into dict of {sensor_id: [(timestamp_utc, value), ...]}."""
    sensors = defaultdict(list)
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                val = float(row["state"])
            except ValueError, TypeError:
                continue
            ts_str = row["last_changed"]
            # Parse ISO timestamp
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            sensors[row["entity_id"]].append((ts, val))
    # Sort by timestamp
    for k in sensors:
        sensors[k].sort(key=lambda x: x[0])
    return sensors


def load_tge_prices(prices_dir):
    """Load all TGE price JSONs into {datetime_local: price_PLN_MWh}."""
    prices = {}
    for p in sorted(prices_dir.glob("**/*.json")):
        if p.name == "index.json":
            continue
        with open(p) as f:
            data = json.load(f)
        for entry in data["prices"]:
            ts = datetime.fromisoformat(entry["time"])
            prices[ts] = entry["price"]
    return prices


# ---------------------------------------------------------------------------
# DATA PREPARATION
# ---------------------------------------------------------------------------


def build_hourly_consumption(sensor_data):
    """Convert cumulative consumption sensor to hourly kWh dict keyed by local datetime."""
    if not sensor_data:
        return {}
    hourly = {}
    # Resample: for each hour, take last reading
    readings_by_hour = defaultdict(list)
    for ts_utc, val in sensor_data:
        ts_local = ts_utc.astimezone(TZ)
        hour_key = ts_local.replace(minute=0, second=0, microsecond=0)
        readings_by_hour[hour_key].append(val)

    # Get last reading per hour
    sorted_hours = sorted(readings_by_hour.keys())
    prev_val = None
    for h in sorted_hours:
        current_val = readings_by_hour[h][-1]  # last reading in that hour
        if prev_val is not None:
            delta = current_val - prev_val
            if 0 < delta < 50:  # sanity: max 50 kWh per hour
                hourly[h] = delta
        prev_val = current_val
    return hourly


def build_monthly_consumption_profile(hourly_consumption):
    """Build average hourly consumption profile per month: {month: [avg_kwh_per_hour_0..23]}."""
    # Accumulate by (month, hour_of_day)
    sums = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))
    for dt, kwh in hourly_consumption.items():
        m = dt.month
        h = dt.hour
        sums[m][h] += kwh
        counts[m][h] += 1

    profiles = {}
    for m in sums:
        profile = []
        for h in range(24):
            if counts[m][h] > 0:
                profile.append(sums[m][h] / counts[m][h])
            else:
                profile.append(0.0)
        profiles[m] = profile
    return profiles


def build_full_year_consumption(monthly_profiles):
    """Generate 8760-hour consumption array for a year (2026).
    Uses actual monthly profiles where available, fills gaps with nearest month."""
    # We have data for months: 8(partial),9,10,11,12,1,2,3
    # Missing: 4,5,6,7 - fill with September (similar summer-like behavior)
    consumption = []
    for month in range(1, 13):
        if month in monthly_profiles:
            profile = monthly_profiles[month]
        elif month in (4, 5, 6, 7):
            # Use September profile scaled to ~12 kWh/day (summer avg)
            if 9 in monthly_profiles:
                sep_profile = monthly_profiles[9]
                sep_daily = sum(sep_profile)
                if sep_daily > 0:
                    scale = 12.0 / sep_daily
                    profile = [v * scale for v in sep_profile]
                else:
                    profile = [0.5] * 24  # fallback
            else:
                profile = [0.5] * 24
        else:
            profile = [0.5] * 24  # fallback

        # Number of days in month (2026)
        if month == 2:
            days = 28
        elif month in (4, 6, 9, 11):
            days = 30
        else:
            days = 31

        for _ in range(days):
            consumption.extend(profile)

    return consumption


# ---------------------------------------------------------------------------
# PRICE SYNTHESIS
# ---------------------------------------------------------------------------


def build_hourly_buy_sell_prices(
    tge_prices, buy_price_sensor, sell_price_sensor, tariff
):
    """Build buy/sell price arrays indexed by (month, hour_of_day) for a typical day.
    Returns avg profiles per (month, day_type, hour)."""
    # From the actual buy price sensor (all-in, brutto)
    buy_by_mh = defaultdict(list)
    for ts_utc, val in buy_price_sensor:
        ts_local = ts_utc.astimezone(TZ)
        buy_by_mh[(ts_local.month, ts_local.hour)].append(val)

    # Average buy prices per (month, hour)
    avg_buy = {}
    for (m, h), vals in buy_by_mh.items():
        avg_buy[(m, h)] = sum(vals) / len(vals)

    # From sell price sensor
    sell_by_h = defaultdict(list)
    for ts_utc, val in sell_price_sensor:
        ts_local = ts_utc.astimezone(TZ)
        sell_by_h[ts_local.hour].append(val)

    avg_sell_by_hour = {}
    for h, vals in sell_by_h.items():
        avg_sell_by_hour[h] = sum(vals) / len(vals)

    # Compute sell/buy ratio per hour from overlap data
    sell_buy_ratio_by_hour = {}
    for h in range(24):
        # Use March data for both (where sell data exists)
        buy_vals = [v for (m, hr), v in avg_buy.items() if hr == h and m == 3]
        sell_val = avg_sell_by_hour.get(h)
        if buy_vals and sell_val and buy_vals[0] > 0:
            sell_buy_ratio_by_hour[h] = sell_val / buy_vals[0]
        else:
            sell_buy_ratio_by_hour[h] = 0.5  # default

    return avg_buy, avg_sell_by_hour, sell_buy_ratio_by_hour


def build_full_year_prices(avg_buy, sell_buy_ratio, tariff):
    """Generate 8760-hour buy and sell price arrays."""
    buy_prices = []
    sell_prices = []

    holidays_2026 = get_polish_holidays(2026)

    # Summer price scale factor (summer TGE prices ~15% lower)
    summer_months = {4, 5, 6, 7, 8, 9}

    for month in range(1, 13):
        days_in_month = 28 if month == 2 else (30 if month in (4, 6, 9, 11) else 31)
        first_day = date(2026, month, 1)

        for day_offset in range(days_in_month):
            current_date = first_day + timedelta(days=day_offset)
            day_type = get_day_type(current_date, holidays_2026)

            for hour in range(24):
                # Get buy price
                if (month, hour) in avg_buy:
                    bp = avg_buy[(month, hour)]
                else:
                    # Extrapolate from nearest available month
                    nearest = None
                    for offset in range(1, 7):
                        for candidate in [month - offset, month + offset]:
                            cm = ((candidate - 1) % 12) + 1
                            if (cm, hour) in avg_buy:
                                nearest = avg_buy[(cm, hour)]
                                break
                        if nearest is not None:
                            break
                    if nearest is None:
                        nearest = 1.0  # fallback
                    bp = nearest
                    # Apply summer discount
                    if month in summer_months:
                        bp *= 0.85

                # Sell price
                ratio = sell_buy_ratio.get(hour, 0.5)
                sp = bp * ratio
                # Summer midday: sell prices drop significantly
                if month in summer_months and 10 <= hour <= 14:
                    sp *= 0.3  # massive midday solar depression

                buy_prices.append(bp)
                sell_prices.append(sp)

    return buy_prices, sell_prices


# ---------------------------------------------------------------------------
# BATTERY SIMULATION
# ---------------------------------------------------------------------------


@dataclass
class SimResult:
    annual_cost: float = 0.0
    total_self_consumed: float = 0.0
    total_exported: float = 0.0
    total_imported: float = 0.0
    total_pv_generated: float = 0.0
    export_revenue: float = 0.0
    import_cost: float = 0.0
    arbitrage_profit: float = 0.0


def simulate_year(
    existing_panels,
    new_panel_count,
    battery_total_kwh,
    consumption_8760,
    buy_prices_8760,
    sell_prices_8760,
):
    """Run hour-by-hour simulation for a full year."""
    result = SimResult()

    max_charge_rate = battery_total_kwh * BATTERY_C_RATE  # kW
    min_soc = battery_total_kwh * MIN_SOC_FRAC
    soc = battery_total_kwh * 0.5  # start at 50%

    # New panels list
    new_panels = [(NEW_PANEL_AZ, NEW_PANEL_TILT, NEW_PANEL_WP)] * new_panel_count

    # Precompute daily PV production for all 365 days
    hour_idx = 0
    for month in range(1, 13):
        days_in_month = 28 if month == 2 else (30 if month in (4, 6, 9, 11) else 31)

        # Determine timezone offset for this month
        # CET=+1, CEST=+2 (Apr-Oct roughly)
        if 4 <= month <= 10:
            tz_off = 2
        else:
            tz_off = 1

        first_doy = date(2026, month, 1).timetuple().tm_yday

        for day_offset in range(days_in_month):
            doy = first_doy + day_offset

            # Compute PV for existing panels
            existing_pv = compute_hourly_pv_kwh(existing_panels, doy, tz_off)
            # Compute PV for new panels
            if new_panel_count > 0:
                new_pv = compute_hourly_pv_kwh(new_panels, doy, tz_off)
            else:
                new_pv = [0.0] * 24

            # Identify cheapest and most expensive hours for arbitrage
            day_buy_prices = buy_prices_8760[hour_idx : hour_idx + 24]
            sorted_hours = sorted(range(24), key=lambda h: day_buy_prices[h])
            cheap_hours = set(sorted_hours[:5])  # 5 cheapest hours
            expensive_hours = set(sorted_hours[-5:])  # 5 most expensive

            cheap_avg = sum(day_buy_prices[h] for h in cheap_hours) / 5
            expensive_avg = sum(day_buy_prices[h] for h in expensive_hours) / 5
            # Only do arbitrage if spread is profitable after efficiency loss
            arbitrage_profitable = expensive_avg * BATTERY_EFFICIENCY > cheap_avg * 1.05

            for hour in range(24):
                pv_kwh = (existing_pv[hour] + new_pv[hour]) * CLOUD_FACTOR
                cons_kwh = consumption_8760[hour_idx]
                buy_p = buy_prices_8760[hour_idx]
                sell_p = sell_prices_8760[hour_idx]

                result.total_pv_generated += pv_kwh
                net = cons_kwh - pv_kwh  # positive = deficit, negative = surplus

                hour_cost = 0.0

                if net <= 0:
                    # PV surplus
                    surplus = -net
                    result.total_self_consumed += cons_kwh
                    # Charge battery
                    available_capacity = battery_total_kwh - soc
                    charge = min(
                        surplus, available_capacity / CHARGE_EFF, max_charge_rate
                    )
                    soc += charge * CHARGE_EFF
                    export = surplus - charge
                    if export > 0:
                        revenue = export * sell_p
                        result.export_revenue += revenue
                        result.total_exported += export
                        hour_cost -= revenue
                else:
                    # Deficit - try battery first
                    result.total_self_consumed += pv_kwh
                    available_energy = (soc - min_soc) * DISCHARGE_EFF
                    discharge_energy = min(
                        net, available_energy, max_charge_rate * DISCHARGE_EFF
                    )
                    if discharge_energy > 0:
                        soc -= discharge_energy / DISCHARGE_EFF
                    grid_import = net - discharge_energy
                    if grid_import > 0:
                        cost = grid_import * buy_p
                        result.import_cost += cost
                        result.total_imported += grid_import
                        hour_cost += cost

                # Arbitrage: charge from grid during cheap hours
                if (
                    arbitrage_profitable
                    and hour in cheap_hours
                    and soc < battery_total_kwh * 0.95
                ):
                    arb_capacity = min(
                        max_charge_rate, (battery_total_kwh * 0.95 - soc) / CHARGE_EFF
                    )
                    if arb_capacity > 0:
                        soc += arb_capacity * CHARGE_EFF
                        arb_cost = arb_capacity * buy_p
                        hour_cost += arb_cost
                        result.arbitrage_profit -= arb_cost
                        result.total_imported += arb_capacity
                        result.import_cost += arb_cost

                # Arbitrage: prefer discharging during expensive hours
                if (
                    arbitrage_profitable
                    and hour in expensive_hours
                    and soc > min_soc + 1.0
                ):
                    arb_discharge = min(
                        max_charge_rate * DISCHARGE_EFF,
                        (soc - min_soc - 1.0) * DISCHARGE_EFF,
                    )
                    if arb_discharge > 0 and net <= 0:
                        # Export arbitrage energy
                        soc -= arb_discharge / DISCHARGE_EFF
                        revenue = arb_discharge * sell_p
                        hour_cost -= revenue
                        result.arbitrage_profit += revenue
                        result.total_exported += arb_discharge
                        result.export_revenue += revenue

                result.annual_cost += hour_cost
                hour_idx += 1

    return result


# ---------------------------------------------------------------------------
# SCENARIO ENGINE
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    pv_panels_added: int
    battery_added_kwh: float
    cost: float

    @property
    def pv_added_kwp(self):
        return self.pv_panels_added * NEW_PANEL_WP / 1000

    @property
    def total_pv_kwp(self):
        return sum(p[2] for p in EXISTING_PANELS) / 1000 + self.pv_added_kwp

    @property
    def total_battery_kwh(self):
        return EXISTING_BATTERY_KWH + self.battery_added_kwh


def generate_scenarios(budget):
    """Generate investment scenarios: sweep PV panels count, remainder to battery."""
    scenarios = []
    max_panels = int(budget / PV_PANEL_COST)

    # Coarse sweep: 0 to max panels in steps
    step = max(1, max_panels // 20)
    panel_counts = list(range(0, max_panels + 1, step))
    if max_panels not in panel_counts:
        panel_counts.append(max_panels)

    for n_panels in panel_counts:
        pv_cost = n_panels * PV_PANEL_COST
        remaining = budget - pv_cost
        # Battery: buy in 15kWh units
        n_battery_units = int(remaining / BATTERY_UNIT_COST)
        battery_kwh = n_battery_units * BATTERY_UNIT_KWH
        battery_cost = n_battery_units * BATTERY_UNIT_COST
        total_cost = pv_cost + battery_cost
        if total_cost <= budget:
            scenarios.append(Scenario(n_panels, battery_kwh, total_cost))

    # Also add pure battery scenario and battery + minimal PV combos
    # Deduplicate
    seen = set()
    unique = []
    for s in scenarios:
        key = (s.pv_panels_added, s.battery_added_kwh)
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return sorted(unique, key=lambda s: s.pv_panels_added)


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------


def print_results(results, baseline_cost):
    """Print comparison table."""
    print()
    print("=" * 110)
    print("  SOLAR/BATTERY INVESTMENT OPTIMIZER")
    print(
        f"  Budget: {BUDGET:,.0f} PLN | Baseline: {sum(p[2] for p in EXISTING_PANELS) / 1000:.1f} kWp + {EXISTING_BATTERY_KWH:.0f} kWh"
    )
    print("=" * 110)
    print()
    print(f"  Baseline annual cost (no new investment): {baseline_cost:,.0f} PLN")
    print()

    header = (
        f"{'PV Add':>7} {'Batt Add':>8} {'Total PV':>8} {'Tot Batt':>8} "
        f"{'Invested':>9} {'Ann.Cost':>9} {'Savings':>8} {'Payback':>8} "
        f"{'SelfCons':>8} {'Export':>8} {'PV Gen':>8}"
    )
    print(header)
    print(
        f"{'(kWp)':>7} {'(kWh)':>8} {'(kWp)':>8} {'(kWh)':>8} "
        f"{'(PLN)':>9} {'(PLN)':>9} {'(PLN)':>8} {'(yrs)':>8} "
        f"{'(%)':>8} {'(kWh)':>8} {'(kWh)':>8}"
    )
    print("-" * 110)

    best_savings = 0
    best_idx = 0

    for i, (scenario, sim) in enumerate(results):
        savings = baseline_cost - sim.annual_cost
        if savings > best_savings:
            best_savings = savings
            best_idx = i

    for i, (scenario, sim) in enumerate(results):
        savings = baseline_cost - sim.annual_cost
        payback = scenario.cost / savings if savings > 0 else float("inf")
        total_cons = sim.total_self_consumed + sim.total_imported
        self_cons_pct = (
            (sim.total_self_consumed / total_cons * 100) if total_cons > 0 else 0
        )

        marker = " *" if i == best_idx else "  "

        print(
            f"{scenario.pv_added_kwp:>6.1f}{marker}"
            f"{scenario.battery_added_kwh:>8.0f} "
            f"{scenario.total_pv_kwp:>8.1f} "
            f"{scenario.total_battery_kwh:>8.0f} "
            f"{scenario.cost:>9,.0f} "
            f"{sim.annual_cost:>9,.0f} "
            f"{savings:>8,.0f} "
            f"{payback:>8.1f} "
            f"{self_cons_pct:>7.0f}% "
            f"{sim.total_exported:>8,.0f} "
            f"{sim.total_pv_generated:>8,.0f}"
        )

    print("-" * 110)
    print("  * = Best annual savings")
    print()

    # Print optimal recommendation
    best_scenario, best_sim = results[best_idx]
    best_savings_val = baseline_cost - best_sim.annual_cost
    payback = (
        best_scenario.cost / best_savings_val if best_savings_val > 0 else float("inf")
    )

    print("  RECOMMENDATION:")
    print(
        f"    Add {best_scenario.pv_panels_added} panels ({best_scenario.pv_added_kwp:.1f} kWp SW-facing)"
        f" + {best_scenario.battery_added_kwh:.0f} kWh battery"
    )
    print(
        f"    Cost: {best_scenario.pv_panels_added * PV_PANEL_COST:,.0f}"
        f" + {int(best_scenario.battery_added_kwh / BATTERY_UNIT_KWH) * BATTERY_UNIT_COST:,.0f}"
        f" = {best_scenario.cost:,.0f} PLN"
    )
    print(f"    Expected annual savings: ~{best_savings_val:,.0f} PLN")
    print(f"    Payback period: ~{payback:.1f} years")
    print()

    # Savings breakdown
    print("  SAVINGS BREAKDOWN (optimal scenario):")
    print(f"    PV generated:         {best_sim.total_pv_generated:>8,.0f} kWh/year")
    print(f"    Self-consumed:        {best_sim.total_self_consumed:>8,.0f} kWh/year")
    print(f"    Exported to grid:     {best_sim.total_exported:>8,.0f} kWh/year")
    print(f"    Imported from grid:   {best_sim.total_imported:>8,.0f} kWh/year")
    print(f"    Import cost:          {best_sim.import_cost:>8,.0f} PLN/year")
    print(f"    Export revenue:       {best_sim.export_revenue:>8,.0f} PLN/year")
    print(f"    Arbitrage net:        {best_sim.arbitrage_profit:>8,.0f} PLN/year")
    print()

    # Also find best payback scenario
    best_payback = float("inf")
    best_pb_idx = 0
    for i, (scenario, sim) in enumerate(results):
        savings = baseline_cost - sim.annual_cost
        if savings > 0 and scenario.cost > 0:
            pb = scenario.cost / savings
            if pb < best_payback:
                best_payback = pb
                best_pb_idx = i

    if best_pb_idx != best_idx:
        pb_scenario, pb_sim = results[best_pb_idx]
        pb_savings = baseline_cost - pb_sim.annual_cost
        print("  FASTEST PAYBACK:")
        print(
            f"    {pb_scenario.pv_panels_added} panels ({pb_scenario.pv_added_kwp:.1f} kWp)"
            f" + {pb_scenario.battery_added_kwh:.0f} kWh battery"
        )
        print(
            f"    Payback: {best_payback:.1f} years (savings: {pb_savings:,.0f} PLN/year)"
        )
        print()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main():
    print("Loading data...")

    # Load CSV
    sensors = load_csv_sensors(CSV_PATH)
    print(f"  Loaded {sum(len(v) for v in sensors.values()):,} sensor readings")

    # Load tariff
    tariff = load_tariff(TARIFF_PATH)
    print(f"  Loaded tariff: {tariff['name']}")

    # Load TGE prices
    tge_prices = load_tge_prices(PRICES_DIR)
    print(f"  Loaded {len(tge_prices)} hourly TGE prices")

    # Build consumption profile
    print("\nBuilding consumption model...")
    hourly_cons = build_hourly_consumption(
        sensors.get("sensor.total_household_energy_consumption", [])
    )
    monthly_profiles = build_monthly_consumption_profile(hourly_cons)
    consumption_8760 = build_full_year_consumption(monthly_profiles)
    total_annual_cons = sum(consumption_8760)
    print(f"  Annual consumption estimate: {total_annual_cons:,.0f} kWh")
    for m in sorted(monthly_profiles.keys()):
        daily = sum(monthly_profiles[m])
        print(f"    Month {m:2d}: {daily:.1f} kWh/day avg")

    # Build price model
    print("\nBuilding price model...")
    buy_sensor = sensors.get("sensor.pge_tge_fixing_1_rate", [])
    sell_sensor = sensors.get("sensor.pstryk_sell_price", [])
    avg_buy, avg_sell, sell_buy_ratio = build_hourly_buy_sell_prices(
        tge_prices, buy_sensor, sell_sensor, tariff
    )
    buy_prices_8760, sell_prices_8760 = build_full_year_prices(
        avg_buy, sell_buy_ratio, tariff
    )
    avg_buy_price = sum(buy_prices_8760) / len(buy_prices_8760)
    avg_sell_price = sum(sell_prices_8760) / len(sell_prices_8760)
    print(f"  Avg buy price:  {avg_buy_price:.3f} PLN/kWh")
    print(f"  Avg sell price: {avg_sell_price:.3f} PLN/kWh")

    # Simulate baseline (no new investment)
    print("\nSimulating baseline (2.3 kWp + 15 kWh)...")
    baseline = simulate_year(
        EXISTING_PANELS,
        0,
        EXISTING_BATTERY_KWH,
        consumption_8760,
        buy_prices_8760,
        sell_prices_8760,
    )
    print(f"  Baseline annual cost: {baseline.annual_cost:,.0f} PLN")
    print(f"  Baseline PV generation: {baseline.total_pv_generated:,.0f} kWh")
    print(f"  Baseline self-consumption: {baseline.total_self_consumed:,.0f} kWh")
    print(f"  Baseline grid import: {baseline.total_imported:,.0f} kWh")
    print(f"  Baseline grid export: {baseline.total_exported:,.0f} kWh")

    # Generate and simulate scenarios
    print("\nGenerating scenarios...")
    scenarios = generate_scenarios(BUDGET)
    print(f"  Testing {len(scenarios)} scenarios...")

    results = []
    for i, scenario in enumerate(scenarios):
        sim = simulate_year(
            EXISTING_PANELS,
            scenario.pv_panels_added,
            scenario.total_battery_kwh,
            consumption_8760,
            buy_prices_8760,
            sell_prices_8760,
        )
        results.append((scenario, sim))
        savings = baseline.annual_cost - sim.annual_cost
        print(
            f"  [{i + 1}/{len(scenarios)}] +{scenario.pv_added_kwp:.1f}kWp "
            f"+{scenario.battery_added_kwh:.0f}kWh → "
            f"savings: {savings:,.0f} PLN/yr"
        )

    # Output
    print_results(results, baseline.annual_cost)


if __name__ == "__main__":
    main()
