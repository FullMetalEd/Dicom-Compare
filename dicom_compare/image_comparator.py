"""DICOM image pixel data comparison"""

import numpy as np
import pydicom
from typing import Dict, List, Optional, Tuple
from rich.console import Console

from .models import DicomInstance
from .image_models import (
    ImageComparisonResult, ImageFileComparisonResult, ImageStats,
    ImageDifferenceType, ImageComparisonSummary
)
from .dicom_loader import DicomStudy

console = Console()

class ImageProcessor:
    """Handle DICOM image extraction and preprocessing"""
    
    def __init__(self, normalize: bool = True):
        self.normalize = normalize
    
    def extract_pixel_data(self, dicom_instance: DicomInstance) -> Optional[np.ndarray]:
        """Extract pixel data from DICOM instance"""
        try:
            # Load the DICOM file
            ds = pydicom.dcmread(dicom_instance.file_path)
            
            # Check if pixel data exists
            if not hasattr(ds, 'PixelData') or ds.PixelData is None:
                return None
            
            # Get pixel array
            pixel_array = ds.pixel_array
            
            # Apply DICOM transformations if requested
            if self.normalize:
                pixel_array = self._normalize_image(pixel_array, ds)
            
            return pixel_array
            
        except Exception as e:
            console.print(f"⚠️  Failed to extract pixel data from {dicom_instance.sop_instance_uid}: {e}", style="yellow")
            return None
    
    def _normalize_image(self, pixel_array: np.ndarray, ds: pydicom.Dataset) -> np.ndarray:
        """Apply DICOM normalization (rescale slope/intercept, window/level)"""
        
        # Apply rescale slope and intercept
        if hasattr(ds, 'RescaleSlope') and hasattr(ds, 'RescaleIntercept'):
            slope = float(ds.RescaleSlope)
            intercept = float(ds.RescaleIntercept)
            pixel_array = pixel_array * slope + intercept
        
        # Apply window/level if present (simplified for now)
        if hasattr(ds, 'WindowCenter') and hasattr(ds, 'WindowWidth'):
            try:
                center = float(ds.WindowCenter) if not isinstance(ds.WindowCenter, list) else float(ds.WindowCenter[0])
                width = float(ds.WindowWidth) if not isinstance(ds.WindowWidth, list) else float(ds.WindowWidth[0])
                
                min_val = center - width / 2
                max_val = center + width / 2
                pixel_array = np.clip(pixel_array, min_val, max_val)
            except (ValueError, TypeError):
                # Skip windowing if values are invalid
                pass
        
        return pixel_array
    
    def get_image_stats(self, pixel_array: Optional[np.ndarray], ds: Optional[pydicom.Dataset] = None) -> ImageStats:
        """Get statistical information about an image"""
        if pixel_array is None:
            return ImageStats(
                shape=(0,), dtype="none", min_value=0, max_value=0, 
                mean_value=0, has_pixel_data=False
            )
        
        stats = ImageStats(
            shape=pixel_array.shape,
            dtype=str(pixel_array.dtype),
            min_value=float(np.min(pixel_array)),
            max_value=float(np.max(pixel_array)),
            mean_value=float(np.mean(pixel_array)),
            has_pixel_data=True
        )
        
        # Add DICOM-specific info if available
        if ds:
            stats.bits_allocated = getattr(ds, 'BitsAllocated', None)
            stats.bits_stored = getattr(ds, 'BitsStored', None)
            stats.photometric_interpretation = getattr(ds, 'PhotometricInterpretation', None)
        
        return stats

