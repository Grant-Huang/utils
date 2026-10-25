"""
line_salabim.py
===============
Three-station production line, rendered with salabim's NATIVE animation engine.

The exact same scenario is also implemented in ../simpy_demo/line_simpy.py using
SimPy + hand-drawn matplotlib frames, so the two GIFs can be compared side by side:
"native animation" (this file) vs. "draw-it-all-yourself" (the SimPy one).

Scenario
--------
Parts arrive (exponential interarrival, mean ~4) and flow through:
    ARRIVAL  ->  MACHINING (2 CNC machines)  ->  ASSEMBLY (1)  ->  INSPECTION (1)
Each station has a queue in front of it while its resource is busy.
At t=25 one CNC machine breaks down (turns red, "DOWN") and is repaired 15 units
later, after which it comes back online.

salabim specifics worth noting
-------------------------------
* salabim 26 defaults to the "yieldless" component style (uses greenlet under the
  hood), so process() methods call self.hold(...) / self.request(...) directly with
  NO `yield`. We follow that style here.
* Even for a HEADLESS video export, salabim builds a Tk root and imports PIL.ImageTk,
  so the script must run with a display (xvfb-run) and needs python3-tk + a Pillow
  that ships ImageTk. Run it as:  xvfb-run -a python3.12 line_salabim.py
* fps must be set (via animation_parameters) BEFORE env.video(...) is called.
* We animate resource.requesters() queues with the built-in AnimateQueue, and give
  each Part a custom animation_objects(self, id) so queued parts show up as little
  numbered circles -- the native salabim look.
"""

import salabim as sim

# ----------------------------------------------------------------------------
# Global, mutable simulation state that the animation reads every frame.
# (salabim dynamic attributes are callables taking the animation time `t`.)
# ----------------------------------------------------------------------------
stats = {"completed": 0, "arrived": 0}
cnc_down = [False]          # True while the 2nd CNC machine is broken down
FAIL_AT = 18.0             # sim time at which one CNC fails
REPAIR_TIME = 10.0         # how long the repair takes (recovers at t=28, before end)
HORIZON = 36.0             # total simulated time units

# Colors reused throughout
C_IDLE = "#4caf50"         # green  -> machine idle/available
C_BUSY = "#ff9800"         # orange -> machine busy / processing
C_DOWN = "#e53935"         # red    -> machine broken down
C_ZONE = "#eceff1"         # light panel background for each zone


# ----------------------------------------------------------------------------
# Component: a Part flowing through the three stations.
# ----------------------------------------------------------------------------
class Part(sim.Component):
    def animation_objects(self, id):
        """Native salabim hook: how this component is drawn inside an AnimateQueue.

        Must return (dimx, dimy, *animation_objects); dimx/dimy set the spacing
        used by AnimateQueue. We draw a small numbered circle per queued part.
        """
        d = 22
        circle = sim.AnimateCircle(
            radius=9,
            fillcolor="#1e88e5",
            linecolor="white",
            linewidth=1,
            text=str(self.sequence_number()),
            textcolor="white",
            fontsize=9,
        )
        return (d, d, circle)

    def process(self):
        # --- MACHINING: 2 CNC machines (capacity 2) ---
        self.request(machining)                 # waits in machining.requesters()
        self.hold(sim.Uniform(5, 7).sample())   # ~6 units, while in claimers()
        self.release(machining)

        # --- ASSEMBLY: single assembler ---
        self.request(assembly)
        self.hold(sim.Normal(5, 0.6).sample())  # ~5 units
        self.release(assembly)

        # --- INSPECTION: single inspector ---
        self.request(inspection)
        self.hold(sim.Uniform(2.5, 3.5).sample())  # ~3 units
        self.release(inspection)

        stats["completed"] += 1                 # a finished part leaves the line


# ----------------------------------------------------------------------------
# Component: the source that keeps creating Parts.
# ----------------------------------------------------------------------------
class PartGenerator(sim.Component):
    def process(self):
        while env.now() < HORIZON:
            Part()
            stats["arrived"] += 1
            self.hold(sim.Exponential(4).sample())  # mean interarrival ~4


# ----------------------------------------------------------------------------
# Component: the single CNC breakdown + repair event.
# Modeled by shrinking the machining resource's capacity from 2 to 1 (the broken
# machine can no longer accept work) and restoring it after the repair.
# ----------------------------------------------------------------------------
class CNCFailure(sim.Component):
    def process(self):
        self.hold(FAIL_AT)             # run normally until t = FAIL_AT
        cnc_down[0] = True
        machining.set_capacity(1)      # only 1 CNC usable during the breakdown
        self.hold(REPAIR_TIME)         # repair period
        cnc_down[0] = False
        machining.set_capacity(2)      # machine comes back online


# ----------------------------------------------------------------------------
# Helper: color for each of the two CNC machine rectangles, read every frame.
# claimed_quantity() = how many machines are currently processing a part.
# ----------------------------------------------------------------------------
def cnc_color(index):
    def _f(t):
        claimed = machining.claimed_quantity()
        if index == 1 and cnc_down[0]:
            return C_DOWN                 # the 2nd machine is the one that breaks
        if claimed >= index + 1:
            return C_BUSY
        return C_IDLE
    return _f


def cnc_label(index):
    def _f(t):
        if index == 1 and cnc_down[0]:
            return f"CNC-{index + 1}\nDOWN"
        claimed = machining.claimed_quantity()
        return f"CNC-{index + 1}\n" + ("BUSY" if claimed >= index + 1 else "IDLE")
    return _f


