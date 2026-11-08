"""Isolated A3.4 filters. Never selected by FusionDetector in production.

The observation remains the visible centroid. No actor pose, dimensions, or
reference trajectory is fed into these filters. Noise values are hypotheses.
"""
from dataclasses import dataclass
import math
import numpy as np
from carla_multi_agent.fusion_detector import KalmanTracker


@dataclass(frozen=True)
class Settings:
    name: str
    process: str = 'legacy'
    q: float = .1
    r: float = .5
    p0: float = 10.


def process_covariance(dt, spectral_density):
    """Continuous white acceleration: q has units m^2/s^3, state [p,v]."""
    if not math.isfinite(dt) or dt <= 0 or not math.isfinite(spectral_density) or spectral_density < 0:
        raise ValueError('finite positive dt and nonnegative spectral density required')
    identity = np.eye(3)
    return spectral_density * np.block([[dt**3 / 3 * identity, dt**2 / 2 * identity],
                                        [dt**2 / 2 * identity, dt * identity]])


class ExperimentalTracker(KalmanTracker):
    def __init__(self, observation, settings):
        super().__init__(observation)
        if settings.process not in ('legacy','continuous'):
            raise ValueError('unknown process model')
        if any(not math.isfinite(v) or v <= 0 for v in (settings.q,settings.r,settings.p0)):
            raise ValueError('positive finite hypothesis parameters required')
        self.settings = settings
        self.P = np.eye(6,dtype=np.float32) * settings.p0
        self.R = np.eye(3,dtype=np.float32) * settings.r
        self.Q = np.eye(6,dtype=np.float32) * settings.q

    def predict(self,dt=.1):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('positive finite dt required')
        if self.settings.process=='continuous':
            self.Q=process_covariance(dt,self.settings.q)
        super().predict(dt)

    def get_state(self):
        state=super().get_state()
        model=state['estimation_quality']['model']
        model['initial_covariance_diagonal']=[self.settings.p0]*6
        model['experimental_settings']=dict(name=self.settings.name,process=self.settings.process,
            q=self.settings.q,r=self.settings.r,p0=self.settings.p0,physically_calibrated=False)
        return state


# Declared before replay: CWA q=2 matches only the legacy velocity variance
# rate 0.1/0.05, NOT the full legacy Q and NOT a fitted physical acceleration.
SETTINGS=[Settings('baseline'),Settings('legacy_q001',q=.01),Settings('legacy_q05',q=.5),
          Settings('legacy_r025',r=.25),Settings('legacy_r1',r=1.),
          Settings('legacy_p1',p0=1.),Settings('legacy_p100',p0=100.),
          Settings('cwa_q025','continuous',.25),Settings('cwa_q1','continuous',1.),
          Settings('cwa_q2','continuous',2.),Settings('cwa_q4','continuous',4.),
          Settings('cwa_q16','continuous',16.),Settings('cwa_r025','continuous',2.,.25),
          Settings('cwa_r1','continuous',2.,1.),Settings('cwa_p1','continuous',2.,.5,1.),
          Settings('cwa_p100','continuous',2.,.5,100.)]
