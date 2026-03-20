"""
Timing Simulation - Recording Loop with Simulated Hardware

Monte-Carlo simulation of the full recording pipeline.
No actual sleeping — all latencies are drawn from realistic distributions
and the recording loop logic is replayed analytically.

Simulates:
  - ESP32 serial communication (LED select/on/off, sensor query)
  - LED stabilization (deterministic 1000 ms)
  - Camera frame capture (ImSwitch GigE layer read)
  - HDF5 disk write latency growing with file size (3-day recording)
  - Write-behind queue back-pressure when disk is slow

Compares:
  OLD: synchronous HDF5 write blocks recording thread
  NEW: write-behind queue (v2.5) — recording thread enqueues and returns

Usage:
    python scripts/timing_simulation.py
    python scripts/timing_simulation.py --days 3 --interval 5 --no-plot
"""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import dataclass, field

import numpy as np

# ============================================================================
# CAMERA / HARDWARE PARAMETERS
# ============================================================================

FRAME_H = 1024
FRAME_W = 1224
FRAME_BYTES = FRAME_H * FRAME_W * 2  # uint16

RNG = np.random.default_rng(42)

# ============================================================================
# LATENCY MODELS  (all return seconds)
# ============================================================================


def lat_esp32_led_setup() -> float:
    """select_led_type() + led_on(): two serial round-trips ~18 ms total."""
    return max(0.005, RNG.normal(0.018, 0.005))


def lat_esp32_led_off() -> float:
    """led_off(): one serial round-trip ~10 ms."""
    return max(0.003, RNG.normal(0.010, 0.004))


def lat_camera_capture() -> float:
    """
    HIK GigE frame read via ImSwitch napari layer.
    Usually fast, but napari GIL / layer-refresh contention causes occasional spikes.
        90 %:  60–140 ms  (normal)
        10 %: 180–420 ms  (contention spike)
    """
    if RNG.random() < 0.90:
        return max(0.040, RNG.normal(0.090, 0.025))
    return max(0.120, RNG.normal(0.280, 0.070))


def lat_sensor_query() -> float:
    """DHT22 read + serial round-trip every 5 frames: ~28 ms."""
    return max(0.010, RNG.normal(0.028, 0.012))


def lat_hdf5_write_sync(frame_number: int) -> float:
    """
    Synchronous HDF5 write: 1 frame chunk + 17 timeseries resize+write.

    Latency grows with file size:
      - B-tree traversal for timeseries resize gets slower as datasets grow
      - OS page-cache pressure increases with large files
      - Chunk cache eviction becomes more frequent after ~10k frames

    Spike model (3 categories):
        96 %: base write    (fast path, chunk cache warm)
         3 %: cache flush   (chunk cache evict → disk seek)
         1 %: OS writeback  (kernel writeback blocks write syscall)
    """
    # Base latency grows with file size (in ms)
    #   early frames:  ~20 ms
    #   10k frames:    ~35 ms
    #   50k frames:    ~55 ms
    progress = min(frame_number / 50_000, 1.0)
    base_ms = 20 + progress * 35

    roll = RNG.random()
    if roll < 0.01:
        # OS writeback spike: 200–700 ms
        return max(0.100, RNG.normal(0.380, 0.150))
    if roll < 0.04:
        # Chunk cache flush: 70–180 ms
        return max(0.050, RNG.normal(0.110, 0.035))
    # Normal write
    return max(0.005, RNG.normal(base_ms / 1000.0, base_ms / 1000.0 * 0.25))


def lat_enqueue() -> float:
    """
    Write-behind queue enqueue: numpy memcpy (~2.5 MB) + queue.put().
    ~0.8 ms on modern CPU.
    """
    return max(0.0003, RNG.normal(0.0008, 0.0002))


# ============================================================================
# SIMULATION CORE  (pure analytic — no actual sleeping)
# ============================================================================


