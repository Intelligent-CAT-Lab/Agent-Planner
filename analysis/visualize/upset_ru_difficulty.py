from pathlib import Path
from io import BytesIO
import json
import yaml
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from matplotlib.patches import Patch
from upsetplot import UpSet
from datasets import load_dataset
import warnings

warnings.filterwarnings("ignore")

# ============================
# Constants and Configuration
# ============================

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG1 = "default"
CONFIG2 = "refiner"
DIFFICULTY_COLORS = ["#88CCEE", "#DDCC77", "#CC6677", "#117733"]
SWE_PRO_SAMPLED = BASE_DIR / "SWE-bench_Pro-os" / "SWE-agent" / "script" / "sample-data" / "samples" / "python" / "swebench-pro" / "sampled_instances.yaml"
SWE_PRO_GOLD = BASE_DIR / "analysis" / "analysis-results" / "swebench-pro_gold_patch_file_analysis.csv"

# Load name mappings
def load_name_maps():
    """Load name mappings from name_map.json."""
    name_map_path = Path(__file__).parent / "name_map.json"
    with open(name_map_path) as f:
        maps = json.load(f)
    return maps['MODEL_NAME_MAP'], maps['DATASET_NAME_MAP'], maps['CONFIG_NAME_MAP']

MODEL_NAME_MAP, DATASET_NAME_MAP, CONFIG_NAME_MAP = load_name_maps()

# Model file prefixes
MODEL_FILES = {
    'minimax-m2.5': 'minimax-m2.5',
    'gemini-2.5-flash': 'gemini-2.5-flash',
    'deepseek-chat-v3-0324': 'deepseek-chat-v3-0324'
}

# ============================
# Core Data Processing Functions
# ============================

def difficulty_from_file_count(num):
    """Convert number of modified files to difficulty level."""
    if num == 1:
        return 'easy'
    elif num in [2, 3]:
        return 'medium'
    elif 4 <= num <= 10:
        return 'hard'
    else:
        return 'very hard'

