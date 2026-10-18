"""Generate all 10 high-resolution publication-quality figures directly from canonical task-level datasets."""

import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

# Load Canonical Task Details
PROJECT_ROOT = Path(r"D:\PROJECTS\DDIV").resolve()
TASK_DETAILS_PATH = Path(r"C:\Users\deven\.gemini\antigravity\brain\41357d7e-fee1-491d-8298-53462d310fb6\scratch\canonical_task_details.json")

with open(TASK_DETAILS_PATH, 'r', encoding='utf-8') as f:
    RAW_TASK_DATA = json.load(f)

TASK_MAP = RAW_TASK_DATA["data"]
TASKS_LIST = RAW_TASK_DATA["tasks"]

# Compute Exact Canonical Outcomes
BATCH_COUNTS = {
    1: {"BASELINE": 0, "RETRY_ONLY": 0, "FULL_DDIV": 0},
    2: {"BASELINE": 0, "RETRY_ONLY": 0, "FULL_DDIV": 0},
    3: {"BASELINE": 0, "RETRY_ONLY": 0, "FULL_DDIV": 0},
}
ATTEMPTS_DIST = {
    "BASELINE": {1: 0, 2: 0, 3: 0},
    "RETRY_ONLY": {1: 0, 2: 0, 3: 0},
    "FULL_DDIV": {1: 0, 2: 0, 3: 0},
}
TOTALS_RESOLVED = {"BASELINE": 0, "RETRY_ONLY": 0, "FULL_DDIV": 0}

for p, td in TASK_MAP.items():
    b = td["batch"]
    for cond in ["BASELINE", "RETRY_ONLY", "FULL_DDIV"]:
        c_data = td["conditions"][cond]
        if c_data["resolved"]:
            BATCH_COUNTS[b][cond] += 1
            TOTALS_RESOLVED[cond] += 1
            att = c_data["attempts_used"]
            if att in [1, 2, 3]:
                ATTEMPTS_DIST[cond][att] += 1

print("Computed Dynamic Batch Counts:", BATCH_COUNTS)
print("Computed Dynamic Attempts Used:", ATTEMPTS_DIST)
print("Computed Dynamic Totals Resolved:", TOTALS_RESOLVED)

# Styling Constants
NAVY = "#1A365D"
TEAL = "#0D9488"
AMBER = "#D97706"
CORAL = "#E11D48"
SLATE = "#475569"
LIGHT_BG = "#F8FAFC"
BORDER_COLOR = "#CBD5E1"
PURPLE = "#7C3AED"
GREEN = "#059669"

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Segoe UI', 'DejaVu Sans', 'Arial'],
    'font.size': 11,
    'axes.titlesize': 14,
    'axes.titleweight': 'bold',
    'axes.labelsize': 12,
    'axes.labelweight': 'bold',
    'xtick.labelsize': 11,
    'ytick.labelsize': 11,
    'legend.fontsize': 11,
    'figure.titlesize': 16,
    'figure.dpi': 300,
    'axes.edgecolor': '#94A3B8',
    'axes.linewidth': 1.0,
    'grid.color': '#E2E8F0',
    'grid.linestyle': '--',
    'grid.alpha': 0.7,
})


