"""Validation gate for the filter-function dephasing model (src/noise_spectrum.py).

These anchor tests must pass for the right reason before the non-Markovian model
is used for any claim:

1. White-noise limit reproduces the Markovian exp(-t/T2) decay AND is invariant
   to DD pulse count (if this fails, the conventions are wrong and nothing else
   is trustworthy).
2. Under 1/f noise, DD increases coherence and more pulses help more (this is the
   entire reason the module exists; if it fails, the DD lever is dead).
3. The 1/f -> white limit matches a known analytic CPMG suppression scaling.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.noise_spectrum import (
    DephasingSpectrum,
    coherence,
    cpmg_switch_times,
    dephasing_fidelity,
)

T2 = 9600.0


# =============================================================================
# Anchor 1: white-noise limit == Markovian exp(-t/T2), DD-invariant
# =============================================================================


@pytest.mark.parametrize("t", [500.0, 2000.0, 6000.0, 9600.0])
def test_white_noise_reproduces_exp_t2(t: float) -> None:
    """A pure white floor S=2/T2 gives coherence exp(-t/T2) (free induction)."""
    spec = DephasingSpectrum(white_t2_ns=T2)
    assert coherence(t, spec, n_pulses=0) == pytest.approx(np.exp(-t / T2), rel=2e-3)


@pytest.mark.parametrize("n", [0, 1, 4, 16])
def test_white_noise_is_dd_invariant(n: int) -> None:
    """Against white noise, DD does NOT change coherence (defining property)."""
    spec = DephasingSpectrum(white_t2_ns=T2)
    t = 6000.0
    assert coherence(t, spec, n_pulses=n) == pytest.approx(np.exp(-t / T2), rel=3e-3)


def test_white_noise_matches_pulse_module_idle_fidelity() -> None:
    """Dephasing-only fidelity here matches src.pulse idle dephasing in the white limit.

    src.pulse idle coherence is exp(-t/T2); its state fidelity for a pure-dephasing
    idle (T1 -> inf) is (2 + exp(-t/T2))/3. This module must agree.
    """
    spec = DephasingSpectrum(white_t2_ns=T2)
    t = 4000.0
    expected = (2.0 + np.exp(-t / T2)) / 3.0
    assert dephasing_fidelity(t, spec, n_pulses=0) == pytest.approx(expected, rel=3e-3)


# =============================================================================
# Anchor 2: under 1/f noise, DD helps and more pulses help more
# =============================================================================


def test_one_over_f_dd_improves_coherence() -> None:
    """Against 1/f noise, a CPMG echo beats free induction decay."""
    spec = DephasingSpectrum(white_t2_ns=None, one_over_f_amp=1e-7)
    t = 6000.0
    fid_free = coherence(t, spec, n_pulses=0)
    fid_echo = coherence(t, spec, n_pulses=1)
    assert fid_echo > fid_free + 1e-3


def test_one_over_f_more_pulses_help_more() -> None:
    """Against 1/f noise, coherence increases monotonically with CPMG order."""
    spec = DephasingSpectrum(white_t2_ns=None, one_over_f_amp=1e-7)
    t = 6000.0
    cohs = [coherence(t, spec, n_pulses=n) for n in (0, 1, 2, 4, 8)]
    assert all(b >= a - 1e-6 for a, b in zip(cohs[:-1], cohs[1:], strict=True))
    assert cohs[-1] > cohs[0] + 1e-2  # the effect is non-trivial


def test_one_over_f_dd_invariance_breaks() -> None:
    """The whole point: unlike white noise, 1/f coherence depends on pulse count."""
    spec = DephasingSpectrum(white_t2_ns=None, one_over_f_amp=1e-7)
    t = 6000.0
    assert coherence(t, spec, n_pulses=8) != pytest.approx(
        coherence(t, spec, n_pulses=0), rel=0.05
    )


# =============================================================================
# Mechanics
# =============================================================================


def test_cpmg_switch_times_layout() -> None:
    """CPMG places n pulses at (2j-1)/(2n) fractions of the window."""
    assert cpmg_switch_times(100.0, 0).size == 0
    assert cpmg_switch_times(100.0, 1) == pytest.approx([50.0])
    assert cpmg_switch_times(100.0, 2) == pytest.approx([25.0, 75.0])


def test_coherence_decreases_with_time_under_one_over_f() -> None:
    """Longer free evolution under 1/f noise means lower coherence."""
    spec = DephasingSpectrum(white_t2_ns=None, one_over_f_amp=1e-7)
    assert coherence(2000.0, spec, 0) > coherence(8000.0, spec, 0)