@dataclass
class FrameResult:
    frame_number: int
    actual_interval: float  # seconds since previous frame end
    frame_cycle_duration: float  # total time from deadline to frame saved/enqueued
    t_esp32: float
    t_stab: float
    t_camera: float
    t_led_off: float
    t_write: float  # sync write OR enqueue
    t_sensor: float
    deadline_lag: float  # > 0 means we started late (previous frame was long)


@dataclass
class SimResult:
    label: str
    interval_sec: float
    frames: list[FrameResult] = field(default_factory=list)
    queue_depth_history: list[int] = field(default_factory=list)  # NEW only

    @property
    def actual_intervals(self) -> list[float]:
        return [f.actual_interval for f in self.frames[1:]]

    @property
    def late_starts(self) -> list[float]:
        """Frames that started after their deadline."""
        return [f.deadline_lag for f in self.frames if f.deadline_lag > 0.001]

    def print_stats(self, interval_sec: float):
        ivs = self.actual_intervals
        n = len(self.frames)
        print(f"\n{'='*62}")
        print(f"  {self.label}")
        print(f"{'='*62}")
        print(f"  Frames simulated      : {n:,}")
        print(
            f"  Duration simulated    : {n * interval_sec / 3600:.1f} h  "
            f"({n * interval_sec / 86400:.2f} days)"
        )
        print(f"  Target interval       : {interval_sec:.1f} s")
        print("")
        print("  actual_interval statistics:")
        print(f"    Mean                : {statistics.mean(ivs):.4f} s")
        print(f"    Std dev             : {statistics.stdev(ivs)*1000:.2f} ms")
        print(f"    Median              : {statistics.median(ivs):.4f} s")
        print(f"    Min                 : {min(ivs):.4f} s")
        print(
            f"    Max                 : {max(ivs):.4f} s  "
            f"(+{(max(ivs)-interval_sec):.2f} s over target)"
        )
        print(f"    P95                 : {np.percentile(ivs, 95):.4f} s")
        print(f"    P99                 : {np.percentile(ivs, 99):.4f} s")
        print("")
        print("  Interval deviations:")
        print(
            f"    > 500 ms over target: "
            f"{sum(1 for v in ivs if v > interval_sec + 0.5):,}  "
            f"({sum(1 for v in ivs if v > interval_sec + 0.5)/len(ivs)*100:.1f} %)"
        )
        print(
            f"    >   1 s over target : "
            f"{sum(1 for v in ivs if v > interval_sec + 1):,}  "
            f"({sum(1 for v in ivs if v > interval_sec + 1)/len(ivs)*100:.1f} %)"
        )
        print(
            f"    >   2 s over target : "
            f"{sum(1 for v in ivs if v > interval_sec + 2):,}  "
            f"({sum(1 for v in ivs if v > interval_sec + 2)/len(ivs)*100:.1f} %)"
        )
        print("")
        late = self.late_starts
        print(f"  Late frame starts     : {len(late):,} / {n:,}  " f"({len(late)/n*100:.1f} %)")
        if late:
            print(f"    Mean late start lag : {statistics.mean(late)*1000:.1f} ms")
            print(f"    Max  late start lag : {max(late)*1000:.1f} ms")
        if self.queue_depth_history:
            print("")
            print("  Write queue depth:")
            print(f"    Mean              : {statistics.mean(self.queue_depth_history):.2f}")
            print(f"    Max               : {max(self.queue_depth_history)}")
            full_count = sum(1 for d in self.queue_depth_history if d >= 32)
            print(
                f"    Queue full (>=32) : {full_count} times "
                f"{'← back-pressure occurred' if full_count else ''}"
            )