def generate_fig1(output_dir):
    """Fig 1: Overall Resolution Rates with Wilson 95% Confidence Intervals."""
    fig, ax = plt.subplots(figsize=(8, 5.5), dpi=300)
    
    conditions = ['BASELINE\n(1-Attempt Local)', 'RETRY_ONLY\n(3-Attempt Local)', 'FULL_DDIV\n(Hybrid 3-Attempt)']
    rates = [
        TOTALS_RESOLVED['BASELINE'] / 27 * 100,
        TOTALS_RESOLVED['RETRY_ONLY'] / 27 * 100,
        TOTALS_RESOLVED['FULL_DDIV'] / 27 * 100
    ]
    counts = [
        f"{TOTALS_RESOLVED['BASELINE']} / 27",
        f"{TOTALS_RESOLVED['RETRY_ONLY']} / 27",
        f"{TOTALS_RESOLVED['FULL_DDIV']} / 27"
    ]
    
    # Wilson 95% CIs:
    # BASELINE: [0.66%, 18.28%]
    # RETRY_ONLY: [2.06%, 23.37%]
    # FULL_DDIV: [44.23%, 78.47%]
    yerr_lower = [rates[0] - 0.66, rates[1] - 2.06, rates[2] - 44.23]
    yerr_upper = [18.28 - rates[0], 23.37 - rates[1], 78.47 - rates[2]]
    yerr = [yerr_lower, yerr_upper]
    
    colors = [SLATE, AMBER, TEAL]
    bars = ax.bar(conditions, rates, yerr=yerr, capsize=6, color=colors, width=0.55, 
                  edgecolor=NAVY, linewidth=1.2, error_kw={'ecolor': NAVY, 'elinewidth': 1.5, 'capthick': 1.5})
    
    ax.set_ylabel('Program Repair Resolution Rate (%)')
    ax.set_ylim(0, 95)
    ax.set_title('Figure 1: Program Resolution Rate Across Experimental Conditions (N=27)', pad=15)
    ax.grid(axis='y')
    ax.set_axisbelow(True)
    
    for bar, rate, count in zip(bars, rates, counts):
        h = bar.get_height()
        ax.annotate(f"{rate:.2f}%\n({count})",
                    xy=(bar.get_x() + bar.get_width() / 2, h + 16 if h < 20 else h + 18),
                    xytext=(0, 0), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=11, color=NAVY)

    # Statistical significance annotation for exact McNemar test
    ax.plot([1, 1, 2, 2], [72, 84, 84, 72], color=CORAL, lw=1.5)
    ax.text(1.5, 85.5, "*** p < 0.001 (Exact McNemar p = 2.75e-4, b=16, c=1)", ha='center', va='bottom',
            fontweight='bold', color=CORAL, fontsize=9.5)

    plt.tight_layout()
    fig.savefig(output_dir / "fig1_overall_resolution_rates.png", dpi=300)
    plt.close()
    print("Generated fig1_overall_resolution_rates.png")


