"""
Analysis module for live ROI detection and activity computation during recording.
"""

from .live_analysis_worker import LiveAnalysisWorker
from .roi_detector import RoiDetectionResult, detect_rois_hough

__all__ = ["detect_rois_hough", "RoiDetectionResult", "LiveAnalysisWorker"]
