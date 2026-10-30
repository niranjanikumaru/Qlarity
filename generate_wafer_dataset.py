"""
================================================================================
SEMICONDUCTOR FABRICATION & YIELD SIMULATOR
Synthetic Wafer Parametric & Defect Dataset Generator (35,000 Dies)
================================================================================
Authors: Expert Semiconductor Physicist & Data Science Team
Target Node: Advanced 28nm High-k Metal Gate (HKMG) Planar CMOS
Substrate: 300 mm Silicon Wafer

Physics & Modeling Overview:
----------------------------
1. Wafer Geometry & Coordinate System:
   - 300 mm diameter silicon wafer (R = 150 mm).
   - Regular 2D Cartesian die grid mapped onto a circular boundary.
   - Polar transformation: radius r = sqrt(X^2 + Y^2), normalized radius rho in [0, 1].

2. Process Parameter Base Distributions (3-Sigma Fab Standards):
   - Gate Length (L_g): Nominal = 28.0 nm, 3-sigma = +/- 2.4 nm (sigma = 0.80 nm).
   - Equivalent Oxide Thickness (T_ox): Nominal = 1.20 nm, 3-sigma = +/- 0.06 nm (sigma = 0.020 nm).
   - Threshold Voltage (V_th): Nominal = 0.350 V, 3-sigma = +/- 0.045 V (sigma = 0.015 V).

3. Spatial Correlation, Edge Roll-Off & Defect Clusters:
   - Systematic Within-Wafer (WIW) variation modeled via 2D Gaussian spatial filtering
     (scipy.ndimage.gaussian_filter), representing furnace temperature gradients,
     slurry distribution, and plasma chamber non-uniformities.
   - Non-linear radial edge roll-off (rho^3 to rho^4):
     * Gate CD shrinkage due to etch microloading and plasma density gradients.
     * Oxide thinning due to Chemical Mechanical Planarization (CMP) over-polishing.
     * Variance expansion near wafer perimeter (increased edge turbulence).
   - Three localized defect clusters:
     * Cluster 1: Reticle/particle contamination hotspot (oxide thinning & pinhole leakage).
     * Cluster 2: Optical lithography defocus aberration (severe gate CD necking & DIBL).
     * Cluster 3: Bevel slip / thermal stress dislocation arc.

4. Deterministic Vectorized Subthreshold Leakage Current Model (I_leak):
   - I_sub: Classical MOSFET subthreshold diffusion current:
     I_sub ~ (W/L_g) * exp(-V_th_eff / (n * v_t))
     where v_t = k_B * T / q (thermal voltage ~ 25.86 mV at 300 K),
     and n is the subthreshold ideality factor.
   - Drain-Induced Barrier Lowering (DIBL) & Short-Channel Effects (SCE):
     V_th_eff = V_th - delta_V_DIBL(L_g).
   - Gate Direct Tunneling Leakage (I_gate):
     Quantum mechanical tunneling through ultra-thin dielectric (T_ox < 1.5 nm):
     I_gate ~ exp(-gamma_ox * (T_ox - T_ox0) / T_ox0).
   - Unified compact formulation captures exponential surge as V_th drops or T_ox thins.

5. Parametric Yield Classification:
   - Yield_Pass = 1 if I_leak <= I_threshold (strict specification limit: 30 nA),
     Yield_Pass = 0 otherwise (parametric failure).

Outputs:
- Generates 35,000 dies as a pandas DataFrame.
- Comprehensive statistical summary with yield analysis.
- Saves output to 'synthetic_wafer_data.csv'.
================================================================================
"""

import sys
import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

# ==============================================================================
# 1. PHYSICAL CONSTANTS & FAB PROCESS CONFIGURATION
# ==============================================================================
# Simulation reproducibility seed
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
# Gate Length (L_g)
NOMINAL_LG_NM = 28.0             # nm
SIGMA_LG_NM = 0.80               # 3-sigma = +/- 2.4 nm (+/- 8.6%)

# Equivalent Oxide Thickness (T_ox / EOT)
NOMINAL_TOX_NM = 1.20            # nm (12.0 Angstroms)
SIGMA_TOX_NM = 0.020             # 3-sigma = +/- 0.06 nm (+/- 5.0%)

# Threshold Voltage (V_th)
NOMINAL_VTH_V = 0.350            # V (350 mV)
SIGMA_VTH_V = 0.015              # 3-sigma = +/- 0.045 V (+/- 12.8%)

