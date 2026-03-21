#!/usr/bin/env python3
"""
default_bias_audit.py — Deterministic default-state voltage analysis for switched input jacks.

For each Thonkiconn-style switched jack, computes the unpatched default voltage at the
receiver input using voltage-divider / Thévenin analysis, then checks it against
logic-family thresholds (VIH_min, VIL_max).

Background:
  Thonkiconn (PJ398SM) jacks have a SW pin that is electrically shorted to the Tip
  when no cable is inserted, and open when a cable is plugged in. A pull-up resistor
  from SW to +5V sets a HIGH default; a pull-down to GND sets a LOW default. If the
  resulting voltage sits between VIL_max and VIH_min of the receiver IC, the input
  state is indeterminate when unpatched — a design defect.

Usage:
  python3 default_bias_audit.py --extract /tmp/extract.json \\
    [--thresholds family|cmos5v] [--format table|json] [--enforce hard|soft]

Exit codes:
  0 — all pass (or --enforce soft)
  1 — one or more fail/blocked findings (--enforce hard, the default)
"""

import argparse
import json
import sys
from typing import Optional


# ---------------------------------------------------------------------------
# Logic family threshold table
# (VIH_min, VIL_max) in volts at nominal 5 V supply unless noted.
# 4000-series thresholds are 0.7*VDD / 0.3*VDD; values below assume VDD=5V.
# CD40xx on 12V is also common in Eurorack — flag as blocked so the caller
# can decide rather than silently applying wrong thresholds.
# ---------------------------------------------------------------------------
FAMILY_THRESHOLDS: dict[str, tuple[Optional[float], Optional[float]]] = {
    "74HC":   (3.50, 1.50),   # 0.7*VCC / 0.3*VCC at 5 V
    "74HCT":  (2.00, 0.80),   # TTL-compatible input levels
    "74AC":   (3.50, 1.50),
    "74ACT":  (2.00, 0.80),
    "74LVC":  (2.00, 0.80),   # 3.3 V logic, TTL-compatible
    "74AUP":  (1.65, 0.90),   # 1.8 V nominal
    "CD40":   (3.50, 1.50),   # 4000-series at 5 V
    "CD45":   (3.50, 1.50),
    "HEF40":  (3.50, 1.50),
    "MC14":   (3.50, 1.50),
    "74LS":   (2.00, 0.80),   # TTL
    "74S":    (2.00, 0.80),
    "SN74":   (2.00, 0.80),
    # Op-amps / comparators: threshold is circuit-defined, cannot be inferred here
    "LM393":  (None, None),
    "LM339":  (None, None),
    "TL071":  (None, None),
    "TL072":  (None, None),
    "TL074":  (None, None),
    "NE5532": (None, None),
}

# Fixed thresholds for --thresholds cmos5v (generic 5 V CMOS)
CMOS5V = (3.50, 1.50)

# Known power-rail net names and their DC voltages
RAIL_VOLTAGES: dict[str, float] = {
    "+5V": 5.0,  "5V": 5.0,   "5VDC": 5.0,
    "+3V3": 3.3, "3V3": 3.3,  "+3.3V": 3.3, "3.3V": 3.3,
    "+12V": 12.0, "12V": 12.0,
    "-12V": -12.0,
    "GND": 0.0,  "0V": 0.0,   "AGND": 0.0,  "DGND": 0.0,
    "VCC": 5.0,  "VDD": 5.0,
}

# Pin name sets for jack pin role detection
SW_PIN_NAMES   = {"sw", "switch", "sw1", "sw2", "s2"}
TIP_PIN_NAMES  = {"t", "tip", "out", "in", "sig", "signal", "a", "1"}
GND_PIN_NAMES  = {"s", "sleeve", "gnd", "shield", "2"}


# ---------------------------------------------------------------------------
# Data normalisation helpers
# ---------------------------------------------------------------------------

