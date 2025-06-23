import zipfile
import tempfile
from pathlib import Path
from typing import List, Optional
from rich.console import Console

console = Console()

class DicomExtractor:
    """Handles extraction of ZIP files and discovery of DICOM files"""
    
    def __init__(self):
        self.dicom_extensions = {'.dcm', '.dicom', '.dic', ''}  # Include files with no extension
    
    def extract_zip(self, zip_path: Path, extract_to: Path) -> Path:
        """
        Extract ZIP file to specified directory
        
        Args:
            zip_path: Path to ZIP file
            extract_to: Directory to extract to
            
        Returns:
            Path to extracted content
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_to)
            
            return extract_to
            
        except zipfile.BadZipFile:
            raise ValueError(f"Invalid ZIP file: {zip_path}")
        except Exception as e:
            raise ValueError(f"Failed to extract {zip_path}: {str(e)}")
    
    def find_dicom_files(self, root_path: Path) -> List[Path]:
        """
        Recursively find all DICOM files in directory
        
        Args:
            root_path: Root directory to search
            
        Returns:
            List of paths to DICOM files
        """
        dicom_files = []
        
        for file_path in root_path.rglob('*'):
            if file_path.is_file() and self._is_likely_dicom(file_path):
                dicom_files.append(file_path)
        
        return sorted(dicom_files)  # Sort for consistent ordering
    
    def _is_likely_dicom(self, file_path: Path) -> bool:
        """
        Check if file is likely a DICOM file based on extension and content
        
        Args:
            file_path: Path to file to check
            
        Returns:
            True if likely DICOM file
        """
        # Check extension first
        if file_path.suffix.lower() in self.dicom_extensions:
            # For files with DICOM extensions or no extension, check content
            return self._check_dicom_header(file_path)
        
        return False
    
    def _check_dicom_header(self, file_path: Path) -> bool:
        """
        Check if file has DICOM header
        
        Args:
            file_path: Path to file to check
            
        Returns:
            True if file has DICOM header
        """
        try:
            with open(file_path, 'rb') as f:
                # Skip to position 128 where DICOM prefix should be
                f.seek(128)
                prefix = f.read(4)
                return prefix == b'DICM'
        except:
            return False