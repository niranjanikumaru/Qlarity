"""
================================================================================
SEMICONDUCTOR YIELD & BENCHMARK GRAPH GENERATOR
Exports High-Resolution PNGs of Classical vs Quantum Analysis & Wafer Spatial Maps
================================================================================
Output: Individual publication-ready PNG figures (300 DPI) + Combined Dashboard
Location: ./output_charts/
================================================================================
"""

import os
import sys
import json
import time
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.colors as mcolors

# ==============================================================================
# GLOBAL STYLING & DIRECTORY SETUP
# ==============================================================================
OUTPUT_DIR = Path('output_charts')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Modern typography & palette settings
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica']
plt.rcParams['axes.edgecolor'] = '#cccccc'
plt.rcParams['axes.linewidth'] = 0.8
plt.rcParams['grid.color'] = '#e2e2e2'
plt.rcParams['grid.linestyle'] = '--'
plt.rcParams['grid.alpha'] = 0.7

COLORS = {
    'mc': '#f39c12',        # Golden amber for Monte Carlo
    'strat': '#3498db',     # Blue for Stratified
    'is': '#e74c3c',        # Red for Importance Sampling
    'exact': '#2ecc71',     # Emerald green for Exact
    'cdf': '#1abc9c',       # Teal for Conditional CDF
    'iqae': '#9b59b6',      # Royal purple for Quantum IQAE
    'pass': '#27ae60',      # Green
    'fail': '#c0392b',      # Dark red
    'bg_dark': '#1a2520',   # Dark wafer background
    'wafer_rim': '#4e6d58'  # Wafer edge border
}

# ==============================================================================
# 1. LOAD WAFER DATASET & VERIFY METRICS
# ==============================================================================
csv_candidates = [
    Path('synthetic_wafer_data.csv'),
    Path('../synthetic_wafer_data.csv'),
    Path('c:/Users/Lenovo/Downloads/Qlarity_Yield_Implemented/synthetic_wafer_data.csv')
]
csv_path = next((p for p in csv_candidates if p.exists()), None)
if not csv_path:
    raise FileNotFoundError("Could not find synthetic_wafer_data.csv")

print(f"Loading wafer dataset from '{csv_path}'...")
df = pd.read_csv(csv_path)
TOTAL_DIES = len(df)
TRUE_YIELD = float(df['Yield_Pass'].mean())
TRUE_FAIL = 1.0 - TRUE_YIELD

print(f"Loaded {TOTAL_DIES:,} dies. True Yield = {TRUE_YIELD*100:.2f}%, Failure Rate = {TRUE_FAIL*100:.2f}%")

# Load Qlarity benchmark summary if available
summary_candidates = [
    Path('qlarity-yield/evidence/benchmark-summary.json'),
    Path('evidence/benchmark-summary.json'),
    Path('../qlarity-yield/evidence/benchmark-summary.json')
]
bench_path = next((p for p in summary_candidates if p.exists()), None)
bench_data = {}
if bench_path:
    bench_data = json.loads(bench_path.read_text())

# ==============================================================================
# 2. RUN REPEATED SAMPLING EXPERIMENTS (MC, STRATIFIED, IS)
# ==============================================================================
SAMPLE_SIZES = [50, 100, 250, 500, 1000, 2500, 5000, 10000]
N_TRIALS = 300

rho = df['Normalized_Radius'].values
strata = np.zeros(TOTAL_DIES, dtype=int)
strata[rho >= 0.60] = 1
strata[rho >= 0.85] = 2
stratum_weights = [np.mean(strata == s) for s in range(3)]

# Importance Sampling Proposal (bias toward edge and low Vth)
risk_score = (1.0 + 2.2 * (rho**3)) + np.maximum(0, (0.350 - df['Threshold_Voltage_V'].values) / 0.015)
proposal_prob = risk_score / risk_score.sum()
uniform_prob = 1.0 / TOTAL_DIES
importance_weights = uniform_prob / proposal_prob

