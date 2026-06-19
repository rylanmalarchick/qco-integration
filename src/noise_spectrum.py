"""Filter-function dephasing under a classical noise power spectral density.

The Markovian Lindblad model in ``src.pulse`` cannot represent dynamical
decoupling (DD): against memoryless (white) dephasing, refocusing pulses provably
do not help. Real transmons are dominated by 1/f (colored, non-Markovian)
dephasing, under which DD does help. This module computes pure-dephasing
coherence decay for an arbitrary control sequence via the filter-function
formalism, making DD-aware reasoning possible while staying O(timeline) scalable
(no 2**n state).

Model. A qubit experiences classical dephasing H_noise(t) = (1/2) beta(t) sigma_z
with stationary Gaussian noise of one-sided PSD S(omega) (units rad/ns for omega,
so S has units 1/ns). Under a control sequence that toggles the qubit sign at
each pi pulse (toggling-frame switching function y(t) in {+1,-1}), the accumulated
phase is Gaussian and the coherence is

    W(t) = exp(-chi(t)),   chi(t) = (1 / 2pi) * integral_0^inf S(omega) |y~(omega)|^2 d omega

where y~(omega) = integral_0^t y(t') e^{i omega t'} dt' is computed analytically
for the piecewise-constant y of a pulse sequence.

Conventions are fixed by the white-noise anchor (see tests): S(omega) = 2/T2
(constant) reproduces W(t) = exp(-t/T2), matching ``src.pulse`` idle dephasing,
and is DD-invariant. A 1/f component S(omega) = A/omega is the part DD suppresses.

References: Cywinski et al., PRB 77, 174509 (2008); Biercuk et al., PRA 79,
062324 (2009); Uhrig, PRL 98, 100504 (2007).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DephasingSpectrum:
    """One-sided dephasing PSD S(omega), omega in rad/ns, S in 1/ns.

    Composed of an optional white floor (Markovian, sets the bare T2) and an
    optional 1/f component (colored, DD-suppressible) with low/high cutoffs.
    """

    white_t2_ns: float | None = None  # white floor S0 = 2/T2 reproducing exp(-t/T2)
    one_over_f_amp: float = 0.0  # A in S_1/f(omega) = A / omega   (1/ns * rad/ns)
    omega_low: float = 2 * np.pi * 1e-6  # rad/ns; IR cutoff (~MHz-scale 1/f knee)
    omega_high: float = 2 * np.pi * 1.0  # rad/ns; UV cutoff (~GHz)

    def __post_init__(self) -> None:
        if self.white_t2_ns is not None and self.white_t2_ns <= 0:
            raise ValueError(f"white_t2_ns must be positive, got {self.white_t2_ns}")
        if self.one_over_f_amp < 0:
            raise ValueError(f"one_over_f_amp must be >= 0, got {self.one_over_f_amp}")
        if self.omega_high <= self.omega_low:
            raise ValueError("omega_high must exceed omega_low")

    def __call__(self, omega: np.ndarray) -> np.ndarray:
        """Evaluate S(omega) on an array of (positive) angular frequencies."""
        s = np.zeros_like(omega, dtype=float)
        if self.white_t2_ns is not None:
            s += 2.0 / self.white_t2_ns
        if self.one_over_f_amp > 0:
            band = (omega >= self.omega_low) & (omega <= self.omega_high)
            s = s + np.where(band, self.one_over_f_amp / np.maximum(omega, 1e-300), 0.0)
        return s


def cpmg_switch_times(total_ns: float, n_pulses: int) -> np.ndarray:
    """CPMG pi-pulse times on [0, total_ns]: centers of 2n equal sub-intervals.

    n_pulses = 0 is free induction decay (no pulses). Pulses are treated as
    instantaneous; finite pulse-error cost is handled separately by the gate
    model in ``src.pulse``.
    """
    if n_pulses < 0:
        raise ValueError(f"n_pulses must be >= 0, got {n_pulses}")
    if total_ns <= 0:
        raise ValueError(f"total_ns must be positive, got {total_ns}")
    if n_pulses == 0:
        return np.array([])
    j = np.arange(1, n_pulses + 1)
    return total_ns * (2 * j - 1) / (2 * n_pulses)


def _filter_function(omega: np.ndarray, total_ns: float, switch_times: np.ndarray) -> np.ndarray:
    """|y~(omega)|^2 for the toggling-frame switching function of a pulse sequence.

    y(t) starts at +1 and flips sign at each pulse time. With ordered switch
    points 0 = s_0 < s_1 < ... < s_m = t and constant value y_k on (s_k, s_{k+1}),
        y~(omega) = sum_k y_k (e^{i omega s_{k+1}} - e^{i omega s_k}) / (i omega).
    The omega -> 0 limit is handled analytically (y~ -> sum_k y_k * interval).
    """
    edges = np.concatenate(([0.0], np.asarray(switch_times, dtype=float), [total_ns]))
    values = np.array([(-1.0) ** k for k in range(len(edges) - 1)])

    omega = np.asarray(omega, dtype=float)
    safe = np.where(omega == 0.0, 1.0, omega)
    y_tilde = np.zeros_like(omega, dtype=complex)
    for k, y_k in enumerate(values):
        a, b = edges[k], edges[k + 1]
        term = (np.exp(1j * safe * b) - np.exp(1j * safe * a)) / (1j * safe)
        y_tilde += y_k * term
    # omega == 0: integral of y over [0,t]
    dc = float(np.sum(values * np.diff(edges)))
    y_tilde = np.where(omega == 0.0, dc + 0j, y_tilde)
    result: np.ndarray = np.abs(y_tilde) ** 2
    return result


def coherence(
    total_ns: float,
    spectrum: DephasingSpectrum | Callable[[np.ndarray], np.ndarray],
    n_pulses: int = 0,
    *,
    grid_points: int = 200_000,
) -> float:
    """Coherence W(t) = exp(-chi) for a CPMG-n sequence over [0, total_ns].

    chi = (1/2pi) integral_0^inf S(omega) |y~(omega)|^2 d omega, evaluated on a
    dense linear omega grid. The integrand decays as S(omega)/omega^2 at high
    omega; grid_points / omega_max are chosen so the white-noise anchor converges
    to ~1e-3 (verified in tests).
    """
    switch_times = cpmg_switch_times(total_ns, n_pulses) if n_pulses else np.array([])

    # White (Markovian) part is handled analytically: by Parseval, for a constant
    # PSD S0 the toggling-frame integral gives chi_white = S0 * t / 2 exactly,
    # independent of the pulse sequence (y(t)^2 = 1 always). Doing this in closed
    # form removes the grid error that otherwise grows with pulse count and makes
    # DD-invariance against white noise exact, not approximate.
    chi_white = 0.0
    colored: Callable[[np.ndarray], np.ndarray]
    if isinstance(spectrum, DephasingSpectrum):
        if spectrum.white_t2_ns is not None:
            chi_white = total_ns / spectrum.white_t2_ns  # (2/T2) * t / 2
        colored = DephasingSpectrum(
            white_t2_ns=None,
            one_over_f_amp=spectrum.one_over_f_amp,
            omega_low=spectrum.omega_low,
            omega_high=spectrum.omega_high,
        )
        has_colored = spectrum.one_over_f_amp > 0
    else:
        colored = spectrum
        has_colored = True

    chi_colored = 0.0
    if has_colored:
        # Resolve sub-interval oscillations: highest feature ~ 1/min_gap.
        min_gap = total_ns / (2 * max(n_pulses, 1))
        omega_max = max(50.0 / min_gap, 4 * np.pi / total_ns * 50)
        omega = np.linspace(omega_max / grid_points, omega_max, grid_points)
        s = colored(omega) if callable(colored) else colored.__call__(omega)
        integrand = s * _filter_function(omega, total_ns, switch_times)
        chi_colored = float(np.trapezoid(integrand, omega) / (2 * np.pi))

    return float(np.exp(-(chi_white + chi_colored)))


def dephasing_fidelity(
    total_ns: float,
    spectrum: DephasingSpectrum,
    n_pulses: int = 0,
) -> float:
    """Single-qubit average gate fidelity from dephasing coherence W over a window.

    A pure-dephasing channel with coherence W has average gate fidelity
    (2 + W) / 3 (entanglement fidelity (1 + W) / 2 mapped through (d F_e + 1)/(d+1)
    with d = 2). Pulse-error cost of the n refocusing gates is added by the caller
    via the calibrated gate model in ``src.pulse``.
    """
    w = coherence(total_ns, spectrum, n_pulses)
    f_e = (1.0 + w) / 2.0
    return (2.0 * f_e + 1.0) / 3.0
