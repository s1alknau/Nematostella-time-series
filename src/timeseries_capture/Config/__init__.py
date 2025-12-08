"""
Configuration Module for Camera System Setup

This module handles configuration for single and multi-camera setups.
"""

from .camera_system_config import (
    CameraConfig,
    CameraSystemConfig,
    load_camera_system_config,
)

__all__ = [
    "CameraConfig",
    "CameraSystemConfig",
    "load_camera_system_config",
]
