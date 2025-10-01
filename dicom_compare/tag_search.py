import difflib
import sys
import os
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict, Counter
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Platform-specific imports for keyboard handling
try:
    import termios
    import tty
    import select
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

from dicom_compare.models import (
    HierarchicalDicomData, TagInfo, SearchResult,
    PatientInfo, StudyInfo, SeriesInfo, InstanceInfo
)

console = Console()

class TagSearchEngine:
    """Fuzzy search engine for DICOM tags across hierarchical data"""

    def __init__(self, hierarchical_data: HierarchicalDicomData, similarity_threshold: float = 0.3):
        self.data = hierarchical_data
        self.similarity_threshold = similarity_threshold
        self.tag_index = self._build_tag_index()

    def fuzzy_search(self, query: str, level: Optional[str] = None, max_results: int = 20) -> List[SearchResult]:
        """
        Perform fuzzy search across DICOM tags

        Args:
            query: Search query string
            level: Optional hierarchy level filter ("patient", "study", "series", "instance")
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects sorted by relevance
        """
        results = []
        query_lower = query.lower()

        for tag_key, tag_data in self.tag_index.items():
            # Skip if level filter specified and doesn't match
            if level and tag_data['level'] != level:
                continue

            # Calculate similarity scores
            keyword_score = self._fuzzy_match_score(tag_data['keyword'].lower(), query_lower)
            name_score = self._fuzzy_match_score(tag_data['name'].lower(), query_lower)

            # Check value matches
            value_score = 0.0
            for value in tag_data['sample_values'][:10]:  # Check top 10 values
                value_score = max(value_score, self._fuzzy_match_score(str(value).lower(), query_lower))

            # Calculate overall relevance score
            best_score = max(keyword_score, name_score, value_score)

            if best_score >= self.similarity_threshold:
                # Weight by occurrence frequency
                frequency_weight = min(1.0, tag_data['occurrence_count'] / 100.0)
                relevance_score = best_score * (0.8 + 0.2 * frequency_weight)

                result = SearchResult(
                    tag_info=tag_data['tag_info'],
                    hierarchy_level=tag_data['level'],
                    context_id=tag_data['context_examples'][0] if tag_data['context_examples'] else "N/A",
                    similarity_score=relevance_score,
                    occurrence_count=tag_data['occurrence_count'],
                    sample_values=tag_data['sample_values'][:5]  # Top 5 sample values
                )
                results.append(result)

        # Sort by relevance score (descending)
        results.sort(key=lambda x: x.similarity_score, reverse=True)
        return results[:max_results]

    def exact_search(self, query: str, level: Optional[str] = None) -> List[SearchResult]:
        """
        Perform exact match search

        Args:
            query: Exact search query
            level: Optional hierarchy level filter

        Returns:
            List of exact SearchResult matches
        """
        results = []
        query_lower = query.lower()

        for tag_key, tag_data in self.tag_index.items():
            if level and tag_data['level'] != level:
                continue

            # Check for exact matches
            is_exact_match = (
                query_lower == tag_data['keyword'].lower() or
                query_lower == tag_data['name'].lower() or
                query_lower in [str(v).lower() for v in tag_data['sample_values']]
            )

            if is_exact_match:
                result = SearchResult(
                    tag_info=tag_data['tag_info'],
                    hierarchy_level=tag_data['level'],
                    context_id=tag_data['context_examples'][0] if tag_data['context_examples'] else "N/A",
                    similarity_score=1.0,
                    occurrence_count=tag_data['occurrence_count'],
                    sample_values=tag_data['sample_values'][:5]
                )
                results.append(result)

        # Sort by occurrence count (descending)
        results.sort(key=lambda x: x.occurrence_count, reverse=True)
        return results

    def search_by_value(self, value: str, exact: bool = False) -> List[SearchResult]:
        """
        Search for tags containing specific values

        Args:
            value: Value to search for
            exact: Whether to perform exact value matching

        Returns:
            List of SearchResult objects
        """
        results = []
        value_lower = value.lower()

        for tag_key, tag_data in self.tag_index.items():
            matching_values = []

            for tag_value in tag_data['sample_values']:
                tag_value_str = str(tag_value).lower()

                if exact:
                    if value_lower == tag_value_str:
                        matching_values.append(tag_value)
                else:
                    if value_lower in tag_value_str:
                        matching_values.append(tag_value)

            if matching_values:
                result = SearchResult(
                    tag_info=tag_data['tag_info'],
                    hierarchy_level=tag_data['level'],
                    context_id=tag_data['context_examples'][0] if tag_data['context_examples'] else "N/A",
                    similarity_score=1.0 if exact else 0.8,
                    occurrence_count=len(matching_values),
                    sample_values=matching_values[:5]
                )
                results.append(result)

        results.sort(key=lambda x: (x.similarity_score, x.occurrence_count), reverse=True)
        return results

    def get_tag_statistics(self) -> Dict[str, Any]:
        """Get overall tag statistics"""
        level_counts = defaultdict(int)
        vr_counts = defaultdict(int)
        total_tags = len(self.tag_index)

        for tag_data in self.tag_index.values():
            level_counts[tag_data['level']] += 1
            vr_counts[tag_data['tag_info'].vr] += 1

        return {
            'total_unique_tags': total_tags,
            'level_distribution': dict(level_counts),
            'vr_distribution': dict(vr_counts),
            'data_summary': self.data.get_stats()
        }

    def get_tag_details(self, tag_keyword: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific tag (case-insensitive)"""
        keyword_lower = tag_keyword.lower()
        for tag_key, tag_data in self.tag_index.items():
            if tag_data['keyword'].lower() == keyword_lower:
                return {
                    'tag_info': tag_data['tag_info'],
                    'hierarchy_level': tag_data['level'],
                    'occurrence_count': tag_data['occurrence_count'],
                    'unique_values': len(tag_data['sample_values']),
                    'sample_values': tag_data['sample_values'][:10],
                    'context_examples': tag_data['context_examples'][:5]
                }
        return None

    def _build_tag_index(self) -> Dict[str, Dict[str, Any]]:
        """Build searchable index of all tags across hierarchy levels"""
        tag_index = {}

        # Index patient-level tags
        for patient_id, patient in self.data.patients.items():
            for keyword, tag_info in patient.demographics.items():
                key = f"{keyword}_patient"
                self._add_to_index(tag_index, key, tag_info, "patient", patient_id)

        # Index study-level tags
        for study_uid, study in self.data.studies.items():
            for keyword, tag_info in study.metadata.items():
                key = f"{keyword}_study"
                self._add_to_index(tag_index, key, tag_info, "study", study_uid)

        # Index series-level tags
        for series_uid, series in self.data.series.items():
            for keyword, tag_info in series.metadata.items():
                key = f"{keyword}_series"
                self._add_to_index(tag_index, key, tag_info, "series", series_uid)

        # Index instance-level tags
        for sop_uid, instance in self.data.instances.items():
            for keyword, tag_info in instance.metadata.items():
                key = f"{keyword}_instance"
                self._add_to_index(tag_index, key, tag_info, "instance", sop_uid)

        return tag_index

    def _add_to_index(self, index: Dict[str, Dict[str, Any]], key: str,
                     tag_info: TagInfo, level: str, context_id: str):
        """Add tag to search index or update existing entry"""
        if key not in index:
            index[key] = {
                'tag_info': tag_info,
                'keyword': tag_info.keyword,
                'name': tag_info.name,
                'level': level,
                'occurrence_count': 0,
                'sample_values': [],
                'context_examples': []
            }

        # Update occurrence count and sample values
        entry = index[key]
        entry['occurrence_count'] += 1

        # Add unique values and context examples
        if tag_info.value not in entry['sample_values']:
            entry['sample_values'].append(tag_info.value)

        if context_id not in entry['context_examples']:
            entry['context_examples'].append(context_id)

        # Limit sample sizes to avoid memory bloat
        if len(entry['sample_values']) > 20:
            entry['sample_values'] = entry['sample_values'][:20]
        if len(entry['context_examples']) > 10:
            entry['context_examples'] = entry['context_examples'][:10]

    def _fuzzy_match_score(self, text: str, query: str) -> float:
        """Calculate fuzzy matching score using difflib"""
        if not text or not query:
            return 0.0

        # Direct substring match gets higher score
        if query in text:
            return 0.9 + (0.1 * (len(query) / len(text)))

        # Use sequence matcher for fuzzy matching
        matcher = difflib.SequenceMatcher(None, text, query)
        return matcher.ratio()


class InteractiveSearchSession:
    """Interactive search session with command processing"""

    def __init__(self, search_engine: TagSearchEngine, console: Console = None):
        self.search_engine = search_engine
        self.console = console or Console()
        self.current_filter = None
        self.search_history = []
        self.last_results = []

        # Search mode management
        self.search_modes = [
            'fuzzy', 'exact', 'tag', 'value',
            'filter_patient', 'filter_study', 'filter_series', 'filter_instance'
        ]
        self.current_mode = 'fuzzy'  # Default mode

    def _cycle_search_mode(self):
        """Cycle to the next search mode"""
        current_index = self.search_modes.index(self.current_mode)
        next_index = (current_index + 1) % len(self.search_modes)
        self.current_mode = self.search_modes[next_index]

    def _get_mode_prompt(self) -> str:
        """Get the prompt string for current mode"""
        mode_prompts = {
            'fuzzy': 'fuzzy',
            'exact': 'exact',
            'tag': 'tag',
            'value': 'value',
            'filter_patient': 'patient',
            'filter_study': 'study',
            'filter_series': 'series',
            'filter_instance': 'instance'
        }
        return f"{mode_prompts[self.current_mode]}> "

    def _process_direct_input(self, user_input: str) -> bool:
        """Process input based on current mode. Returns True if should quit."""
        if not user_input.strip():
            return False

        # Handle quit commands in any mode
        if user_input.strip().lower() in ['quit', 'exit', 'q']:
            return True

        # Process based on current mode
        if self.current_mode == 'fuzzy':
            self._handle_search(user_input, fuzzy=True)
        elif self.current_mode == 'exact':
            self._handle_search(user_input, fuzzy=False)
        elif self.current_mode == 'tag':
            self._handle_tag_details(user_input)
        elif self.current_mode == 'value':
            self._handle_value_search(user_input)
        elif self.current_mode.startswith('filter_'):
            # Set filter and switch to fuzzy mode
            level = self.current_mode.replace('filter_', '')
            self.current_filter = level
            self.console.print(f"Filter set to: {level}", style="green")
            self.current_mode = 'fuzzy'  # Switch to search mode after setting filter

        return False

    def _get_user_input_with_tab_cycling(self) -> str:
        """Get user input with Tab cycling support"""
        prompt = self._get_mode_prompt()

        # Fallback to simple input if no advanced keyboard handling available
        if not (HAS_TERMIOS or HAS_MSVCRT):
            self.console.print(f"[dim]Tab to cycle modes. Current: {self.current_mode}[/dim]")
            return input(prompt)

        # Advanced keyboard handling for Unix systems
        if HAS_TERMIOS and sys.stdin.isatty():
            return self._unix_input_with_tab(prompt)
        # Windows handling
        elif HAS_MSVCRT:
            return self._windows_input_with_tab(prompt)
        else:
            # Fallback to simple input
            self.console.print(f"[dim]Tab to cycle modes. Current: {self.current_mode}[/dim]")
            return input(prompt)

    def _unix_input_with_tab(self, prompt: str) -> str:
        """Unix/Linux input handler with Tab detection"""
        self.console.print(f"[dim]Press Tab to cycle modes. Current mode: {self.current_mode}[/dim]")
        sys.stdout.write(prompt)
        sys.stdout.flush()

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setraw(sys.stdin.fileno())
            input_chars = []

            while True:
                char = sys.stdin.read(1)

                # Tab character (ASCII 9)
                if ord(char) == 9:
                    # Clear current line and show new mode
                    sys.stdout.write('\r' + ' ' * (len(prompt) + len(input_chars)) + '\r')
                    self._cycle_search_mode()
                    new_prompt = self._get_mode_prompt()
                    sys.stdout.write(f"[{self.current_mode} mode] {new_prompt}")
                    sys.stdout.flush()
                    prompt = new_prompt
                    continue

                # Enter key
                elif ord(char) == 13:  # \r
                    sys.stdout.write('\n')
                    break

                # Backspace
                elif ord(char) == 127 or ord(char) == 8:
                    if input_chars:
                        input_chars.pop()
                        sys.stdout.write('\b \b')
                        sys.stdout.flush()
                    continue

                # Ctrl+C
                elif ord(char) == 3:
                    raise KeyboardInterrupt

                # Regular character
                elif ord(char) >= 32 and ord(char) < 127:
                    input_chars.append(char)
                    sys.stdout.write(char)
                    sys.stdout.flush()

        finally:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

        return ''.join(input_chars)

    def _windows_input_with_tab(self, prompt: str) -> str:
        """Windows input handler with Tab detection"""
        self.console.print(f"[dim]Press Tab to cycle modes. Current mode: {self.current_mode}[/dim]")
        sys.stdout.write(prompt)
        sys.stdout.flush()

        input_chars = []

        while True:
            char = msvcrt.getch()

            # Tab character
            if char == b'\t':
                # Clear current line and show new mode
                sys.stdout.write('\r' + ' ' * (len(prompt) + len(input_chars)) + '\r')
                self._cycle_search_mode()
                new_prompt = self._get_mode_prompt()
                sys.stdout.write(f"[{self.current_mode} mode] {new_prompt}")
                sys.stdout.flush()
                prompt = new_prompt
                continue

            # Enter key
            elif char == b'\r':
                sys.stdout.write('\n')
                break

            # Backspace
            elif char == b'\x08':
                if input_chars:
                    input_chars.pop()
                    sys.stdout.write('\b \b')
                    sys.stdout.flush()
                continue

            # Ctrl+C
            elif char == b'\x03':
                raise KeyboardInterrupt

            # Regular character
            elif len(char) == 1 and ord(char) >= 32 and ord(char) < 127:
                input_chars.append(char.decode('utf-8'))
                sys.stdout.write(char.decode('utf-8'))
                sys.stdout.flush()

        return ''.join(input_chars)

    def start_session(self) -> None:
        """Start interactive search session"""
        self.console.print("\n🔍 Interactive DICOM Tag Search", style="bold blue")
        self.console.print("Press Tab to cycle search modes, type 'help' for commands, 'quit' to exit\n")

        # Show initial statistics
        stats = self.search_engine.get_tag_statistics()
        self._display_initial_stats(stats)

        while True:
            try:
                command = self._get_user_input_with_tab_cycling().strip()
                if not command:
                    continue

                # Check if this looks like an old-style command (starts with known commands)
                parts = command.split(None, 1)
                if len(parts) > 0 and parts[0].lower() in ['search', 'exact', 'tag', 'value', 'filter', 'help', 'stats', 'history', 'clear', 'last']:
                    # Process as old-style command for backward compatibility
                    should_quit = self.process_command(command)
                else:
                    # Process as direct input based on current mode
                    should_quit = self._process_direct_input(command)

                if should_quit:
                    break

            except KeyboardInterrupt:
                self.console.print("\n👋 Search session interrupted", style="yellow")
                break
            except EOFError:
                break

        self.console.print("👋 Search session ended", style="green")

    def process_command(self, command: str) -> bool:
        """Process a search command. Returns True if should quit."""
        if not command:
            return False

        parts = command.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Track command history
        self.search_history.append(command)
        if len(self.search_history) > 20:
            self.search_history = self.search_history[-20:]

        # Process commands
        if cmd in ['quit', 'exit', 'q']:
            return True
        elif cmd in ['help', 'h']:
            self._display_help()
        elif cmd == 'search':
            self._handle_search(args, fuzzy=True)
        elif cmd == 'exact':
            self._handle_search(args, fuzzy=False)
        elif cmd == 'tag':
            self._handle_tag_details(args)
        elif cmd == 'value':
            self._handle_value_search(args)
        elif cmd == 'stats':
            self._display_stats()
        elif cmd == 'history':
            self._display_history()
        elif cmd == 'filter':
            self._handle_filter(args)
        elif cmd == 'clear':
            self._clear_filters()
        elif cmd == 'last':
            self._display_last_results()
        else:
            # Default to fuzzy search
            self._handle_search(command, fuzzy=True)

        return False

    def _handle_search(self, query: str, fuzzy: bool = True):
        """Handle search command"""
        if not query:
            self.console.print("Please provide a search query", style="red")
            return

        try:
            if fuzzy:
                results = self.search_engine.fuzzy_search(query, level=self.current_filter)
            else:
                results = self.search_engine.exact_search(query, level=self.current_filter)

            self.last_results = results
            self._display_search_results(results, query, fuzzy)

        except Exception as e:
            self.console.print(f"Search error: {e}", style="red")

    def _handle_tag_details(self, tag_keyword: str):
        """Handle tag details command"""
        if not tag_keyword:
            self.console.print("Please provide a tag keyword", style="red")
            return

        details = self.search_engine.get_tag_details(tag_keyword)
        if details:
            self._display_tag_details(details)
        else:
            self.console.print(f"Tag '{tag_keyword}' not found", style="yellow")

    def _handle_value_search(self, value: str):
        """Handle value search command"""
        if not value:
            self.console.print("Please provide a value to search for", style="red")
            return

        results = self.search_engine.search_by_value(value)
        self.last_results = results
        self._display_search_results(results, f"value:{value}", False)

    def _handle_filter(self, level: str):
        """Handle filter command"""
        valid_levels = ['patient', 'study', 'series', 'instance', 'none']
        level = level.lower()

        if level in valid_levels:
            if level == 'none':
                self.current_filter = None
                self.console.print("Filter cleared", style="green")
            else:
                self.current_filter = level
                self.console.print(f"Filter set to: {level}", style="green")
        else:
            self.console.print(f"Invalid level. Use: {', '.join(valid_levels)}", style="red")

    def _clear_filters(self):
        """Clear all filters"""
        self.current_filter = None
        self.console.print("All filters cleared", style="green")

    def _display_last_results(self):
        """Display last search results"""
        if self.last_results:
            self.console.print(f"\nLast search results ({len(self.last_results)} results):")
            self._display_search_results(self.last_results, "last search", False)
        else:
            self.console.print("No previous search results", style="yellow")

    def _display_search_results(self, results: List[SearchResult], query: str, fuzzy: bool):
        """Display formatted search results"""
        if not results:
            self.console.print(f"No results found for '{query}'", style="yellow")
            return

        search_type = "fuzzy" if fuzzy else "exact"
        filter_text = f" (filtered: {self.current_filter})" if self.current_filter else ""

        self.console.print(f"\n🔍 {search_type.title()} search results for '{query}'{filter_text}:")
        self.console.print(f"Found {len(results)} matches\n")

        for i, result in enumerate(results, 1):
            # Create result panel
            tag_info = result.tag_info
            level_color = self._get_level_color(result.hierarchy_level)

            title = f"{i}. {tag_info.keyword} ({tag_info.tag_number})"

            content = f"[bold]{tag_info.name}[/bold]\n"
            content += f"VR: {tag_info.vr} | Level: [{level_color}]{result.hierarchy_level}[/{level_color}]\n"
            content += f"Occurrences: {result.occurrence_count} | Score: {result.similarity_score:.3f}\n"

            if result.sample_values:
                values_text = ", ".join([f'"{v}"' for v in result.sample_values])
                if len(values_text) > 80:
                    values_text = values_text[:77] + "..."
                content += f"Sample values: {values_text}"

            self.console.print(Panel(content, title=title, expand=False))

            # Show context for top results
            if i <= 3 and result.context_id != "N/A":
                self.console.print(f"   Context: {result.context_id}", style="dim")

    def _display_tag_details(self, details: Dict[str, Any]):
        """Display detailed tag information"""
        tag_info = details['tag_info']
        level_color = self._get_level_color(details['hierarchy_level'])

        table = Table(title=f"Tag Details: {tag_info.keyword}")
        table.add_column("Attribute", style="cyan")
        table.add_column("Value", style="white")

        table.add_row("Keyword", tag_info.keyword)
        table.add_row("Name", tag_info.name)
        table.add_row("Tag Number", tag_info.tag_number)
        table.add_row("VR", tag_info.vr)
        table.add_row("Level", f"[{level_color}]{details['hierarchy_level']}[/{level_color}]")
        table.add_row("Occurrences", str(details['occurrence_count']))
        table.add_row("Unique Values", str(details['unique_values']))

        self.console.print(table)

        if details['sample_values']:
            self.console.print(f"\nSample Values:")
            for value in details['sample_values']:
                self.console.print(f"  • {value}", style="dim")

    def _display_initial_stats(self, stats: Dict[str, Any]):
        """Display initial dataset statistics"""
        summary = stats['data_summary']
        level_dist = stats['level_distribution']

        table = Table(title="📊 Dataset Summary")
        table.add_column("Level", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Unique Tags", style="blue", justify="right")

        table.add_row("Patients", str(summary['patients']), str(level_dist.get('patient', 0)))
        table.add_row("Studies", str(summary['studies']), str(level_dist.get('study', 0)))
        table.add_row("Series", str(summary['series']), str(level_dist.get('series', 0)))
        table.add_row("Instances", str(summary['instances']), str(level_dist.get('instance', 0)))
        table.add_row("Total Tags", str(stats['total_unique_tags']), "—")

        self.console.print(table)

    def _display_stats(self):
        """Display current statistics"""
        stats = self.search_engine.get_tag_statistics()
        self._display_initial_stats(stats)

    def _display_history(self):
        """Display search history"""
        if not self.search_history:
            self.console.print("No search history", style="yellow")
            return

        self.console.print("📜 Search History:")
        for i, cmd in enumerate(self.search_history[-10:], 1):  # Show last 10
            self.console.print(f"  {i}. {cmd}", style="dim")

    def _display_help(self):
        """Display help information"""
        help_text = f"""
[bold blue]Enhanced Search Interface:[/bold blue]

[bold green]🔄 Tab Cycling Mode (Recommended):[/bold green]
Press [cyan]Tab[/cyan] to cycle through search modes:
• [yellow]fuzzy[/yellow] - Fuzzy search all tags
• [yellow]exact[/yellow] - Exact match search
• [yellow]tag[/yellow] - Get tag details by keyword
• [yellow]value[/yellow] - Search by tag values
• [yellow]patient/study/series/instance[/yellow] - Filter modes

Current mode: [bold]{self.current_mode}[/bold]
Just type your search term directly in any mode!

[bold blue]Classic Commands (Still Available):[/bold blue]

[cyan]search <term>[/cyan]     - Fuzzy search all tags
[cyan]exact <term>[/cyan]      - Exact match search
[cyan]tag <keyword>[/cyan]     - Get details for specific tag
[cyan]value <text>[/cyan]      - Search by tag values
[cyan]filter <level>[/cyan]    - Filter by hierarchy level (patient/study/series/instance/none)
[cyan]stats[/cyan]             - Show dataset statistics
[cyan]history[/cyan]           - Show search history
[cyan]last[/cyan]              - Show last search results
[cyan]clear[/cyan]             - Clear all filters
[cyan]help[/cyan]              - Show this help
[cyan]quit/exit[/cyan]         - Exit search mode

[yellow]Quick Start:[/yellow]
1. Press Tab to cycle to desired search mode
2. Type your search term directly (no command prefix needed)
3. Press Enter to search

[yellow]Examples:[/yellow]
  [Tab to fuzzy mode] → patient name
  [Tab to exact mode] → PatientID
  [Tab to tag mode] → StudyDate
  [Tab to value mode] → Smith^John
        """
        self.console.print(Panel(help_text, title="Interactive Search Help", expand=False))

    def _get_level_color(self, level: str) -> str:
        """Get color for hierarchy level"""
        colors = {
            'patient': 'green',
            'study': 'blue',
            'series': 'yellow',
            'instance': 'magenta'
        }
        return colors.get(level, 'white')