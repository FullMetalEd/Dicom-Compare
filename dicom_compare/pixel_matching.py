import hashlib
import numpy as np
from typing import Dict, Any, Optional
from rich.console import Console
import pydicom

console = Console()


class PixelMatchingError(Exception):
    """Exception raised when pixel data cannot be extracted or processed"""
    pass


def create_pixel_hash(dicom_instance) -> str:
    """
    Create MD5 hash from pixel data for exact matching

    Args:
        dicom_instance: DicomInstance with pixel data

    Returns:
        MD5 hash string of pixel data

    Raises:
        PixelMatchingError: If pixel data cannot be extracted
    """
    try:
        # Load the DICOM file to access pixel data
        ds = pydicom.dcmread(dicom_instance.file_path, force=True)

        if not hasattr(ds, 'pixel_array'):
            raise PixelMatchingError(f"No pixel data found in {dicom_instance.file_path}")

        pixel_array = ds.pixel_array

        # Convert to bytes and hash
        pixel_bytes = pixel_array.tobytes()
        hash_md5 = hashlib.md5(pixel_bytes)

        return hash_md5.hexdigest()

    except Exception as e:
        raise PixelMatchingError(f"Failed to extract pixel hash from {dicom_instance.file_path}: {str(e)}")


def create_pixel_fingerprint(dicom_instance) -> Dict[str, Any]:
    """
    Create statistical fingerprint from pixel data for similarity matching

    Args:
        dicom_instance: DicomInstance with pixel data

    Returns:
        Dictionary with statistical features of pixel data

    Raises:
        PixelMatchingError: If pixel data cannot be extracted
    """
    try:
        # Load the DICOM file to access pixel data
        ds = pydicom.dcmread(dicom_instance.file_path, force=True)

        if not hasattr(ds, 'pixel_array'):
            raise PixelMatchingError(f"No pixel data found in {dicom_instance.file_path}")

        pixel_array = ds.pixel_array

        # Calculate statistical features
        fingerprint = {
            'shape': pixel_array.shape,
            'mean': float(np.mean(pixel_array)),
            'std': float(np.std(pixel_array)),
            'min': float(np.min(pixel_array)),
            'max': float(np.max(pixel_array)),
            'median': float(np.median(pixel_array)),
            'histogram': np.histogram(pixel_array, bins=50)[0].tolist()  # 50-bin histogram
        }

        return fingerprint

    except Exception as e:
        raise PixelMatchingError(f"Failed to extract pixel fingerprint from {dicom_instance.file_path}: {str(e)}")


def fingerprints_match(fp1: Dict[str, Any], fp2: Dict[str, Any], tolerance: float = 1e-6) -> bool:
    """
    Compare two pixel fingerprints for similarity

    Args:
        fp1: First fingerprint
        fp2: Second fingerprint
        tolerance: Tolerance for floating point comparisons

    Returns:
        True if fingerprints match within tolerance
    """
    # Check shape first (must be exact)
    if fp1['shape'] != fp2['shape']:
        return False

    # Check statistical measures within tolerance
    for key in ['mean', 'std', 'min', 'max', 'median']:
        if abs(fp1[key] - fp2[key]) > tolerance:
            return False

    # Check histogram correlation
    hist1 = np.array(fp1['histogram'])
    hist2 = np.array(fp2['histogram'])

    # Calculate correlation coefficient
    correlation = np.corrcoef(hist1, hist2)[0, 1]

    # Require very high correlation (>0.999) for match
    if np.isnan(correlation) or correlation < 0.999:
        return False

    return True


def create_fingerprint_key(fingerprint: Dict[str, Any]) -> str:
    """
    Create a string key from fingerprint for lookup purposes

    Args:
        fingerprint: Pixel fingerprint dictionary

    Returns:
        String representation suitable for dictionary keys
    """
    # Use shape and basic stats to create a composite key
    shape_str = "x".join(map(str, fingerprint['shape']))
    stats_str = f"{fingerprint['mean']:.3f}_{fingerprint['std']:.3f}_{fingerprint['min']}_{fingerprint['max']}"

    return f"{shape_str}_{stats_str}"