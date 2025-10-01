from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set
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

# Hierarchical inspection models
@dataclass
class TagInfo:
    keyword: str
    name: str
    vr: str
    tag_number: str  # e.g., "(0010,0010)"
    value: Any
    description: Optional[str] = None

@dataclass
class PatientInfo:
    patient_id: str
    demographics: Dict[str, TagInfo] = field(default_factory=dict)
    studies: List[str] = field(default_factory=list)  # Study UIDs
    total_instances: int = 0
    file_sources: Set[str] = field(default_factory=set)  # Which ZIP files contain this patient

@dataclass
class StudyInfo:
    study_uid: str
    patient_id: str
    metadata: Dict[str, TagInfo] = field(default_factory=dict)
    series: List[str] = field(default_factory=list)  # Series UIDs
    total_instances: int = 0
    file_sources: Set[str] = field(default_factory=set)

@dataclass
class SeriesInfo:
    series_uid: str
    study_uid: str
    metadata: Dict[str, TagInfo] = field(default_factory=dict)
    instances: List[str] = field(default_factory=list)  # SOP UIDs
    file_sources: Set[str] = field(default_factory=set)

@dataclass
class InstanceInfo:
    sop_uid: str
    series_uid: str
    file_path: Path
    source_file: str
    metadata: Dict[str, TagInfo] = field(default_factory=dict)

@dataclass
class HierarchicalDicomData:
    patients: Dict[str, PatientInfo] = field(default_factory=dict)
    studies: Dict[str, StudyInfo] = field(default_factory=dict)
    series: Dict[str, SeriesInfo] = field(default_factory=dict)
    instances: Dict[str, InstanceInfo] = field(default_factory=dict)

    def get_stats(self) -> Dict[str, int]:
        """Get summary statistics"""
        return {
            "patients": len(self.patients),
            "studies": len(self.studies),
            "series": len(self.series),
            "instances": len(self.instances)
        }

@dataclass
class SearchResult:
    tag_info: TagInfo
    hierarchy_level: str  # "patient", "study", "series", "instance"
    context_id: str  # PatientID, StudyUID, SeriesUID, or SOPUID
    similarity_score: float
    occurrence_count: int
    sample_values: List[str] = field(default_factory=list)  # Sample values for this tag