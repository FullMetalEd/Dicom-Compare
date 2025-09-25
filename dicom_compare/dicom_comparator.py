from typing import Dict, List, Set, Any
from collections import defaultdict
from rich.console import Console

from dicom_compare.models import (
    DicomInstance, TagDifference, InstanceComparison,
    FileComparisonResult, DifferenceType, ComparisonSummary
)
from dicom_compare.dicom_loader import DicomStudy
from dicom_compare.pixel_matching import (
    create_pixel_hash, create_pixel_fingerprint, fingerprints_match,
    create_fingerprint_key, PixelMatchingError
)

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
        comparison_file: str,
        matching_mode: str = "uid"
    ) -> FileComparisonResult:
        """
        Compare two sets of DICOM studies

        Args:
            baseline_studies: Baseline studies (reference)
            comparison_studies: Studies to compare against baseline
            baseline_file: Name of baseline file
            comparison_file: Name of comparison file
            matching_mode: Matching strategy ('uid', 'hash', 'fingerprint')

        Returns:
            FileComparisonResult containing all comparison data
        """
        # Build instance lookup for both studies
        baseline_instances = self._build_instance_lookup(baseline_studies, matching_mode)
        comparison_instances = self._build_instance_lookup(comparison_studies, matching_mode)
        
        # Find matched, missing, and extra instances  
        matched_instances = []
        missing_instances = []
        extra_instances = []
        
        baseline_sop_uids = set(baseline_instances.keys())
        comparison_sop_uids = set(comparison_instances.keys())
        
        # Find matches and compare
        if matching_mode == "fingerprint":
            # Special handling for fingerprint matching
            matched_instances = self._match_by_fingerprint(
                baseline_instances, comparison_instances,
                baseline_file, comparison_file
            )
            # For fingerprint mode, remaining logic needs different approach
            baseline_matched = {comp.sop_instance_uid for comp in matched_instances}
            comparison_matched = set()
            for comp in matched_instances:
                # Find corresponding comparison instance
                for key, instance in comparison_instances.items():
                    if hasattr(instance, '_pixel_fingerprint'):
                        baseline_instances_list = [inst for inst in baseline_instances.values()
                                                 if inst.sop_instance_uid == comp.sop_instance_uid]
                        if baseline_instances_list:
                            baseline_inst = baseline_instances_list[0]
                            if (hasattr(baseline_inst, '_pixel_fingerprint') and
                                fingerprints_match(baseline_inst._pixel_fingerprint, instance._pixel_fingerprint)):
                                comparison_matched.add(instance.sop_instance_uid)
                                break

            # Missing/extra for fingerprint mode
            all_baseline = {inst.sop_instance_uid: inst for inst in baseline_instances.values()}
            all_comparison = {inst.sop_instance_uid: inst for inst in comparison_instances.values()}

            missing_sop_uids = set(all_baseline.keys()) - baseline_matched
            extra_sop_uids = set(all_comparison.keys()) - comparison_matched

        else:
            # Standard UID/hash matching
            common_keys = baseline_sop_uids.intersection(comparison_sop_uids)
            for key in common_keys:
                baseline_instance = baseline_instances[key]
                comparison_instance = comparison_instances[key]

                instance_comparison = self._compare_instances(
                    baseline_instance, comparison_instance,
                    baseline_file, comparison_file
                )
                matched_instances.append(instance_comparison)

            # Find missing instances (in baseline but not in comparison)
            missing_sop_uids = baseline_sop_uids - comparison_sop_uids
            # Find extra instances (in comparison but not in baseline)
            extra_sop_uids = comparison_sop_uids - baseline_sop_uids

        # Handle missing and extra instances based on matching mode
        if matching_mode == "fingerprint":
            # For fingerprint mode, use the SOPInstanceUID-based sets calculated above
            for sop_uid in missing_sop_uids:
                missing_instances.append(all_baseline[sop_uid])
            for sop_uid in extra_sop_uids:
                extra_instances.append(all_comparison[sop_uid])
        else:
            # For UID/hash mode, use key-based matching
            for key in missing_sop_uids:
                missing_instances.append(baseline_instances[key])
            for key in extra_sop_uids:
                extra_instances.append(comparison_instances[key])
        
        return FileComparisonResult(
            baseline_file=baseline_file,
            comparison_file=comparison_file,
            matched_instances=matched_instances,
            missing_instances=missing_instances,
            extra_instances=extra_instances,
            total_instances_baseline=len(baseline_instances),
            total_instances_comparison=len(comparison_instances)
        )
    
    def _build_instance_lookup(self, studies: Dict[str, DicomStudy], matching_mode: str = "uid") -> Dict[str, DicomInstance]:
        """Build flat lookup of instances by appropriate matching key"""
        instances = {}
        failed_instances = []

        for study in studies.values():
            for series in study.series.values():
                for instance in series.instances.values():
                    try:
                        if matching_mode == "uid":
                            key = instance.sop_instance_uid
                        elif matching_mode == "hash":
                            key = create_pixel_hash(instance)
                        elif matching_mode == "fingerprint":
                            fingerprint = create_pixel_fingerprint(instance)
                            key = create_fingerprint_key(fingerprint)
                            # Store fingerprint for later comparison
                            instance._pixel_fingerprint = fingerprint
                        else:
                            raise ValueError(f"Unknown matching mode: {matching_mode}")

                        instances[key] = instance

                    except PixelMatchingError as e:
                        failed_instances.append((instance.sop_instance_uid, str(e)))
                        console.print(f"   ❌ Failed to process {instance.file_path.name}: {e}", style="red")
                        continue

        if failed_instances and matching_mode != "uid":
            console.print(f"   ⚠️  {len(failed_instances)} instances failed pixel processing and were skipped", style="yellow")

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
        #if len(baseline.tags) == 0:
        #    console.print(f"⚠️  Baseline instance {baseline.sop_instance_uid} has no tags!", style="yellow")
        #if len(comparison.tags) == 0:
        #   console.print(f"⚠️  Comparison instance {comparison.sop_instance_uid} has no tags!", style="yellow")
        
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
    def debug_instance_tags(self, instance: DicomInstance, max_tags: int = 10) -> None:
        """Debug function to show tags in an instance"""
        console.print(f"Debug tags for {instance.sop_instance_uid}:", style="cyan")
        for i, (tag, value) in enumerate(instance.tags.items()):
            if i >= max_tags:
                console.print(f"   ... and {len(instance.tags) - max_tags} more tags", style="dim")
                break
            console.print(f"   {tag}: {str(value)[:100]}{'...' if len(str(value)) > 100 else ''}", style="dim")

    def _match_by_fingerprint(
        self,
        baseline_instances: Dict[str, DicomInstance],
        comparison_instances: Dict[str, DicomInstance],
        baseline_file: str,
        comparison_file: str
    ) -> List[InstanceComparison]:
        """
        Match instances using pixel fingerprints for similarity-based comparison

        Args:
            baseline_instances: Dictionary of baseline instances (key = fingerprint key)
            comparison_instances: Dictionary of comparison instances (key = fingerprint key)
            baseline_file: Name of baseline file
            comparison_file: Name of comparison file

        Returns:
            List of matched InstanceComparison objects
        """
        matched_instances = []
        used_comparison_keys = set()

        # For each baseline instance, find the best matching comparison instance
        for baseline_key, baseline_instance in baseline_instances.items():
            if not hasattr(baseline_instance, '_pixel_fingerprint'):
                continue

            best_match = None
            best_comparison_key = None

            # Look for exact fingerprint key match first
            if baseline_key in comparison_instances and baseline_key not in used_comparison_keys:
                comparison_instance = comparison_instances[baseline_key]
                if hasattr(comparison_instance, '_pixel_fingerprint'):
                    if fingerprints_match(baseline_instance._pixel_fingerprint,
                                        comparison_instance._pixel_fingerprint):
                        best_match = comparison_instance
                        best_comparison_key = baseline_key

            # If no exact match, search all comparison instances
            if best_match is None:
                for comp_key, comparison_instance in comparison_instances.items():
                    if (comp_key not in used_comparison_keys and
                        hasattr(comparison_instance, '_pixel_fingerprint')):
                        if fingerprints_match(baseline_instance._pixel_fingerprint,
                                            comparison_instance._pixel_fingerprint):
                            best_match = comparison_instance
                            best_comparison_key = comp_key
                            break

            # If we found a match, create comparison
            if best_match is not None:
                instance_comparison = self._compare_instances(
                    baseline_instance, best_match,
                    baseline_file, comparison_file
                )
                matched_instances.append(instance_comparison)
                used_comparison_keys.add(best_comparison_key)

        return matched_instances
