from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum

class ImageDifferenceType(Enum):
    EXACT_MATCH = "EXACT_MATCH"
    PIXEL_VALUE_DIFF = "PIXEL_VALUE_DIFF"
    DIMENSION_DIFF = "DIMENSION_DIFF"
    MISSING_PIXEL_DATA = "MISSING_PIXEL_DATA"
    FORMAT_DIFF = "FORMAT_DIFF"
    NORMALIZATION_DIFF = "NORMALIZATION_DIFF"

@dataclass
class ImageStats:
    """Statistical information about an image"""
    shape: Tuple[int, ...]
    dtype: str
    min_value: float
    max_value: float
    mean_value: float
    has_pixel_data: bool
    bits_allocated: Optional[int] = None
    bits_stored: Optional[int] = None
    photometric_interpretation: Optional[str] = None

@dataclass
class ImageComparisonResult:
    """Result of comparing two DICOM images"""
    sop_instance_uid: str
    baseline_file: str
    comparison_file: str
    is_exact_match: bool
    difference_type: ImageDifferenceType
    similarity_score: float  # 0.0 to 1.0
    
    # Difference statistics
    pixel_differences: Optional[int] = None
    max_difference: Optional[float] = None
    mean_difference: Optional[float] = None
    rmse: Optional[float] = None  # Root mean square error
    
    # Image information
    baseline_stats: Optional[ImageStats] = None
    comparison_stats: Optional[ImageStats] = None
    
    # Processing notes
    normalization_applied: bool = False
    tolerance_used: float = 0.0

@dataclass
class ImageFileComparisonResult:
    """Results comparing images between two files"""
    baseline_file: str
    comparison_file: str
    image_comparisons: List[ImageComparisonResult]
    missing_instances: List = None  # Will be DicomInstance
    extra_instances: List = None    # Will be DicomInstance
    total_instances_baseline: int = 0
    total_instances_comparison: int = 0
    tolerance_used: float = 0.0
    
    def __post_init__(self):
        if self.missing_instances is None:
            self.missing_instances = []
        if self.extra_instances is None:
            self.extra_instances = []
    
    @property
    def exact_matches(self) -> int:
        return sum(1 for comp in self.image_comparisons if comp.is_exact_match)
    
    @property
    def pixel_differences(self) -> int:
        return len(self.image_comparisons) - self.exact_matches
    
    @property
    def average_similarity(self) -> float:
        if not self.image_comparisons:
            return 0.0
        return sum(comp.similarity_score for comp in self.image_comparisons) / len(self.image_comparisons)

@dataclass
class ImageComparisonSummary:
    """Overall summary of image comparison results"""
    baseline_file: str
    comparison_files: List[str]
    file_results: List[ImageFileComparisonResult]
    tolerance_used: float
    normalization_applied: bool
    total_images_compared: int
    
    @property
    def overall_exact_matches(self) -> int:
        return sum(result.exact_matches for result in self.file_results)
    
    @property
    def overall_similarity(self) -> float:
        if not self.file_results:
            return 0.0
        total_similarity = sum(result.average_similarity * len(result.image_comparisons) 
                             for result in self.file_results)
        total_comparisons = sum(len(result.image_comparisons) for result in self.file_results)
        return total_similarity / total_comparisons if total_comparisons > 0 else 0.0