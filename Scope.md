:::thinking
The user is clarifying that the minimum requirement is 2 DICOM files (original and at least one comparison), but the tool should support comparing the original against as many comparison files as needed. This is important for the validation logic and error handling.

Let me update the requirements to reflect this clearly.
:::
# DICOM Compare Tool - Requirements & Implementation Plan

## Requirements

### Core Functionality
- **Minimum 2 files required**: At least one original and one comparison file
- **Multi-file comparison**: Support unlimited comparison files via multiple `-f` flags
- **DICOM extraction**: Decompress ZIP files and discover DICOM files
- **Study matching**: Match DICOM instances across different exports using UIDs
- **Tag comparison**: Compare DICOM tags between matched instances against the baseline (first file)
- **Difference detection**: Identify missing/extra instances and tag differences

### Output Requirements
- **Terminal summary**: Rich formatted console output with statistics and highlights
- **CSV reporting**: Optional CSV export via `-r/--report` flag
- **Excel reporting** (Stretch): Enhanced Excel reports with charts and graphs

### CLI Interface
```bash
# Minimum usage (2 files)
dicomcompare -f original.zip -f export1.zip

# Multiple comparisons against original
dicomcompare -f original.zip -f export1.zip -f export2.zip -f export3.zip -r ./reports/comparison.csv

# Error case (only 1 file)
dicomcompare -f original.zip  # Should show error: "At least 2 files required for comparison"
```

## Implementation Steps

### 1. **Project Setup & Dependencies**
```python
# Core dependencies
typer          # CLI framework
pydicom        # DICOM file handling
rich           # Terminal formatting
pathlib        # Path handling

# Reporting dependencies
pandas         # Data manipulation
openpyxl       # Excel export (stretch goal)
matplotlib     # Charts for Excel (stretch goal)
```

### 2. **Core Architecture**

#### **CLI Layer (main.py)**
- Typer CLI setup with multiple file inputs
- **Validation**: Ensure minimum 2 files provided
- Report path validation and CSV/Excel format detection
- Orchestrate the comparison workflow with first file as baseline
- Handle temporary directory cleanup

#### **Data Extraction (dicom_extractor.py)**
- ZIP file extraction to temporary directories
- Recursive DICOM file discovery
- Error handling for corrupted/invalid files

#### **DICOM Organization (dicom_loader.py)**
- Load DICOM files using pydicom
- Build hierarchical data structure: Study → Series → Instance
- Create lookup indices using:
  - StudyInstanceUID
  - SeriesInstanceUID
  - SOPInstanceUID

#### **Comparison Engine (dicom_comparator.py)**
- **Baseline Comparison Model**: First file (`-f`) is the reference/original
- **Instance Matching Algorithm**:
  - Primary: SOPInstanceUID
  - Fallback: SeriesInstanceUID + InstanceNumber
  - Handle orphaned instances
- **Tag Comparison Logic**:
  - Compare each comparison file against the baseline
  - Track differences per comparison file
  - Handle DICOM sequences and nested structures
  - Track private tags separately

#### **Data Models (models.py)**
```python
@dataclass
class DicomInstance:
    sop_instance_uid: str
    series_instance_uid: str
    study_instance_uid: str
    tags: Dict[str, Any]
    file_path: Path
    source_file: str  # Which input file this came from

@dataclass
class ComparisonResult:
    baseline_file: str
    comparison_files: List[str]
    matched_instances: Dict[str, InstanceComparison]  # Key: SOPInstanceUID
    missing_instances: Dict[str, List[DicomInstance]]  # Per comparison file
    extra_instances: Dict[str, List[DicomInstance]]    # Per comparison file
    summary_stats: ComparisonSummary
```

### 3. **Comparison Logic**

#### **Baseline vs Multiple Comparisons**
- **First file** = Baseline/Original (reference truth)
- **Subsequent files** = Comparison exports to validate
- For each comparison file:
  - Match instances against baseline
  - Compare all DICOM tags against baseline values
  - Track differences specific to that comparison

#### **Instance Level Comparison**
```python
# Comparison structure
baseline_instance vs comparison1_instance
baseline_instance vs comparison2_instance  
baseline_instance vs comparison3_instance
# etc.
```

