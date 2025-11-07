__version__ = "0.0.1"

from napari_plugin_engine import napari_hook_implementation
from ._widget import NematostallTimelapseCaptureWidget


@napari_hook_implementation
def napari_experimental_provide_dock_widget():
    """Provide the timelapse capture dock widget."""
    return NematostallTimelapseCaptureWidget


__all__ = [
    "__version__",
    "NematostallTimelapseCaptureWidget",
    "napari_experimental_provide_dock_widget",
]
