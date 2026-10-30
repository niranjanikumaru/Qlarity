"""
================================================================================
SEMICONDUCTOR FABRICATION & YIELD SIMULATOR
Synthetic Wafer Parametric & Defect Dataset Generator (35,000 Dies)
================================================================================
Authors: Expert Semiconductor Physicist & Data Science Team
Target Node: Advanced 28nm High-k Metal Gate (HKMG) Planar CMOS
Substrate: 300 mm Silicon Wafer (Radius = 150 mm)

Four Distinct Wafer Process Conditions Supported:
-------------------------------------------------
1. Nominal Wafer (Baseline · High Yield):
   - Standard 28nm process centered at nominal targets (Lg=28nm, Tox=1.20nm, Vth=0.350V).
   - Nominal 3-sigma drift (sigma_Lg=0.80nm, sigma_Tox=0.020nm, sigma_Vth=0.015V).
   - Realistic CMP/plasma edge roll-off gradient + 3 defect clusters.
   - Typical Overall Yield: ~81.8%.

2. Equipment Drift Wafer (Tool Excursion · Low Yield):
   - Shifted nominal Gaussian means (Lg -> 26.6nm, Tox -> 1.155nm, Vth -> 0.325V).
   - Severe fab-wide subthreshold leakage exponential surge.
   - Typical Overall Yield: ~19.9%.

3. Localized Defect Wafer (Scratch / Severe Quadrant Defect):
   - Smooth radial edge roll-off disabled (clean perimeter).
   - Massive localized penalty injected into quadrant (X > 50 mm and Y < 50 mm)
     plus mechanical particle/scratch track.
   - Defect Zone Yield: 0.0%, Non-Defect Zone Yield: >99.8%.
   - Typical Overall Yield: ~78.4%.

4. High Variance Wafer (Noisy Process / Poor Cpk):
   - Nominal means remain centered at standard targets.
   - Standard deviations (sigma) doubled in Gaussian distributions (2x sigma).
   - Heavy-tail leakage loss due to broad process variance.
   - Typical Overall Yield: ~70.6%.
================================================================================
"""

import sys
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

# ==============================================================================
# 1. PHYSICAL CONSTANTS & FAB PROCESS CONFIGURATION
# ==============================================================================
RANDOM_SEED = 42
np.random.seed(RANDOM_SEED)

# Wafer & Die Geometry
TOTAL_DIES = 35000               # Target dataset size: exactly 35,000 dies
WAFER_DIAMETER_MM = 300.0        # Industry-standard 300 mm wafer
WAFER_RADIUS_MM = WAFER_DIAMETER_MM / 2.0  # 150.0 mm
N_GRID = 220                     # 2D discrete lattice size (220 x 220 > 35,000 dies)

# Physical Constants (SI Units)
BOLTZMANN_K = 1.380649e-23       # J / K
E_CHARGE = 1.60217663e-19        # Coulombs
FAB_TEMPERATURE_K = 300.0        # Wafer probe test temperature (300 K / ~27 °C)
THERMAL_VOLTAGE_VT = (BOLTZMANN_K * FAB_TEMPERATURE_K) / E_CHARGE  # ~ 0.02586 V

# Technology Node Parameters (28nm Planar HKMG CMOS)
NOMINAL_LG_NM = 28.0             # nm
SIGMA_LG_NM = 0.80               # 3-sigma = +/- 2.4 nm (+/- 8.6%)

NOMINAL_TOX_NM = 1.20            # nm (12.0 Angstroms)
SIGMA_TOX_NM = 0.020             # 3-sigma = +/- 0.06 nm (+/- 5.0%)

NOMINAL_VTH_V = 0.350            # V (350 mV)
SIGMA_VTH_V = 0.015              # 3-sigma = +/- 0.045 V (+/- 12.8%)

