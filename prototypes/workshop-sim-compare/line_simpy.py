"""
line_simpy.py
=============
The SAME three-station production line as ../salabim_demo/line_salabim.py, but here
the simulation engine is SimPy and EVERY pixel of the animation is drawn by hand with
matplotlib. There is no built-in animation: we run the model, record a timeline of
state snapshots, then render each snapshot into a frame and stitch the frames into a
GIF with Pillow. This is the "draw-it-all-yourself" counterpart to salabim's native
animation.

Scenario (identical to the salabim demo)
----------------------------------------
Parts arrive (exponential interarrival, mean ~4) and flow through:
    ARRIVAL  ->  MACHINING (2 CNC machines)  ->  ASSEMBLY (1)  ->  INSPECTION (1)
At t=18 one CNC machine breaks down (shown red, "DOWN") and is repaired 10 units
later. The breakdown is modeled with a SimPy PreemptiveResource: the repair process
seizes one of the two machine slots at high priority, so only one CNC remains usable
during the repair.

Rendering
---------
matplotlib runs on the Agg backend (no display needed). Each frame is a figure drawn
from one timeline snapshot; frames are converted to Pillow images and saved as an
animated GIF (save_all + append_images + per-frame duration + loop=0).
"""

import io
import random

import matplotlib
matplotlib.use("Agg")                 # headless backend, no display required
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyArrow
import simpy
from PIL import Image

random.seed(7)                        # reproducible run

# ----------------------------------------------------------------------------
# Scenario parameters (match the salabim demo)
# ----------------------------------------------------------------------------
MEAN_INTERARRIVAL = 4.0
FAIL_AT = 18.0
REPAIR_TIME = 10.0
HORIZON = 36.0
DT = 0.2                               # snapshot interval -> HORIZON/DT frames

# Colors (match the salabim demo)
C_IDLE = "#4caf50"
C_BUSY = "#ff9800"
C_DOWN = "#e53935"
C_ZONE = "#eceff1"
C_PART = "#1e88e5"

# ----------------------------------------------------------------------------
# Live simulation state. The Part / failure processes mutate these; the recorder
# process samples them into `timeline` every DT units.
# ----------------------------------------------------------------------------
live = {
    "mach_wait": [], "mach_serve": [],
    "asm_wait": [], "asm_serve": [],
    "insp_wait": [], "insp_serve": [],
    "arrived": 0, "completed": 0, "cnc_down": False,
}
timeline = []


def _add(key, pid):
    live[key].append(pid)


def _remove(key, pid):
    if pid in live[key]:
        live[key].remove(pid)


# ----------------------------------------------------------------------------
# One Part flowing through the three stations.
# ----------------------------------------------------------------------------
def part_process(env, pid, machining, assembly, inspection):
    # ---- MACHINING (2 CNC, may be preempted by a breakdown) ----
    remaining = random.uniform(5, 7)          # ~6 units of machining work
    _add("mach_wait", pid)
    while remaining > 1e-9:
        # priority 0 = normal (the repair uses priority -1 so it outranks us)
        with machining.request(priority=0) as req:
            yield req
            _remove("mach_wait", pid)
            _add("mach_serve", pid)
            start = env.now
            try:
                yield env.timeout(remaining)
                remaining = 0.0               # finished machining
            except simpy.Interrupt:
                # A breakdown preempted this machine: save the work left and
                # loop back to grab the still-working machine (or wait for it).
                remaining -= env.now - start
                _remove("mach_serve", pid)
                _add("mach_wait", pid)
    _remove("mach_serve", pid)

    # ---- ASSEMBLY (single assembler) ----
    _add("asm_wait", pid)
    with assembly.request() as req:
        yield req
        _remove("asm_wait", pid)
        _add("asm_serve", pid)
        yield env.timeout(max(0.5, random.normalvariate(5, 0.6)))   # ~5 units
    _remove("asm_serve", pid)

    # ---- INSPECTION (single inspector) ----
    _add("insp_wait", pid)
    with inspection.request() as req:
        yield req
        _remove("insp_wait", pid)
        _add("insp_serve", pid)
        yield env.timeout(random.uniform(2.5, 3.5))                 # ~3 units
    _remove("insp_serve", pid)

    live["completed"] += 1                    # part leaves the line