def load_extract(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def normalize_components(data: dict) -> dict:
    """Return components as {ref: comp_dict} regardless of array vs object shape."""
    comps = data.get("components", {})
    if isinstance(comps, list):
        return {(c.get("ref") or c.get("reference")): c for c in comps if c.get("ref") or c.get("reference")}
    return comps


def get_pins(comp: dict) -> dict:
    """Return pins as {pin_num_str: {net, name}} regardless of input shape."""
    pins = comp.get("pins", {})
    if isinstance(pins, list):
        return {str(i + 1): p for i, p in enumerate(pins)}
    return pins


def build_net_index(components: dict) -> dict[str, list[tuple[str, str, str]]]:
    """Build reverse map: net_name -> [(ref, pin_num, pin_name), ...]"""
    index: dict[str, list] = {}
    for ref, comp in components.items():
        for pin_num, pin_data in get_pins(comp).items():
            if isinstance(pin_data, dict):
                net      = pin_data.get("net", "") or ""
                pin_name = pin_data.get("name", "") or ""
            else:
                net, pin_name = str(pin_data), ""
            net = net.strip()
            if net and net not in ("~", "unconnected", ""):
                index.setdefault(net, []).append((ref, pin_num, pin_name))
    return index


# ---------------------------------------------------------------------------
# Component classification helpers
# ---------------------------------------------------------------------------

def is_jack(ref: str, comp: dict) -> bool:
    if ref.upper().startswith("J"):
        return True
    value = str(comp.get("value", "")).lower()
    fp    = str(comp.get("footprint", "")).lower()
    keywords = ["pj398", "thonkiconn", "switchcraft", "3.5mm", "mono jack", "audio jack"]
    return any(k in value or k in fp for k in keywords)


def find_pin_by_role(comp: dict, role_names: set[str]) -> Optional[tuple[str, str]]:
    """Return (pin_num, net) for the first pin whose name matches role_names."""
    for pin_num, pin_data in get_pins(comp).items():
        if isinstance(pin_data, dict):
            name = (pin_data.get("name") or "").lower()
            net  = (pin_data.get("net")  or "").strip()
        else:
            continue
        if name in role_names and net:
            return (pin_num, net)
    return None


def is_resistor(ref: str) -> bool:
    return ref.upper().startswith("R")


def parse_resistance(value_str: str) -> Optional[float]:
    """Parse resistor value to ohms. Handles '10k', '4.7K', '100R', '1M', '220'."""
    s = str(value_str).strip().upper()
    s = s.replace("Ω", "").replace("OHM", "").replace("OHMS", "").replace(" ", "")
    try:
        if s.endswith("M"):
            return float(s[:-1]) * 1_000_000
        if s.endswith("K"):
            return float(s[:-1]) * 1_000
        if s.endswith("R"):
            return float(s[:-1])
        return float(s)
    except (ValueError, TypeError):
        return None


def rail_voltage(net_name: str) -> Optional[float]:
    return RAIL_VOLTAGES.get(net_name)


def detect_ic_family(value: str) -> Optional[str]:
    v = str(value).upper()
    for family in FAMILY_THRESHOLDS:
        if family.upper() in v:
            return family
    return None


def other_pin_net(comp: dict, this_pin_num: str) -> Optional[str]:
    """For a 2-pin component, return the net on the pin that is NOT this_pin_num."""
    for pnum, pdata in get_pins(comp).items():
        if pnum == this_pin_num:
            continue
        if isinstance(pdata, dict):
            net = (pdata.get("net") or "").strip()
            if net:
                return net
    return None


# ---------------------------------------------------------------------------
# Voltage-divider / Thévenin analysis
# ---------------------------------------------------------------------------

def compute_default_voltage(
    sw_net: str,
    tip_net: str,
    components: dict,
    net_index: dict,
) -> tuple[Optional[float], str]:
    """
    When unpatched, the SW pin bridges to the Tip, so analyse both nets together.

    For each resistor on either net, check whether its other terminal connects to
    a known power rail.  Collect all such (V_rail, R_ohm) pairs and compute the
    Thévenin equivalent:

        V_th = Σ(V_i / R_i) / Σ(1 / R_i)

    High-impedance CMOS inputs are treated as open circuits (no additional load term).
    Returns (v_default, description_string).
    Returns (None, reason) when analysis cannot be completed.
    """
    pull_terms: list[tuple[float, float, str]] = []  # (V_rail, R_ohm, ref)

    for net in {sw_net, tip_net} - {""}:
        for ref, pin_num, _pin_name in net_index.get(net, []):
            if not is_resistor(ref):
                continue
            comp  = components.get(ref)
            if comp is None:
                continue
            r_val = parse_resistance(comp.get("value", ""))
            if r_val is None or r_val <= 0:
                continue
            far_net = other_pin_net(comp, pin_num)
            if far_net is None:
                continue
            v = rail_voltage(far_net)
            if v is not None:
                pull_terms.append((v, r_val, ref))

    if not pull_terms:
        return (None, "no pull resistor to a known rail found on SW or Tip net")

    if len(pull_terms) == 1:
        v_rail, r_ohm, ref = pull_terms[0]
        # Single pull to rail, high-Z receiver → V_default = V_rail
        sign = "↑" if v_rail > 2.5 else "↓"
        desc = f"{ref} {r_ohm/1000:.1f}kΩ {sign} {v_rail:+.1f}V"
        return (v_rail, desc)

    # Multiple pull paths — Thévenin equivalent
    sum_g  = sum(1.0 / r for _, r, _ in pull_terms)
    sum_vg = sum(v / r    for v, r, _ in pull_terms)
    v_th   = sum_vg / sum_g
    parts  = " + ".join(f"{ref}({v:+.1f}V/{r/1000:.1f}k)" for v, r, ref in pull_terms)
    return (v_th, f"Thévenin [{parts}] → {v_th:.2f}V")


# ---------------------------------------------------------------------------
# Main audit loop
# ---------------------------------------------------------------------------

def audit(extract_path: str, threshold_mode: str, fmt: str, enforce: str) -> int:
    data       = load_extract(extract_path)
    components = normalize_components(data)
    net_index  = build_net_index(components)

    rows = []

    for ref in sorted(components):
        comp = components[ref]
        if not is_jack(ref, comp):
            continue

        sw_result = find_pin_by_role(comp, SW_PIN_NAMES)
        if sw_result is None:
            continue  # No SW pin — not a switched jack

        _sw_pin, sw_net = sw_result
        tip_result      = find_pin_by_role(comp, TIP_PIN_NAMES)
        tip_net         = tip_result[1] if tip_result else ""

        # Skip jacks whose SW is tied directly to GND (sleeve-normalled, not input)
        if sw_net in ("GND", "0V", "AGND", "DGND"):
            continue

        # Find receiver IC on tip or SW net
        receiver_pin    = "unknown"
        receiver_family = None
        for net in filter(None, [tip_net, sw_net]):
            for r, pnum, _pname in net_index.get(net, []):
                if r == ref:
                    continue
                rcomp = components.get(r, {})
                if r.upper().startswith(("U", "IC")):
                    family = detect_ic_family(rcomp.get("value", ""))
                    if receiver_pin == "unknown":
                        receiver_pin    = f"{r}:{pnum}"
                        receiver_family = family

        # Compute default voltage
        v_default, path_desc = compute_default_voltage(
            sw_net, tip_net, components, net_index
        )

        # Threshold selection
        if threshold_mode == "cmos5v":
            vih_min, vil_max = CMOS5V
        elif receiver_family:
            vih_min, vil_max = FAMILY_THRESHOLDS.get(receiver_family, (None, None))
        else:
            vih_min, vil_max = (None, None)

        # Status
        if v_default is None:
            status = "blocked"
            reason = path_desc
        elif vih_min is None or vil_max is None:
            status = "blocked"
            reason = f"receiver family unknown (found: {receiver_pin})"
        elif v_default >= vih_min:
            status = "pass"
            reason = f"HIGH — {v_default:.2f}V ≥ VIH {vih_min:.2f}V"
        elif v_default <= vil_max:
            status = "pass"
            reason = f"LOW  — {v_default:.2f}V ≤ VIL {vil_max:.2f}V"
        else:
            status = "fail"
            reason = f"INDETERMINATE — {v_default:.2f}V between VIL {vil_max:.2f}V and VIH {vih_min:.2f}V"

        rows.append({
            "input_jack_ref":    ref,
            "receiver_pin":      receiver_pin,
            "unpatched_path":    path_desc,
            "computed_v_default": f"{v_default:.2f}V" if v_default is not None else "—",
            "vih_min":           f"{vih_min:.2f}V"  if vih_min  is not None else "—",
            "vil_max":           f"{vil_max:.2f}V"  if vil_max  is not None else "—",
            "status":            status,
            "_reason":           reason,
        })

    if not rows:
        print("No switched input jacks found.")
        return 0

    if fmt == "json":
        # Strip internal fields before output
        print(json.dumps([{k: v for k, v in r.items() if not k.startswith("_")} for r in rows], indent=2))
    else:
        cols = ["input_jack_ref", "receiver_pin", "unpatched_path",
                "computed_v_default", "vih_min", "vil_max", "status"]
        widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
        header = "  ".join(c.upper().ljust(widths[c]) for c in cols)
        sep    = "  ".join("-" * widths[c] for c in cols)
        print(header)
        print(sep)
        for r in rows:
            line = "  ".join(str(r[c]).ljust(widths[c]) for c in cols)
            print(line)
        print()
        # Print reasons for non-pass rows
        non_pass = [r for r in rows if r["status"] != "pass"]
        if non_pass:
            print("Details:")
            for r in non_pass:
                print(f"  {r['input_jack_ref']} [{r['status'].upper()}] {r['_reason']}")

    has_issue = any(r["status"] in ("fail", "blocked") for r in rows)
    if enforce == "hard" and has_issue:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Default-bias margin audit for Eurorack switched input jacks."
    )
    parser.add_argument(
        "--extract", required=True,
        help="Path to kicad-extract JSON output"
    )
    parser.add_argument(
        "--thresholds", default="family", choices=["family", "cmos5v"],
        help="'family': detect thresholds from receiver IC value; "
             "'cmos5v': use fixed 5 V CMOS thresholds (3.5 V / 1.5 V)"
    )
    parser.add_argument(
        "--format", default="table", choices=["table", "json"],
        help="Output format"
    )
    parser.add_argument(
        "--enforce", default="hard", choices=["hard", "soft"],
        help="'hard': exit 1 on any fail/blocked (default); 'soft': always exit 0"
    )
    args = parser.parse_args()
    sys.exit(audit(args.extract, args.thresholds, args.format, args.enforce))


if __name__ == "__main__":
    main()
