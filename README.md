# DICOM Compare Tool

A powerful CLI tool for comparing DICOM studies from different ZIP exports to identify differences and troubleshoot export inconsistencies at both metadata and pixel data levels.

## Overview

The DICOM Compare tool helps medical imaging professionals and DICOM system administrators validate DICOM exports by comparing studies from different systems or export methodologies. This is particularly useful for:

- **Troubleshooting export functionality** - Identify which tags or pixels differ between export methods
- **System validation** - Ensure DICOM exports maintain data integrity
- **Migration testing** - Verify data consistency when moving between systems
- **Quality assurance** - Compare original studies with processed/anonymized versions
- **Image integrity validation** - Verify pixel data preservation across different export methods

## Features

### 🏷️ **Tag Comparison**
- ✅ **Multi-file comparison** - Compare one baseline against multiple comparison files
- ✅ **Recursive ZIP extraction** - Handles nested folder structures in ZIP files
- ✅ **Comprehensive tag analysis** - Compares all DICOM tags including sequences
- ✅ **Rich terminal output** - Beautiful formatted results with statistics
- ✅ **CSV/Excel reporting** - Detailed exportable reports with charts
- ✅ **Instance matching** - Matches DICOM instances using SOPInstanceUID
- ✅ **Difference categorization** - Identifies missing, extra, and modified tags

### 🖼️ **Image Comparison**
- ✅ **Pixel-level validation** - Compare actual image pixel data
- ✅ **Tolerance support** - Allow minor differences (useful for lossy compression)
- ✅ **DICOM normalization** - Apply rescale slope/intercept and windowing
- ✅ **Similarity scoring** - Calculate percentage of matching pixels
- ✅ **Statistical analysis** - RMSE, max/mean differences, and more
- ✅ **Dimension validation** - Detect image size differences
- ✅ **Missing pixel data detection** - Identify instances without image data

### 📊 **Reporting & Analytics**
- ✅ **Professional Excel reports** with charts and conditional formatting
- ✅ **CSV exports** for further analysis
- ✅ **Terminal dashboards** with color-coded results
- ✅ **Quality grading** (A+ to D) for export assessment
- ✅ **Statistical breakdowns** by difference type and impact level

## Installation

### Prerequisites

#### Nix

Support for Nix flakes out of the box. You can add it to your flake like this:

Add the input:
```nix
dicom-compare.url = "github:FullMetalEd/Dicom-Compare";
```

Then you add it as a package in the packages section of your modules in the nixosConfiguration:
```nix
modules = [
            # List of the config files this profile needs.
            ./configuration.nix
            (
              {nixpkgs, ...}:
                {
                  environment.systemPackages = [
                    inputs.dicom-compare.packages."${systemSettings.system}".default
                  ];
                }
            )
          ];
```

#### Run as a python module from source

**uv packages manager required.**

Download the repo, and run ```uv sync``` this will download and setup the venv you need.
you can then run commands like ```uv run dicom_compare/main.py --help```, this will print the command help information.


### Install Dependencies

```bash
# Using uv (recommended)
uv add typer[all] pydicom rich pandas openpyxl matplotlib numpy

# Or using pip
pip install typer[all] pydicom rich pandas openpyxl matplotlib numpy
```

### Or run without installing from Nix
```nix
nix run github:FullMetalEd/Dicom-Compare -- --help
```

## Quick Start

### Tag Comparison
```bash
# Compare DICOM metadata tags
dicom-compare compare -f original.zip -f export1.zip

# Compare original against multiple exports with reporting
dicom-compare compare -f original.zip -f method1.zip -f method2.zip -r analysis.xlsx

# Verbose output for debugging
dicom-compare compare -f original.zip -f export1.zip -v
```

### Image Comparison
```bash
# Compare image pixel data (exact match)
dicom-compare image -f original.zip -f export1.zip

# Allow small differences (useful for lossy compression)
dicom-compare image -f original.zip -f export1.zip -t 1.0

# Image comparison with Excel report
dicom-compare image -f original.zip -f export1.zip -r image_analysis.xlsx

# Disable DICOM normalization
dicom-compare image -f original.zip -f export1.zip --no-normalize
```

### Inspection
```bash
# See what's inside ZIP files before comparing
dicom-compare inspect -f study1.zip -f study2.zip
```

## Command Reference

### `compare` - Tag Comparison

```bash
dicom-compare compare [OPTIONS]
```

**Options:**
- `-f, --file PATH` - ZIP files to compare (minimum 2 required, first is baseline)
- `-r, --report PATH` - Save detailed report to CSV/Excel file
- `-v, --verbose` - Enable verbose debugging output
- `--help` - Show help message

**What it compares:**
- All DICOM metadata tags
- Tag values, presence/absence
- Instance matching by SOPInstanceUID
- Study/Series organization

### `image` - Image Pixel Data Comparison

```bash
dicom-compare image [OPTIONS]
```

