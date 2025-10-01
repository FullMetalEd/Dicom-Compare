import pydicom
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict
from rich.console import Console
from rich.progress import track

from dicom_compare.models import (
    HierarchicalDicomData, PatientInfo, StudyInfo, SeriesInfo, InstanceInfo, TagInfo
)
from dicom_compare.dicom_extractor import DicomExtractor
from dicom_compare.utils import create_temp_dir, cleanup_temp_dirs

console = Console()

class HierarchicalDicomLoader:
    """Loads DICOM files and organizes into hierarchical structure with tag categorization"""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.failed_files = []

        # Define tag categorization
        self.patient_tags = self._get_patient_level_tags()
        self.study_tags = self._get_study_level_tags()
        self.series_tags = self._get_series_level_tags()
        self.instance_tags = self._get_instance_level_tags()

    def load_hierarchical_data(self, files: List[Path]) -> HierarchicalDicomData:
        """
        Load DICOM files from ZIP archives and organize hierarchically

        Args:
            files: List of ZIP file paths to process

        Returns:
            HierarchicalDicomData with organized DICOM metadata
        """
        data = HierarchicalDicomData()
        temp_dirs = []

        try:
            extractor = DicomExtractor(verbose=False)  # Always quiet for hierarchical loading

            for file in files:
                if self.verbose:
                    console.print(f"📦 Processing {file.name}...", style="cyan")

                temp_dir = create_temp_dir()
                temp_dirs.append(temp_dir)

                # Extract ZIP file
                extracted_path, stats = extractor.extract_zip(file, temp_dir)
                dicom_files = extractor.find_dicom_files(extracted_path)

                if not dicom_files:
                    if self.verbose:
                        console.print(f"⚠️  No DICOM files found in {file.name}", style="yellow")
                    continue

                # Process DICOM files
                file_desc = f"Loading {file.name}" if len(files) > 1 else "Loading DICOM files"

                if self.verbose:
                    # Show progress bar when verbose
                    for dicom_file in track(dicom_files, description=file_desc):
                        try:
                            self._process_dicom_file(dicom_file, str(file), extracted_path, data)
                        except Exception as e:
                            self.failed_files.append((dicom_file, str(e)))
                            console.print(f"❌ Failed to process {dicom_file.name}: {e}", style="red")
                else:
                    # Silent processing when not verbose
                    for dicom_file in dicom_files:
                        try:
                            self._process_dicom_file(dicom_file, str(file), extracted_path, data)
                        except Exception as e:
                            self.failed_files.append((dicom_file, str(e)))

            # Post-process: Update counts and relationships
            self._update_hierarchy_counts(data)

            if self.failed_files:
                if self.verbose:
                    console.print(f"⚠️  Failed to process {len(self.failed_files)} files", style="yellow")
                    # Show details of failed files in verbose mode
                    for failed_file, error in self.failed_files[:5]:  # Show first 5
                        console.print(f"   {failed_file.name}: {error}", style="dim")
                    if len(self.failed_files) > 5:
                        console.print(f"   ... and {len(self.failed_files) - 5} more", style="dim")
                # In non-verbose mode, failed files are silently ignored

            return data

        finally:
            cleanup_temp_dirs(temp_dirs)

    def _process_dicom_file(self, dicom_file: Path, source_file: str,
                          extracted_path: Path, data: HierarchicalDicomData):
        """Process a single DICOM file and add to hierarchical data"""

        # Read DICOM dataset
        ds = pydicom.dcmread(dicom_file, stop_before_pixels=True)

        # Extract hierarchical identifiers
        patient_id = self._safe_get_tag(ds, 'PatientID', 'UNKNOWN')
        study_uid = self._safe_get_tag(ds, 'StudyInstanceUID', 'UNKNOWN')
        series_uid = self._safe_get_tag(ds, 'SeriesInstanceUID', 'UNKNOWN')
        sop_uid = self._safe_get_tag(ds, 'SOPInstanceUID', 'UNKNOWN')

        # Categorize tags by hierarchy level
        categorized_tags = self._categorize_tags(ds)

        # Create/update Patient
        if patient_id not in data.patients:
            data.patients[patient_id] = PatientInfo(patient_id=patient_id)

        patient = data.patients[patient_id]
        patient.file_sources.add(source_file)
        patient.demographics.update(categorized_tags['patient'])
        if study_uid not in patient.studies:
            patient.studies.append(study_uid)

        # Create/update Study
        if study_uid not in data.studies:
            data.studies[study_uid] = StudyInfo(study_uid=study_uid, patient_id=patient_id)

        study = data.studies[study_uid]
        study.file_sources.add(source_file)
        study.metadata.update(categorized_tags['study'])
        if series_uid not in study.series:
            study.series.append(series_uid)

        # Create/update Series
        if series_uid not in data.series:
            data.series[series_uid] = SeriesInfo(series_uid=series_uid, study_uid=study_uid)

        series = data.series[series_uid]
        series.file_sources.add(source_file)
        series.metadata.update(categorized_tags['series'])
        if sop_uid not in series.instances:
            series.instances.append(sop_uid)

        # Create Instance
        data.instances[sop_uid] = InstanceInfo(
            sop_uid=sop_uid,
            series_uid=series_uid,
            metadata=categorized_tags['instance'],
            file_path=dicom_file.relative_to(extracted_path),
            source_file=source_file
        )

    def _categorize_tags(self, ds) -> Dict[str, Dict[str, TagInfo]]:
        """Categorize DICOM tags by hierarchy level"""
        categorized = {
            'patient': {},
            'study': {},
            'series': {},
            'instance': {}
        }

        for tag in ds:
            keyword = tag.keyword
            if not keyword:
                continue

            tag_info = TagInfo(
                keyword=keyword,
                name=tag.name,
                vr=tag.VR,
                tag_number=f"({tag.tag.group:04X},{tag.tag.element:04X})",
                value=self._format_tag_value(tag.value),
                description=tag.name
            )

            # Assign to appropriate hierarchy level
            if keyword in self.patient_tags:
                categorized['patient'][keyword] = tag_info
            elif keyword in self.study_tags:
                categorized['study'][keyword] = tag_info
            elif keyword in self.series_tags:
                categorized['series'][keyword] = tag_info
            else:
                categorized['instance'][keyword] = tag_info

        return categorized

    def _update_hierarchy_counts(self, data: HierarchicalDicomData):
        """Update instance counts throughout the hierarchy"""

        # Update series instance counts
        for series in data.series.values():
            series.instances = list(set(series.instances))  # Remove duplicates

        # Update study instance counts
        for study in data.studies.values():
            study.series = list(set(study.series))  # Remove duplicates
            study.total_instances = sum(
                len(data.series[series_uid].instances)
                for series_uid in study.series
                if series_uid in data.series
            )

        # Update patient instance counts
        for patient in data.patients.values():
            patient.studies = list(set(patient.studies))  # Remove duplicates
            patient.total_instances = sum(
                data.studies[study_uid].total_instances
                for study_uid in patient.studies
                if study_uid in data.studies
            )

    def _safe_get_tag(self, ds, tag_keyword: str, default: str = 'UNKNOWN') -> str:
        """Safely extract a tag value from DICOM dataset"""
        try:
            value = getattr(ds, tag_keyword, default)
            return str(value) if value else default
        except Exception:
            return default

    def _format_tag_value(self, value) -> str:
        """Format tag value for display"""
        if value is None:
            return "NULL"

        # Handle sequences
        if hasattr(value, '__iter__') and not isinstance(value, (str, bytes)):
            try:
                if len(value) > 3:
                    return f"[{len(value)} items]"
                else:
                    return str(list(value))
            except:
                return str(value)

        # Handle large binary data
        if isinstance(value, bytes) and len(value) > 100:
            return f"<{len(value)} bytes>"

        return str(value)

    def _get_patient_level_tags(self) -> Set[str]:
        """Return set of patient-level DICOM tag keywords"""
        return {
            'PatientName', 'PatientID', 'PatientBirthDate', 'PatientSex',
            'PatientAge', 'PatientWeight', 'PatientSize', 'PatientComments',
            'PatientBirthName', 'OtherPatientNames', 'ResponsiblePerson',
            'ResponsiblePersonRole', 'PatientIdentityRemoved',
            'DeidentificationMethod', 'EthnicGroup', 'PatientReligiousPreference',
            'PatientSpeciesDescription', 'PatientBreedDescription',
            'BreedRegistrationSequence', 'ResponsibleOrganization'
        }

    def _get_study_level_tags(self) -> Set[str]:
        """Return set of study-level DICOM tag keywords"""
        return {
            'StudyInstanceUID', 'StudyDate', 'StudyTime', 'ReferringPhysicianName',
            'StudyID', 'AccessionNumber', 'StudyDescription', 'PhysiciansOfRecord',
            'NameOfPhysiciansReadingStudy', 'AdmittingDiagnosesDescription',
            'PatientAge', 'PatientSize', 'PatientWeight', 'Occupation',
            'AdditionalPatientHistory', 'InstitutionName', 'InstitutionAddress',
            'ReferringPhysicianAddress', 'ReferringPhysicianTelephoneNumbers',
            'InstitutionalDepartmentName', 'PhysiciansOfRecordIdentificationSequence',
            'PerformingPhysicianIdentificationSequence'
        }

    def _get_series_level_tags(self) -> Set[str]:
        """Return set of series-level DICOM tag keywords"""
        return {
            'SeriesInstanceUID', 'SeriesNumber', 'SeriesDate', 'SeriesTime',
            'SeriesDescription', 'Modality', 'PerformingPhysicianName',
            'ProtocolName', 'SeriesType', 'OperatorsName', 'BodyPartExamined',
            'PatientPosition', 'Laterality', 'ImageType', 'ContrastBolusAgent',
            'ScanOptions', 'MRAcquisitionType', 'SequenceName', 'AngioFlag',
            'SliceThickness', 'SpacingBetweenSlices', 'DataCollectionDiameter',
            'ReconstructionDiameter', 'DistanceSourceToDetector', 'GantryDetectorTilt',
            'TableHeight', 'RotationDirection', 'ExposureTime', 'XRayTubeCurrent',
            'Exposure', 'FilterType', 'GeneratorPower', 'FocalSpots',
            'ConvolutionKernel', 'PatientOrientation'
        }

    def _get_instance_level_tags(self) -> Set[str]:
        """Return set of instance-level DICOM tag keywords"""
        return {
            'SOPInstanceUID', 'SOPClassUID', 'InstanceNumber', 'ImagePositionPatient',
            'ImageOrientationPatient', 'FrameOfReferenceUID', 'PositionReferenceIndicator',
            'SliceLocation', 'ImageComments', 'QualityControlImage', 'BurnedInAnnotation',
            'LossyImageCompression', 'LossyImageCompressionRatio', 'LossyImageCompressionMethod',
            'IconImageSequence', 'PresentationLUTShape', 'IrradiationEventUID',
            'Rows', 'Columns', 'BitsAllocated', 'BitsStored', 'HighBit',
            'PixelRepresentation', 'PhotometricInterpretation', 'SamplesPerPixel',
            'PlanarConfiguration', 'PixelAspectRatio', 'SmallestImagePixelValue',
            'LargestImagePixelValue', 'RedPaletteColorLookupTableDescriptor',
            'WindowCenter', 'WindowWidth', 'WindowCenterWidthExplanation',
            'RescaleIntercept', 'RescaleSlope', 'RescaleType',
            'ContentDate', 'ContentTime', 'InstanceCreationDate', 'InstanceCreationTime',
            'InstanceCreatorUID', 'SOPInstanceStatus', 'SOPAuthorizationComment'
        }