# Leakage Current Physics Model Coefficients
I_NOMINAL_A = 1.0e-8             # 10.0 nA baseline off-state leakage at nominal conditions
SUBTHRESHOLD_SWING_N = 1.26      # Subthreshold body-effect coefficient (n = 1 + C_dep / C_ox)
GAMMA_TOX_TUNNELING = 4.80       # Direct tunneling / dielectric sensitivity parameter
DIBL_COEFFICIENT_V = 0.028       # Drain-Induced Barrier Lowering sensitivity factor (V)

# Parametric Test Threshold Limit (Strict Fab QA Criteria)
I_LEAK_FAIL_THRESHOLD_A = 3.0e-8  # 30.0 nA (3.0e-8 A)


# ==============================================================================
# 2. WAFER GRID & CIRCULAR COORDINATE SYSTEM GENERATION
# ==============================================================================
def generate_circular_wafer_grid(
    total_dies: int = TOTAL_DIES,
    wafer_radius_mm: float = WAFER_RADIUS_MM,
    grid_dim: int = N_GRID
) -> dict:
    """
    Constructs a 2D discrete wafer coordinate system and selects the closest
    `total_dies` to form a contiguous circular wafer layout.
    """
    grid_y, grid_x = np.indices((grid_dim, grid_dim))
    center_y = (grid_dim - 1) / 2.0
    center_x = (grid_dim - 1) / 2.0

    dist_grid_sq = (grid_x - center_x) ** 2 + (grid_y - center_y) ** 2
    dist_grid = np.sqrt(dist_grid_sq)

    sorted_flat_indices = np.argsort(dist_grid.ravel())
    selected_flat_indices = sorted_flat_indices[:total_dies]

    max_selected_grid_r = dist_grid.ravel()[selected_flat_indices[-1]]
    mm_per_grid_unit = wafer_radius_mm / max_selected_grid_r

    die_grid_x = grid_x.ravel()[selected_flat_indices]
    die_grid_y = grid_y.ravel()[selected_flat_indices]

    die_x_mm = (die_grid_x - center_x) * mm_per_grid_unit
    die_y_mm = (die_grid_y - center_y) * mm_per_grid_unit
    radius_mm = np.sqrt(die_x_mm**2 + die_y_mm**2)
    normalized_radius = radius_mm / wafer_radius_mm

    return {
        "selected_flat_indices": selected_flat_indices,
        "grid_x": die_grid_x,
        "grid_y": die_grid_y,
        "x_mm": die_x_mm,
        "y_mm": die_y_mm,
        "radius_mm": radius_mm,
        "rho": normalized_radius,
        "grid_shape": (grid_dim, grid_dim)
    }


# ==============================================================================
# 3. SPATIAL CORRELATION & DEFECT CLUSTER ENGINE
# ==============================================================================
def generate_spatial_correlation_field(
    grid_shape: tuple,
    filter_sigma: float,
    seed: int
) -> np.ndarray:
    """
    Generates a smoothly varying 2D Gaussian random field via scipy.ndimage.gaussian_filter.
    """
    rng = np.random.RandomState(seed)
    white_noise = rng.randn(*grid_shape)
    smoothed_field = gaussian_filter(white_noise, sigma=filter_sigma, mode="reflect")
    standardized_field = (smoothed_field - np.mean(smoothed_field)) / np.std(smoothed_field)
    return standardized_field


def evaluate_defect_clusters(x_mm: np.ndarray, y_mm: np.ndarray) -> tuple:
    """
    Computes spatial activation kernels for 3 localized defect clusters:
    - Cluster 1: Reticle/particle contamination hotspot (+45 mm, +50 mm).
    - Cluster 2: Optical lithography defocus aberration hotspot (-60 mm, -40 mm).
    - Cluster 3: Edge crystal slip / thermal stress dislocation (-35 mm, +110 mm).
    """
    c1 = np.exp(-((x_mm - 45.0)**2 + (y_mm - 50.0)**2) / (2.0 * (11.0**2)))
    c2 = np.exp(-((x_mm - (-60.0))**2 + (y_mm - (-40.0))**2) / (2.0 * (9.0**2)))
    c3 = np.exp(-((x_mm - (-35.0))**2 + (y_mm - 110.0)**2) / (2.0 * (12.0**2)))
    return c1, c2, c3


