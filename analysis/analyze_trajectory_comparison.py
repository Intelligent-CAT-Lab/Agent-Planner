"""
Alternative analysis techniques for investigating refiner effectiveness.

Deep-dive analyses:
1. Trajectory divergence analysis - when do vanilla and refiner paths diverge?
2. Phase transition analysis - how do phase sequences differ?
3. Pattern timing analysis - when do patterns first appear?
4. Efficiency frontier analysis - cost vs. success tradeoffs
5. Reproducibility vs. Validation analysis - for R-U cases

Usage:
    python analysis/analyze_trajectory_comparison.py --json <path-to-analysis-json>
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import defaultdict
import re


class TrajectoryComparator:
    """Advanced trajectory comparison and analysis."""

    def __init__(self, analysis_json_path: Path):
        self.json_path = analysis_json_path
        with open(analysis_json_path, 'r') as f:
            self.data = json.load(f)

        self.subscript_map = str.maketrans('₀₁₂₃₄₅₆₇₈₉', '0123456789')

    def parse_langutory(self, lang: str) -> List[Tuple[str, int]]:
        """
        Parse langutory string to list of (phase, count) tuples.
        E.g., 'L_navigate₃P₁V₁' -> [('L_navigate', 3), ('P', 1), ('V', 1)]
        """
        if not lang:
            return []

        # Convert subscripts to normal digits
        normalized = lang.translate(self.subscript_map)

        # Pattern: phase name followed by digits
        pattern = r'([A-Za-z_]+)(\d+)'
        matches = re.findall(pattern, normalized)

        return [(phase, int(count)) for phase, count in matches]

    def compute_trajectory_divergence(self, vanilla_lang: str, refiner_lang: str) -> Dict:
        """
        Compute when and how trajectories diverge.
        Returns divergence point, shared prefix length, and divergence type.
        """
        vanilla_seq = self.parse_langutory(vanilla_lang)
        refiner_seq = self.parse_langutory(refiner_lang)

        # Flatten to full sequences
        vanilla_full = []
        for phase, count in vanilla_seq:
            vanilla_full.extend([phase] * count)

        refiner_full = []
        for phase, count in refiner_seq:
            refiner_full.extend([phase] * count)

        # Find common prefix
        common_prefix_len = 0
        for i in range(min(len(vanilla_full), len(refiner_full))):
            if vanilla_full[i] == refiner_full[i]:
                common_prefix_len += 1
            else:
                break

        # Determine divergence type
        if common_prefix_len == len(vanilla_full) == len(refiner_full):
            divergence_type = 'identical'
        elif common_prefix_len == len(vanilla_full):
            divergence_type = 'refiner_extended'
        elif common_prefix_len == len(refiner_full):
            divergence_type = 'refiner_shortened'
        else:
            divergence_type = 'diverged'

        return {
            'common_prefix_length': common_prefix_len,
            'vanilla_total_steps': len(vanilla_full),
            'refiner_total_steps': len(refiner_full),
            'divergence_point': common_prefix_len if divergence_type == 'diverged' else None,
            'divergence_type': divergence_type,
            'vanilla_sequence': vanilla_full,
            'refiner_sequence': refiner_full
        }

    def analyze_phase_transitions(self, instances: List[Dict]) -> Dict:
        """
        Analyze phase transition patterns.
        Identifies common transition patterns that lead to success/failure.
        """
        transitions = {
            'vanilla': defaultdict(int),
            'refiner': defaultdict(int)
        }

        successful_transitions = {
            'vanilla': defaultdict(int),
            'refiner': defaultdict(int)
        }

        for inst in instances:
            vanilla_seq = self.parse_langutory(inst['vanilla']['lang'])
            refiner_seq = self.parse_langutory(inst['refiner']['lang'])

            # Extract transitions (phase -> next_phase)
            for seq, run_type in [(vanilla_seq, 'vanilla'), (refiner_seq, 'refiner')]:
                for i in range(len(seq) - 1):
                    transition = f"{seq[i][0]} -> {seq[i+1][0]}"
                    transitions[run_type][transition] += 1

                    # Track successful transitions
                    if inst[run_type]['resolved']:
                        successful_transitions[run_type][transition] += 1

        # Compute success rates for transitions
        transition_success_rates = {
            'vanilla': {},
            'refiner': {}
        }

        for run_type in ['vanilla', 'refiner']:
            for transition, count in transitions[run_type].items():
                success_count = successful_transitions[run_type][transition]
                transition_success_rates[run_type][transition] = {
                    'total': count,
                    'successful': success_count,
                    'success_rate': success_count / count if count > 0 else 0
                }

        return {
            'all_transitions': dict(transitions),
            'transition_success_rates': transition_success_rates
        }

    def analyze_ru_validation_vs_reproduction(self) -> Dict:
        """
        For R-U cases, analyze whether vanilla likely did validation or reproduction.
        Hypothesis: Quick validation-only runs might accidentally pass,
        while thorough reproduction reveals real issues.
        """
        ru_instances = self.data['category_details']['R-U']['instances']

        analysis = {
            'total': len(ru_instances),
            'vanilla_validation_only': [],  # Only V phases, no L_reproduce
            'vanilla_reproduction_focused': [],  # Heavy L_reproduce presence
            'vanilla_mixed': [],  # Both V and L_reproduce
            'refiner_shifts': {
                'validation_to_reproduction': [],  # Vanilla did V, refiner did L_reproduce
                'reproduction_to_validation': [],  # Opposite
                'both_same_focus': []
            }
        }

        for inst in ru_instances:
            iid = inst['instance_id']
            vanilla_phases = set(inst['vanilla']['unique_phases'].split(',')) if inst['vanilla']['unique_phases'] else set()
            refiner_phases = set(inst['refiner']['unique_phases'].split(',')) if inst['refiner']['unique_phases'] else set()

            # Categorize vanilla approach
            has_v = any('V_' in p for p in vanilla_phases)
            has_l_reproduce = 'L_reproduce' in vanilla_phases

            vanilla_lang_full = inst['vanilla']['lang']
            v_count = sum(count for phase, count in self.parse_langutory(vanilla_lang_full) if 'V_' in phase)
            l_reproduce_count = sum(count for phase, count in self.parse_langutory(vanilla_lang_full) if phase == 'L_reproduce')

            if has_v and not has_l_reproduce:
                analysis['vanilla_validation_only'].append({
                    'instance_id': iid,
                    'v_count': v_count,
                    'cost': inst['vanilla']['cost'],
                    'steps': inst['vanilla']['steps']
                })
            elif has_l_reproduce and l_reproduce_count >= v_count:
                analysis['vanilla_reproduction_focused'].append({
                    'instance_id': iid,
                    'l_reproduce_count': l_reproduce_count,
                    'v_count': v_count,
                    'cost': inst['vanilla']['cost'],
                    'steps': inst['vanilla']['steps']
                })
            else:
                analysis['vanilla_mixed'].append({
                    'instance_id': iid,
                    'l_reproduce_count': l_reproduce_count,
                    'v_count': v_count
                })

            # Analyze refiner shift
            refiner_v_count = sum(count for phase, count in self.parse_langutory(inst['refiner']['lang']) if 'V_' in phase)
            refiner_l_reproduce_count = sum(count for phase, count in self.parse_langutory(inst['refiner']['lang']) if phase == 'L_reproduce')

            vanilla_focus = 'validation' if v_count > l_reproduce_count else 'reproduction'
            refiner_focus = 'validation' if refiner_v_count > refiner_l_reproduce_count else 'reproduction'

            if vanilla_focus == 'validation' and refiner_focus == 'reproduction':
                analysis['refiner_shifts']['validation_to_reproduction'].append(iid)
            elif vanilla_focus == 'reproduction' and refiner_focus == 'validation':
                analysis['refiner_shifts']['reproduction_to_validation'].append(iid)
            else:
                analysis['refiner_shifts']['both_same_focus'].append(iid)

        return analysis

    def analyze_uu_trajectory_divergence(self) -> Dict:
        """
        For U-U cases with triggers, analyze trajectory divergence patterns.
        Why did the refiner change the path but not improve the outcome?
        """
        uu_instances = self.data['category_details']['U-U']['instances']

        analysis = {
            'total': len(uu_instances),
            'divergence_types': defaultdict(list),
            'early_divergence': [],  # Diverge within first 25% of trajectory
            'late_divergence': [],   # Diverge after 75% of trajectory
            'mid_divergence': [],    # Diverge in the middle
            'cost_efficiency': {
                'refiner_more_expensive_but_failed': [],  # Higher cost, still failed
                'refiner_cheaper_but_failed': []  # Lower cost, still failed
            }
        }

        for inst in uu_instances:
            iid = inst['instance_id']
            div = self.compute_trajectory_divergence(
                inst['vanilla']['lang'],
                inst['refiner']['lang']
            )

            analysis['divergence_types'][div['divergence_type']].append(iid)

            # Analyze divergence timing
            if div['divergence_type'] == 'diverged' and div['divergence_point'] is not None:
                divergence_ratio = div['divergence_point'] / div['vanilla_total_steps'] if div['vanilla_total_steps'] > 0 else 0

                if divergence_ratio < 0.25:
                    analysis['early_divergence'].append({
                        'instance_id': iid,
                        'divergence_point': div['divergence_point'],
                        'vanilla_steps': div['vanilla_total_steps']
                    })
                elif divergence_ratio > 0.75:
                    analysis['late_divergence'].append({
                        'instance_id': iid,
                        'divergence_point': div['divergence_point'],
                        'vanilla_steps': div['vanilla_total_steps']
                    })
                else:
                    analysis['mid_divergence'].append({
                        'instance_id': iid,
                        'divergence_point': div['divergence_point'],
                        'vanilla_steps': div['vanilla_total_steps']
                    })

            # Cost efficiency analysis
            cost_ratio = inst['refiner']['cost'] / inst['vanilla']['cost'] if inst['vanilla']['cost'] > 0 else float('inf')

            if cost_ratio > 1.5:  # 50% more expensive
                analysis['cost_efficiency']['refiner_more_expensive_but_failed'].append({
                    'instance_id': iid,
                    'vanilla_cost': inst['vanilla']['cost'],
                    'refiner_cost': inst['refiner']['cost'],
                    'cost_increase': (cost_ratio - 1) * 100
                })
            elif cost_ratio < 0.8:  # 20% cheaper
                analysis['cost_efficiency']['refiner_cheaper_but_failed'].append({
                    'instance_id': iid,
                    'vanilla_cost': inst['vanilla']['cost'],
                    'refiner_cost': inst['refiner']['cost'],
                    'cost_decrease': (1 - cost_ratio) * 100
                })

        return analysis

    def analyze_efficiency_frontier(self) -> Dict:
        """
        Analyze cost-effectiveness tradeoffs.
        Plot instances on cost vs. success dimensions.
        """
        all_categories = ['R-R', 'R-U', 'U-R', 'U-U']

        frontier = {
            'vanilla': {
                'resolved': {'costs': [], 'steps': []},
                'unresolved': {'costs': [], 'steps': []}
            },
            'refiner': {
                'resolved': {'costs': [], 'steps': []},
                'unresolved': {'costs': [], 'steps': []}
            },
            'improvement_efficiency': []  # U-R cases: cost increase vs. benefit
        }

        for cat in all_categories:
            instances = self.data['category_details'][cat]['instances']

            for inst in instances:
                # Vanilla
                status = 'resolved' if inst['vanilla']['resolved'] else 'unresolved'
                frontier['vanilla'][status]['costs'].append(inst['vanilla']['cost'])
                frontier['vanilla'][status]['steps'].append(inst['vanilla']['steps'])

                # Refiner
                status = 'resolved' if inst['refiner']['resolved'] else 'unresolved'
                frontier['refiner'][status]['costs'].append(inst['refiner']['cost'])
                frontier['refiner'][status]['steps'].append(inst['refiner']['steps'])

                # Track improvement efficiency for U-R
                if cat == 'U-R':
                    cost_increase = inst['refiner']['cost'] - inst['vanilla']['cost']
                    frontier['improvement_efficiency'].append({
                        'instance_id': inst['instance_id'],
                        'cost_increase': cost_increase,
                        'vanilla_cost': inst['vanilla']['cost'],
                        'refiner_cost': inst['refiner']['cost'],
                        'vanilla_steps': inst['vanilla']['steps'],
                        'refiner_steps': inst['refiner']['steps']
                    })

        # Compute statistics
        for run_type in ['vanilla', 'refiner']:
            for status in ['resolved', 'unresolved']:
                costs = frontier[run_type][status]['costs']
                steps = frontier[run_type][status]['steps']

                if costs:
                    frontier[run_type][status]['avg_cost'] = sum(costs) / len(costs)
                    frontier[run_type][status]['median_cost'] = sorted(costs)[len(costs) // 2]
                    frontier[run_type][status]['avg_steps'] = sum(steps) / len(steps)
                    frontier[run_type][status]['median_steps'] = sorted(steps)[len(steps) // 2]

        return frontier

    def generate_report(self, output_dir: Path):
        """Generate comprehensive trajectory comparison report."""
        output_dir.mkdir(parents=True, exist_ok=True)

        print("\n" + "="*80)
        print("TRAJECTORY COMPARISON ANALYSIS")
        print("="*80)

        # 1. Phase transition analysis
        print("\n[1] Analyzing phase transitions...")
        all_instances = []
        for cat in ['R-R', 'R-U', 'U-R', 'U-U']:
            all_instances.extend(self.data['category_details'][cat]['instances'])

        phase_analysis = self.analyze_phase_transitions(all_instances)

        # 2. R-U validation vs reproduction
        print("[2] Analyzing R-U validation vs reproduction patterns...")
        ru_analysis = self.analyze_ru_validation_vs_reproduction()

        # 3. U-U trajectory divergence
        print("[3] Analyzing U-U trajectory divergence...")
        uu_div_analysis = self.analyze_uu_trajectory_divergence()

        # 4. Efficiency frontier
        print("[4] Computing efficiency frontier...")
        efficiency = self.analyze_efficiency_frontier()

        report = {
            'phase_transitions': phase_analysis,
            'ru_validation_analysis': ru_analysis,
            'uu_divergence_analysis': uu_div_analysis,
            'efficiency_frontier': efficiency
        }

        # Save report
        json_path = output_dir / f"{self.json_path.stem}-trajectory-analysis.json"
        with open(json_path, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n✓ Trajectory analysis saved to: {json_path}")

        # Print summary
        self._print_summary(report, ru_analysis, uu_div_analysis, efficiency)

        return report

    def _print_summary(self, report: Dict, ru_analysis: Dict, uu_div: Dict, efficiency: Dict):
        """Print formatted summary."""
        print("\n" + "="*80)
        print("TRAJECTORY ANALYSIS SUMMARY")
        print("="*80)

        # R-U Analysis
        print(f"\nR-U Cases ({ru_analysis['total']} instances):")
        print(f"  Vanilla validation-only: {len(ru_analysis['vanilla_validation_only'])} instances")
        print(f"  Vanilla reproduction-focused: {len(ru_analysis['vanilla_reproduction_focused'])} instances")
        print(f"  Vanilla mixed approach: {len(ru_analysis['vanilla_mixed'])} instances")

        print(f"\n  Refiner shifts:")
        print(f"    Validation → Reproduction: {len(ru_analysis['refiner_shifts']['validation_to_reproduction'])}")
        print(f"    Reproduction → Validation: {len(ru_analysis['refiner_shifts']['reproduction_to_validation'])}")
        print(f"    Same focus maintained: {len(ru_analysis['refiner_shifts']['both_same_focus'])}")

        # U-U Analysis
        print(f"\nU-U Cases ({uu_div['total']} instances):")
        print(f"  Divergence types:")
        for div_type, instances in uu_div['divergence_types'].items():
            print(f"    {div_type}: {len(instances)} instances")

        print(f"\n  Divergence timing:")
        print(f"    Early divergence (<25%): {len(uu_div['early_divergence'])}")
        print(f"    Mid divergence (25-75%): {len(uu_div['mid_divergence'])}")
        print(f"    Late divergence (>75%): {len(uu_div['late_divergence'])}")

        print(f"\n  Cost efficiency:")
        print(f"    Refiner more expensive but failed: {len(uu_div['cost_efficiency']['refiner_more_expensive_but_failed'])}")
        print(f"    Refiner cheaper but failed: {len(uu_div['cost_efficiency']['refiner_cheaper_but_failed'])}")

        # Efficiency Frontier
        print(f"\nEfficiency Frontier:")
        for run_type in ['vanilla', 'refiner']:
            print(f"\n  {run_type.capitalize()}:")
            for status in ['resolved', 'unresolved']:
                data = efficiency[run_type][status]
                if 'avg_cost' in data:
                    print(f"    {status.capitalize()}: avg=${data['avg_cost']:.4f}, median=${data['median_cost']:.4f}, avg_steps={data['avg_steps']:.1f}")

        # Improvement efficiency
        if efficiency['improvement_efficiency']:
            improvements = efficiency['improvement_efficiency']
            avg_cost_increase = sum(i['cost_increase'] for i in improvements) / len(improvements)
            print(f"\n  U-R Improvement Efficiency:")
            print(f"    Average cost increase: ${avg_cost_increase:.4f}")
            print(f"    Min cost increase: ${min(i['cost_increase'] for i in improvements):.4f}")
            print(f"    Max cost increase: ${max(i['cost_increase'] for i in improvements):.4f}")

        print("\n" + "="*80)


def main():
    parser = argparse.ArgumentParser(
        description='Advanced trajectory comparison analysis'
    )
    parser.add_argument('--json', type=Path, required=True,
                       help='Path to analysis JSON file from analyze_pattern_resolution.py')
    parser.add_argument('--output-dir', type=Path, default=None,
                       help='Output directory (default: same as input JSON)')

    args = parser.parse_args()

    if not args.json.exists():
        raise FileNotFoundError(f"JSON file not found: {args.json}")

    output_dir = args.output_dir if args.output_dir else args.json.parent

    print(f"Input JSON: {args.json}")
    print(f"Output directory: {output_dir}")

    comparator = TrajectoryComparator(args.json)
    comparator.generate_report(output_dir)

    print("\n✓ Trajectory comparison complete!")


if __name__ == "__main__":
    main()
