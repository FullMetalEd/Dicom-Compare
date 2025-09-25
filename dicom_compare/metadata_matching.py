from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from rich.console import Console
import hashlib

console = Console()


@dataclass
class MatchResult:
    """Result of a matching attempt"""
    success: bool
    strategy: str
    confidence: float  # 0.0 to 1.0
    match_key: str
    details: str


class MetadataMatchingError(Exception):
    """Exception raised when metadata cannot be extracted for matching"""
    pass


def safe_get_tag(instance, tag_name: str, default=None) -> Any:
    """Safely get a tag value from DICOM instance"""
    return instance.tags.get(tag_name, default)


def create_spatial_key(instance) -> Optional[str]:
    """
    Create spatial matching key using slice location and orientation

    Args:
        instance: DicomInstance

    Returns:
        Spatial key string or None if required tags missing
    """
    try:
        slice_location = safe_get_tag(instance, 'SliceLocation')
        image_orientation = safe_get_tag(instance, 'ImageOrientationPatient')
        pixel_spacing = safe_get_tag(instance, 'PixelSpacing')
        rows = safe_get_tag(instance, 'Rows')
        cols = safe_get_tag(instance, 'Columns')

        # Check if we have essential spatial data
        if slice_location is None:
            return None

        # Build composite key
        orientation_str = ""
        if image_orientation and len(image_orientation) >= 6:
            # Round to 3 decimals to handle minor floating point differences
            orientation_str = "_".join(f"{float(x):.3f}" for x in image_orientation[:6])

        spacing_str = ""
        if pixel_spacing and len(pixel_spacing) >= 2:
            spacing_str = f"{float(pixel_spacing[0]):.3f}x{float(pixel_spacing[1]):.3f}"

        dims_str = f"{rows or 0}x{cols or 0}"

        return f"spatial_{slice_location:.3f}_{orientation_str}_{spacing_str}_{dims_str}"

    except Exception as e:
        console.print(f"   ⚠️  Error creating spatial key for {instance.sop_instance_uid}: {e}", style="yellow")
        return None


def create_acquisition_key(instance) -> Optional[str]:
    """
    Create acquisition matching key using series/instance numbers and timing

    Args:
        instance: DicomInstance

    Returns:
        Acquisition key string or None if required tags missing
    """
    try:
        series_number = safe_get_tag(instance, 'SeriesNumber')
        instance_number = safe_get_tag(instance, 'InstanceNumber')
        slice_thickness = safe_get_tag(instance, 'SliceThickness')
        echo_time = safe_get_tag(instance, 'EchoTime')
        repetition_time = safe_get_tag(instance, 'RepetitionTime')

        # Need at least series and instance numbers
        if series_number is None or instance_number is None:
            return None

        # Build composite key
        key_parts = [f"acq_{series_number}_{instance_number}"]

        if slice_thickness is not None:
            key_parts.append(f"thick_{float(slice_thickness):.2f}")

        if echo_time is not None:
            key_parts.append(f"te_{float(echo_time):.2f}")

        if repetition_time is not None:
            key_parts.append(f"tr_{float(repetition_time):.2f}")

        return "_".join(key_parts)

    except Exception as e:
        console.print(f"   ⚠️  Error creating acquisition key for {instance.sop_instance_uid}: {e}", style="yellow")
        return None


def create_position_key(instance) -> Optional[str]:
    """
    Create position matching key using 3D coordinates

    Args:
        instance: DicomInstance

    Returns:
        Position key string or None if required tags missing
    """
    try:
        image_position = safe_get_tag(instance, 'ImagePositionPatient')

        if not image_position or len(image_position) < 3:
            return None

        # Round to 2 decimals for position matching (typically in mm)
        x, y, z = float(image_position[0]), float(image_position[1]), float(image_position[2])

        return f"pos_{x:.2f}_{y:.2f}_{z:.2f}"

    except Exception as e:
        console.print(f"   ⚠️  Error creating position key for {instance.sop_instance_uid}: {e}", style="yellow")
        return None