mc_rmse_list, strat_rmse_list, is_rmse_list = [], [], []
mc_ci_list, strat_ci_list, is_ci_list = [], [], []

print("Simulating classical sampling across sample budgets...")
for N in SAMPLE_SIZES:
    mc_ests, strat_ests, is_ests = [], [], []
    for trial in range(N_TRIALS):
        rng = np.random.RandomState(trial + 100)
        
        # 1. Simple Monte Carlo
        idx_mc = rng.choice(TOTAL_DIES, size=N, replace=False)
        mc_ests.append(df['Yield_Pass'].iloc[idx_mc].mean())
        
        # 2. Stratified Sampling
        n_per_s = [int(round(w * N)) for w in stratum_weights]
        n_per_s[-1] = N - sum(n_per_s[:-1])
        s_est = 0.0
        for s in range(3):
            s_idx = np.where(strata == s)[0]
            samp = rng.choice(s_idx, size=n_per_s[s], replace=False)
            s_est += df['Yield_Pass'].iloc[samp].mean() * stratum_weights[s]
        strat_ests.append(s_est)
        
        # 3. Importance Sampling
        idx_is = rng.choice(TOTAL_DIES, size=N, replace=True, p=proposal_prob)
        fails = (df['Yield_Pass'].iloc[idx_is].values == 0).astype(float)
        p_fail_hat = (fails * importance_weights[idx_is]).mean()
        is_ests.append(1.0 - p_fail_hat)
        
    mc_rmse_list.append(np.sqrt(np.mean((np.array(mc_ests) - TRUE_YIELD)**2)))
    strat_rmse_list.append(np.sqrt(np.mean((np.array(strat_ests) - TRUE_YIELD)**2)))
    is_rmse_list.append(np.sqrt(np.mean((np.array(is_ests) - TRUE_YIELD)**2)))
    
    mc_ci_list.append(1.96 * np.std(mc_ests))
    strat_ci_list.append(1.96 * np.std(strat_ests))
    is_ci_list.append(1.96 * np.std(is_ests))

# ==============================================================================
# GRAPH 1: CONVERGENCE RATES (RMSE VS SAMPLE SIZE N)
# ==============================================================================
print("Generating Graph 1: Convergence Rates...")
fig, ax = plt.subplots(figsize=(8, 6), dpi=300)
ax.plot(SAMPLE_SIZES, [e * 100 for e in mc_rmse_list], 'o-', color=COLORS['mc'], label='Simple Monte Carlo (MC)', linewidth=2.2, markersize=6)
ax.plot(SAMPLE_SIZES, [e * 100 for e in strat_rmse_list], 's-', color=COLORS['strat'], label='Stratified Spatial Sampling', linewidth=2.2, markersize=6)
ax.plot(SAMPLE_SIZES, [e * 100 for e in is_rmse_list], '^-', color=COLORS['is'], label='Classical Importance Sampling (IS)', linewidth=2.2, markersize=6)

# Theoretical 1/sqrt(N) Central Limit line
n_fine = np.linspace(40, 12000, 300)
theoretical_mc = (np.sqrt(TRUE_YIELD * TRUE_FAIL) / np.sqrt(n_fine)) * 100
ax.plot(n_fine, theoretical_mc, 'k--', alpha=0.6, linewidth=1.8, label=r'Theoretical $O(1/\sqrt{N})$ Limit')

ax.set_xscale('log')
ax.set_yscale('log')
ax.set_xlabel('Sample Size $N$ (Die Electrical Test Probes)', fontsize=12, fontweight='bold', labelpad=8)
ax.set_ylabel('Estimation RMSE (% Yield Error)', fontsize=12, fontweight='bold', labelpad=8)
ax.set_title('Estimation Error Convergence vs Test Sample Size\n(35,000-Die Silicon Wafer Ground Truth: 81.80% Yield)', fontsize=13, fontweight='bold', pad=12)
ax.grid(True, which='both', linestyle='--', alpha=0.5)
ax.legend(frameon=True, facecolor='white', framealpha=0.9, fontsize=10, loc='upper right')

