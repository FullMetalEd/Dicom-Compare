import tempfile
import shutil
from pathlib import Path
from typing import List

def validate_inputs(files: List[Path]) -> None:
    """Validate CLI inputs"""
    if len(files) < 2:
        raise ValueError(
            "At least 2 files required for comparison.\n"
            "Usage: dicomcompare -f baseline.zip -f comparison1.zip [-f comparison2.zip ...]"
        )
    
    for file in files:
        if not file.exists():
            raise ValueError(f"File not found: {file}")
        
        if not file.suffix.lower() == '.zip':
            raise ValueError(f"Only ZIP files supported: {file}")

def create_temp_dir() -> Path:
    """Create temporary directory for extraction"""
    return Path(tempfile.mkdtemp(prefix="dicomcompare_"))

def cleanup_temp_dirs(temp_dirs: List[Path]) -> None:
    """Clean up temporary directories"""
    for temp_dir in temp_dirs:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)