def create_sequence_key(instance) -> Optional[str]:
    """
    Create sequence matching key using MR timing parameters

    Args:
        instance: DicomInstance

    Returns:
        Sequence key string or None if required tags missing
    """
    try:
        echo_time = safe_get_tag(instance, 'EchoTime')
        repetition_time = safe_get_tag(instance, 'RepetitionTime')
        flip_angle = safe_get_tag(instance, 'FlipAngle')
        inversion_time = safe_get_tag(instance, 'InversionTime')

        # Need at least one timing parameter
        if all(x is None for x in [echo_time, repetition_time, flip_angle]):
            return None

        key_parts = ["seq"]

        if echo_time is not None:
            key_parts.append(f"te{float(echo_time):.2f}")
        if repetition_time is not None:
            key_parts.append(f"tr{float(repetition_time):.2f}")
        if flip_angle is not None:
            key_parts.append(f"fa{float(flip_angle):.1f}")
        if inversion_time is not None:
            key_parts.append(f"ti{float(inversion_time):.2f}")

        return "_".join(key_parts)

    except Exception as e:
        console.print(f"   ⚠️  Error creating sequence key for {instance.sop_instance_uid}: {e}", style="yellow")
        return None


def create_dimensional_key(instance) -> Optional[str]:
    """
    Create dimensional matching key using image characteristics

    Args:
        instance: DicomInstance

    Returns:
        Dimensional key string or None if required tags missing
    """
    try:
        rows = safe_get_tag(instance, 'Rows')
        cols = safe_get_tag(instance, 'Columns')
        bits_allocated = safe_get_tag(instance, 'BitsAllocated')
        pixel_spacing = safe_get_tag(instance, 'PixelSpacing')
        slice_thickness = safe_get_tag(instance, 'SliceThickness')

        if rows is None or cols is None:
            return None

        key_parts = [f"dim_{rows}x{cols}"]

        if bits_allocated is not None:
            key_parts.append(f"bits{bits_allocated}")

        if pixel_spacing and len(pixel_spacing) >= 2:
            key_parts.append(f"ps{float(pixel_spacing[0]):.3f}x{float(pixel_spacing[1]):.3f}")

        if slice_thickness is not None:
            key_parts.append(f"thick{float(slice_thickness):.2f}")

        return "_".join(key_parts)

    except Exception as e:
        console.print(f"   ⚠️  Error creating dimensional key for {instance.sop_instance_uid}: {e}", style="yellow")
        return None


def try_metadata_matching(instance, strategy: str) -> MatchResult:
    """
    Try to create a matching key using the specified strategy

    Args:
        instance: DicomInstance
        strategy: Matching strategy name

    Returns:
        MatchResult with success status and details
    """
    strategy_map = {
        'spatial': (create_spatial_key, 0.95, "Spatial position and orientation"),
        'acquisition': (create_acquisition_key, 0.85, "Series/instance numbers and timing"),
        'position': (create_position_key, 0.90, "3D spatial coordinates"),
        'sequence': (create_sequence_key, 0.75, "MR sequence parameters"),
        'dimensional': (create_dimensional_key, 0.70, "Image dimensions and characteristics")
    }

    if strategy not in strategy_map:
        return MatchResult(
            success=False,
            strategy=strategy,
            confidence=0.0,
            match_key="",
            details=f"Unknown strategy: {strategy}"
        )

    key_func, confidence, description = strategy_map[strategy]

    try:
        match_key = key_func(instance)

        if match_key is not None:
            return MatchResult(
                success=True,
                strategy=strategy,
                confidence=confidence,
                match_key=match_key,
                details=description
            )
        else:
            return MatchResult(
                success=False,
                strategy=strategy,
                confidence=0.0,
                match_key="",
                details=f"Required tags missing for {description.lower()}"
            )

    except Exception as e:
        return MatchResult(
            success=False,
            strategy=strategy,
            confidence=0.0,
            match_key="",
            details=f"Error in {description.lower()}: {str(e)}"
        )