# Annotation box
ax.annotate('IS achieves ~50-59% lower variance\nfor small sample budgets', 
            xy=(100, is_rmse_list[1]*100), xytext=(220, 1.2),
            arrowprops=dict(arrowstyle='->', color='#333333', lw=1.2),
            bbox=dict(boxstyle='round,pad=0.4', facecolor='#fffbe6', edgecolor='#e6d594', alpha=0.9),
            fontsize=9.5)

plt.tight_layout()
g1_path = OUTPUT_DIR / 'chart_1_convergence_rates.png'
plt.savefig(g1_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g1_path}")

# ==============================================================================
# GRAPH 2: VARIANCE REDUCTION PERCENTAGE
# ==============================================================================
print("Generating Graph 2: Variance Reduction...")
fig, ax = plt.subplots(figsize=(8, 5.5), dpi=300)
x_pos = np.arange(len(SAMPLE_SIZES))
w = 0.38

vr_strat = [(1.0 - (s / m)**2) * 100 for s, m in zip(strat_rmse_list, mc_rmse_list)]
vr_is = [(1.0 - (i / m)**2) * 100 for i, m in zip(is_rmse_list, mc_rmse_list)]

b1 = ax.bar(x_pos - w/2, vr_strat, width=w, label='Stratified Spatial Sampling', color=COLORS['strat'], alpha=0.85, edgecolor='#1f618d')
b2 = ax.bar(x_pos + w/2, vr_is, width=w, label='Classical Importance Sampling (IS)', color=COLORS['is'], alpha=0.85, edgecolor='#922b21')

ax.set_xticks(x_pos)
ax.set_xticklabels([f"{n:,}" for n in SAMPLE_SIZES], fontsize=10)
ax.set_xlabel('Sample Size $N$', fontsize=12, fontweight='bold', labelpad=8)
ax.set_ylabel('Variance Reduction vs Naive MC (%)', fontsize=12, fontweight='bold', labelpad=8)
ax.set_title('Variance Reduction Over Simple Monte Carlo\n(Quantifying Statistical Efficiency of Domain-Informed Sampling)', fontsize=13, fontweight='bold', pad=12)
ax.set_ylim(0, 75)
ax.grid(True, axis='y', linestyle='--', alpha=0.5)
ax.legend(frameon=True, facecolor='white', framealpha=0.9, fontsize=10, loc='upper right')

for bar in b2:
    y = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, y + 1.2, f'{y:.1f}%', ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#922b21')

plt.tight_layout()
g2_path = OUTPUT_DIR / 'chart_2_variance_reduction.png'
plt.savefig(g2_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g2_path}")

# ==============================================================================
# GRAPH 3: ESTIMATOR ERROR COMPARISON (QLARITY WORKBENCH SUITE)
# ==============================================================================
print("Generating Graph 3: Estimator Error Comparison...")
methods = ['Exact Encoded', 'Conditional CDF', 'Monte Carlo', 'Importance Sampling', 'Quantum IQAE']
mean_err = [0.0, 0.0, 0.00516 * 100, 0.00487 * 100, 0.00413 * 100]
max_err = [0.0, 0.0, 0.02168 * 100, 0.01986 * 100, 0.01330 * 100]
colors_m = [COLORS['exact'], COLORS['cdf'], COLORS['mc'], COLORS['is'], COLORS['iqae']]

fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=300)
x = np.arange(len(methods))
w = 0.35

bar_mean = ax.bar(x - w/2, mean_err, width=w, label='Mean Absolute Error (% Yield)', color=colors_m, alpha=0.85, edgecolor='#333333', linewidth=0.8)
bar_max = ax.bar(x + w/2, max_err, width=w, label='Maximum Absolute Error (% Yield)', color=colors_m, alpha=0.4, hatch='//', edgecolor='#333333', linewidth=0.8)