#### **Difference Categories**
- **Value differences**: Same tag, different values between baseline and comparison
- **Missing tags**: Tag present in baseline but missing in comparison
- **Extra tags**: Tag present in comparison but missing in baseline
- **Missing instances**: Instances in baseline but not in comparison
- **Extra instances**: Instances in comparison but not in baseline

### 4. **Reporting System**

#### **Terminal Output (Rich Formatting)**
```
╭─ DICOM Comparison Summary ─────────────────────────╮
│ Baseline: original.zip                             │
│ Comparisons: export1.zip, export2.zip             │
│ Total Studies: 2                                   │
│ Total Instances: 1,247                             │
╰────────────────────────────────────────────────────╯

╭─ Comparison Results ───────────────────────────────╮
│                                                    │
│ 📁 export1.zip vs baseline:                       │
│   ✅ Perfect Matches: 1,200 (96.2%)                │
│   ⚠️  Tag Differences: 45 (3.6%)                   │
│   ❌ Missing Instances: 2 (0.2%)                   │
│                                                    │
│ 📁 export2.zip vs baseline:                       │
│   ✅ Perfect Matches: 1,156 (92.7%)                │
│   ⚠️  Tag Differences: 89 (7.1%)                   │
│   ❌ Missing Instances: 2 (0.2%)                   │
╰────────────────────────────────────────────────────╯

╭─ Most Common Differences ──────────────────────────╮
│ PatientName: 45 instances across 2 files          │
│ StudyDate: 23 instances across 1 file             │
│ SeriesDescription: 12 instances across 2 files    │
╰────────────────────────────────────────────────────╯
```

#### **CSV Report Structure**
```csv
BaselineFile,ComparisonFile,SOPInstanceUID,StudyInstanceUID,SeriesInstanceUID,TagName,BaselineValue,ComparisonValue,DifferenceType
original.zip,export1.zip,1.2.3.4.5,1.2.3.4,1.2.3.5,PatientName,John Doe,J. Doe,VALUE_DIFF
original.zip,export1.zip,1.2.3.4.6,1.2.3.4,1.2.3.5,StudyDate,20240101,,MISSING_TAG
original.zip,export2.zip,1.2.3.4.5,1.2.3.4,1.2.3.5,PatientName,John Doe,John Smith,VALUE_DIFF
```

### 5. **CLI Validation**

#### **Input Validation Logic**
```python
def validate_inputs(files: List[Path]) -> None:
    if len(files) < 2:
        typer.echo("❌ Error: At least 2 files required for comparison", err=True)
        typer.echo("Usage: dicomcompare -f baseline.zip -f comparison1.zip [-f comparison2.zip ...]")
        raise typer.Exit(1)
    
    for file in files:
        if not file.exists():
            typer.echo(f"❌ Error: File not found: {file}", err=True)
            raise typer.Exit(1)
        
        if not file.suffix.lower() == '.zip':
            typer.echo(f"❌ Error: Only ZIP files supported: {file}", err=True)
            raise typer.Exit(1)
```

### 6. **Stretch Goal: Excel Reporting**

#### **Enhanced Excel Features**
- **Multiple worksheets**:
  - Summary sheet with baseline vs each comparison
  - Per-comparison detailed differences
  - Instance-level comparison matrix
- **Charts per comparison**:
  - Match percentage by comparison file
  - Most common differing tags
  - Instance count comparisons

### 7. **Usage Examples**

```bash
# Minimum usage (original + 1 comparison)
dicomcompare -f original.zip -f export_method1.zip

# Multiple export methods against original
dicomcompare -f original.zip -f method1.zip -f method2.zip -f method3.zip

# With reporting
dicomcompare -f original.zip -f method1.zip -f method2.zip -r ./analysis.csv

# Error cases
dicomcompare -f only_one_file.zip  # Error: minimum 2 files required
dicomcompare  # Error: no files provided
```

This clarifies that the tool treats the first file as the baseline/original and compares all subsequent files against it, with a minimum requirement of 2 files total.