def load_swebench_pro_data():
    """Load SWE-bench Pro instance IDs and their difficulties."""
    with open(SWE_PRO_SAMPLED, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    
    instance_ids = [item['instance_id'] for item in data if 'instance_id' in item]
    
    df = pd.read_csv(SWE_PRO_GOLD).set_index('instance_id')
    difficulties = df.reindex(instance_ids)['num_files_modified'].map(difficulty_from_file_count)
    
    return {"instance_id": instance_ids, "difficulty": difficulties.tolist()}

def create_binary_dataframe(resolved_ids, all_ids, config_name):
    """Create a binary indicator DataFrame for resolved/unresolved instances."""
    data = []
    for inst_id in all_ids:
        data.append({
            "instance_id": inst_id, 
            config_name: 1 if inst_id in resolved_ids else 0
        })
    return pd.DataFrame(data)

def load_eval_results(path):
    """Load evaluation results JSON and extract resolved IDs."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if "resolved_ids" in data:
        return data["resolved_ids"]
    else:
        return [k for k, v in data.items() if v is True]

def create_dataset(path1, config1, path2, config2, benchmark_type="verified"):
    """Create merged dataset for two configurations."""
    # Load resolved IDs
    resolved_ids1 = load_eval_results(path1)
    resolved_ids2 = load_eval_results(path2)
    
    # Get instance IDs based on benchmark type
    if benchmark_type == "verified":
        swe_bench = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
        all_ids = list(swe_bench['instance_id'])
    else:  # pro
        swe_data = load_swebench_pro_data()
        all_ids = swe_data['instance_id']
    
    # Create DataFrames
    df1 = create_binary_dataframe(resolved_ids1, all_ids, config1)
    df2 = create_binary_dataframe(resolved_ids2, all_ids, config2)
    
    # Merge
    merged_df = pd.merge(df1, df2, on='instance_id')
    
    # Add difficulty
    if benchmark_type == "verified":
        difficulty_levels = {
            '<15 min fix': 'easy',
            '15 min - 1 hour': 'medium',
            '1-4 hours': 'hard',
            '>4 hours': 'very hard'
        }
        difficulty_mapping = {
            row["instance_id"]: difficulty_levels.get(row.get("difficulty"), "unknown")
            for row in swe_bench
        }
        merged_df["difficulty"] = merged_df["instance_id"].map(difficulty_mapping)
    else:
        merged_df = pd.merge(merged_df, pd.DataFrame(swe_data), on='instance_id', how='left')
    
    return merged_df

# ============================
# Visualization Functions
# ============================

def create_upset_image(df, config1, config2, show_difficulty_title=True):
    """Render UpSet plot and return as image array."""
    # Map config names to display names
    config1_display = CONFIG_NAME_MAP.get(config1, config1)
    config2_display = CONFIG_NAME_MAP.get(config2, config2)

    # Rename columns for display
    df_display = df.rename(columns={config1: config1_display, config2: config2_display})
    df_display = df_display.set_index([config1_display, config2_display])

    upset = UpSet(
        df_display,
        intersection_plot_elements=0,
        show_counts=True,
        sort_categories_by=None,
    )

    # Only show difficulty title if requested
    difficulty_title = "Instances by Difficulty" if show_difficulty_title else ""
    upset.add_stacked_bars(
        by="difficulty",
        colors=DIFFICULTY_COLORS,
        title=difficulty_title,
        elements=10
    )
    upset.plot()
    fig = plt.gcf()
    
    # Clean up axes
    for ax in fig.get_axes():
        ax.grid(False, axis='y')
        leg = ax.get_legend()
        if leg:
            leg.remove()
        
        # Set font sizes
        ax.xaxis.label.set_fontsize(20)
        ax.yaxis.label.set_fontsize(20)
        ax.tick_params(axis='x', labelsize=22)
        ax.tick_params(axis='y', labelsize=8)
        ax.tick_params(axis='both', labelsize=12)
        if ax.get_title():
            ax.set_title(ax.get_title(), fontsize=14, fontweight='bold')
    
    # Adjust text positions
    for i, ax in enumerate(fig.get_axes(), 1):
        for text in ax.texts:
            if i < 4:
                text.set_fontsize(18)
            else:
                text.set_fontsize(26)
                text.set_rotation(90)
                x, y = text.get_position()
                text.set_position((x, y + 5))
                text.set_va('bottom')
    
    # Save to buffer as PNG for composite
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=300, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    img = mpimg.imread(buf, format='png')
    buf.close()
    return img

def create_composite_figure(images, model_names, dataset_names):
    """Create composite figure with images for multiple models and dataset row labels."""
    n_models = len(images[0])
    n_datasets = len(images)
    fig, axes = plt.subplots(n_datasets, n_models, figsize=(11, 10))

    for row_idx, row_images in enumerate(images):
        for col_idx, (ax, img) in enumerate(zip(axes[row_idx], row_images)):
            ax.imshow(img)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)

            # Column title (model name) on top row
            if row_idx == 0:
                ax.set_title(model_names[col_idx], fontsize=16, fontweight='bold', pad=10)

            # Row label (dataset name) - positioned to avoid overlap
            if col_idx == 0:
                # Use text positioned outside the axis instead of ylabel
                ax.text(0.3, 0.5, dataset_names[row_idx],
                       transform=ax.transAxes,
                       fontsize=16, fontweight='bold',
                       rotation=90, va='center', ha='right')

    # Add legend
    legend_elements = [
        Patch(facecolor=DIFFICULTY_COLORS[i], label=label)
        for i, label in enumerate(["Easy", "Medium", "Hard", "Very Hard"])
    ]
    fig.legend(
        handles=legend_elements,
        loc='upper center',
        fontsize=14,
        frameon=True,
        ncol=4,
        bbox_to_anchor=(0.5, 0.97),
        handleheight=1.0,
        handlelength=1.0,
    )

    plt.subplots_adjust(wspace=0.02, hspace=-0.1, left=0.08, right=0.99, top=0.93, bottom=0.02)
    return fig

# ============================
# Main Execution
# ============================

def main():
    verified_images = []
    pro_images = []

    # Get model display names in order
    model_display_names = [MODEL_NAME_MAP[m] for m in MODEL_FILES.keys()]

    # Get dataset display names
    dataset_display_names = [
        DATASET_NAME_MAP['swebench'],
        DATASET_NAME_MAP['swebench-pro']
    ]

    # Process Verified benchmark
    for idx, (model_key, file_prefix) in enumerate(MODEL_FILES.items()):
        file1 = BASE_DIR / "SWE-agent" / "reports" / "default" / "swebench" / model_key / f"{file_prefix}.run-1.json"
        file2 = BASE_DIR / "SWE-agent" / "reports" / "refiner" / "version-5" / "swebench" / model_key / f"{file_prefix}.run-1.json"
        df = create_dataset(file1, CONFIG1, file2, CONFIG2, benchmark_type="verified")
        # Only show difficulty title on the first (leftmost) subplot
        verified_images.append(create_upset_image(df, CONFIG1, CONFIG2, show_difficulty_title=(idx == 0)))

    # Process PRO benchmark
    for idx, (model_key, file_prefix) in enumerate(MODEL_FILES.items()):
        file1 = BASE_DIR / "SWE-bench_Pro-os" / "SWE-agent" / "reports" / "default" / "swebench-pro" / "python" / model_key / "run-1" / "eval_results.json"
        file2 = BASE_DIR / "SWE-bench_Pro-os" / "SWE-agent" / "reports" / "refiner" / "version-5" / "swebench-pro" / "python" / model_key / "run-1" / "eval_results.json"
        df = create_dataset(file1, CONFIG1, file2, CONFIG2, benchmark_type="pro")
        # Only show difficulty title on the first (leftmost) subplot
        pro_images.append(create_upset_image(df, CONFIG1, CONFIG2, show_difficulty_title=(idx == 0)))

    # Create and save composite figure
    fig = create_composite_figure(
        [verified_images, pro_images],
        model_display_names,
        dataset_display_names
    )
    output_path = BASE_DIR / "analysis" / "figures" / "upset_ru_difficulty.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight', pad_inches=0.05)
    plt.close(fig)

    print(f"Figure saved to {output_path}")

if __name__ == "__main__":
    main()
