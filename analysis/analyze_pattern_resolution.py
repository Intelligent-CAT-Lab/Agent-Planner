"""
Comprehensive analysis of pattern resolution comparing vanilla and planner runs (monitor/refiner).

Analyzes:
1. Overall resolution statistics (R-R, R-U, U-R, U-U)
2. Trigger status breakdown
3. Instance-level details for U-R and R-U cases
4. Cost and step comparisons
5. Pattern analysis
6. Deeper insights into why triggers don't change outcomes

Usage:
    python analysis/analyze_pattern_resolution.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench --config refiner
    python analysis/analyze_pattern_resolution.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench --config monitor
"""

import json
import csv
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict, Counter
from dataclasses import dataclass, asdict


@dataclass
class InstanceData:
    """Data structure for a single instance run."""
    instance_id: str
    resolved: bool
    has_issue: bool
    patterns: Dict[str, bool]
    lang: str
    unique_phases: str
    cost: float
    steps: int
    has_planner: bool = False
    overlapping_issues: List[str] = None

    def __post_init__(self):
        if self.overlapping_issues is None:
            self.overlapping_issues = []


@dataclass
class ComparisonResult:
    """Results comparing vanilla and planner runs."""
    category: str  # R-R, R-U, U-R, U-U
    count: int
    percentage: float
    instances: List[Dict]
    avg_vanilla_cost: float
    avg_planner_cost: float
    avg_vanilla_steps: float
    avg_planner_steps: float
    pattern_distribution: Dict[str, int]


