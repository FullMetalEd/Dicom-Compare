from typing import Dict, List, Set, Any
from collections import defaultdict
from rich.console import Console

from models import (
    DicomInstance, TagDifference, InstanceComparison, 
    FileComparisonResult, DifferenceType, ComparisonSummary
)
from dicom_loader import DicomStudy

console = Console()

class DicomComparator:
    """Handles comparison logic between DICOM studies"""
    
    def __init__(self):
        self.ignored_tags = {
            # Tags that commonly differ and might not be relevant for comparison
            'InstanceCreationDate',
            'InstanceCreationTime',
            'ImplementationVersionName',
            'SourceApplicationEntityTitle',
            'StationName',
            'InstitutionName',
            'InstitutionalDepartmentName'
        }
    
    def compare_studies(
        self, 
        baseline_studies: Dict[str, DicomStudy],
        comparison_studies: Dict[str, DicomStudy],
        baseline_file: str,
        comparison_file: str
    ) -> FileComparisonResult:
        """
        Compare two sets of DICOM studies
        
        Args:
            baseline_studies: Baseline studies (reference)
            comparison_studies: Studies to compare against baseline
            baseline_file: Name of baseline file
            comparison_file: Name of comparison file
            
        Returns:
            FileComparisonResult containing all comparison data
        """
        # Build instance lookup for both studies
        baseline_instances = self._build_instance_lookup(baseline_studies)
        comparison_instances = self._build_instance_lookup(comparison_studies)
        
        # Find matched, missing, and extra instances  
        matched_instances = []
        missing_instances = []
        extra_instances = []
        
        baseline_sop_uids = set(baseline_instances.keys())
        comparison_sop_uids = set(comparison_instances.keys())
        
        # Find matches and compare
        common_sop_uids = baseline_sop_uids.intersection(comparison_sop_uids)
        for sop_uid in common_sop_uids:
            baseline_instance = baseline_instances[sop_uid]
            comparison_instance = comparison_instances[sop_uid]
            
            instance_comparison = self._compare_instances(
                baseline_instance, comparison_instance, 
                baseline_file, comparison_file
            )
            matched_instances.append(instance_comparison)
        
        # Find missing instances (in baseline but not in comparison)
        missing_sop_uids = baseline_sop_uids - comparison_sop_uids
        for sop_uid in missing_sop_uids:
            missing_instances.append(baseline_instances[sop_uid])
        
        # Find extra instances (in comparison but not in baseline)
        extra_sop_uids = comparison_sop_uids - baseline_sop_uids
        for sop_uid in extra_sop_uids:
            extra_instances.append(comparison_instances[sop_uid])
        
        return FileComparisonResult(
            baseline_file=baseline_file,
            comparison_file=comparison_file,
            matched_instances=matched_instances,
            missing_instances=missing_instances,
            extra_instances=extra_instances,
            total_instances_baseline=len(baseline_instances),
            total_instances_comparison=len(comparison_instances)
        )
    
    def _build_instance_lookup(self, studies: Dict[str, DicomStudy]) -> Dict[str, DicomInstance]:
        """Build flat lookup of instances by SOPInstanceUID"""
        instances = {}
        for study in studies.values():
            for series in study.series.values():
                for instance in series.instances.values():
                    instances[instance.sop_instance_uid] = instance
        return instances
    
    def _compare_instances(
        self,
        baseline: DicomInstance,
        comparison: DicomInstance,
        baseline_file: str,
        comparison_file: str
    ) -> InstanceComparison:
        """
        Compare two DICOM instances
        
        Args:
            baseline: Baseline instance
            comparison: Comparison instance
            baseline_file: Name of baseline file
            comparison_file: Name of comparison file
            
        Returns:
            InstanceComparison with all differences
        """
        tag_differences = []
        
        # Get all unique tags from both instances
        all_tags = set(baseline.tags.keys()) | set(comparison.tags.keys())
        
        for tag_keyword in all_tags:
            # Skip ignored tags
            if tag_keyword in self.ignored_tags:
                continue
            
            baseline_value = baseline.tags.get(tag_keyword)
            comparison_value = comparison.tags.get(tag_keyword)
            
            # Determine difference type
            if baseline_value is None and comparison_value is not None:
                # Tag exists in comparison but not baseline
                tag_diff = TagDifference(
                    tag_name=tag_keyword,
                    tag_keyword=tag_keyword,
                    baseline_value=None,
                    comparison_value=comparison_value,
                    difference_type=DifferenceType.EXTRA_TAG,
                    vr="UK"  # Unknown VR
                )
                tag_differences.append(tag_diff)
                
            elif baseline_value is not None and comparison_value is None:
                # Tag exists in baseline but not comparison
                tag_diff = TagDifference(
                    tag_name=tag_keyword,
                    tag_keyword=tag_keyword,
                    baseline_value=baseline_value,
                    comparison_value=None,
                    difference_type=DifferenceType.MISSING_TAG,
                    vr="UK"
                )
                tag_differences.append(tag_diff)
                
            elif baseline_value != comparison_value:
                # Values are different
                diff_type = DifferenceType.VALUE_DIFF
                
                # Check if it's a type difference
                if type(baseline_value) != type(comparison_value):
                    diff_type = DifferenceType.TYPE_DIFF
                
                tag_diff = TagDifference(
                    tag_name=tag_keyword,
                    tag_keyword=tag_keyword,
                    baseline_value=baseline_value,
                    comparison_value=comparison_value,
                    difference_type=diff_type,
                    vr="UK"
                )
                tag_differences.append(tag_diff)
        
        is_perfect_match = len(tag_differences) == 0
        
        return InstanceComparison(
            sop_instance_uid=baseline.sop_instance_uid,
            baseline_file=baseline_file,
            comparison_file=comparison_file,
            tag_differences=tag_differences,
            is_perfect_match=is_perfect_match
        )