# ----------------------------------------------------------------------------
# Source: keeps generating parts until the horizon.
# ----------------------------------------------------------------------------
def source(env, machining, assembly, inspection):
    pid = 0
    while env.now < HORIZON:
        pid += 1
        live["arrived"] += 1
        env.process(part_process(env, pid, machining, assembly, inspection))
        yield env.timeout(random.expovariate(1.0 / MEAN_INTERARRIVAL))


# ----------------------------------------------------------------------------
# Breakdown + repair: seize one machine slot at high priority (preempt) so only
# one CNC is usable during the repair, then release it.
# ----------------------------------------------------------------------------
def breakdown(env, machining):
    yield env.timeout(FAIL_AT)
    live["cnc_down"] = True
    with machining.request(priority=-1, preempt=True) as req:
        yield req                             # occupy one machine as "broken"
        yield env.timeout(REPAIR_TIME)
    live["cnc_down"] = False                  # machine back online


# ----------------------------------------------------------------------------
# Recorder: snapshot the live state every DT units into `timeline`.
# ----------------------------------------------------------------------------
def recorder(env):
    while True:
        timeline.append({
            "t": env.now,
            "mach_wait": list(live["mach_wait"]),
            "mach_serve": list(live["mach_serve"]),
            "asm_wait": list(live["asm_wait"]),
            "asm_serve": list(live["asm_serve"]),
            "insp_wait": list(live["insp_wait"]),
            "insp_serve": list(live["insp_serve"]),
            "arrived": live["arrived"],
            "completed": live["completed"],
            "cnc_down": live["cnc_down"],
        })
        yield env.timeout(DT)


# ----------------------------------------------------------------------------
# Run the simulation and collect the timeline.
# ----------------------------------------------------------------------------
def run_simulation():
    env = simpy.Environment()
    machining = simpy.PreemptiveResource(env, capacity=2)
    assembly = simpy.Resource(env, capacity=1)
    inspection = simpy.Resource(env, capacity=1)

    env.process(source(env, machining, assembly, inspection))
    env.process(breakdown(env, machining))
    env.process(recorder(env))
    env.run(until=HORIZON)
    return timeline


# ----------------------------------------------------------------------------
# Draw one frame from a snapshot. Returns a PIL image.
# ----------------------------------------------------------------------------
# Static zone geometry in axis coordinates (0..960 x 0..540 to mirror salabim).
ZONES = [
    (20, 150, 160, 280, "ARRIVAL"),
    (210, 150, 260, 280, "MACHINING (2 CNC)"),
    (500, 150, 180, 280, "ASSEMBLY"),
    (710, 150, 190, 280, "INSPECTION"),
]


def _dots(ax, pids, x, y0, dy, cols=1, colgap=26):
    """Draw a vertical (optionally multi-column) stack of numbered part dots."""
    for i, pid in enumerate(pids[:16]):       # cap drawn dots so it stays tidy
        col = i // 8
        row = i % 8
        cx = x + col * colgap
        cy = y0 + row * dy
        ax.add_patch(Circle((cx, cy), 9, facecolor=C_PART, edgecolor="white", lw=1, zorder=5))
        ax.text(cx, cy, str(pid), ha="center", va="center", color="white",
                fontsize=7, zorder=6)


