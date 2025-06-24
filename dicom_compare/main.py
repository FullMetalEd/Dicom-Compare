import typer
from typing import List, Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint
from collections import defaultdict, Counter

# Excel availability check
try:
    import pandas as pd
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.chart import PieChart, BarChart, Reference
    from openpyxl.chart.series import DataPoint, SeriesLabel
    from openpyxl.utils.dataframe import dataframe_to_rows
    EXCEL_AVAILABLE = True
except ImportError as e:
    EXCEL_AVAILABLE = False
    pd = None
    console = Console()  # Create console here for error message
    console.print(f"⚠️  Excel dependencies not available: {e}", style="yellow")

from dicom_compare.dicom_extractor import DicomExtractor, ExtractionStats
from dicom_compare.dicom_loader import DicomLoader
from dicom_compare.dicom_comparator import DicomComparator
from dicom_compare.models import ComparisonSummary, FileComparisonResult
from dicom_compare.utils import validate_inputs, create_temp_dir, cleanup_temp_dirs
from dicom_compare.image_command import run_image_comparison

app = typer.Typer(
    name="dicomcompare",
    help="Compare DICOM studies from different ZIP exports to identify differences",
    add_completion=False
)

console = Console()

@app.command("image")
def compare_images(
    files: List[Path] = typer.Option(
        ..., 
        "-f", 
        "--file", 
        help="ZIP files to compare (first file is baseline, minimum 2 files required)"
    ),
    report: Optional[Path] = typer.Option(
        None,
        "-r",
        "--report",
        help="Path to save image comparison report (CSV/Excel format)"
    ),
    tolerance: float = typer.Option(
        0.0,
        "-t",
        "--tolerance",
        help="Tolerance for pixel differences (0.0 = exact match, higher = more tolerant)"
    ),
    normalize: bool = typer.Option(
        True,
        "--normalize/--no-normalize",
        help="Apply DICOM normalization (rescale slope/intercept, window/level)"
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Enable verbose output"
    )
):
    """
    Compare DICOM image pixel data between studies.
    
    This command compares the actual pixel values of DICOM images rather than 
    just the metadata tags. Useful for validating that image data is preserved 
    across different export methods.
    """
    run_image_comparison(files, report, tolerance, normalize, verbose)

@app.command()
def inspect(
    files: List[Path] = typer.Option(
        ..., 
        "-f", 
        "--file", 
        help="ZIP files to inspect"
    )
):
    """
    Inspect ZIP files to see what DICOM content they contain.
    """
    console.print("🔍 Inspecting ZIP files...", style="blue")
    
    temp_dirs = []
    try:
        extractor = DicomExtractor()
        
        for file in files:
            console.print(f"\n📦 Inspecting {file.name}:", style="bold cyan")
            
            temp_dir = create_temp_dir()
            temp_dirs.append(temp_dir)
            
            # Extract
            extracted_path = extractor.extract_zip(file, temp_dir)
            
            # Find DICOMs
            dicom_files = extractor.find_dicom_files(extracted_path)
            
            if dicom_files:
                console.print(f"\n✅ Found {len(dicom_files)} DICOM files", style="green")
                
                # Group by directory
                by_directory = defaultdict(list)
                for dicom_file in dicom_files:
                    relative_path = dicom_file.relative_to(extracted_path)
                    directory = str(relative_path.parent)
                    by_directory[directory].append(relative_path.name)
                
                for directory, files in by_directory.items():
                    console.print(f"   📁 {directory}: {len(files)} DICOM files", style="cyan")
                    for dicom_file in files[:3]:  # Show first 3 files per directory
                        console.print(f"      {dicom_file}", style="dim")
                    if len(files) > 3:
                        console.print(f"      ... and {len(files) - 3} more files", style="dim")
                
                # Load first few to check SOPInstanceUIDs
                console.print(f"\n🔍 Checking DICOM content:", style="cyan")
                for i, dicom_file in enumerate(dicom_files[:5]):  # Check first 5
                    try:

                        ds = pydicom.dcmread(dicom_file, stop_before_pixels=True)
                        sop_uid = getattr(ds, 'SOPInstanceUID', 'MISSING')
                        series_uid = getattr(ds, 'SeriesInstanceUID', 'MISSING')
                        relative_path = dicom_file.relative_to(extracted_path)
                        console.print(f"   📄 {relative_path}", style="dim")
                        console.print(f"      SOPInstanceUID = {sop_uid}", style="dim")
                        console.print(f"      SeriesInstanceUID = {series_uid}", style="dim")
                    except Exception as e:
                        console.print(f"   ❌ {dicom_file.name}: Error reading - {e}", style="red")
                
                if len(dicom_files) > 5:
                    console.print(f"   ... and {len(dicom_files) - 5} more DICOM files", style="dim")
            else:
                console.print("❌ No DICOM files found", style="red")
    
    finally:
        cleanup_temp_dirs(temp_dirs)