ax.set_xticks(x)
ax.set_xticklabels(methods, fontsize=10, fontweight='bold')
ax.set_ylabel('Estimation Absolute Error (% Yield)', fontsize=12, fontweight='bold', labelpad=8)
ax.set_title('Yield Estimation Accuracy Across 24 Benchmark Executions\n(Evaluated on Identical Discrete Semiconductor Predicate)', fontsize=13, fontweight='bold', pad=12)
ax.grid(True, axis='y', linestyle='--', alpha=0.5)
ax.legend(frameon=True, facecolor='white', framealpha=0.9, fontsize=10, loc='upper left')

for bar in bar_mean[2:]:
    y = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, y + 0.03, f'{y:.3f}%', ha='center', va='bottom', fontsize=8.5, fontweight='bold')
for bar in bar_max[2:]:
    y = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2.0, y + 0.03, f'{y:.3f}%', ha='center', va='bottom', fontsize=8.5)

plt.tight_layout()
g3_path = OUTPUT_DIR / 'chart_3_estimator_error_comparison.png'
plt.savefig(g3_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g3_path}")

# ==============================================================================
# GRAPH 4: PRACTICAL RUNTIME & RESOURCE COMPLEXITY
# ==============================================================================
print("Generating Graph 4: Practical Runtime & Resource Scaling...")
eval_labels = [
    'Conditional CDF\n(384 Queries)',
    'Monte Carlo\n(177,084 Evals)',
    'Importance Sampling\n(177,084 Evals)',
    'Exact Enumeration\n(1,536 Evals)',
    'Quantum IQAE\n(53,248 A-Calls)'
]
runtimes_ms = [0.135, 1.222, 2.190, 19.922, 1868.769]
colors_res = [COLORS['cdf'], COLORS['mc'], COLORS['is'], COLORS['exact'], COLORS['iqae']]

fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=300)
bars = ax.bar(eval_labels, runtimes_ms, color=colors_res, alpha=0.88, edgecolor='#333333', linewidth=0.8)
ax.set_yscale('log')
ax.set_ylabel('Wall-Clock Computation Time (Milliseconds) [Log Scale]', fontsize=11, fontweight='bold', labelpad=8)
ax.set_title('Execution Runtime Comparison (Simulator vs Classical Multi-Core)\nHighlighting Practical Circuit Synthesis & Depth Overhead', fontsize=12.5, fontweight='bold', pad=12)
ax.grid(True, which='both', axis='y', linestyle='--', alpha=0.5)

for bar, val in zip(bars, runtimes_ms):
    if val >= 1000:
        label = f"{val/1000:.2f} s"
    elif val >= 1:
        label = f"{val:.2f} ms"
    else:
        label = f"{val*1000:.0f} µs"
    ax.text(bar.get_x() + bar.get_width()/2.0, val * 1.35, label, ha='center', va='bottom', fontsize=9, fontweight='bold')

plt.tight_layout()
g4_path = OUTPUT_DIR / 'chart_4_execution_time_resources.png'
plt.savefig(g4_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g4_path}")

# ==============================================================================
# GRAPH 5: CIRCULAR 300 MM WAFER YIELD MAP (PASS/FAIL)
# ==============================================================================
print("Generating Graph 5: Spatial Wafer Yield Map...")
fig, ax = plt.subplots(figsize=(8, 8), dpi=300)
ax.set_facecolor(COLORS['bg_dark'])
fig.patch.set_facecolor('#ffffff')

# Plot dies
cmap_pf = mcolors.ListedColormap([COLORS['fail'], COLORS['pass']])
scatter = ax.scatter(df['Wafer_X_mm'], df['Wafer_Y_mm'], c=df['Yield_Pass'], cmap=cmap_pf, s=2.2, alpha=0.92, edgecolors='none')

# Wafer rim & orientation notch
wafer_rim = plt.Circle((0, 0), 150.0, fill=False, color=COLORS['wafer_rim'], linewidth=2.5, linestyle='-')
ax.add_patch(wafer_rim)
notch = plt.Circle((0, -150.0), 4.5, fill=True, facecolor='#111814', edgecolor=COLORS['wafer_rim'], linewidth=1.5)
ax.add_patch(notch)