# ==============================================================================
# 4. PHYSICAL PARAMETER GENERATION (SUPPORTING 4 NOMINAL TEST SCENARIOS)
# ==============================================================================
def synthesize_process_parameters(
    grid_info: dict,
    wafer_type: str = "nominal"
) -> dict:
    """
    Synthesizes Gate Length (L_g), Oxide Thickness (T_ox), and Threshold Voltage (V_th)
    for one of the four specified manufacturing conditions:
      1. 'nominal'           : Baseline process centered at nominal targets with radial edge loss.
      2. 'equipment_drift'   : Tool excursion shifting Gaussian distribution centers.
      3. 'localized_defect'  : No radial gradient; massive localized quadrant penalty (X>50, Y<50).
      4. 'high_variance'     : Means centered; standard deviations (sigma) doubled in normal noise.
    """
    total_dies = len(grid_info["x_mm"])
    selected_indices = grid_info["selected_flat_indices"]
    rho = grid_info["rho"]
    x_mm = grid_info["x_mm"]
    y_mm = grid_info["y_mm"]

    # Systematic spatial correlation fields
    spatial_Lg_grid = generate_spatial_correlation_field(grid_info["grid_shape"], 16.0, seed=101)
    spatial_Tox_grid = generate_spatial_correlation_field(grid_info["grid_shape"], 14.0, seed=202)
    spatial_Vth_grid = generate_spatial_correlation_field(grid_info["grid_shape"], 18.0, seed=303)

    s_Lg = spatial_Lg_grid.ravel()[selected_indices]
    s_Tox = spatial_Tox_grid.ravel()[selected_indices]
    s_Vth = spatial_Vth_grid.ravel()[selected_indices]

    # Microscopic uncorrelated random noise
    rng_micro = np.random.RandomState(404)
    rand_Lg = rng_micro.randn(total_dies)
    rand_Tox = rng_micro.randn(total_dies)
    rand_Vth = rng_micro.randn(total_dies)

    # Defect clusters
    c1, c2, c3 = evaluate_defect_clusters(x_mm, y_mm)

    # --------------------------------------------------------------------------
    # SCENARIO 1: THE NOMINAL WAFER (Baseline · High Yield ~81.8%)
    # --------------------------------------------------------------------------
    if wafer_type == "nominal":
        # Base targets
        mean_Lg = NOMINAL_LG_NM
        mean_Tox = NOMINAL_TOX_NM
        mean_Vth = NOMINAL_VTH_V

        sigma_Lg = SIGMA_LG_NM
        sigma_Tox = SIGMA_TOX_NM
        sigma_Vth = SIGMA_VTH_V

        # Radial edge gradients active
        edge_variance_multiplier = 1.0 + 2.2 * (rho**3.0)
        edge_shift_Lg = -1.40 * (rho**3.0)
        edge_shift_Tox = -0.045 * (rho**3.5)
        edge_shift_Vth = -0.025 * (rho**3.0)

        Lg = (
            mean_Lg
            + (0.60 * s_Lg + 0.40 * rand_Lg) * sigma_Lg * edge_variance_multiplier
            + edge_shift_Lg - 2.80 * c2 - 1.20 * c3
        )
        Tox = (
            mean_Tox
            + (0.60 * s_Tox + 0.40 * rand_Tox) * sigma_Tox * edge_variance_multiplier
            + edge_shift_Tox - 0.090 * c1 - 0.045 * c3
        )
        Vth = (
            mean_Vth
            + (0.60 * s_Vth + 0.40 * rand_Vth) * sigma_Vth * edge_variance_multiplier
            + edge_shift_Vth - 0.055 * c1 - 0.070 * c2 - 0.045 * c3
        )

    # --------------------------------------------------------------------------
    # SCENARIO 2: THE "EQUIPMENT DRIFT" WAFER (Low Yield ~19.9%)
    # Shift the nominal means (the center of Gaussian distributions)
    # --------------------------------------------------------------------------
    elif wafer_type == "equipment_drift":
        # Process means drift significantly out-of-spec:
        # Etch microloading/over-etch narrows gate: 28.0 -> 26.60 nm
        # Oxidation pressure/temp undershoot thins oxide: 1.20 -> 1.155 nm
        # Implantation dosage/halo drift drops threshold: 0.350 -> 0.325 V
        mean_Lg = 26.60
        mean_Tox = 1.155
        mean_Vth = 0.325

        sigma_Lg = SIGMA_LG_NM
        sigma_Tox = SIGMA_TOX_NM
        sigma_Vth = SIGMA_VTH_V

        edge_variance_multiplier = 1.0 + 2.2 * (rho**3.0)
        edge_shift_Lg = -1.40 * (rho**3.0)
        edge_shift_Tox = -0.045 * (rho**3.5)
        edge_shift_Vth = -0.025 * (rho**3.0)

        Lg = (
            mean_Lg
            + (0.60 * s_Lg + 0.40 * rand_Lg) * sigma_Lg * edge_variance_multiplier
            + edge_shift_Lg - 2.80 * c2 - 1.20 * c3
        )
        Tox = (
            mean_Tox
            + (0.60 * s_Tox + 0.40 * rand_Tox) * sigma_Tox * edge_variance_multiplier
            + edge_shift_Tox - 0.090 * c1 - 0.045 * c3
        )
        Vth = (
            mean_Vth
            + (0.60 * s_Vth + 0.40 * rand_Vth) * sigma_Vth * edge_variance_multiplier
            + edge_shift_Vth - 0.055 * c1 - 0.070 * c2 - 0.045 * c3
        )

    # --------------------------------------------------------------------------
    # SCENARIO 3: THE "LOCALIZED DEFECT" WAFER (Scratch/Particle ~78.4% Yield)
    # Instead of smooth radial gradient, inject massive localized quadrant penalty
    # (e.g., forcefully drop Vth for all dies where X > 50 and Y < 50)
    # --------------------------------------------------------------------------
    elif wafer_type == "localized_defect":
        mean_Lg = NOMINAL_LG_NM
        mean_Tox = NOMINAL_TOX_NM
        mean_Vth = NOMINAL_VTH_V

        sigma_Lg = SIGMA_LG_NM
        sigma_Tox = SIGMA_TOX_NM
        sigma_Vth = SIGMA_VTH_V

        # Smooth radial edge gradient is explicitly DISABLED
        edge_variance_multiplier = 1.0
        edge_shift_Lg = 0.0
        edge_shift_Tox = 0.0
        edge_shift_Vth = 0.0

        Lg = (
            mean_Lg
            + (0.60 * s_Lg + 0.40 * rand_Lg) * sigma_Lg
        )
        Tox = (
            mean_Tox
            + (0.60 * s_Tox + 0.40 * rand_Tox) * sigma_Tox
        )
        Vth = (
            mean_Vth
            + (0.60 * s_Vth + 0.40 * rand_Vth) * sigma_Vth
        )

        # Inject massive localized defect penalty into quadrant (X > 50 and Y < 50)
        quadrant_mask = (x_mm > 50.0) & (y_mm < 50.0)

        # Forcefully drop Vth and Tox in the defect zone
        Vth = np.where(quadrant_mask, Vth - 0.080, Vth)
        Tox = np.where(quadrant_mask, Tox - 0.080, Tox)
        Lg = np.where(quadrant_mask, Lg - 1.50, Lg)

        # Add physical scratch line artifact across the quadrant boundary
        scratch_line = np.abs((y_mm - 0.45 * x_mm + 15.0)) < 3.5
        scratch_extent = (x_mm > 20.0) & (x_mm < 135.0) & (y_mm > -60.0) & (y_mm < 40.0)
        scratch_mask = scratch_line & scratch_extent
        Vth = np.where(scratch_mask, Vth - 0.070, Vth)
        Tox = np.where(scratch_mask, Tox - 0.070, Tox)

    # --------------------------------------------------------------------------
    # SCENARIO 4: THE "HIGH VARIANCE" WAFER (Noisy Process ~70.6% Yield)
    # Keep nominal means centered, but double standard deviation (sigma)
    # --------------------------------------------------------------------------
    elif wafer_type == "high_variance":
        mean_Lg = NOMINAL_LG_NM
        mean_Tox = NOMINAL_TOX_NM
        mean_Vth = NOMINAL_VTH_V

        # Double the standard deviations (2x sigma)
        sigma_Lg = SIGMA_LG_NM * 2.0       # 0.80 -> 1.60 nm
        sigma_Tox = SIGMA_TOX_NM * 2.0     # 0.020 -> 0.040 nm
        sigma_Vth = SIGMA_VTH_V * 2.0      # 0.015 -> 0.030 V

        edge_variance_multiplier = 1.0 + 2.2 * (rho**3.0)
        edge_shift_Lg = -1.40 * (rho**3.0)
        edge_shift_Tox = -0.045 * (rho**3.5)
        edge_shift_Vth = -0.025 * (rho**3.0)

        # Doubled noise distributions
        Lg = (
            mean_Lg
            + (0.60 * s_Lg + 0.40 * rand_Lg) * sigma_Lg * edge_variance_multiplier
            + edge_shift_Lg - 2.80 * c2 - 1.20 * c3
        )
        Tox = (
            mean_Tox
            + (0.60 * s_Tox + 0.40 * rand_Tox) * sigma_Tox * edge_variance_multiplier
            + edge_shift_Tox - 0.090 * c1 - 0.045 * c3
        )
        Vth = (
            mean_Vth
            + (0.60 * s_Vth + 0.40 * rand_Vth) * sigma_Vth * edge_variance_multiplier
            + edge_shift_Vth - 0.055 * c1 - 0.070 * c2 - 0.045 * c3
        )

    else:
        raise ValueError(f"Unknown wafer_type '{wafer_type}'. Choose from: 'nominal', 'equipment_drift', 'localized_defect', 'high_variance'")

    # Enforce physically bounded semiconductor limits
    Lg = np.clip(Lg, 15.0, 40.0)
    Tox = np.clip(Tox, 0.70, 1.90)
    Vth = np.clip(Vth, 0.08, 0.60)

    return {"Lg_nm": Lg, "Tox_nm": Tox, "Vth_V": Vth}