# Leakage Current Physics Model Coefficients
I_NOMINAL_A = 1.0e-8             # 10.0 nA baseline off-state leakage at nominal conditions
SUBTHRESHOLD_SWING_N = 1.26      # Subthreshold body-effect coefficient (n = 1 + C_dep / C_ox)
GAMMA_TOX_TUNNELING = 4.80       # Direct tunneling / dielectric sensitivity parameter
DIBL_COEFFICIENT_V = 0.028       # Drain-Induced Barrier Lowering sensitivity factor (V)

# Parametric Test Threshold Limit (Strict Fab QA Criteria)
# Die fails test if total standby leakage exceeds 30 nA
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

    Parameters:
        total_dies: Target number of dies on the wafer (35,000).
        wafer_radius_mm: Physical wafer radius in mm (150 mm).
        grid_dim: Dimension of the discrete bounding grid.

    Returns:
        Dictionary containing grid indices, physical coordinates, and radial distances.
    """
    # Create 2D coordinate lattice
    grid_y, grid_x = np.indices((grid_dim, grid_dim))
    center_y = (grid_dim - 1) / 2.0
    center_x = (grid_dim - 1) / 2.0

    # Calculate discrete distance from wafer center
    dist_grid_sq = (grid_x - center_x) ** 2 + (grid_y - center_y) ** 2
    dist_grid = np.sqrt(dist_grid_sq)

    # Sort all grid sites by radial distance to extract the circular disk of dies
    sorted_flat_indices = np.argsort(dist_grid.ravel())
    selected_flat_indices = sorted_flat_indices[:total_dies]

    # Map the edge of selected dies to the physical wafer edge (150 mm)
    max_selected_grid_r = dist_grid.ravel()[selected_flat_indices[-1]]
    mm_per_grid_unit = wafer_radius_mm / max_selected_grid_r

    # Extract coordinates for the 35,000 dies
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
    Emulates long-range systematic fab signatures (CMP, RTA furnace temperature, gas flow).

    Parameters:
        grid_shape: 2D dimensions of the wafer bounding lattice.
        filter_sigma: Standard deviation for Gaussian kernel smoothing.
        seed: Random seed for independent parameter fields.

    Returns:
        Standardized 2D spatial field with zero mean and unit variance.
    """
    rng = np.random.RandomState(seed)
    white_noise = rng.randn(*grid_shape)
    smoothed_field = gaussian_filter(white_noise, sigma=filter_sigma, mode="reflect")
    standardized_field = (smoothed_field - np.mean(smoothed_field)) / np.std(smoothed_field)
    return standardized_field


def evaluate_defect_clusters(
    x_mm: np.ndarray,
    y_mm: np.ndarray
) -> tuple:
    """
    Computes spatial activation kernels for 3 localized defect clusters:
    - Cluster 1: Reticle/particle contamination hotspot (+45 mm, +50 mm).
    - Cluster 2: Optical lithography defocus aberration hotspot (-60 mm, -40 mm).
    - Cluster 3: Edge crystal slip / thermal stress dislocation (-35 mm, +110 mm).

    Returns:
        Tuple of (cluster1_intensity, cluster2_intensity, cluster3_intensity)
    """
    # Defect Cluster 1: Chemical contamination / pinhole particle
    c1_dist_sq = (x_mm - 45.0)**2 + (y_mm - 50.0)**2
    cluster1 = np.exp(-c1_dist_sq / (2.0 * (11.0**2)))

    # Defect Cluster 2: Lithography stepper focus / dosage error
    c2_dist_sq = (x_mm - (-60.0))**2 + (y_mm - (-40.0))**2
    cluster2 = np.exp(-c2_dist_sq / (2.0 * (9.0**2)))

    # Defect Cluster 3: Bevel mechanical stress / thermal slip
    c3_dist_sq = (x_mm - (-35.0))**2 + (y_mm - 110.0)**2
    cluster3 = np.exp(-c3_dist_sq / (2.0 * (12.0**2)))

    return cluster1, cluster2, cluster3


