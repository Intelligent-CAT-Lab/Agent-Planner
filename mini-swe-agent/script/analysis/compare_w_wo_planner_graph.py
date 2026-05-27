"""
Compare graph complexity metrics between vanilla (no planner) vs config (monitor/refiner).
Example usage:
python compare_w_wo_planner_graph.py \
  --config refiner \
  --model deepseek-chat-v3-0324 \
  --run-id 1 \
  --version-id 1 \
  --reproducible
"""
import json
import argparse
from pathlib import Path
import numpy as np
import networkx as nx
from typing import Dict, List
from collections import defaultdict


def load_sample_instances(model: str, run_id: int) -> List[str]:
    """Load sampled instance IDs."""
    script_dir = Path(__file__).parent.parent
    sample_path = script_dir / "sample-data" / "samples" / "swebench" / model / str(run_id) / "sampled_instances.json"

    with open(sample_path, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    return [s['instance_id'] for s in samples]


def analyze_graph(graph_file: Path) -> Dict[str, float]:
    """Extract graph complexity metrics from JSON."""
    try:
        with open(graph_file, 'r', encoding='utf-8') as f:
            graph_data = json.load(f)

        nodes = graph_data.get('nodes', [])
        node_count = len(nodes)

        # Max step index
        max_step_index = 0
        for node in nodes:
            step_indices = node.get('step_indices', [])
            if step_indices:
                max_step_index = max(max_step_index, max(step_indices))

        # Execution edges only
        edges = graph_data.get('edges', [])
        exec_edge_count = sum(1 for edge in edges if edge.get('type') == 'exec')

        # Loop detection
        exec_edges = [(edge['source'], edge['target']) for edge in edges if edge.get('type') == 'exec']
        G_exec = nx.DiGraph()
        G_exec.add_edges_from(exec_edges)

        try:
            cycles = list(nx.simple_cycles(G_exec))
            loop_count = len(cycles)
            avg_loop_length = np.mean([len(cycle) for cycle in cycles]) if cycles else 0
        except:
            loop_count = 0
            avg_loop_length = 0

        return {
            "node_count": node_count,
            "exec_edge_count": exec_edge_count,
            "loop_count": loop_count,
            "avg_loop_length": float(avg_loop_length),
            "max_step_index": max_step_index
        }

    except Exception as e:
        return None


def find_graph_file(base_path: Path, instance_id: str) -> Path:
    """Find graph JSON file for an instance."""
    pattern = f"**/{instance_id}/{instance_id}.json"
    matches = list(base_path.glob(pattern))
    if matches:
        return matches[0]

    pattern = f"**/{instance_id}.json"
    matches = list(base_path.glob(pattern))
    return matches[0] if matches else None


def analyze_instance_graphs(graph_paths: List[Path], instance_ids: List[str]) -> Dict[str, List[Dict]]:
    """Analyze graphs for instances across multiple runs."""
    results = defaultdict(list)

    for graph_path in graph_paths:
        for instance_id in instance_ids:
            graph_file = find_graph_file(graph_path, instance_id)
            if graph_file and graph_file.exists():
                metrics = analyze_graph(graph_file)
                if metrics:
                    results[instance_id].append(metrics)

    return dict(results)


def compute_average_metrics(instance_results: Dict[str, List[Dict]]) -> Dict[str, Dict]:
    """Compute average metrics for each instance across runs."""
    avg_results = {}

    for instance_id, metrics_list in instance_results.items():
        if not metrics_list:
            continue

        avg_metrics = {}
        for key in ["node_count", "exec_edge_count", "loop_count", "avg_loop_length", "max_step_index"]:
            values = [m[key] for m in metrics_list if key in m]
            avg_metrics[key] = np.mean(values) if values else 0

        avg_results[instance_id] = avg_metrics

    return avg_results


def compute_overall_averages(results: Dict[str, Dict]) -> Dict[str, float]:
    """Compute overall average metrics across all instances."""
    if not results:
        return {
            "node_count": 0,
            "exec_edge_count": 0,
            "loop_count": 0,
            "avg_loop_length": 0,
            "max_step_index": 0
        }

    metrics = ["node_count", "exec_edge_count", "loop_count", "avg_loop_length", "max_step_index"]
    averages = {}

    for metric in metrics:
        values = [r[metric] for r in results.values() if metric in r]
        averages[metric] = float(np.mean(values)) if values else 0

    return averages


def generate_comparison_report(config: str, model: str, run_id: int, version_id: str,
                               vanilla_avg: Dict, config_avg: Dict,
                               vanilla_results: Dict, config_results: Dict) -> Dict:
    """Generate comparison report."""
    report = {
        'config': config,
        'model': model,
        'run_id': run_id,
        'version_id': version_id,
        'vanilla_average': vanilla_avg,
        'config_average': config_avg,
        'comparison': {}
    }

    metrics = ["node_count", "exec_edge_count", "loop_count", "avg_loop_length", "max_step_index"]
    for metric in metrics:
        v_val = vanilla_avg[metric]
        c_val = config_avg[metric]
        diff = c_val - v_val
        diff_pct = (diff / v_val * 100) if v_val > 0 else 0

        report['comparison'][metric] = {
            'vanilla': v_val,
            'config': c_val,
            'difference': diff,
            'difference_pct': diff_pct
        }

    # Instance-level details
    report['instance_count'] = {
        'vanilla': len(vanilla_results),
        'config': len(config_results)
    }

    return report


def print_summary(report: Dict):
    """Print comparison summary."""
    print("\n" + "="*80)
    print(f"Graph Complexity Comparison: {report['config'].upper()} vs Vanilla")
    print(f"Model: {report['model']}, Run: {report['run_id']}")
    if report['version_id']:
        print(f"Version: {report['version_id']}")
    print("="*80)

    print(f"\nInstance Count:")
    print(f"  Vanilla: {report['instance_count']['vanilla']}")
    print(f"  {report['config'].capitalize()}: {report['instance_count']['config']}")

    print(f"\nMetrics Comparison:")
    print(f"{'Metric':<20} {'Vanilla':>12} {report['config'].capitalize():>12} {'Diff':>12} {'Diff %':>12}")
    print("-" * 70)

    metrics_labels = [
        ("Nodes", "node_count"),
        ("Exec Edges", "exec_edge_count"),
        ("Loops", "loop_count"),
        ("Avg Loop Length", "avg_loop_length"),
        ("Steps", "max_step_index")
    ]

    for label, key in metrics_labels:
        comp = report['comparison'][key]
        print(f"{label:<20} {comp['vanilla']:>12.2f} {comp['config']:>12.2f} "
              f"{comp['difference']:>+12.2f} {comp['difference_pct']:>+11.1f}%")

    print("="*80)


def save_report(report: Dict, output_dir: Path):
    """Save comparison report to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    version_suffix = f"_version-{report['version_id']}" if report['version_id'] else ""
    output_file = output_dir / f"{report['config']}_{report['model'].split('/')[-1]}_run{report['run_id']}{version_suffix}_graph_comparison.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to: {output_file}")
    return output_file


def main():
    parser = argparse.ArgumentParser(description='Compare graph complexity between vanilla and planner configs')
    parser.add_argument('--config', type=str, required=True, choices=['monitor', 'refiner'],
                       help='Config type: monitor or refiner')
    parser.add_argument('--model', type=str, required=True,
                       help='Model name (e.g., gpt-5-mini, deepseek-chat-v3-0324)')
    parser.add_argument('--run-id', type=int, required=True,
                       help='Run ID for config graphs')
    parser.add_argument('--version-id', type=str, default=None,
                       help='Version ID (optional)')
    parser.add_argument('--reproducible', action='store_true',
                       help='Use reproducible mode with sampled instances from vanilla runs 1,2,3')

    args = parser.parse_args()

    script_dir = Path(__file__).parent.parent.parent

    # Load sampled instances if reproducible
    if args.reproducible:
        instance_ids = load_sample_instances(args.model, args.run_id)
        print(f"Loaded {len(instance_ids)} sampled instances")

        # Vanilla graphs from runs 1, 2, 3
        vanilla_paths = [
            script_dir / "graphs" / "default" / "swebench" / args.model / str(i)
            for i in [1, 2, 3]
        ]

        print(f"\nAnalyzing vanilla graphs from runs 1, 2, 3...")
        vanilla_instance_results = analyze_instance_graphs(vanilla_paths, instance_ids)
        vanilla_results = compute_average_metrics(vanilla_instance_results)
        print(f"Analyzed {len(vanilla_results)} vanilla instances (averaged across runs)")
    else:
        print("Non-reproducible mode: skipping vanilla analysis")
        vanilla_results = {}

    # Config graphs
    if args.version_id:
        config_path = script_dir / "graphs" / args.config / f"version-{args.version_id}" / "swebench" / args.model / f"run-{args.run_id}"
    else:
        config_path = script_dir / "graphs" / args.config / "swebench" / args.model / f"run-{args.run_id}"

    print(f"\nAnalyzing {args.config} graphs from run {args.run_id}...")

    if args.reproducible:
        config_instance_results = analyze_instance_graphs([config_path], instance_ids)
        config_results = compute_average_metrics(config_instance_results)
    else:
        # If not reproducible, analyze all graphs in config path
        instance_ids = []
        for graph_file in config_path.rglob("*.json"):
            if graph_file.parent.name == graph_file.stem:
                instance_ids.append(graph_file.stem)
        config_instance_results = analyze_instance_graphs([config_path], instance_ids)
        config_results = compute_average_metrics(config_instance_results)

    print(f"Analyzed {len(config_results)} {args.config} instances")

    # Compute overall averages
    vanilla_avg = compute_overall_averages(vanilla_results)
    config_avg = compute_overall_averages(config_results)

    # Generate report
    report = generate_comparison_report(
        args.config, args.model, args.run_id, args.version_id,
        vanilla_avg, config_avg, vanilla_results, config_results
    )

    # Save and print
    output_dir = Path(__file__).parent / "analysis-results" / "graph"
    save_report(report, output_dir)
    print_summary(report)


if __name__ == "__main__":
    main()