def simulate_old(n_frames: int, interval_sec: float) -> SimResult:
    """
    OLD behaviour: synchronous HDF5 write blocks recording thread.

    Recording loop (absolute deadline):
      deadline[n] = start + n * interval
      wait until deadline[n]
      do: LED setup + stabilization + camera + LED off + SYNC WRITE + sensor query
      → actual_interval = time from prev frame end to this frame end
    """
    result = SimResult(label="OLD: synchronous HDF5 write", interval_sec=interval_sec)
    t = 0.0  # simulated wall clock (seconds)
    start = t
    last_frame_end = 0.0

    for i in range(n_frames):
        fn = i + 1
        deadline = start + i * interval_sec

        # Wait until deadline (or start immediately if already past)
        t_start = max(t, deadline)
        deadline_lag = max(0.0, t - deadline)

        # Frame cycle: all blocking
        t_esp32 = lat_esp32_led_setup()
        t_stab = 1.0  # deterministic
        t_cam = lat_camera_capture()
        t_led_off = lat_esp32_led_off()
        t_write = lat_hdf5_write_sync(fn)  # ← blocks recording thread
        t_sensor = lat_sensor_query() if fn % 5 == 0 else 0.0

        cycle = t_esp32 + t_stab + t_cam + t_led_off + t_write + t_sensor
        t = t_start + cycle

        actual_interval = t - last_frame_end if last_frame_end > 0 else 0.0
        last_frame_end = t

        result.frames.append(
            FrameResult(
                frame_number=fn,
                actual_interval=actual_interval,
                frame_cycle_duration=cycle,
                t_esp32=t_esp32,
                t_stab=t_stab,
                t_camera=t_cam,
                t_led_off=t_led_off,
                t_write=t_write,
                t_sensor=t_sensor,
                deadline_lag=deadline_lag,
            )
        )

    return result


def simulate_new(n_frames: int, interval_sec: float) -> SimResult:
    """
    NEW behaviour (v2.5): write-behind queue.

    Recording thread enqueues frame (near-instant) and returns.
    Background writer thread drains queue at disk speed.
    Queue is bounded at 32 frames — back-pressure if disk is too slow.

    Back-pressure model:
      If queue is full, recording thread blocks until writer frees a slot.
      We simulate this by tracking queue depth analytically:
        queue_depth[n] = frames enqueued - frames written by writer by time t
    """
    result = SimResult(label="NEW: write-behind queue (v2.5)", interval_sec=interval_sec)
    t = 0.0
    start = t
    last_frame_end = 0.0
    MAX_QUEUE = 32

    # Track writer thread state analytically
    # writer_free_at: the simulated time when the writer finishes current item
    writer_free_at = 0.0
    queue_items: list[float] = []  # list of (writer_done_time) for each queued item
    # Approximation: writer processes items sequentially; each takes lat_hdf5_write_sync(fn)

    for i in range(n_frames):
        fn = i + 1
        deadline = start + i * interval_sec
        t_start = max(t, deadline)
        deadline_lag = max(0.0, t - deadline)

        # Frame cycle (recording thread)
        t_esp32 = lat_esp32_led_setup()
        t_stab = 1.0
        t_cam = lat_camera_capture()
        t_led_off = lat_esp32_led_off()
        t_enq = lat_enqueue()  # ← near-instant
        t_sensor = lat_sensor_query() if fn % 5 == 0 else 0.0

        # Compute when recording thread finishes (before any back-pressure)
        t_cycle_end = t_start + t_esp32 + t_stab + t_cam + t_led_off + t_enq + t_sensor

        # Compute queue depth at t_cycle_end
        # Items written by writer up to t_cycle_end
        items_written = sum(1 for done_at in queue_items if done_at <= t_cycle_end)
        current_depth = len(queue_items) - items_written

        # If queue full: recording thread blocks until writer frees a slot
        back_pressure_wait = 0.0
        if current_depth >= MAX_QUEUE:
            # Find the time when the oldest item in queue gets processed
            pending = sorted(done_at for done_at in queue_items if done_at > t_cycle_end)
            if pending:
                unblock_at = pending[0]  # writer frees one slot
                back_pressure_wait = unblock_at - t_cycle_end
                t_cycle_end = unblock_at

        t = t_cycle_end

        # Schedule this frame's write in the writer thread
        # Writer starts after current writer_free_at or t_start (whichever is later)
        write_start = max(writer_free_at, t_start + t_esp32 + t_stab + t_cam + t_led_off + t_enq)
        write_duration = lat_hdf5_write_sync(fn)
        writer_free_at = write_start + write_duration
        queue_items.append(writer_free_at)

        # Keep queue_items list bounded (only keep unfinished writes)
        queue_items = [done_at for done_at in queue_items if done_at > t]

        result.queue_depth_history.append(current_depth)

        actual_interval = t - last_frame_end if last_frame_end > 0 else 0.0
        last_frame_end = t

        result.frames.append(
            FrameResult(
                frame_number=fn,
                actual_interval=actual_interval,
                frame_cycle_duration=t - t_start,
                t_esp32=t_esp32,
                t_stab=t_stab,
                t_camera=t_cam,
                t_led_off=t_led_off,
                t_write=t_enq + back_pressure_wait,  # enqueue + any back-pressure
                t_sensor=t_sensor,
                deadline_lag=deadline_lag,
            )
        )

    return result


