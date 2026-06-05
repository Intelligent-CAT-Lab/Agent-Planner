"""
Comprehensive analysis of pattern resolution comparing vanilla and refiner runs.

Analyzes:
1. Overall resolution statistics (R-R, R-U, U-R, U-U)
2. Trigger status breakdown
3. Instance-level details for U-R and R-U cases
4. Cost and step comparisons
5. Pattern analysis
6. Deeper insights into why triggers don't change outcomes

Usage:
    python analysis/analyze_pattern_resolution.py --agent SWE-agent --model deepseek-chat-v3-0324 --dataset swebench
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
    """Results comparing vanilla and refiner runs."""
    category: str  # R-R, R-U, U-R, U-U
    count: int
    percentage: float
    instances: List[Dict]
    avg_vanilla_cost: float
    avg_refiner_cost: float
    avg_vanilla_steps: float
    avg_refiner_steps: float
    pattern_distribution: Dict[str, int]


class PatternAnalyzer:
    """Analyzer for pattern resolution data."""

    PATTERN_TYPES = ['plan_violation', 'oscillation', 'long_stagnation', 'repeated_view']

    def __init__(self, csv_path: Path, agent_dir: Path = None, config: str = 'refiner',
                 model: str = None, dataset: str = None, run_id: int = 1, version: str = '5'):
        self.csv_path = csv_path
        self.agent_dir = agent_dir
        self.config = config
        self.model = model
        self.dataset = dataset
        self.run_id = run_id
        self.version = version
        self.vanilla_data: Dict[str, InstanceData] = {}
        self.refiner_data: Dict[str, InstanceData] = {}
        self._load_data()

    def _load_data(self):
        """Load and parse CSV data."""
        with open(self.csv_path, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Skip header rows (3 rows)
        data_rows = rows[3:]

        for row in data_rows:
            if not row or not row[0]:
                continue

            instance_id = row[0]

            # Parse vanilla run data (columns 1-10)
            if len(row) > 10 and row[1]:  # Check if vanilla data exists
                vanilla_resolved = row[1] == '1'
                vanilla_has_issue = row[2] == '1'
                vanilla_patterns = {
                    'plan_violation': row[3] == '1',
                    'oscillation': row[4] == '1',
                    'long_stagnation': row[5] == '1',
                    'repeated_view': row[6] == '1'
                }
                vanilla_lang = row[7] if len(row) > 7 else ''
                vanilla_unique_phases = row[8] if len(row) > 8 else ''
                vanilla_cost = float(row[9]) if len(row) > 9 and row[9] else 0.0
                vanilla_steps = int(row[10]) if len(row) > 10 and row[10] else 0

                self.vanilla_data[instance_id] = InstanceData(
                    instance_id=instance_id,
                    resolved=vanilla_resolved,
                    has_issue=vanilla_has_issue,
                    patterns=vanilla_patterns,
                    lang=vanilla_lang,
                    unique_phases=vanilla_unique_phases,
                    cost=vanilla_cost,
                    steps=vanilla_steps
                )

            # Parse refiner run data
            # Structure depends on whether Vanilla Rerun exists:
            # - With rerun: Vanilla (1-10), Vanilla Rerun (11-21), LivePlan (22-33)
            # - Without rerun: Vanilla (1-10), LivePlan (11-22)
            # Detect by checking if column 11 is either vanilla rerun resolution or refiner trigger
            # Vanilla rerun starts with resolution status, refiner starts with trigger status (0/1)
            # We can detect by checking the total row length or header structure
            # For simplicity, check if we have more than 23 columns (means rerun exists)
            if len(row) > 23:
                refiner_start_idx = 22  # Has vanilla rerun
            else:
                refiner_start_idx = 11  # No vanilla rerun

            if len(row) > refiner_start_idx and row[refiner_start_idx]:
                try:
                    refiner_has_planner = row[refiner_start_idx] == '1'
                    refiner_resolved = row[refiner_start_idx + 1] == '1' if len(row) > refiner_start_idx + 1 else False
                    refiner_has_issue = row[refiner_start_idx + 2] == '1' if len(row) > refiner_start_idx + 2 else False
                    refiner_overlapping = row[refiner_start_idx + 3].split(',') if len(row) > refiner_start_idx + 3 and row[refiner_start_idx + 3] else []
                    refiner_patterns = {
                        'plan_violation': row[refiner_start_idx + 4] == '1' if len(row) > refiner_start_idx + 4 else False,
                        'oscillation': row[refiner_start_idx + 5] == '1' if len(row) > refiner_start_idx + 5 else False,
                        'long_stagnation': row[refiner_start_idx + 6] == '1' if len(row) > refiner_start_idx + 6 else False,
                        'repeated_view': row[refiner_start_idx + 7] == '1' if len(row) > refiner_start_idx + 7 else False
                    }
                    refiner_lang = row[refiner_start_idx + 8] if len(row) > refiner_start_idx + 8 else ''
                    refiner_unique_phases = row[refiner_start_idx + 9] if len(row) > refiner_start_idx + 9 else ''
                    refiner_cost = float(row[refiner_start_idx + 10]) if len(row) > refiner_start_idx + 10 and row[refiner_start_idx + 10] else 0.0
                    refiner_steps = int(row[refiner_start_idx + 11]) if len(row) > refiner_start_idx + 11 and row[refiner_start_idx + 11] else 0

                    self.refiner_data[instance_id] = InstanceData(
                        instance_id=instance_id,
                        resolved=refiner_resolved,
                        has_issue=refiner_has_issue,
                        patterns=refiner_patterns,
                        lang=refiner_lang,
                        unique_phases=refiner_unique_phases,
                        cost=refiner_cost,
                        steps=refiner_steps,
                        has_planner=refiner_has_planner,
                        overlapping_issues=refiner_overlapping
                    )
                except (ValueError, IndexError) as e:
                    print(f"Warning: Error parsing refiner data for {instance_id}: {e}")

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

    def _extract_planner_stats(self, planner_data: Dict) -> Dict:
        """Extract summary statistics from planner.json."""
        if not planner_data:
            return None

        summary = planner_data.get('summary', {})
        interventions = planner_data.get('interventions', [])

        # Extract trigger types across all interventions
        trigger_types = set()
        for intervention in interventions:
            rule_triggers = intervention.get('state_summary', {}).get('rule_triggers', [])
            if not rule_triggers:
                trigger_types.add('plan_violation')
            else:
                # rule_triggers is a list of dicts with 'rule_id' key
                for trigger in rule_triggers:
                    if isinstance(trigger, dict):
                        trigger_types.add(trigger.get('rule_id', 'unknown'))
                    else:
                        trigger_types.add(str(trigger))

        # Extract intervention details
        intervention_details = []
        for intervention in interventions:
            rule_triggers = intervention.get('state_summary', {}).get('rule_triggers', [])
            # Extract rule_ids from trigger dicts
            trigger_ids = []
            if rule_triggers:
                for trigger in rule_triggers:
                    if isinstance(trigger, dict):
                        trigger_ids.append(trigger.get('rule_id', 'unknown'))
                    else:
                        trigger_ids.append(str(trigger))
            else:
                trigger_ids = ['plan_violation']

            intervention_details.append({
                'step': intervention.get('step'),
                'planner_type': intervention.get('planner_type'),
                'content': intervention.get('content'),
                'rule_triggers': trigger_ids
            })

        return {
            'total_interventions': summary.get('total_interventions', 0),
            'monitor_count': summary.get('monitor_count', 0),
            'refiner_count': summary.get('refiner_count', 0),
            'monitor_total_latency_ms': summary.get('monitor_total_latency_ms', 0.0),
            'refiner_total_latency_ms': summary.get('refiner_total_latency_ms', 0.0),
            'refiner_total_cost': summary.get('refiner_total_cost', 0.0),
            'trigger_types': sorted(list(trigger_types)),
            'interventions': intervention_details
        }

    def analyze_trigger_status(self) -> Dict:
        """Analyze instances based on trigger status."""
        triggered = [iid for iid, data in self.refiner_data.items() if data.has_planner]
        non_triggered = [iid for iid, data in self.refiner_data.items() if not data.has_planner]

        triggered_resolved = sum(1 for iid in triggered if self.refiner_data[iid].resolved)
        triggered_unresolved = len(triggered) - triggered_resolved

        return {
            'total_refiner_instances': len(self.refiner_data),
            'triggered_count': len(triggered),
            'triggered_percentage': len(triggered) / len(self.refiner_data) * 100 if self.refiner_data else 0,
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
            instances_to_check = [iid for iid, data in self.refiner_data.items() if data.has_planner]
        else:
            instances_to_check = list(self.refiner_data.keys())

        for instance_id in instances_to_check:
            if instance_id not in self.vanilla_data:
                continue

            vanilla = self.vanilla_data[instance_id]
            refiner = self.refiner_data[instance_id]

            if vanilla.resolved and refiner.resolved:
                categories['R-R'].append(instance_id)
            elif vanilla.resolved and not refiner.resolved:
                categories['R-U'].append(instance_id)
            elif not vanilla.resolved and refiner.resolved:
                categories['U-R'].append(instance_id)
            else:
                categories['U-U'].append(instance_id)

        return categories

    def analyze_category_details(self, category: str, instance_ids: List[str]) -> ComparisonResult:
        """Detailed analysis for a specific category."""
        instances_detail = []
        vanilla_costs = []
        refiner_costs = []
        vanilla_steps_list = []
        refiner_steps_list = []
        pattern_counter = Counter()

        for iid in instance_ids:
            if iid not in self.vanilla_data or iid not in self.refiner_data:
                continue

            vanilla = self.vanilla_data[iid]
            refiner = self.refiner_data[iid]

            vanilla_costs.append(vanilla.cost)
            refiner_costs.append(refiner.cost)
            vanilla_steps_list.append(vanilla.steps)
            refiner_steps_list.append(refiner.steps)

            # Count patterns in vanilla run
            for pattern, triggered in vanilla.patterns.items():
                if triggered:
                    pattern_counter[pattern] += 1

            # Load planner stats if has_planner
            planner_stats = None
            if refiner.has_planner:
                planner_data = self._load_planner_json(iid)
                planner_stats = self._extract_planner_stats(planner_data)

            refiner_detail = {
                'resolved': refiner.resolved,
                'has_issue': refiner.has_issue,
                'patterns': refiner.patterns,
                'overlapping_issues': refiner.overlapping_issues,
                'lang': refiner.lang,
                'unique_phases': refiner.unique_phases,
                'cost': refiner.cost,
                'steps': refiner.steps,
                'has_planner': refiner.has_planner
            }

            if planner_stats:
                refiner_detail['planner_stats'] = planner_stats

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
                'refiner': refiner_detail
            })

        total_instances = len(self.refiner_data)

        return ComparisonResult(
            category=category,
            count=len(instance_ids),
            percentage=len(instance_ids) / total_instances * 100 if total_instances > 0 else 0,
            instances=instances_detail,
            avg_vanilla_cost=sum(vanilla_costs) / len(vanilla_costs) if vanilla_costs else 0,
            avg_refiner_cost=sum(refiner_costs) / len(refiner_costs) if refiner_costs else 0,
            avg_vanilla_steps=sum(vanilla_steps_list) / len(vanilla_steps_list) if vanilla_steps_list else 0,
            avg_refiner_steps=sum(refiner_steps_list) / len(refiner_steps_list) if refiner_steps_list else 0,
            pattern_distribution=dict(pattern_counter)
        )

    def analyze_uu_no_change_reasons(self, uu_instances: List[str]) -> Dict:
        """
        Deep analysis of U-U cases where triggers fired but no improvement.
        Investigates:
        1. Pattern persistence (same patterns in both runs)
        2. Phase behavior changes
        3. Cost/step efficiency
        """
        analysis = {
            'total': len(uu_instances),
            'persistent_patterns': [],  # Same patterns appear in both runs
            'new_patterns': [],  # New patterns in refiner
            'resolved_patterns': [],  # Patterns fixed but still unresolved
            'no_pattern_vanilla': [],  # Vanilla had no patterns but still failed
            'phase_changes': {
                'expanded': [],  # More unique phases in refiner
                'reduced': [],  # Fewer unique phases in refiner
                'similar': []   # Similar phase count
            },
            'cost_analysis': {
                'increased': [],  # Refiner cost more
                'decreased': [],  # Refiner cost less
                'similar': []     # Similar cost
            }
        }

        for iid in uu_instances:
            if iid not in self.vanilla_data or iid not in self.refiner_data:
                continue

            vanilla = self.vanilla_data[iid]
            refiner = self.refiner_data[iid]

            # Pattern analysis
            vanilla_pattern_set = {p for p, v in vanilla.patterns.items() if v}
            refiner_pattern_set = {p for p, v in refiner.patterns.items() if v}

            persistent = vanilla_pattern_set & refiner_pattern_set
            new = refiner_pattern_set - vanilla_pattern_set
            resolved = vanilla_pattern_set - refiner_pattern_set

            if persistent:
                analysis['persistent_patterns'].append({
                    'instance_id': iid,
                    'patterns': list(persistent)
                })
            if new:
                analysis['new_patterns'].append({
                    'instance_id': iid,
                    'patterns': list(new)
                })
            if resolved:
                analysis['resolved_patterns'].append({
                    'instance_id': iid,
                    'patterns': list(resolved)
                })
            if not vanilla_pattern_set:
                analysis['no_pattern_vanilla'].append(iid)

            # Phase analysis
            vanilla_phases = set(vanilla.unique_phases.split(',')) if vanilla.unique_phases else set()
            refiner_phases = set(refiner.unique_phases.split(',')) if refiner.unique_phases else set()

            if len(refiner_phases) > len(vanilla_phases) * 1.2:
                analysis['phase_changes']['expanded'].append(iid)
            elif len(refiner_phases) < len(vanilla_phases) * 0.8:
                analysis['phase_changes']['reduced'].append(iid)
            else:
                analysis['phase_changes']['similar'].append(iid)

            # Cost analysis
            cost_ratio = refiner.cost / vanilla.cost if vanilla.cost > 0 else float('inf')
            if cost_ratio > 1.2:
                analysis['cost_analysis']['increased'].append(iid)
            elif cost_ratio < 0.8:
                analysis['cost_analysis']['decreased'].append(iid)
            else:
                analysis['cost_analysis']['similar'].append(iid)

        return analysis

    def analyze_ru_vanilla_behavior(self, ru_instances: List[str]) -> Dict:
        """
        Analyze R-U cases to understand if vanilla success was luck or genuine.
        Checks:
        1. Did vanilla have patterns but still succeed?
        2. Phase diversity comparison
        3. Was vanilla solution brittle (low cost/steps might indicate quick lucky path)?
        """
        analysis = {
            'total': len(ru_instances),
            'vanilla_with_patterns': [],  # Vanilla succeeded despite patterns
            'vanilla_no_patterns': [],  # Vanilla clean success
            'vanilla_quick_wins': [],  # Low cost/steps (potential luck)
            'refiner_pattern_introduced': [],  # Refiner introduced new patterns
            'phase_analysis': {
                'vanilla_phases': [],
                'refiner_phases': [],
                'phase_divergence': []
            }
        }

        # Calculate percentile thresholds for "quick wins"
        all_vanilla_costs = [v.cost for v in self.vanilla_data.values() if v.cost > 0]
        all_vanilla_steps = [v.steps for v in self.vanilla_data.values() if v.steps > 0]

        cost_25th = sorted(all_vanilla_costs)[len(all_vanilla_costs) // 4] if all_vanilla_costs else 0
        steps_25th = sorted(all_vanilla_steps)[len(all_vanilla_steps) // 4] if all_vanilla_steps else 0

        for iid in ru_instances:
            if iid not in self.vanilla_data or iid not in self.refiner_data:
                continue

            vanilla = self.vanilla_data[iid]
            refiner = self.refiner_data[iid]

            vanilla_has_patterns = any(vanilla.patterns.values())
            refiner_pattern_set = {p for p, v in refiner.patterns.items() if v}
            vanilla_pattern_set = {p for p, v in vanilla.patterns.items() if v}

            if vanilla_has_patterns:
                analysis['vanilla_with_patterns'].append({
                    'instance_id': iid,
                    'patterns': list(vanilla_pattern_set),
                    'cost': vanilla.cost,
                    'steps': vanilla.steps
                })
            else:
                analysis['vanilla_no_patterns'].append(iid)

            # Check for quick wins
            if vanilla.cost <= cost_25th and vanilla.steps <= steps_25th:
                analysis['vanilla_quick_wins'].append({
                    'instance_id': iid,
                    'cost': vanilla.cost,
                    'steps': vanilla.steps,
                    'percentile': '25th or below'
                })

            # Pattern introduction
            new_patterns = refiner_pattern_set - vanilla_pattern_set
            if new_patterns:
                analysis['refiner_pattern_introduced'].append({
                    'instance_id': iid,
                    'new_patterns': list(new_patterns)
                })

            # Phase analysis
            vanilla_phases = set(vanilla.unique_phases.split(',')) if vanilla.unique_phases else set()
            refiner_phases = set(refiner.unique_phases.split(',')) if refiner.unique_phases else set()

            phase_overlap = len(vanilla_phases & refiner_phases)
            phase_union = len(vanilla_phases | refiner_phases)
            divergence = 1 - (phase_overlap / phase_union if phase_union > 0 else 0)

            if divergence > 0.5:
                analysis['phase_analysis']['phase_divergence'].append({
                    'instance_id': iid,
                    'divergence': divergence,
                    'vanilla_phases': list(vanilla_phases),
                    'refiner_phases': list(refiner_phases)
                })

        return analysis

    def analyze_planner_aggregates(self, triggered_instances: List[str]) -> Dict:
        """Aggregate planner statistics across all triggered instances."""
        total_triggered = len(triggered_instances)
        total_interventions = 0
        total_monitor_count = 0
        total_refiner_count = 0
        total_monitor_latency_ms = 0.0
        total_refiner_latency_ms = 0.0
        total_refiner_cost = 0.0
        trigger_type_distribution = Counter()

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

            for trigger_type in planner_stats['trigger_types']:
                trigger_type_distribution[trigger_type] += 1

        # Return per-instance averages
        stats = {
            'total_triggered': total_triggered,
            'trigger_type_distribution': dict(trigger_type_distribution)
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
        triggered_instances = [iid for iid, data in self.refiner_data.items() if data.has_planner]
        planner_aggregates = self.analyze_planner_aggregates(triggered_instances)

        # 4. Detailed analysis for each category
        category_results = {}
        for cat, instance_ids in categories.items():
            category_results[cat] = self.analyze_category_details(cat, instance_ids)

        # 5. Special analyses
        uu_analysis = self.analyze_uu_no_change_reasons(categories['U-U'])
        ru_analysis = self.analyze_ru_vanilla_behavior(categories['R-U'])

        # Compile full report
        report = {
            'summary': {
                'total_instances': len(self.refiner_data),
                'trigger_status': trigger_analysis,
                'planner_aggregates': planner_aggregates,
                'categories': {
                    cat: {
                        'count': len(instance_ids),
                        'percentage': len(instance_ids) / len(self.refiner_data) * 100 if self.refiner_data else 0
                    }
                    for cat, instance_ids in categories.items()
                }
            },
            'category_details': {
                cat: {
                    'count': result.count,
                    'percentage': result.percentage,
                    'avg_vanilla_cost': result.avg_vanilla_cost,
                    'avg_refiner_cost': result.avg_refiner_cost,
                    'avg_vanilla_steps': result.avg_vanilla_steps,
                    'avg_refiner_steps': result.avg_refiner_steps,
                    'pattern_distribution': result.pattern_distribution,
                    'instances': result.instances
                }
                for cat, result in category_results.items()
            }
            # ,
            # 'deep_analysis': {
            #     'uu_no_change_investigation': uu_analysis,
            #     'ru_vanilla_luck_investigation': ru_analysis
            # }
        }

        # Save JSON report
        json_path = output_dir / f"{self.csv_path.stem}-analysis.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n✓ JSON report saved to: {json_path}")

        # Print summary
        self._print_summary(report)

        return report

    def _print_summary(self, report: Dict):
        """Print formatted summary to console."""
        print("\n" + "="*80)
        print("PATTERN RESOLUTION ANALYSIS SUMMARY")
        print("="*80)

        summary = report['summary']
        print(f"\nTotal instances: {summary['total_instances']}")

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
            print(f"  Trigger type distribution: {pa['trigger_type_distribution']}")

        print(f"\nResolution Categories (Triggered instances only):")
        for cat, stats in summary['categories'].items():
            print(f"  {cat}: {stats['count']} ({stats['percentage']:.1f}%)")

        print(f"\nCost & Steps Comparison:")
        for cat in ['R-R', 'R-U', 'U-R', 'U-U']:
            details = report['category_details'][cat]
            if details['count'] == 0:
                continue
            print(f"\n  {cat} ({details['count']} instances):")
            print(f"    Vanilla  - Avg cost: ${details['avg_vanilla_cost']:.4f}, Avg steps: {details['avg_vanilla_steps']:.1f}")
            print(f"    Refiner  - Avg cost: ${details['avg_refiner_cost']:.4f}, Avg steps: {details['avg_refiner_steps']:.1f}")
            if details['avg_vanilla_cost'] > 0:
                cost_change = (details['avg_refiner_cost'] - details['avg_vanilla_cost']) / details['avg_vanilla_cost'] * 100
                step_change = (details['avg_refiner_steps'] - details['avg_vanilla_steps']) / details['avg_vanilla_steps'] * 100
                print(f"    Change   - Cost: {cost_change:+.1f}%, Steps: {step_change:+.1f}%")

        # # U-U deep analysis
        # uu = report['deep_analysis']['uu_no_change_investigation']
        # if uu['total'] > 0:
        #     print(f"\nU-U Deep Analysis ({uu['total']} instances):")
        #     print(f"  Persistent patterns: {len(uu['persistent_patterns'])} instances")
        #     print(f"  New patterns introduced: {len(uu['new_patterns'])} instances")
        #     print(f"  Patterns resolved but still failed: {len(uu['resolved_patterns'])} instances")
        #     print(f"  Vanilla had no patterns: {len(uu['no_pattern_vanilla'])} instances")
        #     print(f"  Phase expansion: {len(uu['phase_changes']['expanded'])} instances")
        #     print(f"  Phase reduction: {len(uu['phase_changes']['reduced'])} instances")

        # # R-U deep analysis
        # ru = report['deep_analysis']['ru_vanilla_luck_investigation']
        # if ru['total'] > 0:
        #     print(f"\nR-U Deep Analysis ({ru['total']} instances):")
        #     print(f"  Vanilla had patterns but succeeded: {len(ru['vanilla_with_patterns'])} instances")
        #     print(f"  Vanilla clean success: {len(ru['vanilla_no_patterns'])} instances")
        #     print(f"  Vanilla quick wins (potential luck): {len(ru['vanilla_quick_wins'])} instances")
        #     print(f"  Refiner introduced new patterns: {len(ru['refiner_pattern_introduced'])} instances")
        #     print(f"  High phase divergence: {len(ru['phase_analysis']['phase_divergence'])} instances")

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
    parser.add_argument('--refiner-run', type=int, default=1,
                       help='Refiner run ID (default: 1)')
    parser.add_argument('--refiner-version', type=str, default='5',
                       help='Refiner version (default: 5)')
    parser.add_argument('--csv', type=Path, default=None,
                       help='Path to CSV file (default: analysis/analysis-results/comparison/{agent}-{model}-{dataset}.csv)')
    parser.add_argument('--output-dir', type=Path, default=None,
                       help='Output directory for analysis results (default: analysis/analysis-results/detailed-analysis/)')

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent.parent

    if args.csv:
        csv_path = args.csv
    else:
        csv_path = script_dir / "analysis" / "analysis-results" / "comparison" / f"{args.agent}-{args.model}-{args.dataset}.csv"

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = script_dir / "analysis" / "analysis-results" / "detailed-analysis"

    # Determine agent directory for loading planner.json files
    if args.dataset == 'swebench':
        agent_dir = script_dir / args.agent
    elif args.dataset == 'swebench-pro':
        agent_dir = script_dir / "SWE-bench_Pro-os" / args.agent
    else:
        raise ValueError(f"Unknown dataset: {args.dataset}")

    print(f"Analyzing: {csv_path}")
    print(f"Agent directory: {agent_dir}")
    print(f"Output directory: {output_dir}")

    # Run analysis
    analyzer = PatternAnalyzer(
        csv_path,
        agent_dir=agent_dir,
        config='refiner',
        model=args.model,
        dataset=args.dataset,
        run_id=args.refiner_run,
        version=args.refiner_version
    )
    report = analyzer.generate_report(output_dir)

    print(f"\n✓ Analysis complete!")
    print(f"  Summary printed above")
    print(f"  Detailed JSON saved to: {output_dir}")


if __name__ == "__main__":
    main()
