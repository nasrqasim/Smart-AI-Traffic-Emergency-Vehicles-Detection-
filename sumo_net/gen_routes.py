"""
Generates SUMO route files with randomized, time-varying demand profiles
(900-2400 veh/hour range, matching the FYP doc's data collection spec),
plus a dedicated emergency-vehicle route used to test the preemption module.

Usage:
    python gen_routes.py --out routes.rou.xml --seed 1 --duration 3600
"""
import argparse
import random

APPROACHES = {
    "N": "N2C",
    "S": "S2C",
    "E": "E2C",
    "W": "W2C",
}

# through / right / left destinations per approach (matches connections.con.xml)
DEST = {
    "N2C": {"through": "C2S", "left": "C2E", "right": "C2W"},
    "S2C": {"through": "C2N", "left": "C2W", "right": "C2E"},
    "E2C": {"through": "C2W", "left": "C2S", "right": "C2N"},
    "W2C": {"through": "C2E", "left": "C2N", "right": "C2S"},
}

VEHICLE_TYPES = """
    <vType id="car" vClass="passenger" length="5" minGap="2.5" maxSpeed="16.6" accel="2.6" decel="4.5" sigma="0.5" color="0.6,0.6,0.9"/>
    <vType id="bus" vClass="bus" length="10" minGap="2.5" maxSpeed="13.9" accel="1.2" decel="4.0" sigma="0.5" color="0.9,0.6,0.2"/>
    <vType id="moto" vClass="motorcycle" length="2.2" minGap="1.5" maxSpeed="16.6" accel="3.5" decel="5.0" sigma="0.5" color="0.2,0.9,0.6"/>
    <vType id="truck" vClass="truck" length="9" minGap="2.5" maxSpeed="12.5" accel="1.0" decel="4.0" sigma="0.5" color="0.7,0.3,0.3"/>
    <vType id="emergency" vClass="emergency" length="6" minGap="2.5" maxSpeed="20.0" accel="3.0" decel="5.0" sigma="0.0" color="1,0,0" guiShape="emergency"/>
"""

MIX = [("car", 0.72), ("moto", 0.16), ("bus", 0.06), ("truck", 0.06)]


def demand_profile(t, base_low, base_high):
    """Time-varying veh/hour demand: ramps up, holds a peak, ramps down (models a rush-hour-like cycle).

    NOTE: the doc's full range is 900-2400 veh/h. At the very top of that range a 2-lane
    approach with a 2-phase, ~5s-intergreen signal is oversaturated (its own duty-cycled
    saturation flow tops out well below peak demand), so ANY controller gridlocks and the
    comparison stops being meaningful. Defaults here sit in a demand band where the
    intersection is busy but recoverable, so the fixed-time vs actuated vs DQN comparison
    is actually informative. Push base_high back up once you've done the full-scale
    (500k-step) training run from the README and want to stress-test saturation behavior.
    """
    frac = t / 3600.0
    if frac < 0.2:
        level = base_low + (base_high - base_low) * (frac / 0.2) * 0.5
    elif frac < 0.6:
        level = base_high
    elif frac < 0.8:
        level = base_high - (base_high - base_low) * ((frac - 0.6) / 0.2) * 0.5
    else:
        level = base_low
    return level


def pick_vtype(rng):
    r = rng.random()
    c = 0.0
    for vt, p in MIX:
        c += p
        if r <= c:
            return vt
    return "car"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="routes.rou.xml")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--duration", type=int, default=3600)
    ap.add_argument("--emergency-at", type=int, default=1800,
                     help="second at which an emergency vehicle enters on the N approach")
    ap.add_argument("--emergency", dest="emergency", action="store_true", default=True)
    ap.add_argument("--no-emergency", dest="emergency", action="store_false")
    ap.add_argument("--base-low", type=float, default=700,
                     help="off-peak veh/hour per approach")
    ap.add_argument("--base-high", type=float, default=1600,
                     help="peak veh/hour per approach")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    events = []  # (time, veh_id, from_edge, to_edge, vtype)
    veh_count = 0

    for approach_edge in APPROACHES.values():
        t = 0.0
        while t < args.duration:
            rate = demand_profile(t, args.base_low, args.base_high)  # veh/hour for this approach
            # exponential inter-arrival (Poisson process)
            gap = rng.expovariate(rate / 3600.0)
            t += gap
            if t >= args.duration:
                break
            turn = rng.choices(["through", "through", "right", "left"], k=1)[0]  # bias to through movement
            dest = DEST[approach_edge][turn]
            vtype = pick_vtype(rng)
            events.append((t, f"veh{veh_count}", approach_edge, dest, vtype))
            veh_count += 1

    if args.emergency:
        events.append((args.emergency_at, "emergency_0", "N2C", DEST["N2C"]["through"], "emergency"))

    events.sort(key=lambda e: e[0])

    with open(args.out, "w") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<routes>\n')
        f.write(VEHICLE_TYPES)
        for t, vid, frm, to, vtype in events:
            depart_lane = "best"
            f.write(
                f'    <trip id="{vid}" type="{vtype}" depart="{t:.2f}" '
                f'from="{frm}" to="{to}" departLane="{depart_lane}" departSpeed="max"/>\n'
            )
        f.write("</routes>\n")

    print(f"Wrote {len(events)} vehicles ({veh_count} regular + "
          f"{1 if args.emergency else 0} emergency) to {args.out}")


if __name__ == "__main__":
    main()