# ==============================================================================
# 5. DETERMINISTIC VECTORIZED PHYSICAL LEAKAGE MODEL (I_leak)
# ==============================================================================
def calculate_subthreshold_leakage(
    Lg_nm: np.ndarray,
    Tox_nm: np.ndarray,
    Vth_V: np.ndarray,
    nominal_lg: float = NOMINAL_LG_NM,
    nominal_tox: float = NOMINAL_TOX_NM,
    nominal_vth: float = NOMINAL_VTH_V,
    i_nom: float = I_NOMINAL_A,
    vt: float = THERMAL_VOLTAGE_VT,
    n_swing: float = SUBTHRESHOLD_SWING_N,
    gamma_tox: float = GAMMA_TOX_TUNNELING,
    dibl_coeff: float = DIBL_COEFFICIENT_V
) -> np.ndarray:
    """
    Deterministic, vectorized physical calculation of total off-state standby
    leakage current (I_leak).
    """
    dibl_barrier_shift = dibl_coeff * ((nominal_lg / Lg_nm)**2 - 1.0)
    effective_vth = Vth_V - dibl_barrier_shift

    subthreshold_exp = (nominal_vth - effective_vth) / (n_swing * vt)
    tunneling_exp = gamma_tox * ((nominal_tox - Tox_nm) / nominal_tox)
    geometric_factor = nominal_lg / Lg_nm

    total_exponent = subthreshold_exp + tunneling_exp
    return i_nom * geometric_factor * np.exp(total_exponent)


