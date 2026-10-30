# Model card

Version: illustrative-bulk-nmos-v2.

Functional form: Ioff = I0 * (W/L_um) * exp(-(Vth0 + alpha_L*dL +
alpha_tox*dtox + dVth_mV/1000 - Vgs)/(n*kT/q)). Exact log-space separability
permits per-axis rounded contributions in a reversible compute/compare/uncompute
oracle. The oracle does not load a table of all pass/fail outcomes.

Device defaults are sourced from the supplied `NominalDevice` dataclass.
The UI obtains its defaults and units from `/api/model`; the original API defaults
have also been aligned with that dataclass.

Provenance: illustrative educational expression. The supplied code cites
Taur & Ning (2009) and https://bsim.berkeley.edu/models/bsim4/ as background.
This is NOT a BSIM implementation and coefficients are NOT foundry measurements.

## Validation performed

Finite-grid normalization, scalar/classical parity, encoding error, boundary
conventions, exact/CDF agreement, quantum flag/uncomputation/phase checks and
Grover identities. A continuous conditional-integration reference and bin
resolution study assess discretization numerically.

## Independent engineering validation

No SPICE simulator, licensed/open model card, held-out reference measurements or
fabrication dataset was included in the upload or available project files.
Accordingly no independent engineering-validation claim is made. Prompt 8's
specified fallback is used: retain illustrative status and record the missing
inputs. Required next input: a documented usable device model plus simulator,
or measured leakage data with process/operating conditions and units.

## Uncertainty

Statistics: reported per estimator. Arithmetic: four nearest-integer roundings
bound the log-score discrepancy by 2/scale (apart from machine floating-point
roundoff). For each finite grid, weighted classification disagreement is measured
exhaustively and bounds the probability difference. The threshold is rounded up
and comparison uses >=. Accumulator range is checked before execution.

Discretization is separate; resolution differences and quadrature error estimates
are not rigorous physical-model error bounds. Omitted tails have no modeled
outcomes. Their mass is reported; an arbitrary-outcome extension interval is
reported only for the continuous conditioned model and labeled hypothetical.
Untruncated Gaussian geometry is not physically valid over its full support.

No correlation, aging, interface chemistry, chip-level aggregation or cost model
is claimed. Device assumptions must be replaced and revalidated before engineering use.