# ============================================================================
# PLOTTING
# ============================================================================


def plot_results(old: SimResult, new: SimResult, interval_sec: float, n_days: float):
    try:
        import matplotlib.gridspec as gridspec
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed — skipping plot")
        return

    fig = plt.figure(figsize=(15, 10))
    gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.35)

    fig.suptitle(
        f"Recording Timing Simulation  ·  {n_days:.0f} days @ {interval_sec} s interval  ·  "
        f"{len(old.frames):,} frames  ·  MV-CS013-60GN ({FRAME_H}×{FRAME_W} uint16)",
        fontsize=12,
        fontweight="bold",
    )

    COL_OLD = "#e74c3c"
    COL_NEW = "#27ae60"
    target = interval_sec

    ivs_old = np.array(old.actual_intervals)
    ivs_new = np.array(new.actual_intervals)
    frame_nums = np.arange(2, len(old.frames) + 1)
    t_hours = frame_nums * interval_sec / 3600.0

    # ── 1. actual_interval over time (first 500 frames) ──────────────────
    ax = fig.add_subplot(gs[0, :2])
    n_show = min(500, len(ivs_old))
    ax.plot(
        t_hours[:n_show],
        ivs_old[:n_show],
        color=COL_OLD,
        alpha=0.6,
        linewidth=0.6,
        label="OLD (sync write)",
    )
    ax.plot(
        t_hours[:n_show],
        ivs_new[:n_show],
        color=COL_NEW,
        alpha=0.7,
        linewidth=0.6,
        label="NEW (write-behind)",
    )
    ax.axhline(target, color="black", linestyle="--", linewidth=0.8, label=f"Target {target} s")
    ax.axhline(target + 1, color="orange", linestyle=":", linewidth=0.7, label="+1 s")
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("actual_interval (s)")
    ax.set_title(f"Interval per frame — first {n_show} frames")
    ax.legend(fontsize=8, ncol=4)
    ax.grid(True, alpha=0.3)

    # ── 2. actual_interval over full recording (downsampled) ─────────────
    ax = fig.add_subplot(gs[0, 2])
    step = max(1, len(ivs_old) // 500)
    ax.plot(t_hours[::step], ivs_old[::step], color=COL_OLD, alpha=0.5, linewidth=0.5, label="OLD")
    ax.plot(t_hours[::step], ivs_new[::step], color=COL_NEW, alpha=0.6, linewidth=0.5, label="NEW")
    ax.axhline(target, color="black", linestyle="--", linewidth=0.8)
    ax.set_xlabel("Time (h)")
    ax.set_ylabel("actual_interval (s)")
    ax.set_title("Full recording (downsampled)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # ── 3. Histogram ──────────────────────────────────────────────────────
    ax = fig.add_subplot(gs[1, 0])
    lo = target - 0.5
    hi = target + min(max(ivs_old.max(), ivs_new.max()) - target + 0.5, 5.0)
    bins = np.linspace(lo, hi, 80)
    ax.hist(ivs_old, bins=bins, color=COL_OLD, alpha=0.6, label="OLD", density=True)
    ax.hist(ivs_new, bins=bins, color=COL_NEW, alpha=0.6, label="NEW", density=True)
    ax.axvline(target, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("actual_interval (s)")
    ax.set_ylabel("Density")
    ax.set_title("Interval distribution")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # ── 4. CDF of |deviation| ────────────────────────────────────────────
    ax = fig.add_subplot(gs[1, 1])
    for ivs, color, label in [(ivs_old, COL_OLD, "OLD"), (ivs_new, COL_NEW, "NEW")]:
        dev = np.sort(np.abs(ivs - target)) * 1000
        cdf = np.linspace(0, 100, len(dev))
        ax.plot(dev, cdf, color=color, linewidth=1.5, label=label)
    ax.axvline(500, color="orange", linestyle=":", linewidth=0.8, label="500 ms")
    ax.axvline(1000, color="red", linestyle=":", linewidth=0.8, label="1 s")
    ax.set_xlabel("|actual − target| (ms)")
    ax.set_ylabel("Cumulative % of frames")
    ax.set_title("CDF of interval deviation")
    ax.legend(fontsize=8)
    ax.set_xlim(0, 3000)
    ax.grid(True, alpha=0.3)

    # ── 5. Frame cycle breakdown ──────────────────────────────────────────
    ax = fig.add_subplot(gs[1, 2])
    labels = [
        "ESP32\nsetup",
        "Stabiliz.\n(1000ms)",
        "Camera\ncapture",
        "LED\noff",
        "Write /\nEnqueue",
        "Sensor\nquery",
    ]
    sensor_frames = [f for f in old.frames if f.t_sensor > 0]
    m_old = [
        np.mean([f.t_esp32 for f in old.frames]) * 1000,
        1000.0,
        np.mean([f.t_camera for f in old.frames]) * 1000,
        np.mean([f.t_led_off for f in old.frames]) * 1000,
        np.mean([f.t_write for f in old.frames]) * 1000,
        np.mean([f.t_sensor for f in sensor_frames]) * 1000 if sensor_frames else 0,
    ]
    sensor_frames_new = [f for f in new.frames if f.t_sensor > 0]
    m_new = [
        np.mean([f.t_esp32 for f in new.frames]) * 1000,
        1000.0,
        np.mean([f.t_camera for f in new.frames]) * 1000,
        np.mean([f.t_led_off for f in new.frames]) * 1000,
        np.mean([f.t_write for f in new.frames]) * 1000,
        np.mean([f.t_sensor for f in sensor_frames_new]) * 1000 if sensor_frames_new else 0,
    ]
    x = np.arange(len(labels))
    w = 0.35
    ax.bar(x - w / 2, m_old, w, color=COL_OLD, alpha=0.8, label="OLD")
    ax.bar(x + w / 2, m_new, w, color=COL_NEW, alpha=0.8, label="NEW")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Mean duration (ms)")
    ax.set_title("Cycle component (mean)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")

    # ── 6. Spike count per hour ───────────────────────────────────────────
    ax = fig.add_subplot(gs[2, :2])
    frames_per_hour = int(3600 / interval_sec)
    n_hours = len(ivs_old) // frames_per_hour
    if n_hours > 1:
        spikes_old = [
            np.sum(ivs_old[h * frames_per_hour : (h + 1) * frames_per_hour] > target + 1)
            for h in range(n_hours)
        ]
        spikes_new = [
            np.sum(ivs_new[h * frames_per_hour : (h + 1) * frames_per_hour] > target + 1)
            for h in range(n_hours)
        ]
        hours = np.arange(n_hours)
        w = 0.4
        ax.bar(hours - w / 2, spikes_old, w, color=COL_OLD, alpha=0.7, label="OLD")
        ax.bar(hours + w / 2, spikes_new, w, color=COL_NEW, alpha=0.7, label="NEW")
        ax.set_xlabel("Hour of recording")
        ax.set_ylabel("Frames with interval >1 s late")
        ax.set_title("Timing spikes per hour of recording")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis="y")

    # ── 7. Write queue depth (NEW only) ──────────────────────────────────
    ax = fig.add_subplot(gs[2, 2])
    if new.queue_depth_history:
        step = max(1, len(new.queue_depth_history) // 500)
        ax.plot(
            t_hours[::step],
            new.queue_depth_history[::step],
            color=COL_NEW,
            linewidth=0.7,
            alpha=0.8,
        )
        ax.axhline(32, color="red", linestyle="--", linewidth=0.8, label="Queue limit (32)")
        ax.set_xlabel("Time (h)")
        ax.set_ylabel("Queue depth (frames)")
        ax.set_title("Write queue depth (NEW)")
        ax.set_ylim(0, 35)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    out_path = "scripts/timing_simulation_result.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\n  Plot saved: {out_path}")
    try:
        plt.show()
    except Exception:
        pass  # headless environment


# ============================================================================
# MAIN
# ============================================================================


def main():
    parser = argparse.ArgumentParser(description="Recording timing Monte-Carlo simulation")
    parser.add_argument("--days", type=float, default=3.0, help="Recording duration in days")
    parser.add_argument("--interval", type=float, default=5.0, help="Frame interval in seconds")
    parser.add_argument("--no-plot", action="store_true", help="Skip matplotlib plot")
    args = parser.parse_args()

    n_frames = int(args.days * 86400 / args.interval)
    target = args.interval

    print(f"\n{'='*62}")
    print("  Recording Timing Monte-Carlo Simulation")
    print(f"{'='*62}")
    print(f"  Duration  : {args.days:.1f} days  ({n_frames:,} frames)")
    print(f"  Interval  : {target} s")
    print(f"  Frame     : {FRAME_H}×{FRAME_W} uint16  ({FRAME_BYTES/1e6:.1f} MB)")
    print(f"  Total data: {n_frames * FRAME_BYTES / 1e9:.1f} GB (uncompressed)")

    t0 = time.perf_counter()
    print("\n  Simulating OLD (synchronous HDF5)...")
    old = simulate_old(n_frames, target)
    t1 = time.perf_counter()
    print(f"  Done in {t1-t0:.2f} s")

    print("  Simulating NEW (write-behind queue)...")
    new = simulate_new(n_frames, target)
    t2 = time.perf_counter()
    print(f"  Done in {t2-t1:.2f} s")

    old.print_stats(target)
    new.print_stats(target)

    # ── Summary comparison ────────────────────────────────────────────────
    ivs_old = np.array(old.actual_intervals)
    ivs_new = np.array(new.actual_intervals)

    std_old = statistics.stdev(ivs_old) * 1000
    std_new = statistics.stdev(ivs_new) * 1000
    late1_old = sum(1 for v in ivs_old if v > target + 1)
    late1_new = sum(1 for v in ivs_new if v > target + 1)
    late2_old = sum(1 for v in ivs_old if v > target + 2)
    late2_new = sum(1 for v in ivs_new if v > target + 2)

    print(f"\n{'='*62}")
    print("  IMPROVEMENT SUMMARY")
    print(f"{'='*62}")
    print(
        f"  Interval std dev  : {std_old:.1f} ms  ->  {std_new:.1f} ms  "
        f"({(1-std_new/std_old)*100:.0f} % reduction)"
    )
    print(f"  Max interval      : {max(ivs_old):.2f} s  ->  {max(ivs_new):.2f} s")
    print(
        f"  P99 interval      : {np.percentile(ivs_old,99):.3f} s  ->  "
        f"{np.percentile(ivs_new,99):.3f} s"
    )
    print(
        f"  Frames >1 s late  : {late1_old:,}  ->  {late1_new:,}  "
        f"({(1-late1_new/(late1_old or 1))*100:.0f} % reduction)"
    )
    print(f"  Frames >2 s late  : {late2_old:,}  ->  {late2_new:,}")
    qmax = max(new.queue_depth_history) if new.queue_depth_history else 0
    print(
        f"  Max write queue   : {qmax} / 32  "
        f"({'back-pressure occurred!' if qmax >= 32 else 'no back-pressure'})"
    )

    if not args.no_plot:
        plot_results(old, new, target, args.days)


if __name__ == "__main__":
    main()
