# DICOM Compare Tool

A powerful CLI tool for comparing DICOM studies from different ZIP exports to identify differences and troubleshoot export inconsistencies.

## Overview

The DICOM Compare tool helps medical imaging professionals and DICOM system administrators compare DICOM studies exported from different systems or using different export methodologies. This is particularly useful for:

- **Troubleshooting export functionality** - Identify which tags differ between export methods
- **System validation** - Ensure DICOM exports maintain data integrity
- **Migration testing** - Verify data consistency when moving between systems
- **Quality assurance** - Compare original studies with processed/anonymized versions

## Features

- ✅ **Multi-file comparison** - Compare one baseline against multiple comparison files
- ✅ **Recursive ZIP extraction** - Handles nested folder structures in ZIP files
- ✅ **Comprehensive tag analysis** - Compares all DICOM tags including sequences
- ✅ **Rich terminal output** - Beautiful formatted results with statistics
- ✅ **CSV reporting** - Detailed exportable reports for further analysis
- ✅ **Instance matching** - Matches DICOM instances using SOPInstanceUID
- ✅ **Difference categorization** - Identifies missing, extra, and modified tags
- ✅ **Verbose debugging** - Detailed logs for troubleshooting

## Installation

### Prerequisites

- Python 3.12 or higher
- `uv` package manager (recommended) or `pip`

### Install Dependencies

```bash
# Using uv (recommended)
uv add typer[all] pydicom rich pandas openpyxl matplotlib

# Or using pip
pip install typer[all] pydicom rich pandas openpyxl matplotlib
```

### Download the Tool

```bash
git clone <repository-url>
cd dicomcompare
```

## Quick Start

### Basic Comparison
```bash
# Compare two ZIP files
uv run main.py compare -f original.zip -f export1.zip

# Compare original against multiple exports
uv run main.py compare -f original.zip -f method1.zip -f method2.zip -f method3.zip
```

### With Reporting
```bash
# Generate CSV report
uv run main.py compare -f original.zip -f export1.zip -r results.csv

# Verbose output with debugging
uv run main.py compare -f original.zip -f export1.zip -r results.csv -v
```

### Inspect ZIP Contents
```bash
# See what's inside ZIP files before comparing
uv run main.py inspect -f original.zip -f export1.zip
```

## Command Reference

### `compare` - Main Comparison Command

```bash
uv run main.py compare [OPTIONS]
```

**Options:**
- `-f, --file PATH` - ZIP files to compare (minimum 2 required, first is baseline)
- `-r, --report PATH` - Save detailed report to CSV file
- `-v, --verbose` - Enable verbose debugging output
- `--help` - Show help message

**Examples:**
```bash
# Basic comparison
uv run main.py compare -f baseline.zip -f comparison.zip

# Multiple comparisons with report
uv run main.py compare -f original.zip -f export1.zip -f export2.zip -r analysis.csv

# Verbose debugging
uv run main.py compare -f original.zip -f export1.zip -v
```

### `inspect` - ZIP Content Inspector

```bash
uv run main.py inspect [OPTIONS]
```

**Options:**
- `-f, --file PATH` - ZIP files to inspect

**Example:**
```bash
uv run main.py inspect -f study1.zip -f study2.zip
```

## Understanding the Results

### Terminal Output

The tool displays results in three main sections:

#### 1. Summary Panel
```
╭─ 📋 DICOM Comparison Summary ─╮
│ Baseline: original.zip         │
│ Comparisons: 2                 │
│ Total Studies: 1               │
│ Total Instances: 1,247         │
╰────────────────────────────────╯
```

#### 2. Results Table
```
🔍 Comparison Results
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ File                           ┃ Perfect Matches ┃ Tag Differences ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ export1.zip                    │ 1,200 (96.2%)   │ 45 (3.6%)       │
│ export2.zip                    │ 1,156 (92.7%)   │ 89 (7.1%)       │
└────────────────────────────────┴─────────────────┴─────────────────┘
```

**Column Meanings:**
- **Perfect Matches** - Instances where all tags are identical
- **Tag Differences** - Instances with one or more differing tags
- **Missing Instances** - Instances in baseline but not in comparison
- **Extra Instances** - Instances in comparison but not in baseline
- **Match %** - Percentage of perfectly matching instances

### CSV Report Structure

The CSV report contains detailed information about every difference found:

```csv
ReportType,BaselineFile,ComparisonFile,SOPInstanceUID,TagName,TagKeyword,BaselineValue,ComparisonValue,DifferenceType,VR
```

#### Report Types