# ==============================================================================
# 6. PIPELINE ORCHESTRATION & SINGLE WAFER GENERATION
# ==============================================================================
def generate_single_wafer(
    wafer_type: str = "nominal",
    output_csv: str = None
) -> pd.DataFrame:
    """
    Generates a single 35,000-die wafer dataset for a designated test condition.
    """
    titles = {
        "nominal": "1. NOMINAL WAFER (Baseline Fab Yield)",
        "equipment_drift": "2. EQUIPMENT DRIFT WAFER (Shifted Means · Low Yield)",
        "localized_defect": "3. LOCALIZED DEFECT WAFER (Quadrant Defect & Scratch)",
        "high_variance": "4. HIGH VARIANCE WAFER (Doubled Process Sigma)"
    }

    if output_csv is None:
        output_csv = f"synthetic_wafer_{wafer_type}.csv"

    print("=" * 80)
    print(f"  GENERATING: {titles.get(wafer_type, wafer_type).upper()}")
    print("=" * 80)

    # 1. Grid coordinates
    grid_data = generate_circular_wafer_grid(TOTAL_DIES, WAFER_RADIUS_MM, N_GRID)

    # 2. Process parameters
    params = synthesize_process_parameters(grid_data, wafer_type=wafer_type)

    # 3. Deterministic physical leakage
    leakage_current_A = calculate_subthreshold_leakage(
        Lg_nm=params["Lg_nm"],
        Tox_nm=params["Tox_nm"],
        Vth_V=params["Vth_V"]
    )

    # 4. Parametric Yield
    yield_pass = (leakage_current_A <= I_LEAK_FAIL_THRESHOLD_A).astype(int)

    # 5. Assemble DataFrame
    df = pd.DataFrame({
        "Die_ID": np.arange(1, TOTAL_DIES + 1),
        "Wafer_X_mm": np.round(grid_data["x_mm"], 3),
        "Wafer_Y_mm": np.round(grid_data["y_mm"], 3),
        "Grid_X": grid_data["grid_x"],
        "Grid_Y": grid_data["grid_y"],
        "Radius_mm": np.round(grid_data["radius_mm"], 3),
        "Normalized_Radius": np.round(grid_data["rho"], 4),
        "Gate_Length_nm": np.round(params["Lg_nm"], 3),
        "Oxide_Thickness_nm": np.round(params["Tox_nm"], 4),
        "Threshold_Voltage_V": np.round(params["Vth_V"], 4),
        "Leakage_Current_A": leakage_current_A,
        "Leakage_Current_nA": np.round(leakage_current_A * 1e9, 3),
        "Log10_Leakage_Current": np.round(np.log10(leakage_current_A), 4),
        "Yield_Pass": yield_pass
    })

    # Save to CSV
    df.to_csv(output_csv, index=False)
    print(f"--> Saved dataset successfully to '{output_csv}' ({len(df):,} rows)")

    # Print summary metrics
    total_count = len(df)
    passed_count = int(df["Yield_Pass"].sum())
    failed_count = total_count - passed_count
    overall_yield_pct = (passed_count / total_count) * 100.0

    print(f"    * Total Dies: {total_count:,} | Passing: {passed_count:,} | Failing: {failed_count:,}")
    print(f"    * Overall Wafer Yield: {overall_yield_pct:.2f}%")
    print(f"    * Median Standby Leakage: {df['Leakage_Current_nA'].median():.2f} nA (Limit: 30.0 nA)")
    print(f"    * Mean Standby Leakage:   {df['Leakage_Current_nA'].mean():.2f} nA\n")

    return df