@app.command()
def compare(
    files: List[Path] = typer.Option(
        ..., 
        "-f", 
        "--file", 
        help="ZIP files to compare (first file is baseline, minimum 2 files required)"
    ),
    report: Optional[Path] = typer.Option(
        None,
        "-r",
        "--report",
        help="Path to save CSV/Excel report (format determined by extension)"
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose",
        help="Enable verbose output"
    )
):
    """
    Compare DICOM studies from ZIP files.
    
    The first file specified with -f is treated as the baseline/original.
    All subsequent files are compared against this baseline.
    """
    
    # Validate inputs
    try:
        validate_inputs(files)
        if report:
            validate_report_path(report)
    except Exception as e:
        console.print(f"❌ {str(e)}", style="red")
        raise typer.Exit(1)
    
    console.print("🔍 Starting DICOM comparison...", style="blue")
    
    temp_dirs = []
    extraction_stats = []
    try:
        # Extract ZIP files
        console.print("📦 Extracting ZIP files...", style="yellow")
        extractor = DicomExtractor(verbose=verbose)
        extracted_paths = []
        
        for file in files:
            temp_dir = create_temp_dir()
            temp_dirs.append(temp_dir)
            extracted_path, stats = extractor.extract_zip(file, temp_dir)
            extracted_paths.append((str(file), extracted_path))
            extraction_stats.append((str(file), stats))
        
        # Load DICOM files
        console.print("🏥 Loading DICOM files...", style="yellow")
        loader = DicomLoader(verbose=verbose)
        loaded_studies = []
        
        for i, (file_name, path) in enumerate(extracted_paths):
            studies = loader.load_dicom_files(path, file_name)
            loaded_studies.append((file_name, studies))
            
            # Show results with extraction context
            total_instances = sum(len(series.instances) for study in studies.values() 
                                for series in study.series.values())
            
            # Get corresponding extraction stats
            _, stats = extraction_stats[i]
            
            if stats.non_dicom_files > 0:
                console.print(f"   {Path(file_name).name}: {total_instances} instances ({stats.dicom_files}/{stats.total_files} files were DICOM)", style="cyan")
            else:
                console.print(f"   {Path(file_name).name}: {total_instances} instances (all {stats.total_files} files were DICOM)", style="cyan")
            
            if verbose:
                console.print(f"     Folders: {stats.total_folders}, DICOM files: {stats.dicom_files}, Skipped: {stats.non_dicom_files}", style="dim")
    
        
        # Compare studies
        console.print("🔍 Comparing DICOM studies...", style="yellow")
        comparator = DicomComparator()
        
        baseline_name, baseline_studies = loaded_studies[0]
        comparison_results = []
        
        for comp_name, comp_studies in loaded_studies[1:]:
            result = comparator.compare_studies(
                baseline_studies, comp_studies, 
                baseline_name, comp_name
            )
            comparison_results.append(result)
        
        if verbose:
            console.print("\n🔍 Comparison Debug Info:", style="cyan")
            for i, (comp_name, comp_studies) in enumerate(loaded_studies[1:]):
                result = comparison_results[i]
                console.print(f"   {Path(comp_name).name}:", style="cyan")
                console.print(f"     Baseline instances: {result.total_instances_baseline}", style="dim")
                console.print(f"     Comparison instances: {result.total_instances_comparison}", style="dim")
                console.print(f"     Matched instances: {len(result.matched_instances)}", style="dim")
                console.print(f"     Perfect matches: {sum(1 for comp in result.matched_instances if comp.is_perfect_match)}", style="dim")
                console.print(f"     Tag differences: {sum(1 for comp in result.matched_instances if not comp.is_perfect_match)}", style="dim")
                console.print(f"     Missing instances: {len(result.missing_instances)}", style="dim")
                console.print(f"     Extra instances: {len(result.extra_instances)}", style="dim")
        
        # Create summary
        summary = create_comparison_summary(baseline_name, comparison_results)
        
        # Display results
        display_terminal_results(summary, console)
        
        # Generate report if requested
        if report:
            console.print(f"📊 Generating report: {report}", style="green")
            generate_report(summary, report)
            console.print(f"✅ Report saved to: {report}", style="green")
        
        console.print("🎉 Comparison completed successfully!", style="green")
        
    except Exception as e:
        console.print(f"❌ Error during comparison: {str(e)}", style="red")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)
    
    finally:
        # Cleanup temporary directories
        cleanup_temp_dirs(temp_dirs)

def validate_report_path(report_path: Path) -> None:
    """Validate report path and format"""
    if not report_path.suffix.lower() in ['.csv', '.xlsx']:
        raise ValueError("Report format must be CSV (.csv) or Excel (.xlsx)")
    
    # Ensure parent directory exists
    report_path.parent.mkdir(parents=True, exist_ok=True)

def create_comparison_summary(baseline_name: str, results: List[FileComparisonResult]) -> ComparisonSummary:
    """Create summary from comparison results"""
    comparison_files = [result.comparison_file for result in results]
    
    # Calculate totals from results
    total_instances = results[0].total_instances_baseline if results else 0
    
    # Count unique studies and series from baseline
    total_studies = 1  # Simplified - we'll improve this later
    total_series = 1   # Simplified - we'll improve this later
    
    return ComparisonSummary(
        baseline_file=baseline_name,
        comparison_files=comparison_files,
        file_results=results,
        total_instances=total_instances,
        total_studies=total_studies,
        total_series=total_series
    )