| ReportType | Description |
|------------|-------------|
| `SUMMARY` | High-level statistics and counts |
| `TAG_DIFFERENCE` | Individual tag differences between matched instances |
| `MISSING_INSTANCE` | Instances present in baseline but missing in comparison |
| `EXTRA_INSTANCE` | Instances present in comparison but missing in baseline |

#### Difference Types

| DifferenceType | Meaning | Example |
|----------------|---------|---------|
| `MISSING_TAG` | Tag exists in baseline but not in comparison | Baseline: "ISO_IR 100", Comparison: "NULL" |
| `EXTRA_TAG` | Tag exists in comparison but not in baseline | Baseline: "NULL", Comparison: "FOR PRESENTATION" |
| `VALUE_DIFF` | Tag exists in both but with different values | Baseline: "John Doe", Comparison: "J. Doe" |
| `TYPE_DIFF` | Tag exists in both but with different data types | Baseline: "123", Comparison: 123 |

## Real-World Scenarios

### Scenario 1: Export Method Validation

**Problem:** Testing two different export methods from the same PACS system.

```bash
uv run main.py compare -f original_export.zip -f new_export_method.zip -r validation.csv
```

**Expected Results:**
- High percentage of perfect matches (>95%)
- Minor differences in system-generated tags
- No missing instances

### Scenario 2: Anonymization Validation

**Problem:** Verifying that anonymization properly removes/modifies patient data.

```bash
uv run main.py compare -f original.zip -f anonymized.zip -r anonymization_check.csv
```

**Expected Results:**
- `VALUE_DIFF` for patient-related tags (PatientName, PatientID)
- `MISSING_TAG` for tags that should be removed
- Clinical data should remain unchanged

### Scenario 3: System Migration Testing

**Problem:** Ensuring data integrity when migrating between DICOM systems.

```bash
uv run main.py compare -f source_system.zip -f target_system.zip -r migration_validation.csv
```

**Expected Results:**
- Most instances should match perfectly
- Differences in system-specific tags are acceptable
- Critical clinical tags must be identical

## Troubleshooting

### Common Issues

#### 1. "No DICOM files found"
```bash
# Use inspect to see ZIP contents
uv run main.py inspect -f yourfile.zip

# Common causes:
# - ZIP contains folders but no actual DICOM files
# - Files don't have DICOM headers
# - Files are compressed or encrypted
```

#### 2. "Only 1 instance loaded from large ZIP"
```bash
# Enable verbose mode to see extraction details
uv run main.py compare -f file1.zip -f file2.zip -v

# Common causes:
# - DICOM files are in nested folders not being discovered
# - Files are corrupted or non-standard format
# - Permission issues during extraction
```

#### 3. "No differences found but expected some"
```bash
# Check if comparison level is too lenient
# Certain tags might be in the ignored list

# Common ignored tags:
# - InstanceCreationDate/Time
# - StationName
# - InstitutionName
# - SoftwareVersions
```

#### 4. "CSV report is empty"
The CSV only contains differences. If files are identical, you'll see:
```csv
ReportType,BaselineFile,ComparisonFile,SOPInstanceUID,TagName,TagKeyword,BaselineValue,ComparisonValue,DifferenceType,VR
INFO,INFO,INFO,INFO,NO_DIFFERENCES_FOUND,NO_DIFFERENCES_FOUND,All instances match perfectly,All instances match perfectly,INFO,INFO
```

### Performance Tips

- **Large studies**: Use verbose mode (`-v`) to monitor progress
- **Multiple comparisons**: Process one comparison at a time for large datasets
- **Memory usage**: Tool loads all instances into memory - monitor RAM usage for very large studies

## Interpreting Results for Different Use Cases

### Quality Assurance
- **Look for**: Unexpected `VALUE_DIFF` in critical clinical tags
- **Accept**: Differences in timestamps, system identifiers
- **Red flags**: Missing instances, changes in pixel data

### System Validation
- **Look for**: High match percentages (>98%)
- **Accept**: Differences in implementation-specific tags
- **Red flags**: Systematic missing tags across all instances

### Export Troubleshooting
- **Look for**: Patterns in missing tags
- **Accept**: Some tags may be intentionally excluded
- **Red flags**: Missing required DICOM tags

## File Format Support

- **Input**: ZIP files containing DICOM studies
- **DICOM Detection**: Automatic detection of DICOM files regardless of extension
- **Nested Folders**: Full support for complex directory structures
- **Output**: CSV reports (Excel support coming soon)

## Contributing

Issues and feature requests are welcome! Common enhancement areas:
- Excel reporting with charts
- Custom tag filtering
- Performance optimizations for large datasets
- Additional matching algorithms

---

For more information or support, please check the documentation or open an issue in the repository.