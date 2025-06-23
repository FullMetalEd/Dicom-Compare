import typer
from typing import List, Optional
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

from dicom_extractor import DicomExtractor
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
    try:
        # Extract ZIP files
        console.print("📦 Extracting ZIP files...", style="yellow")
        extractor = DicomExtractor()
        extracted_paths = []
        
        for file in files:
            temp_dir = create_temp_dir()
            temp_dirs.append(temp_dir)
            extracted_path = extractor.extract_zip(file, temp_dir)
            extracted_paths.append((str(file), extracted_path))
            if verbose:
                console.print(f"   Extracted: {file.name}", style="dim")
        
        # Load DICOM files
        console.print("🏥 Loading DICOM files...", style="yellow")
        loader = DicomLoader()
        loaded_studies = []
        
        for file_name, path in extracted_paths:
            studies = loader.load_dicom_files(path, file_name)
            loaded_studies.append((file_name, studies))
            if verbose:
                total_instances = sum(len(series.instances) for study in studies.values() 
                                    for series in study.series.values())
                console.print(f"   {file_name}: {len(studies)} studies, {total_instances} instances", style="dim")
        
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

def display_terminal_results(summary: ComparisonSummary, console: Console) -> None:
    """Display formatted results in terminal"""
    # Create summary panel
    summary_text = f"Baseline: {Path(summary.baseline_file).name}\n"
    summary_text += f"Comparisons: {len(summary.comparison_files)}\n"
    summary_text += f"Total Studies: {summary.total_studies}\n"
    summary_text += f"Total Instances: {summary.total_instances}"
    
    console.print(Panel(summary_text, title="📋 DICOM Comparison Summary", expand=False))
    
    # Create results table
    table = Table(title="🔍 Comparison Results")
    table.add_column("File", style="cyan")
    table.add_column("Perfect Matches", style="green")
    table.add_column("Tag Differences", style="yellow")
    table.add_column("Missing Instances", style="red")
    table.add_column("Extra Instances", style="magenta")
    table.add_column("Match %", style="bright_green")
    
    for result in summary.file_results:
        perfect_matches = sum(1 for comp in result.matched_instances if comp.is_perfect_match)
        tag_diffs = len(result.matched_instances) - perfect_matches
        missing = len(result.missing_instances)
        extra = len(result.extra_instances)
        
        total_baseline = result.total_instances_baseline
        match_pct = (perfect_matches / total_baseline * 100) if total_baseline > 0 else 0
        
        table.add_row(
            Path(result.comparison_file).name,
            str(perfect_matches),
            str(tag_diffs),
            str(missing),
            str(extra),
            f"{match_pct:.1f}%"
        )
    
    console.print(table)

def generate_report(summary: ComparisonSummary, report_path: Path) -> None:
    """Generate CSV or Excel report"""
    if report_path.suffix.lower() == '.csv':
        generate_csv_report(summary, report_path)
    elif report_path.suffix.lower() == '.xlsx':
        generate_excel_report(summary, report_path)

def generate_csv_report(summary: ComparisonSummary, report_path: Path) -> None:
    """Generate CSV report"""
    import pandas as pd
    
    rows = []
    for result in summary.file_results:
        for instance_comp in result.matched_instances:
            if not instance_comp.is_perfect_match:
                for tag_diff in instance_comp.tag_differences:
                    rows.append({
                        'BaselineFile': Path(result.baseline_file).name,
                        'ComparisonFile': Path(result.comparison_file).name,
                        'SOPInstanceUID': instance_comp.sop_instance_uid,
                        'TagName': tag_diff.tag_name,
                        'TagKeyword': tag_diff.tag_keyword,
                        'BaselineValue': str(tag_diff.baseline_value),
                        'ComparisonValue': str(tag_diff.comparison_value),
                        'DifferenceType': tag_diff.difference_type.value,
                        'VR': tag_diff.vr
                    })
    
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