# Radial zones (dashed rings)
core_ring = plt.Circle((0, 0), 150.0 * 0.60, fill=False, color='#7a9482', linewidth=1.2, linestyle=':')
mid_ring = plt.Circle((0, 0), 150.0 * 0.85, fill=False, color='#7a9482', linewidth=1.2, linestyle='--')
ax.add_patch(core_ring)
ax.add_patch(mid_ring)

# Defect cluster callouts
ax.annotate('Cluster 1: Particle Pinhole\nYield = 15.49%', xy=(45, 50), xytext=(65, 80),
            arrowprops=dict(arrowstyle='->', color='#ffffff', lw=1.2),
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#2b1a1a', edgecolor='#e74c3c', alpha=0.9),
            color='#ffffff', fontsize=8.5)

ax.annotate('Cluster 2: Litho Defocus\nYield = 0.64%', xy=(-60, -40), xytext=(-130, -75),
            arrowprops=dict(arrowstyle='->', color='#ffffff', lw=1.2),
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#2b1a1a', edgecolor='#e74c3c', alpha=0.9),
            color='#ffffff', fontsize=8.5)

ax.annotate('Cluster 3: Thermal Slip\nYield = 75.38%', xy=(-35, 110), xytext=(-125, 120),
            arrowprops=dict(arrowstyle='->', color='#ffffff', lw=1.2),
            bbox=dict(boxstyle='round,pad=0.3', facecolor='#2b1a1a', edgecolor='#e74c3c', alpha=0.9),
            color='#ffffff', fontsize=8.5)

ax.set_xlim(-165, 165)
ax.set_ylim(-165, 165)
ax.set_aspect('equal')
ax.set_xlabel('Wafer X Coordinate (mm)', fontsize=11, fontweight='bold', labelpad=8)
ax.set_ylabel('Wafer Y Coordinate (mm)', fontsize=11, fontweight='bold', labelpad=8)
ax.set_title('300 mm Silicon Wafer Parametric Die Yield Map\n(35,000 Dies · 28nm HKMG Node · Overall Yield = 81.80%)', fontsize=12.5, fontweight='bold', pad=12)

# Custom legend
pass_patch = patches.Patch(color=COLORS['pass'], label=f"Pass (I_leak ≤ 30 nA): 28,630 dies ({TRUE_YIELD*100:.1f}%)")
fail_patch = patches.Patch(color=COLORS['fail'], label=f"Fail (I_leak > 30 nA): 6,370 dies ({TRUE_FAIL*100:.1f}%)")
ax.legend(handles=[pass_patch, fail_patch], loc='lower left', frameon=True, facecolor='#19241d', edgecolor='#52654b', labelcolor='#ffffff', fontsize=9.5)

plt.tight_layout()
g5_path = OUTPUT_DIR / 'chart_5_spatial_wafer_yield_map.png'
plt.savefig(g5_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g5_path}")

# ==============================================================================
# GRAPH 6: PARAMETRIC HEATMAPS (Vth, Lg, Tox, Log Ileak)
# ==============================================================================
print("Generating Graph 6: Parametric Heatmaps...")
fig, axes = plt.subplots(2, 2, figsize=(13, 12), dpi=300)
plt.subplots_adjust(wspace=0.25, hspace=0.25)

params_to_plot = [
    ('Threshold_Voltage_V', 'Threshold Voltage $V_{th}$ (V)', 'plasma', axes[0, 0]),
    ('Gate_Length_nm', 'Gate Length $L_g$ (nm)', 'viridis', axes[0, 1]),
    ('Oxide_Thickness_nm', 'Oxide Thickness $T_{ox}$ (nm)', 'cividis', axes[1, 0]),
    ('Log10_Leakage_Current', r'Log Standby Leakage $\log_{10}(I_{leak} \text{ [A]})$', 'inferno', axes[1, 1])
]