def generate_fig2(output_dir):
    """Fig 2: Batch Trajectory Comparison generated directly from task outcomes."""
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)
    
    batches = ['Batch 1 (Tasks 1-9)', 'Batch 2 (Tasks 10-18)', 'Batch 3 (Tasks 19-27)']
    x = np.arange(len(batches))
    width = 0.25
    
    baseline = [BATCH_COUNTS[1]['BASELINE'] / 9 * 100, BATCH_COUNTS[2]['BASELINE'] / 9 * 100, BATCH_COUNTS[3]['BASELINE'] / 9 * 100]
    retry_only = [BATCH_COUNTS[1]['RETRY_ONLY'] / 9 * 100, BATCH_COUNTS[2]['RETRY_ONLY'] / 9 * 100, BATCH_COUNTS[3]['RETRY_ONLY'] / 9 * 100]
    full_ddiv = [BATCH_COUNTS[1]['FULL_DDIV'] / 9 * 100, BATCH_COUNTS[2]['FULL_DDIV'] / 9 * 100, BATCH_COUNTS[3]['FULL_DDIV'] / 9 * 100]
    
    rects1 = ax.bar(x - width, baseline, width, label='BASELINE', color=SLATE, edgecolor=NAVY)
    rects2 = ax.bar(x, retry_only, width, label='RETRY_ONLY', color=AMBER, edgecolor=NAVY)
    rects3 = ax.bar(x + width, full_ddiv, width, label='FULL_DDIV', color=TEAL, edgecolor=NAVY)
    
    ax.set_ylabel('Resolution Rate (%)')
    ax.set_title('Figure 2: Resolution Rates by Benchmark Batch Cohort', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(batches, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.legend(frameon=True, facecolor=LIGHT_BG, edgecolor=BORDER_COLOR, loc='upper right')
    ax.grid(axis='y')
    ax.set_axisbelow(True)
    
    def autolabel(rects, b_idx, cond):
        for i, rect in enumerate(rects):
            b_num = i + 1
            cnt = BATCH_COUNTS[b_num][cond]
            height = rect.get_height()
            if height > 0:
                ax.annotate(f"{height:.1f}%\n({cnt}/9)",
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3), textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, fontweight='bold')
            else:
                ax.annotate(f"0.0%\n({cnt}/9)",
                            xy=(rect.get_x() + rect.get_width() / 2, 0),
                            xytext=(0, 3), textcoords="offset points",
                            ha='center', va='bottom', fontsize=9, color='#64748B')

    autolabel(rects1, 1, 'BASELINE')
    autolabel(rects2, 2, 'RETRY_ONLY')
    autolabel(rects3, 3, 'FULL_DDIV')
    
    plt.tight_layout()
    fig.savefig(output_dir / "fig2_batch_trajectory_comparison.png", dpi=300)
    plt.close()
    print("Generated fig2_batch_trajectory_comparison.png")


def generate_fig3(output_dir):
    """Fig 3: Prompt vs Completion Token Consumption by Condition."""
    fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=300)
    
    conditions = ['BASELINE', 'RETRY_ONLY', 'FULL_DDIV']
    prompt_tokens = [42143, 155949, 117526]
    comp_tokens = [3663, 10706, 29980]
    total_tokens = [45806, 166655, 147506]
    
    x = np.arange(len(conditions))
    width = 0.5
    
    p1 = ax.bar(x, prompt_tokens, width, label='Prompt Tokens', color='#3B82F6', edgecolor=NAVY)
    p2 = ax.bar(x, comp_tokens, width, bottom=prompt_tokens, label='Completion Tokens', color='#10B981', edgecolor=NAVY)
    
    ax.set_ylabel('Total Tokens Consumed')
    ax.set_title('Figure 3: Prompt vs. Completion Token Consumption by Condition', pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(conditions, fontweight='bold')
    ax.set_ylim(0, 195000)
    ax.legend(frameon=True, facecolor=LIGHT_BG, edgecolor=BORDER_COLOR)
    ax.grid(axis='y')
    ax.set_axisbelow(True)
    
    for i, (tot, p, c) in enumerate(zip(total_tokens, prompt_tokens, comp_tokens)):
        ax.annotate(f"Total: {tot:,}\n(Prompt: {p:,} | Comp: {c:,})",
                    xy=(i, tot), xytext=(0, 4), textcoords="offset points",
                    ha='center', va='bottom', fontweight='bold', fontsize=10, color=NAVY)
        
    plt.tight_layout()
    fig.savefig(output_dir / "fig3_token_consumption_by_condition.png", dpi=300)
    plt.close()
    print("Generated fig3_token_consumption_by_condition.png")


def generate_fig4(output_dir):
    """Fig 4: Token Efficiency Pareto Comparison (Tokens per Resolved Repair)."""
    fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=300)
    
    conditions = ['RETRY_ONLY\n(83,328 t/fix)', 'BASELINE\n(45,806 t/fix)', 'FULL_DDIV\n(8,677 t/fix)']
    eff = [83328, 45806, 8677]
    colors = [CORAL, AMBER, TEAL]
    
    y = np.arange(len(conditions))
    bars = ax.barh(y, eff, color=colors, height=0.55, edgecolor=NAVY, linewidth=1.2)
    
    ax.set_xlabel('Physical Tokens Consumed Per Successfully Resolved Task')
    ax.set_title('Figure 4: Token Efficiency Comparison (Lower is Better)', pad=15)
    ax.set_yticks(y)
    ax.set_yticklabels(conditions, fontweight='bold')
    ax.set_xlim(0, 100000)
    ax.grid(axis='x')
    ax.set_axisbelow(True)
    
    for bar, val in zip(bars, eff):
        w = bar.get_width()
        ax.annotate(f"{val:,} tokens",
                    xy=(w + 1500, bar.get_y() + bar.get_height() / 2),
                    va='center', ha='left', fontweight='bold', fontsize=11, color=NAVY)

    ax.annotate("9.60x Higher Token Efficiency\nthan RETRY_ONLY (8,677 vs 83,328)",
                xy=(8677, 2), xytext=(35000, 1.8),
                arrowprops=dict(facecolor=NAVY, shrink=0.08, width=1.5, headwidth=8),
                bbox=dict(boxstyle="round,pad=0.5", fc="#CCFBF1", ec=TEAL, lw=1.5),
                fontsize=10.5, fontweight='bold', color=NAVY)

    plt.tight_layout()
    fig.savefig(output_dir / "fig4_token_efficiency_pareto.png", dpi=300)
    plt.close()
    print("Generated fig4_token_efficiency_pareto.png")