def display_terminal_results(summary: 'ComparisonSummary', console: Console) -> None:
    """Display formatted results in terminal"""
    # Create summary panel
    summary_text = f"Baseline: {Path(summary.baseline_file).name}\n"
    summary_text += f"Comparisons: {len(summary.comparison_files)}\n"
    summary_text += f"Total Studies: {summary.total_studies}\n"
    summary_text += f"Total Instances: {summary.total_instances}"
    
    console.print(Panel(summary_text, title="📋 DICOM Comparison Summary", expand=False))
    
    # Create comprehensive results table
    table = Table(title="🔍 Detailed Comparison Results")
    table.add_column("File", style="cyan", width=25)
    table.add_column("Perfect\nMatches", style="green", justify="right")
    table.add_column("Tag\nDiffs", style="yellow", justify="right")
    table.add_column("Tag Diff\n%", style="bright_yellow", justify="right")
    table.add_column("Missing\nInstances", style="red", justify="right")
    table.add_column("Missing\n%", style="bright_red", justify="right")  # New
    table.add_column("Extra\nInstances", style="magenta", justify="right")
    table.add_column("Extra\n%", style="bright_magenta", justify="right")  # New
    table.add_column("Data\nIntegrity", style="bright_blue", justify="right")  # New
    
    for result in summary.file_results:
        perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
        tag_diffs = len(result.matched_instances) - perfect_matches
        missing = len(result.missing_instances)
        extra = len(result.extra_instances)
        
        total_baseline = result.total_instances_baseline
        total_comparison = result.total_instances_comparison
        
        # Calculate percentages
        tag_diff_pct = (tag_diffs / total_baseline * 100) if total_baseline > 0 else 0
        missing_pct = (missing / total_baseline * 100) if total_baseline > 0 else 0
        extra_pct = (extra / total_comparison * 100) if total_comparison > 0 else 0
        
        # Calculate data integrity score (0-100%)
        integrity_score = _calculate_data_integrity(result)
        
        # Color code integrity score
        if integrity_score >= 95:
            integrity_style = "bright_green"
        elif integrity_score >= 85:
            integrity_style = "green"
        elif integrity_score >= 70:
            integrity_style = "yellow"
        else:
            integrity_style = "red"
        
        table.add_row(
            Path(result.comparison_file).name,
            str(perfect_matches),
            str(tag_diffs),
            f"{tag_diff_pct:.1f}%",
            str(missing),
            f"{missing_pct:.1f}%",
            str(extra),
            f"{extra_pct:.1f}%",
            f"[{integrity_style}]{integrity_score:.1f}%[/{integrity_style}]"
        )
    
    console.print(table)
    
    # Add detailed breakdown
    _display_detailed_breakdown(summary, console)
    
    # Add tag analysis
    _display_tag_analysis(summary, console)

def _calculate_data_integrity(result: 'FileComparisonResult') -> float:
    """Calculate overall data integrity score (0-100%)"""
    total_baseline = result.total_instances_baseline
    if total_baseline == 0:
        return 0.0
    
    # Perfect matches get full score
    perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
    perfect_score = (perfect_matches / total_baseline) * 100
    
    # Tag differences get partial score (75% of full score)
    tag_diffs = len(result.matched_instances) - perfect_matches
    partial_score = (tag_diffs / total_baseline) * 75
    
    # Missing instances get no score
    # Extra instances don't affect score (they're bonus data)
    
    return perfect_score + partial_score

def _display_detailed_breakdown(summary: 'ComparisonSummary', console: Console) -> None:
    """Display detailed breakdown of differences"""
    console.print("\n")
    
    breakdown_table = Table(title="📊 Export Quality Breakdown", show_header=True)
    breakdown_table.add_column("File", style="cyan")
    breakdown_table.add_column("Instance\nMatch Rate", style="green", justify="right")
    breakdown_table.add_column("Tag\nPreservation", style="blue", justify="right")
    breakdown_table.add_column("Quality\nGrade", style="bright_white", justify="center")
    breakdown_table.add_column("Primary Issues", style="yellow")
    
    for result in summary.file_results:
        total_baseline = result.total_instances_baseline
        total_comparison = result.total_instances_comparison
        matched_instances = len(result.matched_instances)
        
        # Instance match rate
        instance_match_rate = (matched_instances / total_baseline * 100) if total_baseline > 0 else 0
        
        # Tag preservation rate (for matched instances)
        if matched_instances > 0:
            perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
            tag_preservation = (perfect_matches / matched_instances * 100)
        else:
            tag_preservation = 0
        
        # Quality grade
        integrity_score = _calculate_data_integrity(result)
        if integrity_score >= 95:
            grade = "A+"
        elif integrity_score >= 90:
            grade = "A"
        elif integrity_score >= 85:
            grade = "B+"
        elif integrity_score >= 80:
            grade = "B"
        elif integrity_score >= 70:
            grade = "C"
        elif integrity_score >= 60:
            grade = "D"
        else:
            grade = "F"
        
        # Identify primary issues
        issues = []
        if len(result.missing_instances) > total_baseline * 0.05:  # >5% missing
            issues.append(f"{len(result.missing_instances)} missing instances")
        if len(result.extra_instances) > total_comparison * 0.05:  # >5% extra
            issues.append(f"{len(result.extra_instances)} extra instances")
        
        tag_diffs = matched_instances - sum(1 for comp in result.matched_instances if comp.is_perfect_match)
        if tag_diffs > matched_instances * 0.1:  # >10% have tag differences
            issues.append(f"{tag_diffs} instances with tag changes")
        
        if not issues:
            issues.append("None detected")
        
        breakdown_table.add_row(
            Path(result.comparison_file).name,
            f"{instance_match_rate:.1f}%",
            f"{tag_preservation:.1f}%",
            grade,
            ", ".join(issues[:2])  # Show first 2 issues
        )
    
    console.print(breakdown_table)