# ==============================================================================
# 7. GENERATE ALL 4 WAFER CONDITIONS & COMPARISON ARTIFACTS
# ==============================================================================
def generate_all_four_wafers() -> dict:
    """
    Executes the generation of all 4 specified wafer test conditions:
      1. Nominal Wafer
      2. Equipment Drift Wafer
      3. Localized Defect Wafer
      4. High Variance Wafer
    Saves individual CSV files, generates comparison visual maps, and produces summary tables.
    """
    wafer_types = ["nominal", "equipment_drift", "localized_defect", "high_variance"]
    datasets = {}

    for w_type in wafer_types:
        df = generate_single_wafer(w_type)
        datasets[w_type] = df

    # Also keep synthetic_wafer_data.csv mapped to nominal for existing scripts/services
    datasets["nominal"].to_csv("synthetic_wafer_data.csv", index=False)
    print("--> Synced 'synthetic_wafer_nominal.csv' to 'synthetic_wafer_data.csv'")

    # Comparative Summary Report
    print("=" * 80)
    print("             SUMMARY REPORT: 4 NOMINAL WAFER TEST CONDITIONS")
    print("=" * 80)
    summary_rows = []
    for w_type, df in datasets.items():
        total = len(df)
        passed = int(df["Yield_Pass"].sum())
        yield_pct = (passed / total) * 100.0
        summary_rows.append({
            "Wafer Condition": w_type.replace("_", " ").title(),
            "Total Dies": total,
            "Passing Dies": passed,
            "Failing Dies": total - passed,
            "Yield (%)": round(yield_pct, 2),
            "Mean Lg (nm)": round(df["Gate_Length_nm"].mean(), 2),
            "Mean Tox (nm)": round(df["Oxide_Thickness_nm"].mean(), 3),
            "Mean Vth (V)": round(df["Threshold_Voltage_V"].mean(), 3),
            "Median Ileak (nA)": round(df["Leakage_Current_nA"].median(), 2)
        })

    summary_df = pd.DataFrame(summary_rows)
    print(summary_df.to_string(index=False))
    print("=" * 80 + "\n")

    # Plot 4-panel comparison graphic
    plot_four_wafer_comparison(datasets, save_path="wafer_comparison_4_tests.png")

    return datasets