for col, title, cmap_name, ax in params_to_plot:
    ax.set_facecolor(COLORS['bg_dark'])
    sc = ax.scatter(df['Wafer_X_mm'], df['Wafer_Y_mm'], c=df[col], cmap=cmap_name, s=1.6, alpha=0.9, edgecolors='none')
    rim = plt.Circle((0, 0), 150.0, fill=False, color=COLORS['wafer_rim'], linewidth=1.5)
    ax.add_patch(rim)
    cbar = plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=9)
    ax.set_xlim(-160, 160)
    ax.set_ylim(-160, 160)
    ax.set_aspect('equal')
    ax.set_title(title, fontsize=11.5, fontweight='bold')
    ax.set_xlabel('Wafer X (mm)', fontsize=9.5)
    ax.set_ylabel('Wafer Y (mm)', fontsize=9.5)

fig.suptitle('Within-Wafer Systematic & Random Parametric Distributions (35,000 Dies)\n28nm High-k Metal Gate CMOS Subthreshold Characteristics', fontsize=13.5, fontweight='bold', y=0.98)
plt.tight_layout()
g6_path = OUTPUT_DIR / 'chart_6_parametric_heatmaps.png'
plt.savefig(g6_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g6_path}")

# ==============================================================================
# GRAPH 7: RADIAL YIELD PROFILE & EDGE ROLL-OFF
# ==============================================================================
print("Generating Graph 7: Radial Yield Profile...")
fig, ax1 = plt.subplots(figsize=(8.5, 5.5), dpi=300)

# Compute binned radial statistics
r_bins = np.linspace(0, 1.0, 26)
bin_centers = 0.5 * (r_bins[:-1] + r_bins[1:]) * 150.0  # In mm
radial_yield = []
radial_std_leak = []

for i in range(len(r_bins) - 1):
    mask = (df['Normalized_Radius'] >= r_bins[i]) & (df['Normalized_Radius'] < r_bins[i+1])
    radial_yield.append(df.loc[mask, 'Yield_Pass'].mean() * 100)
    radial_std_leak.append(df.loc[mask, 'Leakage_Current_nA'].std())

ax1.plot(bin_centers, radial_yield, 'o-', color='#27ae60', linewidth=2.5, markersize=6, label='Die Yield (%)')
ax1.axhline(81.80, color='#888888', linestyle='--', alpha=0.7, label='Wafer Average Yield (81.80%)')
ax1.set_xlabel('Radial Distance from Wafer Center (mm)', fontsize=11.5, fontweight='bold', labelpad=8)
ax1.set_ylabel('Die Yield (%)', color='#27ae60', fontsize=11.5, fontweight='bold', labelpad=8)
ax1.tick_params(axis='y', labelcolor='#27ae60')
ax1.set_ylim(30, 102)
ax1.grid(True, linestyle='--', alpha=0.5)

# Secondary axis for leakage current standard deviation
ax2 = ax1.twinx()
ax2.plot(bin_centers, radial_std_leak, 's--', color='#e74c3c', linewidth=2.0, markersize=5.5, label='Leakage Current Std Dev (nA)')
ax2.set_ylabel('Standby Leakage Current Std Dev (nA)', color='#e74c3c', fontsize=11.5, fontweight='bold', labelpad=8)
ax2.tick_params(axis='y', labelcolor='#e74c3c')
ax2.set_ylim(0, max(radial_std_leak) * 1.25)

# Annotations for edge roll-off
ax1.axvspan(150.0 * 0.85, 150.0, color='#fce4e4', alpha=0.45, label='Edge Roll-off Zone (CMP & Etch Loss)')
ax1.set_title('Radial Yield Profile & Edge Variance Expansion\nSevere Yield Degradation Beyond Bevel Threshold (Radius > 127.5 mm)', fontsize=12.5, fontweight='bold', pad=12)

# Combine legends
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2, loc='lower left', frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5)

plt.tight_layout()
g7_path = OUTPUT_DIR / 'chart_7_radial_yield_profile.png'
plt.savefig(g7_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g7_path}")

