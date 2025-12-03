"""
HDF5 Timeseries Plotter - Interactive visualization tool

Plots timeseries data from HDF5 recordings with interpretable Y-axis labels.

Usage:
    python hdf5_timeseries_plotter.py <path_to_hdf5_file>

Features:
- Interactive plot selection
- Proper Y-axis labels with units
- Multiple subplots for different data types
- Support for phase transitions and LED types
"""

import argparse
import sys
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np


class TimeseriesPlotter:
    """Interactive HDF5 Timeseries Plotter"""

    # Field metadata: (display_name, unit, description)
    FIELD_INFO = {
        "timestamps": ("Timestamp", "seconds (Unix)", "Absolute timestamp"),
        "recording_elapsed_sec": ("Recording Time", "seconds", "Time since recording start"),
        "actual_intervals": ("Actual Interval", "seconds", "Time between frames"),
        "expected_intervals": ("Expected Interval", "seconds", "Target interval"),
        "temperature_celsius": ("Temperature", "°C", "ESP32 sensor temperature"),
        "humidity_percent": ("Humidity", "%", "Relative humidity"),
        "led_type": ("LED Type", "enum", "LED configuration (-1=off, 0=IR, 1=White, 2=Dual)"),
        "led_power": ("LED Power", "%", "LED power level"),
        "phase": ("Phase", "enum", "Recording phase (0=continuous, 1=light, 2=dark)"),
        "phase_transition": ("Phase Transition", "boolean", "Phase change indicator"),
        "cycle_number": ("Cycle Number", "#", "Phase cycle counter"),
        "frame_mean_intensity": ("Frame Intensity", "grayscale", "Mean pixel intensity"),
        "sync_success": ("Sync Success", "boolean", "LED sync successful"),
        "led_stabilization_ms": ("LED Stabilization", "ms", "LED warmup time"),
        "exposure_ms": ("Exposure Time", "ms", "Camera exposure"),
        "capture_duration_ms": ("Capture Duration", "ms", "Total frame capture time"),
    }

    def __init__(self, hdf5_path: str):
        self.hdf5_path = Path(hdf5_path)
        self.file = None
        self.timeseries_group = None

    def open(self):
        """Open HDF5 file"""
        if not self.hdf5_path.exists():
            raise FileNotFoundError(f"File not found: {self.hdf5_path}")

        self.file = h5py.File(self.hdf5_path, 'r')

        # Find timeseries group
        if 'timeseries' in self.file:
            self.timeseries_group = self.file['timeseries']
        else:
            raise ValueError("No 'timeseries' group found in HDF5 file")

        print(f"✅ Opened: {self.hdf5_path.name}")
        print(f"   Available fields: {len(list(self.timeseries_group.keys()))}")

    def close(self):
        """Close HDF5 file"""
        if self.file:
            self.file.close()

    def list_fields(self):
        """List all available fields"""
        print("\n📊 Available Timeseries Fields:")
        print("=" * 70)

        for i, field_name in enumerate(sorted(self.timeseries_group.keys()), 1):
            dataset = self.timeseries_group[field_name]

            # Get field info
            display_name, unit, description = self.FIELD_INFO.get(
                field_name, (field_name, "unknown", "No description")
            )

            # Get data info
            shape = dataset.shape
            dtype = dataset.dtype

            print(f"{i:2d}. {field_name:30s} | {display_name:20s} [{unit}]")
            print(f"    Shape: {shape}, Type: {dtype}")
            print(f"    {description}")

    def get_field_label(self, field_name: str) -> str:
        """Get interpretable axis label for field"""
        display_name, unit, _ = self.FIELD_INFO.get(
            field_name, (field_name, "", "")
        )

        if unit:
            return f"{display_name} ({unit})"
        return display_name

    def plot_fields(self, field_names: list, x_axis: str = "frame_index"):
        """
        Plot selected fields

        Args:
            field_names: List of field names to plot
            x_axis: Field to use as X-axis (default: frame_index)
        """
        if not field_names:
            print("❌ No fields selected")
            return

        # Load X-axis data
        if x_axis in self.timeseries_group:
            x_data = self.timeseries_group[x_axis][:]
            x_label = self.get_field_label(x_axis)
        else:
            # Use frame index as fallback
            x_data = np.arange(len(self.timeseries_group[field_names[0]]))
            x_label = "Frame Index"

        # Create subplots
        n_fields = len(field_names)
        fig, axes = plt.subplots(n_fields, 1, figsize=(12, 4 * n_fields), sharex=True)

        if n_fields == 1:
            axes = [axes]

        fig.suptitle(f"Timeseries Data: {self.hdf5_path.name}", fontsize=14, fontweight='bold')

        for ax, field_name in zip(axes, field_names):
            if field_name not in self.timeseries_group:
                ax.text(0.5, 0.5, f"Field '{field_name}' not found",
                       ha='center', va='center', transform=ax.transAxes)
                continue

            # Load data
            y_data = self.timeseries_group[field_name][:]
            y_label = self.get_field_label(field_name)

            # Plot
            if "transition" in field_name or "success" in field_name:
                # Boolean data - use step plot
                ax.step(x_data, y_data, where='post', linewidth=2, label=field_name)
                ax.set_ylim(-0.1, 1.1)
                ax.set_yticks([0, 1])
                ax.set_yticklabels(['False', 'True'])
            elif field_name in ["led_type", "phase"]:
                # Enum data - use step plot with labels
                ax.step(x_data, y_data, where='post', linewidth=2, label=field_name)

                if field_name == "led_type":
                    ax.set_yticks([-1, 0, 1, 2])
                    ax.set_yticklabels(['Off', 'IR', 'White', 'Dual'])
                elif field_name == "phase":
                    ax.set_yticks([0, 1, 2])
                    ax.set_yticklabels(['Continuous', 'Light', 'Dark'])
            else:
                # Continuous data - line plot
                ax.plot(x_data, y_data, linewidth=1.5, label=field_name)

            # Labels and grid
            ax.set_ylabel(y_label, fontsize=11, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right')

            # Show statistics
            if not (field_name in ["led_type", "phase", "transition", "success"]):
                mean_val = np.mean(y_data)
                std_val = np.std(y_data)
                ax.text(0.02, 0.98, f"μ={mean_val:.2f}, σ={std_val:.2f}",
                       transform=ax.transAxes, va='top', fontsize=9,
                       bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        # X-axis label (only on bottom plot)
        axes[-1].set_xlabel(x_label, fontsize=11, fontweight='bold')

        plt.tight_layout()
        plt.show()

    def interactive_plot(self):
        """Interactive plotting mode"""
        print("\n🎨 Interactive Plotting Mode")
        print("=" * 70)

        # List available fields
        field_list = sorted(self.timeseries_group.keys())

        print("\nAvailable fields:")
        for i, field_name in enumerate(field_list, 1):
            display_name, unit, _ = self.FIELD_INFO.get(
                field_name, (field_name, "", "")
            )
            print(f"  {i:2d}. {field_name:30s} [{unit}]")

        print("\nEnter field numbers to plot (comma-separated, e.g., '1,3,5'):")
        print("Or enter field names directly (comma-separated)")
        print("Press Ctrl+C to exit")

        try:
            user_input = input("> ").strip()

            # Parse input
            selected_fields = []

            if not user_input:
                print("❌ No fields selected")
                return

            for item in user_input.split(','):
                item = item.strip()

                # Try parsing as number
                try:
                    idx = int(item) - 1
                    if 0 <= idx < len(field_list):
                        selected_fields.append(field_list[idx])
                    else:
                        print(f"⚠️ Invalid index: {item}")
                except ValueError:
                    # Try as field name
                    if item in field_list:
                        selected_fields.append(item)
                    else:
                        print(f"⚠️ Unknown field: {item}")

            if selected_fields:
                print(f"\n📈 Plotting: {', '.join(selected_fields)}")
                self.plot_fields(selected_fields)
            else:
                print("❌ No valid fields selected")

        except KeyboardInterrupt:
            print("\n\n👋 Exiting...")


def main():
    parser = argparse.ArgumentParser(
        description="HDF5 Timeseries Plotter - Visualize recording data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  python hdf5_timeseries_plotter.py recording.h5

  # Plot specific fields
  python hdf5_timeseries_plotter.py recording.h5 --fields actual_intervals,temperature_celsius

  # List all available fields
  python hdf5_timeseries_plotter.py recording.h5 --list
        """
    )

    parser.add_argument("hdf5_file", help="Path to HDF5 recording file")
    parser.add_argument("--fields", "-f", help="Comma-separated field names to plot")
    parser.add_argument("--list", "-l", action="store_true", help="List all available fields and exit")
    parser.add_argument("--x-axis", "-x", default="frame_index", help="Field to use as X-axis (default: frame_index)")

    args = parser.parse_args()

    # Create plotter
    plotter = TimeseriesPlotter(args.hdf5_file)

    try:
        plotter.open()

        if args.list:
            # List mode
            plotter.list_fields()
        elif args.fields:
            # Direct plot mode
            field_names = [f.strip() for f in args.fields.split(',')]
            plotter.plot_fields(field_names, x_axis=args.x_axis)
        else:
            # Interactive mode
            plotter.interactive_plot()

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    finally:
        plotter.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