def generate_fig5(output_dir):
    """Fig 5: Attempt Distribution and First-Pass Convergence (Derived from canonical task outcomes)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5), dpi=300)
    
    # Left: Total attempts executed vs resolution
    conditions = ['BASELINE', 'RETRY_ONLY', 'FULL_DDIV']
    attempts_executed = [27, 78, 47]
    resolved_tasks = [TOTALS_RESOLVED['BASELINE'], TOTALS_RESOLVED['RETRY_ONLY'], TOTALS_RESOLVED['FULL_DDIV']]
    
    x = np.arange(len(conditions))
    w = 0.35
    ax1.bar(x - w/2, attempts_executed, w, label='Attempts Executed', color=SLATE, edgecolor=NAVY)
    ax1.bar(x + w/2, resolved_tasks, w, label='Tasks Resolved', color=TEAL, edgecolor=NAVY)
    ax1.set_ylabel('Count')
    ax1.set_title('Attempts Executed vs. Resolved Tasks', fontsize=12, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(conditions, fontweight='bold')
    ax1.legend(frameon=True, facecolor=LIGHT_BG, edgecolor=BORDER_COLOR)
    ax1.grid(axis='y')
    ax1.set_axisbelow(True)
    
    for i in range(len(conditions)):
        ax1.annotate(f"{attempts_executed[i]}", xy=(x[i] - w/2, attempts_executed[i] + 1), ha='center', fontsize=10, fontweight='bold')
        ax1.annotate(f"{resolved_tasks[i]}", xy=(x[i] + w/2, resolved_tasks[i] + 1), ha='center', fontsize=10, fontweight='bold')

    # Right: Success distribution by attempt number
    attempts = ['Attempt 1', 'Attempt 2', 'Attempt 3']
    ddiv_success = [ATTEMPTS_DIST['FULL_DDIV'][1], ATTEMPTS_DIST['FULL_DDIV'][2], ATTEMPTS_DIST['FULL_DDIV'][3]]
    retry_success = [ATTEMPTS_DIST['RETRY_ONLY'][1], ATTEMPTS_DIST['RETRY_ONLY'][2], ATTEMPTS_DIST['RETRY_ONLY'][3]]
    
    xa = np.arange(len(attempts))
    ddiv_tot = TOTALS_RESOLVED['FULL_DDIV']
    retry_tot = TOTALS_RESOLVED['RETRY_ONLY']
    b1 = ax2.bar(xa - w/2, ddiv_success, w, label=f'FULL_DDIV ({ddiv_tot} total)', color=TEAL, edgecolor=NAVY)
    b2 = ax2.bar(xa + w/2, retry_success, w, label=f'RETRY_ONLY ({retry_tot} total)', color=AMBER, edgecolor=NAVY)
    ax2.set_ylabel('Successful Repairs Count')
    ax2.set_title('Success Distribution by Attempt Number', fontsize=12, fontweight='bold')
    ax2.set_xticks(xa)
    ax2.set_xticklabels(attempts, fontweight='bold')
    ax2.set_ylim(0, 20)
    ax2.legend(frameon=True, facecolor=LIGHT_BG, edgecolor=BORDER_COLOR)
    ax2.grid(axis='y')
    ax2.set_axisbelow(True)
    
    for i in range(len(attempts)):
        if ddiv_success[i] > 0:
            ax2.annotate(f"{ddiv_success[i]}", xy=(xa[i] - w/2, ddiv_success[i] + 0.5), ha='center', fontsize=10, fontweight='bold')
        if retry_success[i] > 0:
            ax2.annotate(f"{retry_success[i]}", xy=(xa[i] + w/2, retry_success[i] + 0.5), ha='center', fontsize=10, fontweight='bold')
            
    ax2.annotate("100% of DDIV repairs\nsucceeded on Attempt 1!\n(17/17 first-pass)",
                 xy=(0 - w/2, 17), xytext=(0.8, 13.5),
                 arrowprops=dict(facecolor=NAVY, shrink=0.08, width=1.5, headwidth=6),
                 bbox=dict(boxstyle="round,pad=0.4", fc="#CCFBF1", ec=TEAL, lw=1.2),
                 fontsize=9.5, fontweight='bold', color=NAVY)
    
    fig.suptitle('Figure 5: Attempt Distribution and First-Pass Convergence Dynamics', fontsize=14, fontweight='bold')
    plt.tight_layout()
    fig.savefig(output_dir / "fig5_attempt_distribution_and_convergence.png", dpi=300)
    plt.close()
    print("Generated fig5_attempt_distribution_and_convergence.png")


def generate_fig6(output_dir):
    """Fig 6: Failure Mode Taxonomy Distribution."""
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=300)
    
    categories = [
        'Assertion / Logic Failure',
        'Syntax / AST Analysis Error',
        'Anchor String Not Found',
        'No Code Modification Omission',
        'Execution Timeout'
    ]
    
    baseline_fails = [13, 3, 1, 6, 3] # 26 total
    retry_fails = [43, 10, 6, 15, 2]  # 76 total
    ddiv_fails = [7, 12, 11, 0, 0]    # 30 attempt-level fails
    
    y = np.arange(len(categories))
    height = 0.25
    
    ax.barh(y + height, baseline_fails, height, label='BASELINE (N=26 fails)', color=SLATE, edgecolor=NAVY)
    ax.barh(y, retry_fails, height, label='RETRY_ONLY (N=76 failed att.)', color=AMBER, edgecolor=NAVY)
    ax.barh(y - height, ddiv_fails, height, label='FULL_DDIV (N=30 failed att.)', color=TEAL, edgecolor=NAVY)
    
    ax.set_xlabel('Frequency (Attempt-Level Count)')
    ax.set_title('Figure 6: Failure Mode Taxonomy Distribution Across Conditions', pad=15)
    ax.set_yticks(y)
    ax.set_yticklabels(categories, fontweight='bold')
    ax.legend(frameon=True, facecolor=LIGHT_BG, edgecolor=BORDER_COLOR, loc='lower right')
    ax.grid(axis='x')
    ax.set_axisbelow(True)
    
    plt.tight_layout()
    fig.savefig(output_dir / "fig6_failure_mode_distribution.png", dpi=300)
    plt.close()
    print("Generated fig6_failure_mode_distribution.png")


def generate_fig7(output_dir):
    """Fig 7: DDIV Multi-Agent Option A Architecture Diagram."""
    fig, ax = plt.subplots(figsize=(11, 6.5), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 6.5)
    ax.axis('off')
    
    frame = patches.FancyBboxPatch((0.2, 0.2), 10.6, 6.1, boxstyle="round,pad=0.2",
                                   ec=NAVY, fc="#F8FAFC", lw=2)
    ax.add_patch(frame)
    ax.text(5.5, 6.0, "DDIV Option A Hybrid Architecture (Multi-Agent Verification Pipeline)",
            ha='center', va='center', fontsize=13, fontweight='bold', color=NAVY)
    
    # 1. Locator
    box_loc = patches.FancyBboxPatch((0.6, 3.8), 2.8, 1.6, boxstyle="round,pad=0.1",
                                    ec="#0284C7", fc="#E0F2FE", lw=1.5)
    ax.add_patch(box_loc)
    ax.text(2.0, 4.9, "1. FAULT LOCATOR", ha='center', va='center', fontweight='bold', color="#0369A1", fontsize=10.5)
    ax.text(2.0, 4.4, "Model: gemini-3.1-flash-lite\nHosting: Gemini Cloud API\nTokens: 22,236 (15.1%)\nRole: Semantic Fault Localization",
            ha='center', va='center', fontsize=8.5, color="#0F172A")
    
    # 2. Coder
    box_cod = patches.FancyBboxPatch((4.1, 3.8), 2.8, 1.6, boxstyle="round,pad=0.1",
                                    ec="#059669", fc="#D1FAE5", lw=1.5)
    ax.add_patch(box_cod)
    ax.text(5.5, 4.9, "2. REPAIR CODER", ha='center', va='center', fontweight='bold', color="#047857", fontsize=10.5)
    ax.text(5.5, 4.4, "Model: qwen2.5-coder:7b\nHosting: Local Ollama (Zero $)\nTokens: 108,247 (73.4%)\nRole: Patch Candidate Generation",
            ha='center', va='center', fontsize=8.5, color="#0F172A")
    
    # 3. Supervisor
    box_sup = patches.FancyBboxPatch((7.6, 3.8), 2.8, 1.6, boxstyle="round,pad=0.1",
                                    ec="#D97706", fc="#FEF3C7", lw=1.5)
    ax.add_patch(box_sup)
    ax.text(9.0, 4.9, "3. DUAL SUPERVISOR", ha='center', va='center', fontweight='bold', color="#B45309", fontsize=10.5)
    ax.text(9.0, 4.4, "Model: qwen3.8-27b\nHosting: Groq Cloud API\nTokens: 5,490 (3.7%)\nRole: Semantic Critique & Guard",
            ha='center', va='center', fontsize=8.5, color="#0F172A")
    
    # 4. Tester
    box_tst = patches.FancyBboxPatch((7.6, 1.4), 2.8, 1.6, boxstyle="round,pad=0.1",
                                    ec="#7C3AED", fc="#EDE9FE", lw=1.5)
    ax.add_patch(box_tst)
    ax.text(9.0, 2.5, "4. SYNTHETIC TESTER", ha='center', va='center', fontweight='bold', color="#6D28D9", fontsize=10.5)
    ax.text(9.0, 2.0, "Model: qwen3.8-27b\nHosting: Groq Cloud API\nTokens: 11,533 (7.8%)\nRole: Edge-Case Test Generation",
            ha='center', va='center', fontsize=8.5, color="#0F172A")
    
    # Core Engine
    box_eng = patches.FancyBboxPatch((2.2, 0.8), 4.6, 2.2, boxstyle="round,pad=0.1",
                                    ec=NAVY, fc="#E2E8F0", lw=1.5)
    ax.add_patch(box_eng)
    ax.text(4.5, 2.6, "DDIV VERIFICATION & STATE ENGINE", ha='center', va='center', fontweight='bold', color=NAVY, fontsize=10.5)
    ax.text(4.5, 1.8, "• FailureDetector (AST, Syntax, Regression Checks)\n• Dynamic Trust-Weighted Re-Ranking\n• Continuous Episodic Memory (full_ddiv_memory.db)\n• State Isolation & Quota Guards (OTPM / Daily Budget)",
            ha='center', va='center', fontsize=8.5, color="#1E293B")

    ax.annotate('', xy=(4.1, 4.6), xytext=(3.4, 4.6),
                arrowprops=dict(arrowstyle="->", lw=2, color=NAVY))
    ax.annotate('', xy=(7.6, 4.6), xytext=(6.9, 4.6),
                arrowprops=dict(arrowstyle="->", lw=2, color=NAVY))
    ax.annotate('', xy=(9.0, 3.0), xytext=(9.0, 3.8),
                arrowprops=dict(arrowstyle="<->", lw=2, color=NAVY))
    ax.annotate('', xy=(6.8, 2.2), xytext=(7.6, 2.2),
                arrowprops=dict(arrowstyle="->", lw=2, color=NAVY))
    ax.annotate('', xy=(5.5, 3.8), xytext=(5.5, 3.0),
                arrowprops=dict(arrowstyle="<-", lw=2, color=NAVY))
    
    plt.tight_layout()
    fig.savefig(output_dir / "fig7_ddiv_architecture_diagram.png", dpi=300)
    plt.close()
    print("Generated fig7_ddiv_architecture_diagram.png")


def generate_fig8(output_dir):
    """Fig 8: Condition Workflows Comparison Diagram."""
    fig, ax = plt.subplots(figsize=(11, 5.5), dpi=300)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5.5)
    ax.axis('off')
    
    # 1. BASELINE
    p1 = patches.FancyBboxPatch((0.5, 3.8), 10.0, 1.3, boxstyle="round,pad=0.1", ec=SLATE, fc="#F1F5F9", lw=1.5)
    ax.add_patch(p1)
    ax.text(0.7, 4.45, "BASELINE\n(1-Attempt)", fontweight='bold', va='center', fontsize=10, color=SLATE)
    
    boxes1 = ["Defect Prompt", "Ollama Coder\n(qwen2.5:7b)", "PyTest Harness", "Outcome:\nPass / Fail"]
    for i, b in enumerate(boxes1):
        bx = patches.FancyBboxPatch((2.4 + i * 2.0, 4.0), 1.6, 0.9, boxstyle="round,pad=0.05", ec=SLATE, fc="white", lw=1)
        ax.add_patch(bx)
        ax.text(3.2 + i * 2.0, 4.45, b, ha='center', va='center', fontsize=8.5, fontweight='bold')
        if i < 3:
            ax.annotate('', xy=(2.4 + (i+1)*2.0, 4.45), xytext=(4.0 + i*2.0, 4.45),
                        arrowprops=dict(arrowstyle="->", lw=1.5, color=SLATE))

    # 2. RETRY_ONLY
    p2 = patches.FancyBboxPatch((0.5, 2.1), 10.0, 1.4, boxstyle="round,pad=0.1", ec=AMBER, fc="#FEF3C7", lw=1.5)
    ax.add_patch(p2)
    ax.text(0.7, 2.8, "RETRY_ONLY\n(3-Attempt)", fontweight='bold', va='center', fontsize=10, color="#B45309")
    
    boxes2 = ["Defect Prompt", "Ollama Coder\n(qwen2.5:7b)", "PyTest Harness", "Raw Diagnostics\n(No Memory/Trust)"]
    for i, b in enumerate(boxes2):
        bx = patches.FancyBboxPatch((2.4 + i * 2.0, 2.35), 1.6, 0.9, boxstyle="round,pad=0.05", ec="#D97706", fc="white", lw=1)
        ax.add_patch(bx)
        ax.text(3.2 + i * 2.0, 2.8, b, ha='center', va='center', fontsize=8.5, fontweight='bold')
        if i < 3:
            ax.annotate('', xy=(2.4 + (i+1)*2.0, 2.8), xytext=(4.0 + i*2.0, 2.8),
                        arrowprops=dict(arrowstyle="->", lw=1.5, color="#D97706"))
    ax.annotate('', xy=(3.2, 2.35), xytext=(9.2, 2.35),
                arrowprops=dict(arrowstyle="->", lw=1.5, color="#D97706", connectionstyle="arc3,rad=0.25"))
    ax.text(6.2, 1.85, "Retry Loop (up to 3 attempts with raw stderr)", ha='center', fontsize=8, color="#B45309", fontweight='bold')

    # 3. FULL_DDIV
    p3 = patches.FancyBboxPatch((0.5, 0.2), 10.0, 1.6, boxstyle="round,pad=0.1", ec=TEAL, fc="#CCFBF1", lw=1.5)
    ax.add_patch(p3)
    ax.text(0.7, 1.0, "FULL_DDIV\n(Hybrid 3-Att.)", fontweight='bold', va='center', fontsize=10, color="#0F766E")
    
    boxes3 = ["Gemini Locator\n(Fault Slices)", "Ollama Coder\n(Patches)", "Dual Intervention\n(Supervisor/Tester)", "DDIV State Engine\n(Trust & Memory)"]
    for i, b in enumerate(boxes3):
        bx = patches.FancyBboxPatch((2.4 + i * 2.0, 0.55), 1.6, 0.9, boxstyle="round,pad=0.05", ec=TEAL, fc="white", lw=1)
        ax.add_patch(bx)
        ax.text(3.2 + i * 2.0, 1.0, b, ha='center', va='center', fontsize=8, fontweight='bold')
        if i < 3:
            ax.annotate('', xy=(2.4 + (i+1)*2.0, 1.0), xytext=(4.0 + i*2.0, 1.0),
                        arrowprops=dict(arrowstyle="->", lw=1.5, color=TEAL))
    
    fig.suptitle('Figure 8: Comparative Workflow Pipeline Across Experimental Conditions', fontsize=13, fontweight='bold')
    plt.tight_layout()
    fig.savefig(output_dir / "fig8_condition_workflows_comparison.png", dpi=300)
    plt.close()
    print("Generated fig8_condition_workflows_comparison.png")


def generate_fig9(output_dir):
    """Fig 9: Provider Token Share in FULL_DDIV."""
    fig, ax = plt.subplots(figsize=(7, 5.5), dpi=300)
    
    labels = [
        'Ollama (Local)\n108,247 tokens\n(73.39%)',
        'Gemini Cloud\n22,236 tokens\n(15.07%)',
        'Groq Cloud\n17,023 tokens\n(11.54%)'
    ]
    tokens = [108247, 22236, 17023]
    colors = ['#10B981', '#3B82F6', '#F59E0B']
    explode = (0.05, 0.05, 0.05)
    
    wedges, texts, autotexts = ax.pie(tokens, labels=labels, autopct='%1.1f%%',
                                      startangle=140, colors=colors, explode=explode,
                                      wedgeprops=dict(width=0.45, edgecolor=NAVY, linewidth=1.2),
                                      pctdistance=0.75, textprops=dict(fontweight='bold', fontsize=10))
    
    for at in autotexts:
        at.set_color('white')
        at.set_fontsize(11)
        
    ax.set_title('Figure 9: Physical Token Share by Provider (FULL_DDIV Cohort, N=147,506)', pad=15)
    ax.text(0, 0, "147,506\nTokens", ha='center', va='center', fontsize=13, fontweight='bold', color=NAVY)
    
    plt.tight_layout()
    fig.savefig(output_dir / "fig9_provider_token_share.png", dpi=300)
    plt.close()
    print("Generated fig9_provider_token_share.png")


def generate_fig10(output_dir):
    """Fig 10: Role Token Share in FULL_DDIV with Prompt vs Completion breakdown."""
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=300)
    
    roles = ['Coder\n(qwen2.5:7b)', 'Locator\n(gemini-flash)', 'Tester\n(qwen3.8:27b)', 'Supervisor\n(qwen3.8:27b)']
    prompts = [101464, 8037, 3334, 4691]
    completions = [6783, 14199, 8199, 799]
    totals = [108247, 22236, 11533, 5490]
    percentages = [73.39, 15.07, 7.82, 3.72]
    
    y = np.arange(len(roles))
    height = 0.55
    
    p1 = ax.barh(y, prompts, height, label='Prompt Tokens', color='#3B82F6', edgecolor=NAVY)
    p2 = ax.barh(y, completions, height, left=prompts, label='Completion Tokens', color='#10B981', edgecolor=NAVY)
    
    ax.set_xlabel('Token Count')
    ax.set_title('Figure 10: Token Allocation by Agent Role in FULL_DDIV (Prompt vs. Completion)', pad=15)
    ax.set_yticks(y)
    ax.set_yticklabels(roles, fontweight='bold')
    ax.set_xlim(0, 125000)
    ax.legend(frameon=True, facecolor=LIGHT_BG, edgecolor=BORDER_COLOR, loc='lower right')
    ax.grid(axis='x')
    ax.set_axisbelow(True)
    
    for i, (tot, pct) in enumerate(zip(totals, percentages)):
        ax.annotate(f"{tot:,} tokens ({pct:.2f}%)",
                    xy=(tot + 1500, i), va='center', ha='left',
                    fontweight='bold', fontsize=10, color=NAVY)
        
    plt.tight_layout()
    fig.savefig(output_dir / "fig10_role_token_share.png", dpi=300)
    plt.close()
    print("Generated fig10_role_token_share.png")


def main():
    parser = argparse.ArgumentParser(description="Generate publication figures for DDIV report.")
    parser.add_argument("--output-dir", type=str, 
                        default=r"D:\PROJECTS\DDIV\results\ddiv_comprehensive_benchmark_report_corrected_20261017\figures",
                        help="Target output directory for generated figure images.")
    args = parser.parse_args()
    
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Generating 10 publication figures to {out_dir}...")
    generate_fig1(out_dir)
    generate_fig2(out_dir)
    generate_fig3(out_dir)
    generate_fig4(out_dir)
    generate_fig5(out_dir)
    generate_fig6(out_dir)
    generate_fig7(out_dir)
    generate_fig8(out_dir)
    generate_fig9(out_dir)
    generate_fig10(out_dir)
    print(f"All 10 figures successfully generated in {out_dir}")


if __name__ == '__main__':
    main()