**Options:**
- `-f, --file PATH` - ZIP files to compare (minimum 2 required, first is baseline)
- `-r, --report PATH` - Save image comparison report to CSV/Excel file
- `-t, --tolerance FLOAT` - Tolerance for pixel differences (default: 0.0 = exact match)
- `--normalize/--no-normalize` - Apply DICOM normalization (default: enabled)
- `-v, --verbose` - Enable verbose debugging output
- `--help` - Show help message

**What it compares:**
- Actual pixel values in DICOM images
- Image dimensions and data types
- Statistical similarity measures
- Pixel-level differences with tolerance

**Tolerance Examples:**
```bash
# Exact pixel match only
dicom-compare image -f original.zip -f export.zip -t 0.0

# Allow differences up to 1 pixel value (good for minor compression)
dicom-compare image -f original.zip -f export.zip -t 1.0

# Allow larger differences (useful for lossy compression)
dicom-compare image -f original.zip -f export.zip -t 5.0
```

**Normalization:**
- **Enabled (default)**: Applies DICOM rescale slope/intercept and windowing
- **Disabled**: Compares raw pixel values as stored in the file

### `inspect` - ZIP Content Inspector

```bash
dicom-compare inspect [OPTIONS]
```

**Options:**
- `-f, --file PATH` - ZIP files to inspect

## Understanding the Results

### Tag Comparison Output

```
╭─ 📋 DICOM Comparison Summary ─╮
│ Baseline: original.zip         │
│ Comparisons: 2                 │
│ Total Studies: 1               │
│ Total Instances: 1,247         │
╰────────────────────────────────╯

🔍 Detailed Comparison Results
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
┃ File                           ┃ Perfect Matches ┃ Tag Differences ┃ Missing Instances ┃ Extra Instances ┃ Data    ┃
┃                                ┃                 ┃                 ┃                   ┃                 ┃ Integrity┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
│ export1.zip                    │ 1,200 (96.2%)   │ 47 (3.8%)       │ 0 (0.0%)          │ 0 (0.0%)        │ 96.2%   │
│ export2.zip                    │ 1,156 (92.7%)   │ 91 (7.3%)       │ 0 (0.0%)          │ 0 (0.0%)        │ 92.7%   │
└────────────────────────────────┴─────────────────┴─────────────────┴───────────────────┴─────────────────┴─────────┘
```

### Image Comparison Output

```
╭─ 🖼️ DICOM Image Comparison Summary ─╮
│ Baseline: original.zip               │
│ Comparison Mode: Image Pixel Data    │
│ Tolerance: 1.0                       │
│ Normalization: Applied               │
│ Images Compared: 189                 │
╰──────────────────────────────────────╯

🖼️ Image Comparison Results
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━┓
┃ File                    ┃ Exact ┃ Pixel   ┃ Avg         ┃ Missing   ┃ Extra     ┃ Match   ┃
┃                         ┃ Match ┃ Diffs   ┃ Similarity  ┃ Images    ┃ Images    ┃ %       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━┩
│ export1.zip             │ 150   │ 39      │ 95.2%       │ 0         │ 0         │ 79.4%   │
└─────────────────────────┴───────┴─────────┴─────────────┴───────────┴───────────┴─────────┘
```

**Column Meanings:**

**Tag Comparison:**
- **Perfect Matches** - Instances where all tags are identical
- **Tag Differences** - Instances with one or more differing tags
- **Missing Instances** - Instances in baseline but not in comparison
- **Extra Instances** - Instances in comparison but not in baseline
- **Data Integrity** - Overall quality score (0-100%)

**Image Comparison:**
- **Exact Match** - Images with identical pixel values (within tolerance)
- **Pixel Diffs** - Images with pixel value differences
- **Avg Similarity** - Average percentage of matching pixels
- **Missing Images** - Images in baseline but not in comparison
- **Extra Images** - Images in comparison but not in baseline
- **Match %** - Percentage of exactly matching images

### Report Formats

#### CSV Reports
Simple tabular format with all differences, suitable for:
- Filtering and sorting in spreadsheet applications
- Further analysis with data science tools
- Integration with other systems

#### Excel Reports
Professional multi-sheet reports with:
- **Executive Summary** - Key metrics and charts
- **Detailed Results** - Every comparison result
- **Tag/Image Analysis** - Breakdown by difference type
- **Statistics** - Comprehensive statistical analysis
- **Settings & Info** - Configuration and explanations

## Real-World Use Cases

### Scenario 1: Export Method Validation

**Problem:** Testing two different export methods from the same PACS system.

```bash
# Tag comparison to check metadata preservation
dicom-compare compare -f original_export.zip -f new_export_method.zip -r validation.xlsx

# Image comparison to verify pixel data integrity
dicom-compare image -f original_export.zip -f new_export_method.zip -r pixel_validation.xlsx
```

**Expected Results:**
- Tag comparison: High percentage of perfect matches (>95%)
- Image comparison: Exact pixel matches or very high similarity (>99%)