class ImageComparator:
    """Compare DICOM image pixel data"""
    
    def __init__(self, tolerance: float = 0.0, normalize: bool = True):
        self.tolerance = tolerance
        self.processor = ImageProcessor(normalize=normalize)
        self.normalize = normalize
    
    def compare_studies(
        self,
        baseline_studies: Dict[str, DicomStudy],
        comparison_studies: Dict[str, DicomStudy],
        baseline_file: str,
        comparison_file: str
    ) -> ImageFileComparisonResult:
        """Compare images between two study sets"""
        
        # Build instance lookups (same as tag comparison)
        baseline_instances = self._build_instance_lookup(baseline_studies)
        comparison_instances = self._build_instance_lookup(comparison_studies)
        
        # Find matches and compare
        image_comparisons = []
        missing_instances = []
        extra_instances = []
        
        baseline_sop_uids = set(baseline_instances.keys())
        comparison_sop_uids = set(comparison_instances.keys())
        
        # Compare matched instances
        common_sop_uids = baseline_sop_uids.intersection(comparison_sop_uids)
        for sop_uid in common_sop_uids:
            baseline_instance = baseline_instances[sop_uid]
            comparison_instance = comparison_instances[sop_uid]
            
            image_comparison = self.compare_images(
                baseline_instance, comparison_instance,
                baseline_file, comparison_file
            )
            image_comparisons.append(image_comparison)
        
        # Find missing/extra instances
        missing_sop_uids = baseline_sop_uids - comparison_sop_uids
        for sop_uid in missing_sop_uids:
            missing_instances.append(baseline_instances[sop_uid])
        
        extra_sop_uids = comparison_sop_uids - baseline_sop_uids
        for sop_uid in extra_sop_uids:
            extra_instances.append(comparison_instances[sop_uid])
        
        return ImageFileComparisonResult(
            baseline_file=baseline_file,
            comparison_file=comparison_file,
            image_comparisons=image_comparisons,
            missing_instances=missing_instances,
            extra_instances=extra_instances,
            total_instances_baseline=len(baseline_instances),
            total_instances_comparison=len(comparison_instances),
            tolerance_used=self.tolerance
        )
    
    def compare_images(
        self,
        baseline_instance: DicomInstance,
        comparison_instance: DicomInstance,
        baseline_file: str,
        comparison_file: str
    ) -> ImageComparisonResult:
        """Compare pixel data between two DICOM instances"""
        
        # Extract pixel data
        baseline_pixels = self.processor.extract_pixel_data(baseline_instance)
        comparison_pixels = self.processor.extract_pixel_data(comparison_instance)
        
        # Get image statistics
        baseline_stats = self.processor.get_image_stats(baseline_pixels)
        comparison_stats = self.processor.get_image_stats(comparison_pixels)
        
        # Handle missing pixel data
        if baseline_pixels is None or comparison_pixels is None:
            return ImageComparisonResult(
                sop_instance_uid=baseline_instance.sop_instance_uid,
                baseline_file=baseline_file,
                comparison_file=comparison_file,
                is_exact_match=False,
                difference_type=ImageDifferenceType.MISSING_PIXEL_DATA,
                similarity_score=0.0,
                baseline_stats=baseline_stats,
                comparison_stats=comparison_stats,
                normalization_applied=self.normalize,
                tolerance_used=self.tolerance
            )
        
        # Check dimensions
        if baseline_pixels.shape != comparison_pixels.shape:
            return ImageComparisonResult(
                sop_instance_uid=baseline_instance.sop_instance_uid,
                baseline_file=baseline_file,
                comparison_file=comparison_file,
                is_exact_match=False,
                difference_type=ImageDifferenceType.DIMENSION_DIFF,
                similarity_score=0.0,
                baseline_stats=baseline_stats,
                comparison_stats=comparison_stats,
                normalization_applied=self.normalize,
                tolerance_used=self.tolerance
            )
        
        # Compare pixel values
        return self._compare_pixel_values(
            baseline_instance, comparison_instance,
            baseline_pixels, comparison_pixels,
            baseline_stats, comparison_stats,
            baseline_file, comparison_file
        )
    
    def _compare_pixel_values(
        self, baseline_instance, comparison_instance,
        baseline_pixels, comparison_pixels,
        baseline_stats, comparison_stats,
        baseline_file, comparison_file
    ) -> ImageComparisonResult:
        """Detailed pixel-by-pixel comparison"""
        
        # Calculate differences
        diff_array = np.abs(baseline_pixels.astype(np.float64) - comparison_pixels.astype(np.float64))
        
        # Statistics
        max_diff = np.max(diff_array)
        mean_diff = np.mean(diff_array)
        rmse = np.sqrt(np.mean(diff_array ** 2))
        different_pixels = np.sum(diff_array > self.tolerance)
        total_pixels = diff_array.size
        
        # Similarity score
        similarity = 1.0 - (different_pixels / total_pixels)
        
        # Determine if exact match
        is_exact = max_diff <= self.tolerance
        diff_type = ImageDifferenceType.EXACT_MATCH if is_exact else ImageDifferenceType.PIXEL_VALUE_DIFF
        
        return ImageComparisonResult(
            sop_instance_uid=baseline_instance.sop_instance_uid,
            baseline_file=baseline_file,
            comparison_file=comparison_file,
            is_exact_match=is_exact,
            difference_type=diff_type,
            similarity_score=similarity,
            pixel_differences=int(different_pixels),
            max_difference=float(max_diff),
            mean_difference=float(mean_diff),
            rmse=float(rmse),
            baseline_stats=baseline_stats,
            comparison_stats=comparison_stats,
            normalization_applied=self.normalize,
            tolerance_used=self.tolerance
        )
    
    def _build_instance_lookup(self, studies: Dict[str, DicomStudy]) -> Dict[str, DicomInstance]:
        """Build flat lookup of instances by SOPInstanceUID"""
        instances = {}
        for study in studies.values():
            for series in study.series.values():
                for instance in series.instances.values():
                    instances[instance.sop_instance_uid] = instance
        return instances