def _display_tag_analysis(summary: 'ComparisonSummary', console: Console) -> None:
    """Display tag-level analysis"""
    
    # Collect tag difference statistics
    tag_stats = defaultdict(lambda: {'missing': 0, 'extra': 0, 'value_diff': 0, 'type_diff': 0})
    total_differences = 0
    
    for result in summary.file_results:
        for instance_comp in result.matched_instances:
            if not instance_comp.is_perfect_match:
                for tag_diff in instance_comp.tag_differences:
                    tag_name = tag_diff.tag_keyword
                    diff_type = tag_diff.difference_type.value
                    
                    if diff_type == 'MISSING_TAG':
                        tag_stats[tag_name]['missing'] += 1
                    elif diff_type == 'EXTRA_TAG':
                        tag_stats[tag_name]['extra'] += 1
                    elif diff_type == 'VALUE_DIFF':
                        tag_stats[tag_name]['value_diff'] += 1
                    elif diff_type == 'TYPE_DIFF':
                        tag_stats[tag_name]['type_diff'] += 1
                    
                    total_differences += 1
    
    if tag_stats:
        console.print("\n")
        
        # Tag differences table
        tag_table = Table(title="🏷️ Tag Difference Analysis", show_header=True)
        tag_table.add_column("Tag", style="cyan")
        tag_table.add_column("Missing", style="red", justify="right")
        tag_table.add_column("Extra", style="magenta", justify="right")
        tag_table.add_column("Value\nChanged", style="yellow", justify="right")
        tag_table.add_column("Type\nChanged", style="orange3", justify="right")
        tag_table.add_column("Total\nAffected", style="bright_white", justify="right")
        tag_table.add_column("% of\nDifferences", style="bright_blue", justify="right")
        
        # Sort by total impact
        sorted_tags = sorted(tag_stats.items(), 
                           key=lambda x: sum(x[1].values()), 
                           reverse=True)
        
        for tag_name, stats in sorted_tags[:15]:  # Show top 15
            total_tag_diffs = sum(stats.values())
            diff_percentage = (total_tag_diffs / total_differences * 100) if total_differences > 0 else 0
            
            tag_table.add_row(
                tag_name,
                str(stats['missing']) if stats['missing'] > 0 else "-",
                str(stats['extra']) if stats['extra'] > 0 else "-",
                str(stats['value_diff']) if stats['value_diff'] > 0 else "-",
                str(stats['type_diff']) if stats['type_diff'] > 0 else "-",
                str(total_tag_diffs),
                f"{diff_percentage:.1f}%"
            )
        
        console.print(tag_table)
        
        if len(sorted_tags) > 15:
            console.print(f"   ... and {len(sorted_tags) - 15} more tags with differences", style="dim")
        
        # Summary of difference types
        console.print("\n")
        _display_difference_type_summary(tag_stats, total_differences, console)

def _display_difference_type_summary(tag_stats: dict, total_differences: int, console: Console) -> None:
    """Display summary of difference types"""
    # Count by difference type
    type_counts = {'missing': 0, 'extra': 0, 'value_diff': 0, 'type_diff': 0}
    
    for stats in tag_stats.values():
        for diff_type, count in stats.items():
            type_counts[diff_type] += count
    
    summary_table = Table(title="📈 Difference Type Summary", show_header=True)
    summary_table.add_column("Difference Type", style="cyan")
    summary_table.add_column("Count", style="bright_white", justify="right")
    summary_table.add_column("Percentage", style="bright_blue", justify="right")
    summary_table.add_column("Impact", style="yellow")
    
    # Define impact descriptions
    impact_descriptions = {
        'missing': "Tags removed during export",
        'extra': "Tags added during export", 
        'value_diff': "Tag values modified",
        'type_diff': "Tag data types changed"
    }
    
    for diff_type, count in type_counts.items():
        if count > 0:
            percentage = (count / total_differences * 100) if total_differences > 0 else 0
            summary_table.add_row(
                diff_type.replace('_', ' ').title(),
                str(count),
                f"{percentage:.1f}%",
                impact_descriptions[diff_type]
            )
    
    console.print(summary_table)

def generate_report(summary: ComparisonSummary, report_path: Path) -> None:
    """Generate CSV or Excel report"""
    if report_path.suffix.lower() == '.csv':
        generate_csv_report(summary, report_path)
    elif report_path.suffix.lower() == '.xlsx':
        generate_excel_report(summary, report_path)

