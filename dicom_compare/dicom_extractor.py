import zipfile
import tempfile
import os
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from rich.console import Console
import pydicom

console = Console()

@dataclass
class ExtractionStats:
    """Statistics from ZIP extraction"""
    total_files: int
    total_folders: int
    dicom_files: int
    non_dicom_files: int

class DicomExtractor:
    """Handles extraction of ZIP files and discovery of DICOM files"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.dicom_extensions = {'.dcm', '.dicom', '.dic', ''}
    
    def extract_zip(self, zip_path: Path, extract_to: Path) -> Tuple[Path, ExtractionStats]:
        """Extract ZIP file and return path + extraction statistics"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                
                # Count directories and files
                directories = set()
                files = []
                for item in file_list:
                    if item.endswith('/'):
                        directories.add(item.rstrip('/'))
                    else:
                        files.append(item)
                        # Get directory part
                        dir_part = str(Path(item).parent)
                        if dir_part != '.' and dir_part != '':
                            directories.add(dir_part)
                
                # Show basic summary (always)
                console.print(f"   {zip_path.name}: {len(directories)} folders, {len(files)} files", style="cyan")
                
                if self.verbose:
                    # Show detailed contents only in verbose mode
                    console.print(f"     📂 Directories found:", style="dim")
                    for directory in sorted(directories)[:10]:
                        console.print(f"        {directory}/", style="dim")
                    if len(directories) > 10:
                        console.print(f"        ... and {len(directories) - 10} more directories", style="dim")
                
                zip_ref.extractall(extract_to)
            
            if self.verbose:
                self._debug_directory_structure(extract_to)
            
            # Find DICOM files and create stats
            dicom_files = self.find_dicom_files(extract_to, zip_path.name)
            
            stats = ExtractionStats(
                total_files=len(files),
                total_folders=len(directories),
                dicom_files=len(dicom_files),
                non_dicom_files=len(files) - len(dicom_files)
            )
            
            return extract_to, stats
            
        except zipfile.BadZipFile:
            raise ValueError(f"Invalid ZIP file: {zip_path}")
        except Exception as e:
            raise ValueError(f"Failed to extract {zip_path}: {str(e)}")
    
    def _debug_directory_structure(self, root_path: Path):
        """Debug the extracted directory structure (verbose only)"""
        if not self.verbose:
            return
            
        console.print(f"🗂️  Extracted directory structure:", style="cyan")
        
        total_files = 0
        total_dirs = 0
        
        for item in root_path.rglob('*'):
            relative_path = item.relative_to(root_path)
            if item.is_dir():
                console.print(f"   📁 {relative_path}/", style="blue")
                total_dirs += 1
            else:
                console.print(f"   📄 {relative_path} ({item.stat().st_size} bytes)", style="dim")
                total_files += 1
        
        console.print(f"   Total: {total_dirs} directories, {total_files} files", style="green")
    
    def find_dicom_files(self, root_path: Path, zip_name: str = "") -> List[Path]:
        """Recursively find all DICOM files in directory"""
        if self.verbose:
            console.print(f"🔍 Searching for DICOM files in {root_path}...", style="cyan")
        
        dicom_files = []
        all_files = []
        
        # Use os.walk for reliable recursive directory traversal
        for root, dirs, files in os.walk(root_path):
            root_path_obj = Path(root)
            if self.verbose:
                console.print(f"   📂 Checking: {root_path_obj.relative_to(root_path)}", style="dim")
            
            for file in files:
                file_path = root_path_obj / file
                all_files.append(file_path)
                if self.verbose:
                    console.print(f"      Found: {file} ({file_path.stat().st_size} bytes)", style="dim")
        
        if self.verbose:
            console.print(f"🔍 Total files found: {len(all_files)}", style="green")
        
        # Check each file for DICOM content
        for i, file_path in enumerate(all_files):
            if self.verbose:
                console.print(f"   Checking {i+1}/{len(all_files)}: {file_path.name}...", style="dim")
            
            if self._is_likely_dicom(file_path):
                dicom_files.append(file_path)
                if self.verbose:
                    console.print(f"   ✅ DICOM: {file_path.relative_to(root_path)}", style="green")
            elif self.verbose:
                console.print(f"   ❌ Not DICOM: {file_path.relative_to(root_path)}", style="red")
        
        # Show summary with file type breakdown
        non_dicom_count = len(all_files) - len(dicom_files)
        if zip_name:
            if non_dicom_count > 0:
                console.print(f"   Found {len(dicom_files)} DICOM files ({non_dicom_count} non-DICOM files skipped)", style="green")
            else:
                console.print(f"   Found {len(dicom_files)} DICOM files (all files were DICOM)", style="green")
        else:
            console.print(f"   Found {len(dicom_files)} DICOM files", style="green")
        
        return sorted(dicom_files)
    
    def _is_likely_dicom(self, file_path: Path) -> bool:
        """Check if file is likely a DICOM file"""
        try:
            # Skip obviously non-DICOM files
            skip_extensions = {'.txt', '.xml', '.json', '.log', '.zip', '.rar', '.tar', '.gz', '.md', '.pdf'}
            if file_path.suffix.lower() in skip_extensions:
                if self.verbose:
                    console.print(f"      Skipping {file_path.name} - wrong extension", style="dim")
                return False
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size < 128:
                if self.verbose:
                    console.print(f"      Skipping {file_path.name} - too small ({file_size} bytes)", style="dim")
                return False
            
            # Check DICOM header
            is_dicom = self._check_dicom_header(file_path)
            if self.verbose:
                if is_dicom:
                    console.print(f"      ✅ {file_path.name} is DICOM", style="green")
                else:
                    console.print(f"      ❌ {file_path.name} is not DICOM", style="red")
            
            return is_dicom
            
        except Exception as e:
            if self.verbose:
                console.print(f"      ⚠️  Error checking {file_path.name}: {e}", style="yellow")
            return False
    
    def _check_dicom_header(self, file_path: Path) -> bool:
        """Check if file has DICOM header"""
        try:
            with open(file_path, 'rb') as f:
                file_size = file_path.stat().st_size
                
                # Method 1: Check DICM at position 128
                if file_size >= 132:
                    f.seek(128)
                    prefix = f.read(4)
                    if prefix == b'DICM':
                        if self.verbose:
                            console.print(f"         Found DICM header at position 128", style="dim")
                        return True
                
                # Method 2: Check for DICM anywhere in first 1KB
                f.seek(0)
                header = f.read(min(1024, file_size))
                if b'DICM' in header:
                    if self.verbose:
                        console.print(f"         Found DICM in header", style="dim")
                    return True
                
                # Method 3: Look for DICOM patterns
                dicom_patterns = [b'1.2.840.10008', b'DICOM']
                for pattern in dicom_patterns:
                    if pattern in header:
                        if self.verbose:
                            console.print(f"         Found DICOM pattern: {pattern}", style="dim")
                        return True
                
                # Method 4: Try pydicom parse
                f.seek(0)
                try:
                    ds = pydicom.dcmread(f, stop_before_pixels=True, force=True)
                    if hasattr(ds, 'SOPInstanceUID') or hasattr(ds, 'StudyInstanceUID'):
                        if self.verbose:
                            console.print(f"         Parsed with pydicom", style="dim")
                        return True
                except:
                    pass
                
                if self.verbose:
                    console.print(f"         No DICOM markers found", style="dim")
                return False
                
        except Exception as e:
            if self.verbose:
                console.print(f"         Error reading file: {e}", style="yellow")
            return False