class CSVParser:
    """Smart CSV parser that dynamically detects column structure."""

    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.header_rows = []
        self.data_rows = []
        self.column_map = {}
        self._load_csv()
        self._detect_structure()

    def _load_csv(self):
        """Load CSV and separate headers from data."""
        with open(self.csv_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # First 3 rows are headers
        self.header_rows = rows[:3]
        self.data_rows = rows[3:]

    def _detect_structure(self):
        """
        Detect which columns correspond to which configs.

        Expected structure:
        - Vanilla Run: 10 columns (no trigger status)
        - Monitor Run: 12 columns (includes trigger status)
        - Refiner/Live-Plan Run: 12 columns (includes trigger status)
        """
        # Parse header row 1 to find config sections
        header1 = self.header_rows[0]
        header2 = self.header_rows[1]

        current_col = 0
        config_sections = {}

        # Skip Instance ID column
        current_col = 1

        # Identify sections by header row 1
        while current_col < len(header1):
            section_name = header1[current_col].strip()
            if not section_name:
                current_col += 1
                continue

            section_start = current_col

            # Determine section width based on config type
            # Vanilla: 10 columns, Monitor/Refiner: 12 columns
            if 'Vanilla Run' in section_name and 'Re-run' not in section_name and 'Monitor' not in section_name:
                # Vanilla: no trigger status, 10 columns
                section_width = 10
                config_sections['vanilla'] = (section_start, section_start + section_width)
            elif 'Monitor Run' in section_name or 'Monitor' in section_name:
                # Monitor: has trigger status, 12 columns
                section_width = 12
                config_sections['monitor'] = (section_start, section_start + section_width)
            elif 'Live-Plan' in section_name or 'Refiner' in section_name:
                # Refiner: has trigger status, 12 columns
                section_width = 12
                config_sections['refiner'] = (section_start, section_start + section_width)
            else:
                # Unknown section, skip
                section_width = 1

            current_col = section_start + section_width

        self.column_map = config_sections

    def has_config(self, config: str) -> bool:
        """Check if a config section exists in the CSV."""
        return config in self.column_map

    def parse_vanilla_data(self, row: List[str]) -> Optional[InstanceData]:
        """
        Parse vanilla run data from a row.

        Vanilla structure (10 columns):
        0: Resolution Status
        1: Has Issue
        2-5: Patterns (plan_violation, oscillation, long_stagnation, repeated view)
        6: Lang
        7: Unique Phases
        8: Cost
        9: Steps
        """
        if 'vanilla' not in self.column_map:
            return None

        start, end = self.column_map['vanilla']
        if len(row) <= start or not row[start]:
            return None

        try:
            instance_id = row[0]
            resolved = row[start] == '1'
            has_issue = row[start + 1] == '1'
            patterns = {
                'plan_violation': row[start + 2] == '1',
                'oscillation': row[start + 3] == '1',
                'long_stagnation': row[start + 4] == '1',
                'repeated_view': row[start + 5] == '1'
            }
            lang = row[start + 6] if len(row) > start + 6 else ''
            unique_phases = row[start + 7] if len(row) > start + 7 else ''
            cost = float(row[start + 8]) if len(row) > start + 8 and row[start + 8] else 0.0
            steps = int(row[start + 9]) if len(row) > start + 9 and row[start + 9] else 0

            return InstanceData(
                instance_id=instance_id,
                resolved=resolved,
                has_issue=has_issue,
                patterns=patterns,
                lang=lang,
                unique_phases=unique_phases,
                cost=cost,
                steps=steps
            )
        except (ValueError, IndexError) as e:
            print(f"Warning: Error parsing vanilla data for row: {e}")
            return None

    def parse_planner_data(self, row: List[str], config: str) -> Optional[InstanceData]:
        """
        Parse monitor/refiner run data from a row.

        Structure (12 columns per section):
        0: Trigger Status
        1: Resolution Status
        2: Has Issue
        3: Overlapping issues
        4-7: Patterns (plan_violation, oscillation, long_stagnation, repeated view)
        8: Lang
        9: Unique Phases
        10: Cost
        11: Steps
        """
        if config not in self.column_map:
            return None

        start, end = self.column_map[config]
        if len(row) <= start or not row[start]:
            return None

        try:
            instance_id = row[0]
            has_planner = row[start] == '1'
            resolved = row[start + 1] == '1' if len(row) > start + 1 else False
            has_issue = row[start + 2] == '1' if len(row) > start + 2 else False
            overlapping_str = row[start + 3] if len(row) > start + 3 else ''
            overlapping_issues = overlapping_str.split(',') if overlapping_str else []
            patterns = {
                'plan_violation': row[start + 4] == '1' if len(row) > start + 4 else False,
                'oscillation': row[start + 5] == '1' if len(row) > start + 5 else False,
                'long_stagnation': row[start + 6] == '1' if len(row) > start + 6 else False,
                'repeated_view': row[start + 7] == '1' if len(row) > start + 7 else False
            }
            lang = row[start + 8] if len(row) > start + 8 else ''
            unique_phases = row[start + 9] if len(row) > start + 9 else ''
            cost = float(row[start + 10]) if len(row) > start + 10 and row[start + 10] else 0.0
            steps = int(row[start + 11]) if len(row) > start + 11 and row[start + 11] else 0

            return InstanceData(
                instance_id=instance_id,
                resolved=resolved,
                has_issue=has_issue,
                patterns=patterns,
                lang=lang,
                unique_phases=unique_phases,
                cost=cost,
                steps=steps,
                has_planner=has_planner,
                overlapping_issues=overlapping_issues
            )
        except (ValueError, IndexError) as e:
            print(f"Warning: Error parsing {config} data for row: {e}")
            return None


class PatternAnalyzer:
    """Analyzer for pattern resolution data."""

    PATTERN_TYPES = ['plan_violation', 'oscillation', 'long_stagnation', 'repeated_view']

    def __init__(self, csv_path: Path, config: str, agent_dir: Path = None,
                 model: str = None, dataset: str = None, run_id: int = 1, version: str = '5'):
        self.csv_path = csv_path
        self.config = config  # 'monitor' or 'refiner'
        self.agent_dir = agent_dir
        self.model = model
        self.dataset = dataset
        self.run_id = run_id
        self.version = version
        self.vanilla_data: Dict[str, InstanceData] = {}
        self.planner_data: Dict[str, InstanceData] = {}
        self._load_data()

    def _load_data(self):
        """Load and parse CSV data using smart parser."""
        parser = CSVParser(self.csv_path)

        if not parser.has_config('vanilla'):
            print("Warning: No vanilla data found in CSV")

        if not parser.has_config(self.config):
            raise ValueError(f"Config '{self.config}' not found in CSV. Available: {list(parser.column_map.keys())}")

        # Parse all data rows
        for row in parser.data_rows:
            if not row or not row[0]:
                continue

            instance_id = row[0]

            # Parse vanilla data
            vanilla = parser.parse_vanilla_data(row)
            if vanilla:
                self.vanilla_data[instance_id] = vanilla

            # Parse planner data (monitor or refiner)
            planner = parser.parse_planner_data(row, self.config)
            if planner:
                self.planner_data[instance_id] = planner

    def _load_planner_json(self, instance_id: str) -> Optional[Dict]:
        """Load planner.json for a given instance."""
        if not self.agent_dir or not self.model or not self.dataset:
            return None

        dataset_path = self.dataset if self.dataset != 'swebench-pro' else f"{self.dataset}/python"

        if self.config == 'refiner' and self.version:
            planner_path = (self.agent_dir / "trajectories" / self.config / f"version-{self.version}" /
                          dataset_path / self.model / f"run-{self.run_id}" / instance_id / f"{instance_id}.planner.json")
        else:
            planner_path = (self.agent_dir / "trajectories" / self.config / dataset_path /
                          self.model / f"run-{self.run_id}" / instance_id / f"{instance_id}.planner.json")

        if not planner_path.exists():
            return None

        try:
            with open(planner_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Error loading planner.json for {instance_id}: {e}")
            return None

    def _classify_monitor_trigger(self, content: str) -> str:
        """
        Classify monitor trigger content into pattern categories.
        Reuses logic from collect_pattern_resolution.py.
        """
        content_lower = content.lower()

        if 'plan compliance' in content_lower or 'skipped phases' in content_lower or 'expected to' in content_lower:
            return 'plan_violation'
        if ('repeating action' in content_lower or 'repeated actions' in content_lower or
            'repeating the same reasoning' in content_lower or 'oscillating between' in content_lower or
            'stuck in a loop' in content_lower):
            return 'oscillation'
        if ('seem to navigate' in content_lower or 'trying to reproduce' in content_lower or
            ('spent the last' in content_lower and ('steps editing' in content_lower or 'steps validating' in content_lower))):
            return 'long_stagnation'
        if 'already reviewed this location' in content_lower or 'have already reviewed' in content_lower:
            return 'repeated_view'

        return 'unknown'

    def _extract_planner_stats(self, planner_data: Dict) -> Dict:
        """Extract summary statistics from planner.json."""
        if not planner_data:
            return None

        summary = planner_data.get('summary', {})
        interventions = planner_data.get('interventions', [])

        # Extract intervention details
        intervention_details = []
        for intervention in interventions:
            planner_type = intervention.get('planner_type')

            if planner_type == 'monitor':
                content = intervention.get('content', '')
                intervention_details.append({
                    'step': intervention.get('step'),
                    'planner_type': 'monitor',
                    'content': content[:200],
                    'pattern': self._classify_monitor_trigger(content)
                })
            elif planner_type == 'refiner':
                rule_triggers = intervention.get('state_summary', {}).get('rule_triggers', [])
                # Extract rule_id strings - handle both string and dict formats
                rule_ids = []
                if rule_triggers:
                    for trigger in rule_triggers:
                        if isinstance(trigger, dict):
                            rule_ids.append(trigger.get('rule_id', 'unknown'))
                        else:
                            rule_ids.append(str(trigger))
                else:
                    rule_ids = ['plan_compliance']

                intervention_details.append({
                    'step': intervention.get('step'),
                    'planner_type': 'refiner',
                    'content': intervention.get('content', ''),
                    'rule_ids': rule_ids
                })

        return {
            'total_interventions': summary.get('total_interventions', 0),
            'monitor_count': summary.get('monitor_count', 0),
            'refiner_count': summary.get('refiner_count', 0),
            'monitor_total_latency_ms': summary.get('monitor_total_latency_ms', 0.0),
            'refiner_total_latency_ms': summary.get('refiner_total_latency_ms', 0.0),
            'refiner_total_cost': summary.get('refiner_total_cost', 0.0),
            'interventions': intervention_details
        }

    def _compute_pattern_stats(self) -> Dict:
        """Compute pattern statistics for vanilla and config data."""
        stats = {}

        for name, data_dict in [('vanilla', self.vanilla_data), (self.config, self.planner_data)]:
            with_patterns = sum(1 for d in data_dict.values() if any(d.patterns.values()))
            plan_violation = sum(1 for d in data_dict.values() if d.patterns.get('plan_violation', False))
            oscillation = sum(1 for d in data_dict.values() if d.patterns.get('oscillation', False))
            long_stagnation = sum(1 for d in data_dict.values() if d.patterns.get('long_stagnation', False))
            repeated_view = sum(1 for d in data_dict.values() if d.patterns.get('repeated_view', False))

            blocking = plan_violation + oscillation
            non_blocking = long_stagnation + repeated_view

            stats[name] = {
                'with_patterns': with_patterns,
                'blocking': blocking,
                'plan_violation': plan_violation,
                'oscillation': oscillation,
                'non_blocking': non_blocking,
                'long_stagnation': long_stagnation,
                'repeated_view': repeated_view
            }

        return stats

    def analyze_trigger_status(self) -> Dict:
        """Analyze instances based on trigger status."""
        triggered = [iid for iid, data in self.planner_data.items() if data.has_planner]
        non_triggered = [iid for iid, data in self.planner_data.items() if not data.has_planner]

        triggered_resolved = sum(1 for iid in triggered if self.planner_data[iid].resolved)
        triggered_unresolved = len(triggered) - triggered_resolved

        return {
            'total_planner_instances': len(self.planner_data),
            'triggered_count': len(triggered),
            'triggered_percentage': len(triggered) / len(self.planner_data) * 100 if self.planner_data else 0,
            'triggered_resolved': triggered_resolved,
            'triggered_unresolved': triggered_unresolved,
            'non_triggered_count': len(non_triggered)
        }

    def categorize_instances(self, triggered_only: bool = True) -> Dict[str, List[str]]:
        """Categorize instances by resolution pattern (R-R, R-U, U-R, U-U)."""
        categories = {
            'R-R': [],  # Resolved -> Resolved
            'R-U': [],  # Resolved -> Unresolved
            'U-R': [],  # Unresolved -> Resolved
            'U-U': []   # Unresolved -> Unresolved
        }

        # Get instances to analyze
        if triggered_only:
            instances_to_check = [iid for iid, data in self.planner_data.items() if data.has_planner]
        else:
            instances_to_check = list(self.planner_data.keys())

        for instance_id in instances_to_check:
            if instance_id not in self.vanilla_data:
                continue

            vanilla = self.vanilla_data[instance_id]
            planner = self.planner_data[instance_id]

            if vanilla.resolved and planner.resolved:
                categories['R-R'].append(instance_id)
            elif vanilla.resolved and not planner.resolved:
                categories['R-U'].append(instance_id)
            elif not vanilla.resolved and planner.resolved:
                categories['U-R'].append(instance_id)
            else:
                categories['U-U'].append(instance_id)

        return categories

    def analyze_category_details(self, category: str, instance_ids: List[str]) -> ComparisonResult:
        """Detailed analysis for a specific category."""
        instances_detail = []
        vanilla_costs = []
        planner_costs = []
        vanilla_steps_list = []
        planner_steps_list = []
        pattern_counter = Counter()

        for iid in instance_ids:
            if iid not in self.vanilla_data or iid not in self.planner_data:
                continue

            vanilla = self.vanilla_data[iid]
            planner = self.planner_data[iid]

            vanilla_costs.append(vanilla.cost)
            planner_costs.append(planner.cost)
            vanilla_steps_list.append(vanilla.steps)
            planner_steps_list.append(planner.steps)

            # Count patterns in vanilla run
            for pattern, triggered in vanilla.patterns.items():
                if triggered:
                    pattern_counter[pattern] += 1

            # Load planner stats if has_planner
            planner_stats = None
            if planner.has_planner:
                planner_data_json = self._load_planner_json(iid)
                planner_stats = self._extract_planner_stats(planner_data_json)

            planner_detail = {
                'resolved': planner.resolved,
                'has_issue': planner.has_issue,
                'patterns': planner.patterns,
                'overlapping_issues': planner.overlapping_issues,
                'lang': planner.lang,
                'unique_phases': planner.unique_phases,
                'cost': planner.cost,
                'steps': planner.steps,
                'has_planner': planner.has_planner
            }

            if planner_stats:
                planner_detail['planner_stats'] = planner_stats

            instances_detail.append({
                'instance_id': iid,
                'vanilla': {
                    'resolved': vanilla.resolved,
                    'has_issue': vanilla.has_issue,
                    'patterns': vanilla.patterns,
                    'lang': vanilla.lang,
                    'unique_phases': vanilla.unique_phases,
                    'cost': vanilla.cost,
                    'steps': vanilla.steps
                },
                f'{self.config}': planner_detail
            })

        total_instances = len(self.planner_data)

        return ComparisonResult(
            category=category,
            count=len(instance_ids),
            percentage=len(instance_ids) / total_instances * 100 if total_instances > 0 else 0,
            instances=instances_detail,
            avg_vanilla_cost=sum(vanilla_costs) / len(vanilla_costs) if vanilla_costs else 0,
            avg_planner_cost=sum(planner_costs) / len(planner_costs) if planner_costs else 0,
            avg_vanilla_steps=sum(vanilla_steps_list) / len(vanilla_steps_list) if vanilla_steps_list else 0,
            avg_planner_steps=sum(planner_steps_list) / len(planner_steps_list) if planner_steps_list else 0,
            pattern_distribution=dict(pattern_counter)
        )

    def analyze_planner_aggregates(self, triggered_instances: List[str]) -> Dict:
        """Aggregate planner statistics across all triggered instances."""
        total_triggered = len(triggered_instances)
        total_interventions = 0
        total_monitor_count = 0
        total_refiner_count = 0
        total_monitor_latency_ms = 0.0
        total_refiner_latency_ms = 0.0
        total_refiner_cost = 0.0
        trigger_type_counter = Counter()

        for iid in triggered_instances:
            planner_data = self._load_planner_json(iid)
            if not planner_data:
                continue

            planner_stats = self._extract_planner_stats(planner_data)
            if not planner_stats:
                continue

            total_interventions += planner_stats['total_interventions']
            total_monitor_count += planner_stats['monitor_count']
            total_refiner_count += planner_stats['refiner_count']
            total_monitor_latency_ms += planner_stats['monitor_total_latency_ms']
            total_refiner_latency_ms += planner_stats['refiner_total_latency_ms']
            total_refiner_cost += planner_stats['refiner_total_cost']

            for intervention in planner_stats['interventions']:
                planner_type = intervention.get('planner_type')
                if planner_type == 'monitor':
                    # Count monitor triggers by pattern type
                    pattern = intervention.get('pattern', 'unknown')
                    trigger_type_counter[f"monitor_{pattern}"] += 1
                elif planner_type == 'refiner':
                    # Count refiner triggers by rule_id
                    for rule_id in intervention.get('rule_ids', ['unknown']):
                        trigger_type_counter[rule_id] += 1

        # Return per-instance averages
        stats = {
            'total_triggered': total_triggered,
            'trigger_type_distribution': dict(trigger_type_counter)
        }

        if total_triggered > 0:
            stats['avg_interventions'] = total_interventions / total_triggered
            stats['avg_monitor_count'] = total_monitor_count / total_triggered
            stats['avg_refiner_count'] = total_refiner_count / total_triggered
            stats['avg_monitor_latency_ms'] = total_monitor_latency_ms / total_triggered
            stats['avg_refiner_latency_ms'] = total_refiner_latency_ms / total_triggered
            stats['avg_refiner_cost'] = total_refiner_cost / total_triggered

        return stats

    def generate_report(self, output_dir: Path):
        """Generate comprehensive analysis report."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Trigger status analysis
        trigger_analysis = self.analyze_trigger_status()

        # 2. Categorize instances (triggered only)
        categories = self.categorize_instances(triggered_only=True)

        # 3. Aggregate planner statistics
        triggered_instances = [iid for iid, data in self.planner_data.items() if data.has_planner]
        planner_aggregates = self.analyze_planner_aggregates(triggered_instances)

        # 4. Detailed analysis for each category
        category_results = {}
        for cat, instance_ids in categories.items():
            category_results[cat] = self.analyze_category_details(cat, instance_ids)

        # Compile full report
        report = {
            'config': self.config,
            'summary': {
                'total_instances': len(self.planner_data),
                'trigger_status': trigger_analysis,
                'planner_aggregates': planner_aggregates,
                'categories': {
                    cat: {
                        'count': len(instance_ids),
                        'percentage': len(instance_ids) / len(self.planner_data) * 100 if self.planner_data else 0
                    }
                    for cat, instance_ids in categories.items()
                }
            },
            'category_details': {
                cat: {
                    'count': result.count,
                    'percentage': result.percentage,
                    'avg_vanilla_cost': result.avg_vanilla_cost,
                    f'avg_{self.config}_cost': result.avg_planner_cost,
                    'avg_vanilla_steps': result.avg_vanilla_steps,
                    f'avg_{self.config}_steps': result.avg_planner_steps,
                    'pattern_distribution': result.pattern_distribution,
                    'instances': result.instances
                }
                for cat, result in category_results.items()
            }
        }

        # Save JSON report
        json_path = output_dir / f"{self.csv_path.stem}-{self.config}-analysis.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n✓ JSON report saved to: {json_path}")

        # Print summary
        self._print_summary(report)

        return report

    def _print_summary(self, report: Dict):
        """Print formatted summary to console."""
        config = report['config']
        config_display = config.capitalize()

        print("\n" + "="*80)
        print(f"PATTERN RESOLUTION ANALYSIS SUMMARY - {config_display.upper()}")
        print("="*80)

        summary = report['summary']
        print(f"\nTotal instances: {summary['total_instances']}")

        # Pattern comparison
        pattern_stats = self._compute_pattern_stats()
        print(f"\nPattern Statistics:")
        print(f"  Vanilla run-1:")
        print(f"    With patterns: {pattern_stats['vanilla']['with_patterns']}")
        print(f"    Blocking patterns: {pattern_stats['vanilla']['blocking']} (plan_violation: {pattern_stats['vanilla']['plan_violation']}, oscillation: {pattern_stats['vanilla']['oscillation']})")
        print(f"    Non-blocking patterns: {pattern_stats['vanilla']['non_blocking']} (long_stagnation: {pattern_stats['vanilla']['long_stagnation']}, repeated_view: {pattern_stats['vanilla']['repeated_view']})")
        print(f"  {config_display}:")
        print(f"    With patterns: {pattern_stats[config]['with_patterns']}")
        print(f"    Blocking patterns: {pattern_stats[config]['blocking']} (plan_violation: {pattern_stats[config]['plan_violation']}, oscillation: {pattern_stats[config]['oscillation']})")
        print(f"    Non-blocking patterns: {pattern_stats[config]['non_blocking']} (long_stagnation: {pattern_stats[config]['long_stagnation']}, repeated_view: {pattern_stats[config]['repeated_view']})")

        trigger = summary['trigger_status']
        print(f"\nTrigger Status:")
        print(f"  Triggered: {trigger['triggered_count']} ({trigger['triggered_percentage']:.1f}%)")
        print(f"    - Resolved: {trigger['triggered_resolved']}")
        print(f"    - Unresolved: {trigger['triggered_unresolved']}")
        print(f"  Non-triggered: {trigger['non_triggered_count']}")

        # Planner aggregates
        if 'planner_aggregates' in summary and summary['planner_aggregates']['total_triggered'] > 0:
            pa = summary['planner_aggregates']
            print(f"\nPlanner Statistics (Per triggered instance):")
            print(f"  Avg interventions: {pa.get('avg_interventions', 0):.2f}")
            print(f"  Avg monitor count: {pa.get('avg_monitor_count', 0):.2f}")
            print(f"  Avg refiner count: {pa.get('avg_refiner_count', 0):.2f}")
            print(f"  Avg monitor latency: {pa.get('avg_monitor_latency_ms', 0):.2f}ms")
            print(f"  Avg refiner latency: {pa.get('avg_refiner_latency_ms', 0):.2f}ms")
            print(f"  Avg refiner cost: ${pa.get('avg_refiner_cost', 0):.6f}")
            print(f"  Trigger type distribution:")
            for ttype, count in sorted(pa['trigger_type_distribution'].items(), key=lambda x: -x[1]):
                print(f"    {ttype}: {count}")

        print(f"\nResolution Categories (Triggered instances only):")
        for cat, stats in summary['categories'].items():
            print(f"  {cat}: {stats['count']} ({stats['percentage']:.1f}%)")

        print(f"\nCost & Steps Comparison:")
        for cat in ['R-R', 'R-U', 'U-R', 'U-U']:
            details = report['category_details'][cat]
            if details['count'] == 0:
                continue
            print(f"\n  {cat} ({details['count']} instances):")
            print(f"    Vanilla   - Avg cost: ${details['avg_vanilla_cost']:.4f}, Avg steps: {details['avg_vanilla_steps']:.1f}")
            print(f"    {config_display:9s} - Avg cost: ${details[f'avg_{config}_cost']:.4f}, Avg steps: {details[f'avg_{config}_steps']:.1f}")
            if details['avg_vanilla_cost'] > 0:
                cost_change = (details[f'avg_{config}_cost'] - details['avg_vanilla_cost']) / details['avg_vanilla_cost'] * 100
                step_change = (details[f'avg_{config}_steps'] - details['avg_vanilla_steps']) / details['avg_vanilla_steps'] * 100
                print(f"    Change    - Cost: {cost_change:+.1f}%, Steps: {step_change:+.1f}%")

        print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Comprehensive analysis of pattern resolution data'
    )
    parser.add_argument('--agent', type=str, default='SWE-agent',
                       help='Agent name (default: SWE-agent)')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., deepseek-chat-v3-0324)')
    parser.add_argument('--dataset', type=str, default='swebench',
                       help='Dataset name (default: swebench)')
    parser.add_argument('--config', type=str, nargs='+', default=['monitor', 'refiner'],
                       choices=['monitor', 'refiner'],
                       help='Config(s) to analyze (default: monitor refiner)')
    parser.add_argument('--run', type=int, default=1,
                       help='Run ID (default: 1)')
    parser.add_argument('--refiner-version', type=str, default='5',
                       help='Refiner version (default: 5, only used for refiner config)')
    parser.add_argument('--csv', type=Path, default=None,
                       help='Path to CSV file (default: analysis/analysis-results/comparison/{agent}-{model}-{dataset}.csv)')
    parser.add_argument('--output-dir', type=Path, default=None,
                       help='Output directory for analysis results (default: analysis/analysis-results/detailed-analysis/{config}/)')

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent.parent

    if args.csv:
        csv_path = args.csv
    else:
        csv_path = script_dir / "analysis" / "analysis-results" / "comparison" / f"{args.agent}-{args.model}-{args.dataset}.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    # Determine agent directory for loading planner.json files
    if args.dataset == 'swebench':
        agent_dir = script_dir / args.agent
    elif args.dataset == 'swebench-pro':
        agent_dir = script_dir / "SWE-bench_Pro-os" / args.agent
    else:
        raise ValueError(f"Unknown dataset: {args.dataset}")

    print(f"Analyzing: {csv_path}")
    print(f"Agent directory: {agent_dir}")

    # Detect available configs in CSV
    parser_obj = CSVParser(csv_path)
    available_configs = [cfg for cfg in args.config if parser_obj.has_config(cfg)]

    if not available_configs:
        print(f"\nWarning: None of the requested configs {args.config} are available in the CSV.")
        print(f"Available configs: {list(parser_obj.column_map.keys())}")
        return

    print(f"Requested configs: {args.config}")
    print(f"Available configs: {available_configs}")

    # Process each available config
    processed_count = 0
    for config in available_configs:
        print(f"\n{'='*80}")
        print(f"Processing Config: {config.upper()}")
        print(f"{'='*80}")

        if args.output_dir:
            output_dir = args.output_dir / config
        else:
            output_dir = script_dir / "analysis" / "analysis-results" / "comparison" / "detailed-analysis" / config

        try:
            # Run analysis
            analyzer = PatternAnalyzer(
                csv_path,
                config=config,
                agent_dir=agent_dir,
                model=args.model,
                dataset=args.dataset,
                run_id=args.run,
                version=args.refiner_version if config == 'refiner' else None
            )
            report = analyzer.generate_report(output_dir)
            processed_count += 1

        except Exception as e:
            print(f"\nError processing {config} config: {e}")
            continue

    if processed_count == 0:
        print("\n✗ No configs were successfully processed.")
    else:
        print(f"\n{'='*80}")
        print(f"✓ Analysis complete! Processed {processed_count} config(s).")
        print(f"{'='*80}")


if __name__ == "__main__":
    main()