def generate_csv_report(summary: ComparisonSummary, report_path: Path) -> None:
    """Generate CSV report"""    
    rows = []
    
    # Add summary information first
    summary_rows = []
    for result in summary.file_results:
        perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
        tag_diffs = len(result.matched_instances) - perfect_matches
        missing = len(result.missing_instances)
        extra = len(result.extra_instances)
        
        summary_rows.append({
            'ReportType': 'SUMMARY',
            'BaselineFile': Path(result.baseline_file).name,
            'ComparisonFile': Path(result.comparison_file).name,
            'SOPInstanceUID': 'SUMMARY',
            'TagName': 'TotalInstances',
            'TagKeyword': 'TotalInstances',
            'BaselineValue': str(result.total_instances_baseline),
            'ComparisonValue': str(result.total_instances_comparison),
            'DifferenceType': 'SUMMARY',
            'VR': 'SUMMARY'
        })
        
        summary_rows.append({
            'ReportType': 'SUMMARY',
            'BaselineFile': Path(result.baseline_file).name,
            'ComparisonFile': Path(result.comparison_file).name,
            'SOPInstanceUID': 'SUMMARY',
            'TagName': 'PerfectMatches',
            'TagKeyword': 'PerfectMatches',
            'BaselineValue': str(perfect_matches),
            'ComparisonValue': str(perfect_matches),
            'DifferenceType': 'SUMMARY',
            'VR': 'SUMMARY'
        })
        
        summary_rows.append({
            'ReportType': 'SUMMARY',
            'BaselineFile': Path(result.baseline_file).name,
            'ComparisonFile': Path(result.comparison_file).name,
            'SOPInstanceUID': 'SUMMARY',
            'TagName': 'TagDifferences',
            'TagKeyword': 'TagDifferences',
            'BaselineValue': str(tag_diffs),
            'ComparisonValue': str(tag_diffs),
            'DifferenceType': 'SUMMARY',
            'VR': 'SUMMARY'
        })
    
    rows.extend(summary_rows)
    
    # Add detailed differences
    difference_count = 0
    for result in summary.file_results:
        # Add missing instances
        for missing_instance in result.missing_instances:
            rows.append({
                'ReportType': 'MISSING_INSTANCE',
                'BaselineFile': Path(result.baseline_file).name,
                'ComparisonFile': Path(result.comparison_file).name,
                'SOPInstanceUID': missing_instance.sop_instance_uid,
                'TagName': 'MISSING_INSTANCE',
                'TagKeyword': 'MISSING_INSTANCE',
                'BaselineValue': 'EXISTS',
                'ComparisonValue': 'MISSING',
                'DifferenceType': 'MISSING_INSTANCE',
                'VR': 'INSTANCE'
            })
            difference_count += 1
        
        # Add extra instances
        for extra_instance in result.extra_instances:
            rows.append({
                'ReportType': 'EXTRA_INSTANCE',
                'BaselineFile': Path(result.baseline_file).name,
                'ComparisonFile': Path(result.comparison_file).name,
                'SOPInstanceUID': extra_instance.sop_instance_uid,
                'TagName': 'EXTRA_INSTANCE',
                'TagKeyword': 'EXTRA_INSTANCE',
                'BaselineValue': 'MISSING',
                'ComparisonValue': 'EXISTS',
                'DifferenceType': 'EXTRA_INSTANCE',
                'VR': 'INSTANCE'
            })
            difference_count += 1
        
        # Add tag differences
        for instance_comp in result.matched_instances:
            if not instance_comp.is_perfect_match:
                for tag_diff in instance_comp.tag_differences:
                    rows.append({
                        'ReportType': 'TAG_DIFFERENCE',
                        'BaselineFile': Path(result.baseline_file).name,
                        'ComparisonFile': Path(result.comparison_file).name,
                        'SOPInstanceUID': instance_comp.sop_instance_uid,
                        'TagName': tag_diff.tag_name,
                        'TagKeyword': tag_diff.tag_keyword,
                        'BaselineValue': str(tag_diff.baseline_value) if tag_diff.baseline_value is not None else 'NULL',
                        'ComparisonValue': str(tag_diff.comparison_value) if tag_diff.comparison_value is not None else 'NULL',
                        'DifferenceType': tag_diff.difference_type.value,
                        'VR': tag_diff.vr
                    })
                    difference_count += 1
    
    # If no differences found, add a note
    if difference_count == 0:
        rows.append({
            'ReportType': 'INFO',
            'BaselineFile': 'INFO',
            'ComparisonFile': 'INFO',
            'SOPInstanceUID': 'INFO',
            'TagName': 'NO_DIFFERENCES_FOUND',
            'TagKeyword': 'NO_DIFFERENCES_FOUND',
            'BaselineValue': 'All instances match perfectly',
            'ComparisonValue': 'All instances match perfectly',
            'DifferenceType': 'INFO',
            'VR': 'INFO'
        })
    
    console.print(f"📊 Generated {len(rows)} report rows ({difference_count} actual differences)", style="cyan")
    
    df = pd.DataFrame(rows)
    df.to_csv(report_path, index=False)

def generate_excel_report(summary: 'ComparisonSummary', report_path: Path) -> None:
    """Generate comprehensive Excel report with charts and summary data"""
    #if not EXCEL_AVAILABLE:
    #    console.print("📊 Excel dependencies not available - generating CSV instead", style="yellow")
    #    csv_path = report_path.with_suffix('.csv')
    #    generate_csv_report(summary, csv_path)
    #    return
    
    try:
        console.print("📊 Creating Excel report with charts...", style="cyan")
        
        # Create workbook
        wb = openpyxl.Workbook()
        
        # Remove default sheet
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # Create worksheets
        summary_ws = wb.create_sheet("Executive Summary")
        comparison_ws = wb.create_sheet("Comparison Results")
        tag_analysis_ws = wb.create_sheet("Tag Analysis")
        detailed_ws = wb.create_sheet("Detailed Differences")
        
        # Generate each worksheet
        _create_summary_worksheet(summary_ws, summary, wb)
        _create_comparison_worksheet(comparison_ws, summary)
        _create_tag_analysis_worksheet(tag_analysis_ws, summary)
        _create_detailed_worksheet(detailed_ws, summary)
        
        # Save workbook
        wb.save(report_path)
        console.print(f"✅ Excel report saved: {report_path}", style="green")
        
    except Exception as e:
        console.print(f"📊 Excel generation failed: {e} - generating CSV instead", style="yellow")
        csv_path = report_path.with_suffix('.csv')
        generate_csv_report(summary, csv_path)