# ==============================================================================
# 8. 4-PANEL HIGH-RESOLUTION COMPARISON VISUALIZATION
# ==============================================================================
def plot_four_wafer_comparison(datasets: dict, save_path: str = "wafer_comparison_4_tests.png") -> None:
    """
    Renders a 4-panel side-by-side circular wafer map comparison of die yield (Pass/Fail)
    for all 4 manufacturing conditions.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors
        import matplotlib.patches as patches

        fig, axes = plt.subplots(2, 2, figsize=(16, 15), dpi=200)
        plt.subplots_adjust(wspace=0.18, hspace=0.25)

        titles = [
            ("nominal", "1. Nominal Wafer (Baseline Fab Control)", "Yield = 81.80% · Clean Core, Edge Roll-Off"),
            ("equipment_drift", "2. Equipment Drift Wafer (Shifted Means)", "Yield = 19.93% · Systematic Severe Excursion"),
            ("localized_defect", "3. Localized Defect Wafer (Quadrant Drop)", "Yield = 78.40% · Defect (X>50, Y<50) Yield = 0.0%"),
            ("high_variance", "4. High Variance Wafer (2x Standard Deviation)", "Yield = 70.62% · Broad Noise Tail Leakage")
        ]

        cmap_pf = mcolors.ListedColormap(["#c0392b", "#27ae60"])

        for (w_type, main_title, subtitle), ax in zip(titles, axes.flat):
            df = datasets[w_type]
            ax.set_facecolor("#151f18")

            # Plot dies
            ax.scatter(
                df["Wafer_X_mm"], df["Wafer_Y_mm"],
                c=df["Yield_Pass"], cmap=cmap_pf, s=1.6, alpha=0.92, edgecolors="none"
            )

            # Circular boundary
            wafer_rim = plt.Circle((0, 0), WAFER_RADIUS_MM, fill=False, color="#52705b", linewidth=2.0)
            ax.add_patch(wafer_rim)

            # Orientation notch
            notch = plt.Circle((0, -WAFER_RADIUS_MM), 4.5, fill=True, facecolor="#101712", edgecolor="#52705b", linewidth=1.2)
            ax.add_patch(notch)

            # Annotations specific to conditions
            if w_type == "localized_defect":
                quad_rect = patches.Rectangle((50, -150), 100, 200, linewidth=1.5, edgecolor="#e74c3c", facecolor="#e74c3c", alpha=0.15, linestyle="--")
                ax.add_patch(quad_rect)
                ax.annotate("Massive Defect\nX > 50 & Y < 50\nYield: 0.0%", xy=(80, 0), xytext=(85, 30),
                            arrowprops=dict(arrowstyle="->", color="#ffffff", lw=1.2),
                            bbox=dict(boxstyle="round,pad=0.3", facecolor="#2b1a1a", edgecolor="#e74c3c", alpha=0.9),
                            color="#ffffff", fontsize=9, fontweight="bold")
            elif w_type == "equipment_drift":
                ax.annotate("Fab-Wide Mean Shift:\nLg: 28->26.6nm\nTox: 1.20->1.155nm\nVth: 0.350->0.325V", xy=(0, 0), xytext=(-80, -20),
                            bbox=dict(boxstyle="round,pad=0.4", facecolor="#2b1a1a", edgecolor="#e74c3c", alpha=0.9),
                            color="#ffffff", fontsize=9.5)
            elif w_type == "high_variance":
                ax.annotate("Process Noise Doubled:\n2x Normal Sigma\nExcessive tail leakage", xy=(0, 0), xytext=(-75, -20),
                            bbox=dict(boxstyle="round,pad=0.4", facecolor="#2a2318", edgecolor="#f39c12", alpha=0.9),
                            color="#ffffff", fontsize=9.5)

            ax.set_xlim(-165, 165)
            ax.set_ylim(-165, 165)
            ax.set_aspect("equal")
            ax.set_xlabel("Wafer X (mm)", fontsize=10)
            ax.set_ylabel("Wafer Y (mm)", fontsize=10)
            ax.set_title(f"{main_title}\n{subtitle}", fontsize=11.5, fontweight="bold", pad=8)

        # Legend
        pass_patch = patches.Patch(color="#27ae60", label="Pass (I_leak ≤ 30 nA)")
        fail_patch = patches.Patch(color="#c0392b", label="Fail (I_leak > 30 nA)")
        fig.legend(handles=[pass_patch, fail_patch], loc="lower center", ncol=2, frameon=True,
                   facecolor="#19241d", edgecolor="#52654b", labelcolor="#ffffff", fontsize=11)

        fig.suptitle(
            "Comparative Study: 4 Synthetic Semiconductor Wafer Manufacturing Conditions (35,000 Dies Each)\n"
            "28nm HKMG CMOS Node · Deterministic Vectorized Subthreshold & Tunneling Leakage Analysis",
            fontsize=14.5, fontweight="bold", y=0.98
        )

        plt.savefig(save_path, bbox_inches="tight")
        print(f"--> Saved 4-wafer comparison visual map to '{save_path}'")
        plt.close(fig)

    except ImportError:
        print("[Notice] matplotlib not installed; skipping plot generation.")


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Semiconductor Wafer Dataset Generator")
    parser.add_argument(
        "--wafer-type",
        choices=["nominal", "equipment_drift", "localized_defect", "high_variance", "all"],
        default="all",
        help="Type of wafer dataset to generate (default: all 4 conditions)"
    )
    args = parser.parse_args()

    if args.wafer_type == "all":
        generate_all_four_wafers()
    else:
        generate_single_wafer(args.wafer_type)
