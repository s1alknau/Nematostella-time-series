"""
Nematostella Time-Series Capture Plugin for napari
"""

__version__ = "4.0.0"

# Import the dock widget provider function
from .main_plugin import napari_experimental_provide_dock_widget

__all__ = [
    "napari_experimental_provide_dock_widget",
    "__version__",
]