def _auto_adjust_column_widths(ws, min_width: int = 10, max_width: int = 60) -> None:
    """
    Enhanced auto-adjust column widths based on content
    """
    # Dictionary to track the maximum content length per column
    column_widths = {}
    
    # Iterate through all rows and columns to find content
    for row in ws.iter_rows():
        for cell in row:
            if cell.value is not None:
                column_letter = cell.column_letter
                
                # Convert value to string and measure length
                cell_value = str(cell.value)
                
                # Add extra space for headers and bold text
                if cell.font and cell.font.bold:
                    content_length = len(cell_value) + 4  # Extra padding for headers
                elif cell.font and cell.font.size and cell.font.size > 12:
                    content_length = len(cell_value) + 2  # Extra padding for large text
                else:
                    content_length = len(cell_value)
                
                # Track the maximum width needed for this column
                if column_letter not in column_widths:
                    column_widths[column_letter] = content_length
                else:
                    column_widths[column_letter] = max(column_widths[column_letter], content_length)
    
    # Apply the calculated widths
    for column_letter, width in column_widths.items():
        # Apply min/max constraints
        final_width = max(min_width, min(width + 5, max_width))  # +2 for padding
        ws.column_dimensions[column_letter].width = final_width
        
        # Optional: Show what widths are being applied
        #if ws.title == "Executive Summary":  # Only show for summary sheet
        #    console.print(f"   📏 Column {column_letter}: {final_width} chars", style="dim")