# ==============================================================================
# GRAPH 8: COMPREHENSIVE MASTER EXECUTIVE DASHBOARD
# ==============================================================================
print("Generating Graph 8: Comprehensive Executive Dashboard...")
fig = plt.figure(figsize=(18, 12), dpi=300)
gs = fig.add_gridspec(2, 3, wspace=0.28, hspace=0.32)

# Panel A: Wafer Yield Map
ax_a = fig.add_subplot(gs[0, 0])
ax_a.set_facecolor(COLORS['bg_dark'])
ax_a.scatter(df['Wafer_X_mm'], df['Wafer_Y_mm'], c=df['Yield_Pass'], cmap=cmap_pf, s=1.2, alpha=0.9, edgecolors='none')
ax_a.add_patch(plt.Circle((0, 0), 150.0, fill=False, color=COLORS['wafer_rim'], linewidth=1.5))
ax_a.set_xlim(-160, 160); ax_a.set_ylim(-160, 160); ax_a.set_aspect('equal')
ax_a.set_title('A. 300 mm Wafer Die Yield Map (81.8% Yield)', fontsize=11, fontweight='bold')
ax_a.set_xlabel('X (mm)', fontsize=9); ax_a.set_ylabel('Y (mm)', fontsize=9)

# Panel B: Convergence Rates
ax_b = fig.add_subplot(gs[0, 1])
ax_b.plot(SAMPLE_SIZES, [e * 100 for e in mc_rmse_list], 'o-', color=COLORS['mc'], label='Monte Carlo', lw=1.8)
ax_b.plot(SAMPLE_SIZES, [e * 100 for e in strat_rmse_list], 's-', color=COLORS['strat'], label='Stratified', lw=1.8)
ax_b.plot(SAMPLE_SIZES, [e * 100 for e in is_rmse_list], '^-', color=COLORS['is'], label='Importance Sampling', lw=1.8)
ax_b.plot(n_fine, theoretical_mc, 'k--', alpha=0.5, label='1/√N Limit')
ax_b.set_xscale('log'); ax_b.set_yscale('log')
ax_b.set_title('B. Classical Convergence Rate vs Sample Size', fontsize=11, fontweight='bold')
ax_b.set_xlabel('Sample Size $N$', fontsize=9); ax_b.set_ylabel('RMSE (% Yield)', fontsize=9)
ax_b.grid(True, which='both', linestyle='--', alpha=0.4); ax_b.legend(fontsize=8)

# Panel C: Estimator Absolute Error Comparison
ax_c = fig.add_subplot(gs[0, 2])
bars_c = ax_c.bar(methods, mean_err, color=colors_m, alpha=0.85, edgecolor='#333333', lw=0.8)
ax_c.set_title('C. Estimator Mean Error (Qlarity Suite)', fontsize=11, fontweight='bold')
ax_c.set_ylabel('Mean Absolute Error (%)', fontsize=9)
ax_c.tick_params(axis='x', rotation=25, labelsize=8.5)
ax_c.grid(True, axis='y', linestyle='--', alpha=0.4)
for b in bars_c[2:]:
    y = b.get_height()
    ax_c.text(b.get_x() + b.get_width()/2.0, y + 0.015, f'{y:.3f}%', ha='center', va='bottom', fontsize=8, fontweight='bold')

# Panel D: Radial Yield & Edge Roll-off
ax_d = fig.add_subplot(gs[1, 0])
ax_d.plot(bin_centers, radial_yield, 'o-', color='#27ae60', lw=2.0, ms=5)
ax_d.axvspan(150.0 * 0.85, 150.0, color='#fce4e4', alpha=0.5)
ax_d.axhline(81.80, color='#888888', linestyle='--', alpha=0.6)
ax_d.set_title('D. Radial Die Yield Profile & Edge Loss', fontsize=11, fontweight='bold')
ax_d.set_xlabel('Radius from Center (mm)', fontsize=9); ax_d.set_ylabel('Die Yield (%)', fontsize=9)
ax_d.set_ylim(35, 102); ax_d.grid(True, linestyle='--', alpha=0.4)