def single_machine_color(resource):
    """Color for the single-machine stations (assembly / inspection)."""
    def _f(t):
        return C_BUSY if resource.claimed_quantity() >= 1 else C_IDLE
    return _f


# ----------------------------------------------------------------------------
# Build the model.
# ----------------------------------------------------------------------------
env = sim.Environment()     # yieldless style is the salabim-26 default

machining = sim.Resource("machining", capacity=2)
assembly = sim.Resource("assembly", capacity=1)
inspection = sim.Resource("inspection", capacity=1)

# --- Animation canvas. fps MUST be set before env.video(). ---
env.animation_parameters(
    animate=True,
    synced=False,          # render as fast as possible (we are exporting a video)
    width=960,
    height=540,
    x0=0, y0=0, x1=960,    # 1 user-unit == 1 pixel
    background_color="#fafafa",
    fps=8,                 # 8 fps -> HORIZON*fps = 288 frames (keeps GIF < 5 MB)
    show_fps=False,
    show_menu_buttons=False,
    title="",
)

# ---- Static scenery: title, zone panels, labels ----
sim.AnimateText(
    text="salabim (native animation)  -  3-Station Production Line",
    x=480, y=512, text_anchor="n", fontsize=20, textcolor="#263238",
)

# Zone background panels: (x0, y0, x1, y1, label)
zones = [
    (20, 150, 180, 430, "ARRIVAL"),
    (210, 150, 470, 430, "MACHINING (2 CNC)"),
    (500, 150, 680, 430, "ASSEMBLY"),
    (710, 150, 900, 430, "INSPECTION"),
]
for zx0, zy0, zx1, zy1, label in zones:
    sim.AnimateRectangle(
        spec=(zx0, zy0, zx1, zy1),
        fillcolor=C_ZONE, linecolor="#b0bec5", linewidth=2,
        text=label, text_anchor="n", text_offsety=-10,
        fontsize=14, textcolor="#37474f",
    )

# Flow arrows between zones
for ax in (180, 470, 680):
    sim.AnimateLine(spec=(ax, 290, ax + 30, 290), linecolor="#90a4ae", linewidth=3)

# ---- Machine rectangles ----
# Two CNC machines inside the machining zone
sim.AnimateRectangle(spec=(300, 330, 450, 390), fillcolor=cnc_color(0),
                     linecolor="#455a64", linewidth=2, text=cnc_label(0),
                     fontsize=12, textcolor="white")
sim.AnimateRectangle(spec=(300, 250, 450, 310), fillcolor=cnc_color(1),
                     linecolor="#455a64", linewidth=2, text=cnc_label(1),
                     fontsize=12, textcolor="white")
# Single assembler
sim.AnimateRectangle(spec=(560, 300, 660, 360), fillcolor=single_machine_color(assembly),
                     linecolor="#455a64", linewidth=2,
                     text=lambda t: "ASM\n" + ("BUSY" if assembly.claimed_quantity() else "IDLE"),
                     fontsize=12, textcolor="white")
# Single inspector
sim.AnimateRectangle(spec=(770, 300, 880, 360), fillcolor=single_machine_color(inspection),
                     linecolor="#455a64", linewidth=2,
                     text=lambda t: "INSP\n" + ("BUSY" if inspection.claimed_quantity() else "IDLE"),
                     fontsize=12, textcolor="white")

# ---- Queues: animate each resource's waiting line (requesters) natively ----
# direction="n" stacks waiting parts upward from the given (x, y) anchor.
sim.AnimateText(text="queue", x=250, y=205, fontsize=10, textcolor="#607d8b", text_anchor="n")
sim.AnimateQueue(machining.requesters(), x=250, y=170, direction="n", title="")
sim.AnimateQueue(assembly.requesters(), x=525, y=170, direction="n", title="")
sim.AnimateQueue(inspection.requesters(), x=735, y=170, direction="n", title="")

# ---- Live clock + counters (dynamic text read every frame) ----
sim.AnimateText(text=lambda t: f"Clock  t = {t:6.1f} / {HORIZON:.0f}",
                x=30, y=470, fontsize=18, textcolor="#263238")
sim.AnimateText(text=lambda t: f"Arrived:   {stats['arrived']}",
                x=620, y=468, fontsize=15, textcolor="#1565c0")
sim.AnimateText(text=lambda t: f"Completed: {stats['completed']}",
                x=620, y=448, fontsize=15, textcolor="#2e7d32")
# WIP = parts that have arrived but not yet completed
sim.AnimateText(text=lambda t: f"WIP:       {stats['arrived'] - stats['completed']}",
                x=620, y=428, fontsize=15, textcolor="#ef6c00")

# Legend
sim.AnimateRectangle(spec=(30, 120, 50, 135), fillcolor=C_IDLE)
sim.AnimateText(text="idle", x=55, y=127, fontsize=11, text_anchor="w", textcolor="#37474f")
sim.AnimateRectangle(spec=(110, 120, 130, 135), fillcolor=C_BUSY)
sim.AnimateText(text="busy", x=135, y=127, fontsize=11, text_anchor="w", textcolor="#37474f")
sim.AnimateRectangle(spec=(190, 120, 210, 135), fillcolor=C_DOWN)
sim.AnimateText(text="down", x=215, y=127, fontsize=11, text_anchor="w", textcolor="#37474f")

# ----------------------------------------------------------------------------
# Wire up the active components and record the video.
# ----------------------------------------------------------------------------
PartGenerator()
CNCFailure()

env.video("line_salabim.gif")   # fps already set above
env.run(till=HORIZON)
env.video_close()

print(f"done: arrived={stats['arrived']} completed={stats['completed']}")