def _create_summary_worksheet(ws, summary: 'ComparisonSummary', wb) -> None:
    """Create executive summary worksheet with charts and auto-sized columns"""
    # Set worksheet title
    ws.title = "Executive Summary"
    
    # Header styling
    header_font = Font(name='Calibri', size=16, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='2F5597', end_color='2F5597', fill_type='solid')
    subheader_font = Font(name='Calibri', size=12, bold=True, color='2F5597')
    
    # Title
    ws['A1'] = "DICOM Comparison Report - Executive Summary"
    ws['A1'].font = Font(name='Calibri', size=18, bold=True, color='2F5597')
    ws.merge_cells('A1:H1')
    
    # Basic information section
    ws['A3'] = "Report Information"
    ws['A3'].font = subheader_font
    
    info_data = [
        ("Baseline File:", Path(summary.baseline_file).name),
        ("Comparison Files:", f"{len(summary.comparison_files)} files"),
        ("Total Instances:", summary.total_instances),
        ("Total Studies:", summary.total_studies),
        ("Generated:", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
    ]
    
    for idx, (label, value) in enumerate(info_data, 4):
        ws.cell(row=idx, column=1, value=label).font = Font(bold=True)
        ws.cell(row=idx, column=2, value=value)
    
    # Comparison Summary Table
    ws['A9'] = "Comparison Summary"
    ws['A9'].font = subheader_font
    
    # Create summary table headers
    headers = ["File Name", "Perfect Matches", "Tag Differences", "Missing Instances", "Extra Instances", "Data Integrity %"]
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=10, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
    
    # Populate summary data with better formatting
    for row_idx, result in enumerate(summary.file_results, 11):
        perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
        tag_diffs = len(result.matched_instances) - perfect_matches
        missing = len(result.missing_instances)
        extra = len(result.extra_instances)
        integrity = _calculate_data_integrity(result)
        
        # File name (truncated if too long)
        file_name = Path(result.comparison_file).name
        if len(file_name) > 30:
            file_name = file_name[:27] + "..."
        
        ws.cell(row=row_idx, column=1, value=file_name)
        ws.cell(row=row_idx, column=2, value=perfect_matches)
        ws.cell(row=row_idx, column=3, value=tag_diffs)
        ws.cell(row=row_idx, column=4, value=missing)
        ws.cell(row=row_idx, column=5, value=extra)
        
        # Format integrity percentage with color coding
        integrity_cell = ws.cell(row=row_idx, column=6, value=f"{integrity:.1f}%")
        if integrity >= 95:
            integrity_cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
        elif integrity >= 85:
            integrity_cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
        else:
            integrity_cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
    
    # Add charts
    try:
        chart_start_row = len(summary.file_results) + 13
        _add_data_integrity_chart(ws, summary, start_row=chart_start_row)
        _add_comparison_breakdown_chart(ws, summary, start_row=chart_start_row, start_col=7)
    except Exception as e:
        console.print(f"⚠️  Chart creation failed: {e}", style="yellow")
    
    # Auto-adjust ALL column widths based on content
    console.print("📏 Auto-sizing columns...", style="cyan")
    _auto_adjust_column_widths(ws)

def _add_data_integrity_chart(ws, summary: 'ComparisonSummary', start_row: int) -> None:
    """Add data integrity pie chart"""
    try:
        chart = PieChart()
        chart.title = "Data Integrity Overview"
        chart.width = 15
        chart.height = 10
        
        # Calculate overall integrity
        total_perfect = 0
        total_partial = 0
        total_missing = 0
        
        for result in summary.file_results:
            perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
            tag_diffs = len(result.matched_instances) - perfect_matches
            missing = len(result.missing_instances)
            
            total_perfect += perfect_matches
            total_partial += tag_diffs
            total_missing += missing
        
        # Create data for chart
        chart_data = [
            ["Category", "Count"],
            ["Perfect Match", total_perfect],
            ["Tag Differences", total_partial],
            ["Missing Instances", total_missing]
        ]
        
        # Add data to worksheet
        chart_start_row = start_row
        for row_idx, row_data in enumerate(chart_data):
            for col_idx, value in enumerate(row_data):
                ws.cell(row=chart_start_row + row_idx, column=1 + col_idx, value=value)
        
        # Create chart reference
        data_ref = Reference(ws, min_col=2, min_row=chart_start_row + 1, max_row=chart_start_row + len(chart_data) - 1)
        labels_ref = Reference(ws, min_col=1, min_row=chart_start_row + 1, max_row=chart_start_row + len(chart_data) - 1)
        
        chart.add_data(data_ref, titles_from_data=False)
        chart.set_categories(labels_ref)
        
        # Simplified color coding (skip if it causes issues)
        try:
            if chart.series and len(chart.series) > 0:
                colors = ['00B050', 'FFC000', 'C5504B']  # Green, Orange, Red
                series = chart.series[0]
                for i, color in enumerate(colors):
                    if i < len(chart_data) - 1:  # Skip header
                        point = DataPoint(idx=i)
                        point.graphicalProperties.solidFill = color
                        series.data_points.append(point)
        except Exception as color_error:
            console.print(f"⚠️  Chart coloring skipped: {color_error}", style="dim")
        
        ws.add_chart(chart, f"A{start_row + 5}")
        
    except Exception as e:
        console.print(f"⚠️  Pie chart creation failed: {e}", style="yellow")

def _add_comparison_breakdown_chart(ws, summary: 'ComparisonSummary', start_row: int, start_col: int) -> None:
    """Add comparison breakdown bar chart"""
    try:
        chart = BarChart()
        chart.title = "File Comparison Breakdown"
        chart.x_axis.title = "Files"
        chart.y_axis.title = "Number of Instances"
        chart.width = 15
        chart.height = 10
        
        # Prepare data
        file_names = []
        perfect_matches = []
        tag_diffs = []
        missing_instances = []
        
        for result in summary.file_results:
            file_names.append(Path(result.comparison_file).name[:15])  # Truncate long names
            perfect_count = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
            perfect_matches.append(perfect_count)
            tag_diffs.append(len(result.matched_instances) - perfect_count)
            missing_instances.append(len(result.missing_instances))
        
        # Create data table with series labels in first column
        chart_data = [
            ["Series"] + ["Perfect Matches", "Tag Differences", "Missing Instances"],
        ]
        
        # Add file data as columns
        for i, file_name in enumerate(file_names):
            chart_data.append([
                file_name,
                perfect_matches[i],
                tag_diffs[i], 
                missing_instances[i]
            ])
        
        # Add data to worksheet
        chart_start_col = start_col
        for row_idx, row_data in enumerate(chart_data):
            for col_idx, value in enumerate(row_data):
                ws.cell(row=start_row + row_idx, column=chart_start_col + col_idx, value=value)
        
        # Create chart references
        # Categories are the file names (first column, excluding header)
        categories_ref = Reference(ws, 
                                 min_col=chart_start_col, 
                                 min_row=start_row + 1, 
                                 max_row=start_row + len(file_names))
        
        # Data series are the columns (excluding first column and header)
        data_ref = Reference(ws,
                           min_col=chart_start_col + 1,
                           min_row=start_row,
                           max_col=chart_start_col + 3,  # 3 series columns
                           max_row=start_row + len(file_names))
        
        chart.add_data(data_ref, titles_from_data=True)  # Use titles from data
        chart.set_categories(categories_ref)
        
        # Add chart to worksheet
        col_letter = openpyxl.utils.get_column_letter(start_col)
        ws.add_chart(chart, f"{col_letter}{start_row + len(file_names) + 3}")
        
    except Exception as e:
        console.print(f"⚠️  Bar chart creation failed: {e}", style="yellow")

def _create_comparison_worksheet(ws, summary: 'ComparisonSummary') -> None:
    """Create detailed comparison results worksheet"""
    ws.title = "Comparison Results"
    
    # Create detailed comparison data
    data = []
    headers = ["File", "Total Instances", "Perfect Matches", "Perfect Match %", 
              "Tag Differences", "Tag Diff %", "Missing Instances", "Missing %",
              "Extra Instances", "Extra %", "Data Integrity %", "Quality Grade"]
    data.append(headers)
    
    for result in summary.file_results:
        perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
        tag_diffs = len(result.matched_instances) - perfect_matches
        missing = len(result.missing_instances)
        extra = len(result.extra_instances)
        
        total_baseline = result.total_instances_baseline
        total_comparison = result.total_instances_comparison
        
        # Calculate percentages
        perfect_pct = (perfect_matches / total_baseline * 100) if total_baseline > 0 else 0
        tag_diff_pct = (tag_diffs / total_baseline * 100) if total_baseline > 0 else 0
        missing_pct = (missing / total_baseline * 100) if total_baseline > 0 else 0
        extra_pct = (extra / total_comparison * 100) if total_comparison > 0 else 0
        integrity = _calculate_data_integrity(result)
        
        # Quality grade
        if integrity >= 95:
            grade = "A+"
        elif integrity >= 90:
            grade = "A"
        elif integrity >= 85:
            grade = "B+"
        elif integrity >= 80:
            grade = "B"
        elif integrity >= 70:
            grade = "C"
        else:
            grade = "D"
        
        row = [
            Path(result.comparison_file).name,
            total_comparison,
            perfect_matches,
            round(perfect_pct, 1),
            tag_diffs,
            round(tag_diff_pct, 1),
            missing,
            round(missing_pct, 1),
            extra,
            round(extra_pct, 1),
            round(integrity, 1),
            grade
        ]
        data.append(row)
    
    # Add data to worksheet
    for row_idx, row_data in enumerate(data):
        for col_idx, value in enumerate(row_data):
            cell = ws.cell(row=row_idx + 1, column=col_idx + 1, value=value)
            
            # Header formatting
            if row_idx == 0:
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='2F5597', end_color='2F5597', fill_type='solid')
                cell.alignment = Alignment(horizontal='center')
            
            # Conditional formatting for quality grades
            elif col_idx == 11:  # Quality grade column
                if value in ['A+', 'A']:
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
                elif value in ['B+', 'B']:
                    cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
                else:
                    cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
    
    # Auto-adjust column widths
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 20)
        ws.column_dimensions[column_letter].width = adjusted_width