### Scenario 2: Lossy Compression Analysis

**Problem:** Evaluating the impact of JPEG compression on DICOM images.

```bash
# Compare with tolerance for compression artifacts
dicom-compare image -f uncompressed.zip -f jpeg_compressed.zip -t 2.0 -r compression_analysis.xlsx
```

**Expected Results:**
- Some pixel differences due to compression
- Similarity scores depend on compression level
- Statistical analysis shows compression impact

### Scenario 3: Anonymization Validation

**Problem:** Verifying that anonymization properly removes/modifies patient data while preserving clinical data.

```bash
# Tag comparison to check anonymization
dicom-compare compare -f original.zip -f anonymized.zip -r anonymization_check.xlsx

# Image comparison to ensure pixel data is unchanged
dicom-compare image -f original.zip -f anonymized.zip -r image_integrity_check.xlsx
```

**Expected Results:**
- Tag comparison: Differences in patient-related tags, clinical data unchanged
- Image comparison: Perfect pixel matches (anonymization shouldn't affect images)

### Scenario 4: System Migration Testing

**Problem:** Ensuring data integrity when migrating between DICOM systems.

```bash
# Comprehensive validation
dicom-compare compare -f source_system.zip -f target_system.zip -r migration_tags.xlsx
dicom-compare image -f source_system.zip -f target_system.zip -r migration_images.xlsx
```

**Expected Results:**
- Most instances should match perfectly
- Acceptable differences in system-specific tags
- Critical clinical tags and pixel data must be identical

## Troubleshooting

### Common Issues

#### "No DICOM files found"
```bash
# Use inspect to see ZIP contents
dicom-compare inspect -f yourfile.zip

# Common causes:
# - ZIP contains folders but no actual DICOM files
# - Files don't have DICOM headers
# - Files are compressed or encrypted
```

#### "Only a few instances compared from large ZIP"
```bash
# Enable verbose mode to see extraction details
dicom-compare compare -f file1.zip -f file2.zip -v

# Common causes:
# - DICOM files are in nested folders not being discovered
# - Files are corrupted or non-standard format
# - Permission issues during extraction
```

#### "High pixel differences but tags match"
This often indicates:
- **Lossy compression** applied to one set
- **Different bit depths** (16-bit vs 8-bit)
- **Normalization differences** - try `--no-normalize`
- **Different transfer syntaxes**

#### "Low similarity scores"
- Check if normalization should be disabled: `--no-normalize`
- Increase tolerance for minor differences: `-t 1.0` or higher
- Verify you're comparing the same study data

### Performance Tips

- **Large studies**: Use verbose mode (`-v`) to monitor progress
- **Multiple comparisons**: Process one comparison at a time for large datasets
- **Memory usage**: Image comparison loads pixel data into memory - monitor RAM usage
- **Image comparison**: Much slower than tag comparison due to pixel processing

## File Format Support

- **Input**: ZIP files containing DICOM studies
- **DICOM Detection**: Automatic detection of DICOM files regardless of extension
- **Nested Folders**: Full support for complex directory structures
- **Output**: CSV reports (basic) and Excel reports (advanced with charts)

## Development & Contributing

### Project Structure
```
dicom_compare/
├── __init__.py
├── main.py              # CLI entry point with multiple commands
├── models.py            # Tag comparison data structures
├── image_models.py      # Image comparison data structures
├── dicom_extractor.py   # ZIP extraction logic
├── dicom_loader.py      # DICOM file discovery and loading
├── dicom_comparator.py  # Tag comparison logic
├── image_comparator.py  # Image comparison logic
├── image_command.py     # Image comparison command implementation
└── utils.py             # Helper functions
```

### Running from Source
```bash
# Clone repository
git clone https://github.com/FullMetalEd/Dicom-Compare.git
cd Dicom-Compare

# Install dependencies
uv sync

# Run directly
uv run dicom_compare/main.py --help
```

### Building with Nix
```bash
# Build package
nix build .#dicom-compare

# Run from source
nix run . -- --help

# Development shell
nix develop
```

## License

MIT License - see LICENSE file for details.

## Changelog

### v0.2.0 (Latest)
- ✅ **Added image pixel data comparison** - New `image` command
- ✅ **Multi-command CLI structure** - `compare`, `image`, `inspect`
- ✅ **Tolerance support** for image comparison
- ✅ **DICOM normalization** options
- ✅ **Enhanced Excel reports** with charts and conditional formatting
- ✅ **Statistical analysis** for image similarities
- ✅ **Improved error handling** and progress reporting

### v0.1.0
- ✅ **Basic tag comparison** functionality
- ✅ **ZIP extraction and DICOM discovery**
- ✅ **CSV reporting**
- ✅ **Terminal output with Rich formatting**
- ✅ **Multi-file comparison support**

---

For more information, bug reports, or feature requests, please visit the [GitHub repository](https://github.com/FullMetalEd/Dicom-Compare).