# ==============================================================================
# 4. PHYSICAL PARAMETER GENERATION (L_g, T_ox, V_th)
# ==============================================================================
def synthesize_process_parameters(grid_info: dict) -> dict:
    """
    Synthesizes Gate Length (L_g), Oxide Thickness (T_ox), and Threshold Voltage (V_th)
    by combining:
      1. Nominal values & 3-sigma base Gaussian drift.
      2. 2D spatially correlated systematic fields (scipy.ndimage.gaussian_filter).
      3. Radial edge roll-off (CMP dishing, etch loading, edge variance expansion).
      4. Localized defect clusters.

    Parameters:
        grid_info: Wafer coordinate dictionary.

    Returns:
        Dictionary containing arrays of physical parameters for each die.
    """
    total_dies = len(grid_info["x_mm"])
    selected_indices = grid_info["selected_flat_indices"]
    rho = grid_info["rho"]
    x_mm = grid_info["x_mm"]
    y_mm = grid_info["y_mm"]

    # 1. 2D Spatially Correlated Fields (Systematic within-wafer variation)
    spatial_Lg_grid = generate_spatial_correlation_field(grid_info["grid_shape"], 16.0, seed=101)
    spatial_Tox_grid = generate_spatial_correlation_field(grid_info["grid_shape"], 14.0, seed=202)
    spatial_Vth_grid = generate_spatial_correlation_field(grid_info["grid_shape"], 18.0, seed=303)

    s_Lg = spatial_Lg_grid.ravel()[selected_indices]
    s_Tox = spatial_Tox_grid.ravel()[selected_indices]
    s_Vth = spatial_Vth_grid.ravel()[selected_indices]

    # 2. Microscopic Random Variation (Uncorrelated RDF and Line Edge Roughness)
    rng_micro = np.random.RandomState(404)
    rand_Lg = rng_micro.randn(total_dies)
    rand_Tox = rng_micro.randn(total_dies)
    rand_Vth = rng_micro.randn(total_dies)

    # 3. Radial Gradient (Edge Roll-off Effects):
    # Process variance increases non-linearly near wafer bevel (rho -> 1.0)
    edge_variance_multiplier = 1.0 + 2.2 * (rho**3.0)

    # Systematic mean shifts due to edge over-etch and CMP dishing
    edge_shift_Lg = -1.40 * (rho**3.0)    # Over-etching reduces gate critical dimension (CD)
    edge_shift_Tox = -0.045 * (rho**3.5)  # CMP over-polishing thins dielectric at periphery
    edge_shift_Vth = -0.025 * (rho**3.0)  # Short-channel DIBL roll-off near edge

    # 4. Defect Clusters
    c1, c2, c3 = evaluate_defect_clusters(x_mm, y_mm)

    # Assemble Parameter Fields:
    # 60% systematic spatial correlation + 40% microscopic variation
    Lg = (
        NOMINAL_LG_NM
        + (0.60 * s_Lg + 0.40 * rand_Lg) * SIGMA_LG_NM * edge_variance_multiplier
        + edge_shift_Lg
        - 2.80 * c2    # Cluster 2: severe gate necking
        - 1.20 * c3    # Cluster 3: dislocation strain
    )

    Tox = (
        NOMINAL_TOX_NM
        + (0.60 * s_Tox + 0.40 * rand_Tox) * SIGMA_TOX_NM * edge_variance_multiplier
        + edge_shift_Tox
        - 0.090 * c1   # Cluster 1: gate dielectric erosion / pinhole
        - 0.045 * c3   # Cluster 3: dislocation defect
    )

    Vth = (
        NOMINAL_VTH_V
        + (0.60 * s_Vth + 0.40 * rand_Vth) * SIGMA_VTH_V * edge_variance_multiplier
        + edge_shift_Vth
        - 0.055 * c1   # Cluster 1: oxide damage / flatband shift
        - 0.070 * c2   # Cluster 2: DIBL barrier drop from narrow gate
        - 0.045 * c3   # Cluster 3: crystal defect leakage
    )

    # Enforce physically bounded semiconductor limits
    Lg = np.clip(Lg, 15.0, 40.0)
    Tox = np.clip(Tox, 0.80, 1.80)
    Vth = np.clip(Vth, 0.10, 0.60)

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

    Physical Semiconductor Formulation:
    -----------------------------------
    1. Short-Channel Effect & DIBL (Drain-Induced Barrier Lowering):
       As gate length shrinks, source-to-drain depletion regions overlap,
       causing an effective drop in the electrostatic potential barrier:
           Delta_Vth_DIBL = dibl_coeff * ((nominal_lg / Lg)^2 - 1.0)
           Vth_effective = Vth - Delta_Vth_DIBL

    2. Subthreshold Conduction (Diffusion Leakage):
       Current in the weak inversion regime drops exponentially with Vth:
           I_sub ~ (nominal_lg / Lg) * exp( (nominal_vth - Vth_effective) / (n * vt) )

    3. Dielectric Direct Tunneling (Quantum Leakage):
       Quantum mechanical wave-function tunneling increases exponentially
       as equivalent oxide thickness (T_ox) thins below nominal:
           I_tunnel ~ exp( gamma_tox * (nominal_tox - Tox) / nominal_tox )

    4. Total Standby Off-State Leakage Current:
           I_leak = i_nom * (nominal_lg / Lg) * exp(
               (nominal_vth - (Vth - Delta_Vth_DIBL)) / (n * vt)
               + gamma_tox * (nominal_tox - Tox) / nominal_tox
           )

    Returns:
        1D NumPy array of leakage currents (Amperes).
    """
    # 1. Short-Channel DIBL barrier reduction (V)
    dibl_barrier_shift = dibl_coeff * ((nominal_lg / Lg_nm)**2 - 1.0)
    effective_vth = Vth_V - dibl_barrier_shift

    # 2. Exponent terms representing exponential degradation:
    # Subthreshold component: exponential increase as effective V_th drops
    subthreshold_exp = (nominal_vth - effective_vth) / (n_swing * vt)

    # Oxide tunneling component: exponential increase as T_ox thins
    tunneling_exp = gamma_tox * ((nominal_tox - Tox_nm) / nominal_tox)

    # 3. Geometric channel scaling factor
    geometric_factor = nominal_lg / Lg_nm

    # Total vectorized leakage current (Amperes)
    total_exponent = subthreshold_exp + tunneling_exp
    i_leak_array = i_nom * geometric_factor * np.exp(total_exponent)

    return i_leak_array


# ==============================================================================
# 6. PARAMETRIC YIELD EVALUATION & DATA PIPELINE
# ==============================================================================
def generate_synthetic_wafer_dataset(output_csv: str = "synthetic_wafer_data.csv") -> pd.DataFrame:
    """
    Orchestrates the complete data generation pipeline:
    1. Generates 35,000 die circular wafer coordinates.
    2. Synthesizes correlated L_g, T_ox, and V_th fields.
    3. Calculates deterministic physical leakage current (I_leak).
    4. Computes Yield_Pass flags against the 30 nA tolerance threshold.
    5. Formats a structured pandas DataFrame, displays statistics, and saves CSV.

    Returns:
        pandas DataFrame containing the full dataset.
    """
    print("=" * 80)
    print("  STARTING SYNTHETIC SEMICONDUCTOR WAFER GENERATION (35,000 DIES)")
    print("=" * 80)

    # Step 1: Grid & Coordinates
    print("[1/5] Generating circular 300 mm wafer coordinate grid...")
    grid_data = generate_circular_wafer_grid(TOTAL_DIES, WAFER_RADIUS_MM, N_GRID)

    # Step 2 & 3: Base Distributions, Spatial Correlation, Radial Roll-off & Clusters
    print("[2/5] Synthesizing physical process parameters (L_g, T_ox, V_th)...")
    print("      - Applying 2D Gaussian filters for within-wafer spatial correlation")
    print("      - Introducing non-linear radial edge roll-off gradients")
    print("      - Embedding 3 localized contamination & lithography defect clusters")
    params = synthesize_process_parameters(grid_data)

    # Step 4: Deterministic Physical Leakage Model
    print("[3/5] Computing vectorized subthreshold & quantum tunneling leakage (I_leak)...")
    leakage_current_A = calculate_subthreshold_leakage(
        Lg_nm=params["Lg_nm"],
        Tox_nm=params["Tox_nm"],
        Vth_V=params["Vth_V"]
    )

    # Step 5: Yield Determination
    print(f"[4/5] Evaluating Yield_Pass against strict threshold ({I_LEAK_FAIL_THRESHOLD_A * 1e9:.1f} nA)...")
    yield_pass = (leakage_current_A <= I_LEAK_FAIL_THRESHOLD_A).astype(int)

    # Assemble pandas DataFrame
    print("[5/5] Assembling final pandas DataFrame and calculating statistics...")
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
    print(f"--> Saved dataset successfully to '{output_csv}' ({len(df):,} rows)\n")

    # ==============================================================================
    # 7. COMPREHENSIVE STATISTICAL SUMMARY & YIELD REPORT
    # ==============================================================================
    total_count = len(df)
    passed_count = df["Yield_Pass"].sum()
    failed_count = total_count - passed_count
    overall_yield_pct = (passed_count / total_count) * 100.0

    # Regional Yield Analysis (Center vs Mid-Wafer vs Outer Edge)
    center_mask = df["Normalized_Radius"] < 0.60
    mid_mask = (df["Normalized_Radius"] >= 0.60) & (df["Normalized_Radius"] < 0.85)
    edge_mask = df["Normalized_Radius"] >= 0.85

    center_yield_pct = (df.loc[center_mask, "Yield_Pass"].sum() / center_mask.sum()) * 100.0
    mid_yield_pct = (df.loc[mid_mask, "Yield_Pass"].sum() / mid_mask.sum()) * 100.0
    edge_yield_pct = (df.loc[edge_mask, "Yield_Pass"].sum() / edge_mask.sum()) * 100.0

    # Localized Defect Cluster Yield Analysis
    c1_dist = np.sqrt((df["Wafer_X_mm"] - 45.0)**2 + (df["Wafer_Y_mm"] - 50.0)**2)
    c2_dist = np.sqrt((df["Wafer_X_mm"] - (-60.0))**2 + (df["Wafer_Y_mm"] - (-40.0))**2)
    c3_dist = np.sqrt((df["Wafer_X_mm"] - (-35.0))**2 + (df["Wafer_Y_mm"] - 110.0)**2)

    cluster1_dies = df[c1_dist <= 12.0]
    cluster2_dies = df[c2_dist <= 10.0]
    cluster3_dies = df[c3_dist <= 13.0]

    c1_yield_pct = (cluster1_dies["Yield_Pass"].sum() / len(cluster1_dies)) * 100.0
    c2_yield_pct = (cluster2_dies["Yield_Pass"].sum() / len(cluster2_dies)) * 100.0
    c3_yield_pct = (cluster3_dies["Yield_Pass"].sum() / len(cluster3_dies)) * 100.0

    print("=" * 80)
    print("                    FAB YIELD & PARAMETRIC TEST REPORT")
    print("=" * 80)
    print(f"Total Processed Dies:         {total_count:,}")
    print(f"Passing Dies (Yield_Pass=1):  {passed_count:,}")
    print(f"Failing Dies (Yield_Pass=0):  {failed_count:,}")
    print(f"Overall Wafer Yield:          {overall_yield_pct:.2f} %")
    print("-" * 80)
    print("REGIONAL RADIAL YIELD BREAKDOWN:")
    print(f"  * Inner Core (rho < 0.60):    {center_yield_pct:.2f} %  ({center_mask.sum():,} dies)")
    print(f"  * Mid-Wafer  (0.60 <= rho < 0.85): {mid_yield_pct:.2f} %  ({mid_mask.sum():,} dies)")
    print(f"  * Outer Edge (rho >= 0.85):   {edge_yield_pct:.2f} %  ({edge_mask.sum():,} dies)  [CMP / Etch Loss]")
    print("-" * 80)
    print("LOCALIZED DEFECT CLUSTER IMPACT:")
    print(f"  * Cluster 1 (Particle/Pinhole @ +45,+50 mm):  Yield = {c1_yield_pct:.2f} %  ({len(cluster1_dies)} dies)")
    print(f"  * Cluster 2 (Litho Defocus    @ -60,-40 mm):  Yield = {c2_yield_pct:.2f} %  ({len(cluster2_dies)} dies)")
    print(f"  * Cluster 3 (Thermal Slip     @ -35,+110 mm): Yield = {c3_yield_pct:.2f} %  ({len(cluster3_dies)} dies)")
    print("=" * 80)

    # Parametric Distribution Summary
    param_cols = [
        "Gate_Length_nm",
        "Oxide_Thickness_nm",
        "Threshold_Voltage_V",
        "Leakage_Current_nA",
        "Log10_Leakage_Current"
    ]
    summary_stats = df[param_cols].describe(percentiles=[0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99]).T
    summary_stats["3_sigma_lower"] = summary_stats["mean"] - 3.0 * summary_stats["std"]
    summary_stats["3_sigma_upper"] = summary_stats["mean"] + 3.0 * summary_stats["std"]

    print("\nPROCESS PARAMETER & ELECTRICAL METRICS DISTRIBUTION:")
    pd.set_option("display.max_columns", 12)
    pd.set_option("display.width", 120)
    print(summary_stats[["mean", "std", "min", "50%", "95%", "max", "3_sigma_lower", "3_sigma_upper"]].to_string())
    print("\n" + "=" * 80)

    return df


# ==============================================================================
# 8. OPTIONAL WAFER MAP VISUALIZATION (Google Colab / Jupyter Ready)
# ==============================================================================
def plot_wafer_maps(df: pd.DataFrame, save_fig_path: str = "wafer_maps.png") -> None:
    """
    Renders high-resolution spatial wafer heatmaps for:
      1. Parametric Die Yield (Pass/Fail)
      2. Threshold Voltage (V_th)
      3. Gate Length (L_g)
      4. Log10 Leakage Current (I_leak)

    Safely executes only if matplotlib is installed; otherwise skips gracefully.
    """
    try:
        import matplotlib.pyplot as plt
        import matplotlib.colors as mcolors

        fig, axes = plt.subplots(2, 2, figsize=(15, 14), dpi=150)
        plt.subplots_adjust(wspace=0.25, hspace=0.25)

        # Plot 1: Binary Parametric Yield Map
        ax1 = axes[0, 0]
        cmap_yield = mcolors.ListedColormap(["#d9534f", "#5cb85c"])
        sc1 = ax1.scatter(
            df["Wafer_X_mm"], df["Wafer_Y_mm"],
            c=df["Yield_Pass"], cmap=cmap_yield, s=1.8, alpha=0.9
        )
        cbar1 = plt.colorbar(sc1, ax=ax1, ticks=[0.25, 0.75])
        cbar1.ax.set_yticklabels(["Fail (0)", "Pass (1)"])
        ax1.set_title("1. Die Parametric Yield Map (Pass / Fail)", fontsize=13, fontweight="bold")

        # Plot 2: Gate Length Map
        ax2 = axes[0, 1]
        sc2 = ax2.scatter(
            df["Wafer_X_mm"], df["Wafer_Y_mm"],
            c=df["Gate_Length_nm"], cmap="viridis", s=1.8, alpha=0.9
        )
        plt.colorbar(sc2, ax=ax2, label="Gate Length $L_g$ (nm)")
        ax2.set_title("2. Gate Length ($L_g$) Distribution", fontsize=13, fontweight="bold")

        # Plot 3: Threshold Voltage Map
        ax3 = axes[1, 0]
        sc3 = ax3.scatter(
            df["Wafer_X_mm"], df["Wafer_Y_mm"],
            c=df["Threshold_Voltage_V"], cmap="plasma", s=1.8, alpha=0.9
        )
        plt.colorbar(sc3, ax=ax3, label="Threshold Voltage $V_{th}$ (V)")
        ax3.set_title("3. Threshold Voltage ($V_{th}$) Map", fontsize=13, fontweight="bold")

        # Plot 4: Log10 Subthreshold Leakage Current Map
        ax4 = axes[1, 1]
        sc4 = ax4.scatter(
            df["Wafer_X_mm"], df["Wafer_Y_mm"],
            c=df["Log10_Leakage_Current"], cmap="inferno", s=1.8, alpha=0.9
        )
        plt.colorbar(sc4, ax=ax4, label=r"$\log_{10}(I_{leak} \text{ [A]})$")
        ax4.set_title(r"4. Log Leakage Current ($\log_{10} I_{leak}$)", fontsize=13, fontweight="bold")

        # Format circular axes
        for ax in axes.flat:
            ax.set_xlim(-160, 160)
            ax.set_ylim(-160, 160)
            ax.set_aspect("equal")
            ax.set_xlabel("Wafer X (mm)", fontsize=11)
            ax.set_ylabel("Wafer Y (mm)", fontsize=11)
            # Draw wafer circular boundary
            circle = plt.Circle((0, 0), WAFER_RADIUS_MM, color="black", fill=False, linestyle="--", linewidth=1.2)
            ax.add_patch(circle)

        fig.suptitle(
            "300 mm Silicon Wafer Synthetic Parametric & Yield Maps (35,000 Dies)\n28nm HKMG CMOS Node Simulation",
            fontsize=15, fontweight="bold", y=0.98
        )
        plt.savefig(save_fig_path, bbox_inches="tight")
        print(f"--> Wafer visualization map saved to '{save_fig_path}'")
        plt.close(fig)

    except ImportError:
        print("[Notice] matplotlib not installed; skipping graphic plot generation.")


# ==============================================================================
# MAIN EXECUTION ENTRY POINT
# ==============================================================================
if __name__ == "__main__":
    # Generate dataset and display statistics
    dataset = generate_synthetic_wafer_dataset(output_csv="synthetic_wafer_data.csv")

    # Generate optional visualization
    plot_wafer_maps(dataset, save_fig_path="wafer_maps.png")
