"""Observable tracker diagnostics, deliberately NOT calibrated confidence.

No acceptance threshold, smoothing, or F2MD verdict is derived from this model.
Covariances describe CARLA-world tracker state; they are not ENU ASN.1 confidence.
"""
import copy
import math
import numpy as np


def describe(tracker):
    covariance = np.asarray(tracker.P)
    finite = bool(np.all(np.isfinite(covariance)) and np.all(np.isfinite(tracker.x)))
    minimum = None
    if finite:
        minimum = float(np.linalg.eigvalsh((covariance + covariance.T) / 2).min())
    numerical_valid = finite and minimum >= -1e-9  # roundoff tolerance, not sensor accuracy
    initial = tracker.hits <= 1
    predicted = tracker._quality_event == 'predicted'
    reasons = ['physical_uncertainty_not_calibrated']
    if initial:
        reasons.append('velocity_not_observed_at_initialization')
    if predicted:
        reasons.append('no_measurement_update_for_this_state')
    if not numerical_valid:
        reasons.append('nonfinite_or_invalid_model_covariance')
    phase = 'prediction_only' if predicted else ('initializing' if initial else 'measurement_updated')
    qualification = ('technical_error' if not numerical_valid else
                     ('insufficient_observation' if initial or predicted else 'uncalibrated_estimate'))
    return {
        'schema_version': 1,
        'phase': phase,
        'qualification': qualification,
        'physically_calibrated': False,
        'reasons': reasons,
        'track_age_s': tracker._quality_age_s,
        'last_measurement_age_s': tracker._quality_measurement_age_s,
        'hits': tracker.hits,
        'misses': tracker.misses,
        'consecutive_updates': 0 if predicted else tracker._quality_consecutive_updates,
        'velocity_available': not initial,
        'current_update': copy.deepcopy(tracker._quality_current_update),
        'last_update': copy.deepcopy(tracker._quality_last_update),
        'legacy_score_is_probability': False,
        'model': {
            'frame': 'CARLA_world',
            'covariance_scope': 'uncalibrated_tracker_state_only',
            'numerically_valid': numerical_valid,
            'minimum_covariance_eigenvalue': minimum,
            'state_covariance_diagonal': np.diag(covariance).tolist() if finite else None,
            'process_noise_diagonal_per_step': np.diag(tracker.Q).tolist(),
            'measurement_noise_diagonal': np.diag(tracker.R).tolist(),
            'initial_covariance_diagonal': [10.] * 6,
            'xy_velocity_model_sigma_m_s': math.sqrt(max(0., float(covariance[3, 3]+covariance[4, 4]))) if finite else None,
        },
    }
