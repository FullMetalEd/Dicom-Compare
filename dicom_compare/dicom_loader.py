import pydicom
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
from rich.console import Console
from rich.progress import track

from dicom_compare.models import DicomInstance
from dicom_compare.dicom_extractor import DicomExtractor

console = Console()

@dataclass
class DicomSeries:
    """Represents a DICOM series"""
    series_instance_uid: str
    series_description: str
    modality: str
    instances: Dict[str, DicomInstance] = field(default_factory=dict)

@dataclass 
class DicomStudy:
    """Represents a DICOM study"""
    study_instance_uid: str
    study_description: str
    patient_id: str
    patient_name: str
    study_date: str
    series: Dict[str, DicomSeries] = field(default_factory=dict)

class DicomLoader:
    """Loads and organizes DICOM files into hierarchical structure"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.failed_files = []
    
    def load_dicom_files(self, root_path: Path, source_file_name: str) -> Dict[str, DicomStudy]:
        """
        Load all DICOM files from directory and organize by Study -> Series -> Instance
        
        Args:
            root_path: Root directory containing DICOM files
            source_file_name: Name of source ZIP file for tracking
            
        Returns:
            Dictionary of studies keyed by StudyInstanceUID
        """  
        
        # Find all DICOM files
        extractor = DicomExtractor()
        dicom_files = extractor.find_dicom_files(root_path)
        
        studies = {}
        self.failed_files = []
        
        # Load each DICOM file
        for file_path in track(dicom_files, description=f"Loading DICOMs from {source_file_name[:20]}..."):
            try:
                dicom_instance = self._load_dicom_file(file_path, source_file_name)
                if dicom_instance:
                    self._organize_instance(dicom_instance, studies)
            except Exception as e:
                self.failed_files.append((file_path, str(e)))
                console.print(f"⚠️  Failed to load {file_path.name}: {str(e)}", style="yellow")
        
        if self.failed_files:
            console.print(f"⚠️  {len(self.failed_files)} files failed to load", style="yellow")
        
        return studies
    
    def _load_dicom_file(self, file_path: Path, source_file_name: str) -> Optional[DicomInstance]:
        """
        Load single DICOM file and extract relevant information
        
        Args:
            file_path: Path to DICOM file
            source_file_name: Name of source ZIP file
            
        Returns:
            DicomInstance or None if failed to load
        """
        try:
            # Load DICOM file
            ds = pydicom.dcmread(file_path, force=True)
            
            # Extract required UIDs
            sop_instance_uid = self._safe_get_tag(ds, 'SOPInstanceUID')
            series_instance_uid = self._safe_get_tag(ds, 'SeriesInstanceUID') 
            study_instance_uid = self._safe_get_tag(ds, 'StudyInstanceUID')
            
            if not all([sop_instance_uid, series_instance_uid, study_instance_uid]):
                console.print(f"⚠️  Missing required UIDs in {file_path.name}", style="yellow")
                return None
            
            # Extract all tags for comparison
            tags = self._extract_all_tags(ds)
            
            return DicomInstance(
                sop_instance_uid=sop_instance_uid,
                series_instance_uid=series_instance_uid,
                study_instance_uid=study_instance_uid,
                tags=tags,
                file_path=file_path,
                source_file=source_file_name
            )
            
        except Exception as e:
            raise Exception(f"Failed to load DICOM file: {str(e)}")
    
    def _safe_get_tag(self, ds: pydicom.Dataset, tag_name: str, default: str = "") -> str:
        """Safely get tag value from DICOM dataset"""
        try:
            if hasattr(ds, tag_name):
                value = getattr(ds, tag_name)
                return str(value) if value is not None else default
            return default
        except:
            return default
    
    def _extract_all_tags(self, ds: pydicom.Dataset) -> Dict[str, Any]:
        """
        Extract all DICOM tags for comparison
        
        Args:
            ds: pydicom Dataset
            
        Returns:
            Dictionary of tag values
        """
        tags = {}
        
        for element in ds:
            try:
                # Skip pixel data and large binary elements
                if element.tag in [(0x7fe0, 0x0010)]:  # Pixel Data
                    continue
                
                tag_name = f"({element.tag.group:04x},{element.tag.element:04x})"
                keyword = element.keyword if element.keyword else tag_name
                
                # Handle different value types
                if element.VR == 'SQ':  # Sequence
                    tags[keyword] = self._process_sequence(element.value)
                elif hasattr(element, 'value'):
                    if isinstance(element.value, bytes):
                        # Convert bytes to hex string for comparison
                        tags[keyword] = element.value.hex() if len(element.value) < 1000 else f"<binary:{len(element.value)} bytes>"
                    else:
                        tags[keyword] = element.value
                else:
                    tags[keyword] = str(element)
                    
            except Exception as e:
                # Skip problematic tags
                continue
        
        return tags
    
    def _process_sequence(self, sequence: List) -> List[Dict]:
        """Process DICOM sequence elements"""
        processed_seq = []
        try:
            for item in sequence[:10]:  # Limit to first 10 items to avoid huge sequences
                if hasattr(item, '__iter__'):
                    item_dict = {}
                    for element in item:
                        if element.keyword:
                            item_dict[element.keyword] = str(element.value)
                    processed_seq.append(item_dict)
            return processed_seq
        except:
            return ["<sequence processing failed>"]
    
    def _organize_instance(self, instance: DicomInstance, studies: Dict[str, DicomStudy]) -> None:
        """
        Organize DICOM instance into hierarchical structure
        
        Args:
            instance: DicomInstance to organize
            studies: Dictionary of studies to add to
        """
        study_uid = instance.study_instance_uid
        series_uid = instance.series_instance_uid
        
        # Create study if it doesn't exist
        if study_uid not in studies:
            studies[study_uid] = DicomStudy(
                study_instance_uid=study_uid,
                study_description=instance.tags.get('StudyDescription', ''),
                patient_id=instance.tags.get('PatientID', ''),
                patient_name=instance.tags.get('PatientName', ''),
                study_date=instance.tags.get('StudyDate', '')
            )
        
        study = studies[study_uid]
        
        # Create series if it doesn't exist
        if series_uid not in study.series:
            study.series[series_uid] = DicomSeries(
                series_instance_uid=series_uid,
                series_description=instance.tags.get('SeriesDescription', ''),
                modality=instance.tags.get('Modality', '')
            )
        
        series = study.series[series_uid]
        
        # Add instance to series
        series.instances[instance.sop_instance_uid] = instance

    def load_dicom_files(self, root_path: Path, source_file_name: str) -> Dict[str, DicomStudy]:
        """Load all DICOM files from directory and organize by Study -> Series -> Instance"""
        
        # Find all DICOM files
        extractor = DicomExtractor(verbose=self.verbose)
        dicom_files = extractor.find_dicom_files(root_path)
        
        studies = {}
        self.failed_files = []
        successful_loads = 0
        
        # Load each DICOM file
        for i, file_path in enumerate(dicom_files):
            try:
                if self.verbose:
                    console.print(f"   Loading {i+1}/{len(dicom_files)}: {file_path.name}...", style="dim")
                
                dicom_instance = self._load_dicom_file(file_path, source_file_name)
                if dicom_instance:
                    self._organize_instance(dicom_instance, studies)
                    successful_loads += 1
                    if self.verbose:
                        console.print(f"   ✅ Loaded: {dicom_instance.sop_instance_uid}", style="green")
                elif self.verbose:
                    console.print(f"   ❌ Failed to create instance from {file_path.name}", style="red")
                    
            except Exception as e:
                self.failed_files.append((file_path, str(e)))
                if self.verbose:
                    console.print(f"   ❌ Failed to load {file_path.name}: {str(e)}", style="red")
        
        if self.verbose:
            console.print(f"📊 Successfully loaded {successful_loads} instances", style="green")
            
            if self.failed_files:
                console.print(f"⚠️  {len(self.failed_files)} files failed to load:", style="yellow")
                for failed_file, error in self.failed_files[:3]:
                    console.print(f"     {failed_file.name}: {error}", style="dim")
                if len(self.failed_files) > 3:
                    console.print(f"     ... and {len(self.failed_files) - 3} more failures", style="dim")
            
            # Debug: Show what we loaded
            total_instances = 0
            for study_uid, study in studies.items():
                study_instances = sum(len(series.instances) for series in study.series.values())
                total_instances += study_instances
                console.print(f"   📁 Study {study_uid[:30]}...: {len(study.series)} series, {study_instances} instances", style="cyan")
            
            console.print(f"🎯 Total organized instances: {total_instances}", style="bold green")
        elif self.failed_files:
            # Always show failures even in non-verbose mode
            console.print(f"⚠️  {len(self.failed_files)} files failed to load", style="yellow")
        
        return studies