def _create_tag_analysis_worksheet(ws, summary: 'ComparisonSummary') -> None:
    """Create tag analysis worksheet"""
    
    ws.title = "Tag Analysis"
    
    # Collect tag statistics
    tag_stats = defaultdict(lambda: {'missing': 0, 'extra': 0, 'value_diff': 0, 'type_diff': 0})
    
    for result in summary.file_results:
        for instance_comp in result.matched_instances:
            if not instance_comp.is_perfect_match:
                for tag_diff in instance_comp.tag_differences:
                    tag_name = tag_diff.tag_keyword
                    diff_type = tag_diff.difference_type.value
                    
                    if diff_type == 'MISSING_TAG':
                        tag_stats[tag_name]['missing'] += 1
                    elif diff_type == 'EXTRA_TAG':
                        tag_stats[tag_name]['extra'] += 1
                    elif diff_type == 'VALUE_DIFF':
                        tag_stats[tag_name]['value_diff'] += 1
                    elif diff_type == 'TYPE_DIFF':
                        tag_stats[tag_name]['type_diff'] += 1
    
    # Create data
    headers = ["Tag Name", "Missing Count", "Extra Count", "Value Changed", "Type Changed", "Total Affected", "Impact Level"]
    data = [headers]
    
    # Sort by total impact
    sorted_tags = sorted(tag_stats.items(), key=lambda x: sum(x[1].values()), reverse=True)
    
    for tag_name, stats in sorted_tags:
        total_affected = sum(stats.values())
        
        # Determine impact level
        if total_affected > 100:
            impact = "High"
        elif total_affected > 20:
            impact = "Medium"
        else:
            impact = "Low"
        
        row = [
            tag_name,
            stats['missing'],
            stats['extra'],
            stats['value_diff'],
            stats['type_diff'],
            total_affected,
            impact
        ]
        data.append(row)
    
    # Add to worksheet with formatting
    for row_idx, row_data in enumerate(data):
        for col_idx, value in enumerate(row_data):
            cell = ws.cell(row=row_idx + 1, column=col_idx + 1, value=value)
            
            if row_idx == 0:  # Header
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='2F5597', end_color='2F5597', fill_type='solid')
                cell.alignment = Alignment(horizontal='center')
            elif col_idx == 6:  # Impact level
                if value == "High":
                    cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')
                elif value == "Medium":
                    cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')
                else:
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 25)
        ws.column_dimensions[column_letter].width = adjusted_width

def _create_detailed_worksheet(ws, summary: 'ComparisonSummary') -> None:
    """Create detailed differences worksheet (same as CSV data)"""
    ws.title = "Detailed Differences"
    
    # Create detailed differences data (same as CSV)
    rows = []
    headers = ['ReportType', 'BaselineFile', 'ComparisonFile', 'SOPInstanceUID', 'TagName', 'TagKeyword', 'BaselineValue', 'ComparisonValue', 'DifferenceType', 'VR']
    rows.append(headers)
    
    for result in summary.file_results:
        # Add missing instances
        for missing_instance in result.missing_instances:
            rows.append([
                'MISSING_INSTANCE',
                Path(result.baseline_file).name,
                Path(result.comparison_file).name,
                missing_instance.sop_instance_uid,
                'MISSING_INSTANCE',
                'MISSING_INSTANCE',
                'EXISTS',
                'MISSING',
                'MISSING_INSTANCE',
                'INSTANCE'
            ])
        
        # Add extra instances
        for extra_instance in result.extra_instances:
            rows.append([
                'EXTRA_INSTANCE',
                Path(result.baseline_file).name,
                Path(result.comparison_file).name,
                extra_instance.sop_instance_uid,
                'EXTRA_INSTANCE',
                'EXTRA_INSTANCE',
                'MISSING',
                'EXISTS',
                'EXTRA_INSTANCE',
                'INSTANCE'
            ])
        
        # Add tag differences
        for instance_comp in result.matched_instances:
            if not instance_comp.is_perfect_match:
                for tag_diff in instance_comp.tag_differences:
                    rows.append([
                        'TAG_DIFFERENCE',
                        Path(result.baseline_file).name,
                        Path(result.comparison_file).name,
                        instance_comp.sop_instance_uid,
                        tag_diff.tag_name,
                        tag_diff.tag_keyword,
                        str(tag_diff.baseline_value) if tag_diff.baseline_value is not None else 'NULL',
                        str(tag_diff.comparison_value) if tag_diff.comparison_value is not None else 'NULL',
                        tag_diff.difference_type.value,
                        tag_diff.vr
                    ])
    
    # Add to worksheet
    for row_idx, row_data in enumerate(rows):
        for col_idx, value in enumerate(row_data):
            cell = ws.cell(row=row_idx + 1, column=col_idx + 1, value=value)
            
            if row_idx == 0:  # Header
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='2F5597', end_color='2F5597', fill_type='solid')
                cell.alignment = Alignment(horizontal='center')
    
    # Auto-adjust columns
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 30)
        ws.column_dimensions[column_letter].width = adjusted_width

if __name__ == "__main__":
    app()