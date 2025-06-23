from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from pathlib import Path
from enum import Enum

class DifferenceType(Enum):
    VALUE_DIFF = "VALUE_DIFF"
    MISSING_TAG = "MISSING_TAG"
    EXTRA_TAG = "EXTRA_TAG"
    TYPE_DIFF = "TYPE_DIFF"

@dataclass
class DicomInstance:
    sop_instance_uid: str
    series_instance_uid: str
    study_instance_uid: str
    tags: Dict[str, Any]
    file_path: Path
    source_file: str

@dataclass
class TagDifference:
    tag_name: str
    tag_keyword: str
    baseline_value: Any
    comparison_value: Any
    difference_type: DifferenceType
    vr: str  # Value Representation

@dataclass
class InstanceComparison:
    sop_instance_uid: str
    baseline_file: str
    comparison_file: str
    tag_differences: List[TagDifference]
    is_perfect_match: bool

@dataclass
class FileComparisonResult:
    baseline_file: str
    comparison_file: str
    matched_instances: List[InstanceComparison]
    missing_instances: List[DicomInstance]  # In baseline but not in comparison
    extra_instances: List[DicomInstance]    # In comparison but not in baseline
    total_instances_baseline: int
    total_instances_comparison: int

@dataclass
class ComparisonSummary:
    baseline_file: str
    comparison_files: List[str]
    file_results: List[FileComparisonResult]
    total_instances: int
    total_studies: int
    total_series: int