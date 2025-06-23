import typer
from typing import List, Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint
import pandas as pd

from dicom_extractor import DicomExtractor, ExtractionStats
from dicom_loader import DicomLoader
from dicom_comparator import DicomComparator
from models import ComparisonSummary, FileComparisonResult  # Added missing import
from utils import validate_inputs, create_temp_dir, cleanup_temp_dirs

app = typer.Typer(
    name="dicomcompare",
    help="Compare DICOM studies from different ZIP exports to identify differences",
    add_completion=False
)

console = Console()

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
                from collections import defaultdict
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
                        import pydicom
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
    from collections import defaultdict, Counter
    
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

def generate_excel_report(summary: ComparisonSummary, report_path: Path) -> None:
    """Generate Excel report with multiple sheets"""
    # This will be implemented in the stretch goal phase
    console.print("📊 Excel reporting not yet implemented - generating CSV instead", style="yellow")
    csv_path = report_path.with_suffix('.csv')
    generate_csv_report(summary, csv_path)

if __name__ == "__main__":
    app()