def render_frame(snap):
    fig = plt.figure(figsize=(9.6, 5.4), dpi=100)   # -> 960x540 px
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 960)
    ax.set_ylim(0, 540)
    ax.axis("off")
    fig.patch.set_facecolor("#fafafa")

    # Title
    ax.text(480, 512, "SimPy + matplotlib (hand-drawn)  -  3-Station Production Line",
            ha="center", va="center", fontsize=16, color="#263238")

    # Zone panels + labels
    for zx, zy, zw, zh, label in ZONES:
        ax.add_patch(Rectangle((zx, zy), zw, zh, facecolor=C_ZONE,
                               edgecolor="#b0bec5", lw=2, zorder=1))
        ax.text(zx + zw / 2, zy + zh - 12, label, ha="center", va="top",
                fontsize=11, color="#37474f", zorder=2)

    # Flow arrows between zones
    for ax0 in (170, 475, 695):
        ax.add_patch(FancyArrow(ax0, 290, 28, 0, width=2, head_width=10,
                                head_length=8, facecolor="#90a4ae",
                                edgecolor="#90a4ae", zorder=2))

    n_serve = len(snap["mach_serve"])
    down = snap["cnc_down"]

    # --- Two CNC machine rectangles ---
    # CNC-1 (top): busy if at least one part is machining.
    c0 = C_BUSY if n_serve >= 1 else C_IDLE
    s0 = "BUSY" if n_serve >= 1 else "IDLE"
    ax.add_patch(Rectangle((300, 215), 150, 55, facecolor=c0, edgecolor="#455a64", lw=2, zorder=3))
    ax.text(375, 242, f"CNC-1  {s0}", ha="center", va="center", color="white", fontsize=11, zorder=4)
    # CNC-2 (bottom): the machine that breaks down.
    if down:
        c1, s1 = C_DOWN, "DOWN"
    elif n_serve >= 2:
        c1, s1 = C_BUSY, "BUSY"
    else:
        c1, s1 = C_IDLE, "IDLE"
    ax.add_patch(Rectangle((300, 155), 150, 55, facecolor=c1, edgecolor="#455a64", lw=2, zorder=3))
    ax.text(375, 182, f"CNC-2  {s1}", ha="center", va="center", color="white", fontsize=11, zorder=4)

    # --- Assembly machine ---
    ca = C_BUSY if snap["asm_serve"] else C_IDLE
    ax.add_patch(Rectangle((560, 185), 100, 55, facecolor=ca, edgecolor="#455a64", lw=2, zorder=3))
    ax.text(610, 212, "ASM\n" + ("BUSY" if snap["asm_serve"] else "IDLE"),
            ha="center", va="center", color="white", fontsize=10, zorder=4)

    # --- Inspection machine ---
    ci = C_BUSY if snap["insp_serve"] else C_IDLE
    ax.add_patch(Rectangle((770, 185), 110, 55, facecolor=ci, edgecolor="#455a64", lw=2, zorder=3))
    ax.text(825, 212, "INSP\n" + ("BUSY" if snap["insp_serve"] else "IDLE"),
            ha="center", va="center", color="white", fontsize=10, zorder=4)

    # --- Queued parts (waiting lines), drawn as numbered dots ---
    ax.text(235, 300, "queue", ha="center", fontsize=9, color="#607d8b")
    _dots(ax, snap["mach_wait"], 235, 170, 20)
    _dots(ax, snap["asm_wait"], 525, 170, 20)
    _dots(ax, snap["insp_wait"], 735, 170, 20)
    # Parts currently being machined, shown as small dots on the machines
    for i, pid in enumerate(snap["mach_serve"][:2]):
        ax.add_patch(Circle((280, 242 - i * 60), 9, facecolor=C_PART, edgecolor="white", lw=1, zorder=6))
        ax.text(280, 242 - i * 60, str(pid), ha="center", va="center", color="white", fontsize=7, zorder=7)

    # --- Clock + live counters ---
    ax.text(30, 470, f"Clock  t = {snap['t']:6.1f} / {HORIZON:.0f}",
            fontsize=16, color="#263238")
    wip = snap["arrived"] - snap["completed"]
    ax.text(620, 470, f"Arrived:   {snap['arrived']}", fontsize=13, color="#1565c0")
    ax.text(620, 450, f"Completed: {snap['completed']}", fontsize=13, color="#2e7d32")
    ax.text(620, 430, f"WIP:       {wip}", fontsize=13, color="#ef6c00")

    # --- Legend ---
    for lx, col, lab in [(30, C_IDLE, "idle"), (110, C_BUSY, "busy"), (190, C_DOWN, "down")]:
        ax.add_patch(Rectangle((lx, 120), 20, 15, facecolor=col, zorder=3))
        ax.text(lx + 25, 127, lab, va="center", fontsize=10, color="#37474f")

    # Rasterize the figure into a PIL image via a PNG buffer.
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


# ----------------------------------------------------------------------------
# Main: simulate, render every snapshot, assemble the GIF.
# ----------------------------------------------------------------------------
def main():
    snaps = run_simulation()
    print(f"simulated {len(snaps)} snapshots; "
          f"arrived={snaps[-1]['arrived']} completed={snaps[-1]['completed']}")

    frames = [render_frame(s) for s in snaps]
    # Quantize to a palette to keep the GIF small (flat colors compress well).
    pal_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=64) for f in frames]

    pal_frames[0].save(
        "line_simpy.gif",
        save_all=True,
        append_images=pal_frames[1:],
        duration=125,          # ms per frame (~8 fps, matches the salabim demo)
        loop=0,
        optimize=True,
        disposal=2,
    )
    print("wrote line_simpy.gif")


if __name__ == "__main__":
    main()