# Panel E: Computational Runtime & Complexity
ax_e = fig.add_subplot(gs[1, 1])
bars_e = ax_e.bar(eval_labels, runtimes_ms, color=colors_res, alpha=0.85, edgecolor='#333333', lw=0.8)
ax_e.set_yscale('log')
ax_e.set_title('E. Practical Runtime (Simulator vs Classical)', fontsize=11, fontweight='bold')
ax_e.set_ylabel('Time (ms) [Log Scale]', fontsize=9)
ax_e.tick_params(axis='x', rotation=22, labelsize=8)
ax_e.grid(True, which='both', axis='y', linestyle='--', alpha=0.4)
for b, val in zip(bars_e, runtimes_ms):
    lbl = f"{val/1000:.2f}s" if val >= 1000 else f"{val:.1f}ms" if val >= 1 else f"{val*1000:.0f}µs"
    ax_e.text(b.get_x() + b.get_width()/2.0, val * 1.3, lbl, ha='center', va='bottom', fontsize=8, fontweight='bold')

# Panel F: Variance Reduction Summary
ax_f = fig.add_subplot(gs[1, 2])
bars_f = ax_f.bar(x_pos - w/2, vr_strat, width=w, label='Stratified Spatial', color=COLORS['strat'], alpha=0.85)
bars_f2 = ax_f.bar(x_pos + w/2, vr_is, width=w, label='Importance Sampling', color=COLORS['is'], alpha=0.85)
ax_f.set_xticks(x_pos); ax_f.set_xticklabels([f"{n:,}" for n in SAMPLE_SIZES], fontsize=8, rotation=20)
ax_f.set_title('F. Variance Gain over Naive Monte Carlo (%)', fontsize=11, fontweight='bold')
ax_f.set_xlabel('Sample Size $N$', fontsize=9); ax_f.set_ylabel('Variance Reduction (%)', fontsize=9)
ax_f.set_ylim(0, 75); ax_f.grid(True, axis='y', linestyle='--', alpha=0.4); ax_f.legend(fontsize=8)

fig.suptitle('Executive Dashboard: Classical Algorithms vs Quantum Amplitude Estimation (IQAE) in Semiconductor Fab Analytics', 
             fontsize=14.5, fontweight='bold', y=0.98)

plt.tight_layout()
g8_path = OUTPUT_DIR / 'chart_8_comprehensive_dashboard.png'
plt.savefig(g8_path, dpi=300)
plt.close(fig)
print(f"  -> Saved: {g8_path}")

# ==============================================================================
# SUMMARY TABLE & REPORT
# ==============================================================================
print("\n" + "=" * 80)
print("                    EXPORTED PNG CHARTS SUMMARY (300 DPI)")
print("=" * 80)
charts_info = [
    ('chart_1_convergence_rates.png', 'RMSE Convergence: Simple MC vs Stratified vs IS vs 1/sqrt(N)'),
    ('chart_2_variance_reduction.png', 'Statistical Efficiency: Variance Reduction (%) over Naive MC'),
    ('chart_3_estimator_error_comparison.png', 'Accuracy Benchmark: Mean & Max Absolute Error across 5 Estimators'),
    ('chart_4_execution_time_resources.png', 'Runtime & Resource Scaling: Wall-clock time (log scale) per method'),
    ('chart_5_spatial_wafer_yield_map.png', 'Wafer Die Map: 300 mm circular disk, defect clusters & pass/fail status'),
    ('chart_6_parametric_heatmaps.png', 'Process Field Maps: 2D distributions of Vth, Lg, Tox, and log(Ileak)'),
    ('chart_7_radial_yield_profile.png', 'Radial Edge Loss: Yield and Leakage variance vs radius (mm)'),
    ('chart_8_comprehensive_dashboard.png', 'Master Executive Infographic Dashboard combining all 6 analysis panels')
]

for fname, desc in charts_info:
    fpath = OUTPUT_DIR / fname
    size_kb = fpath.stat().st_size / 1024
    print(f"  * {fname:36s} [{size_kb:6.1f} KB]  --> {desc}")
print("=" * 80)
