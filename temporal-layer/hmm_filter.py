import numpy as np
from hmmlearn import hmm
import logging

logger = logging.getLogger(__name__)

class TemporalHMMFilter:
    """
    Hidden Markov Model to filter transient noise from telemetry sequences.
    States: 0 (Healthy), 1 (Degrading), 2 (Failing)
    """
    def __init__(self, n_states=3):
        self.n_states = n_states
        self.fitted = False
        # Gaussian HMM for continuous feature streams
        self.model = hmm.GaussianHMM(n_components=n_states, covariance_type="diag", n_iter=100)
        
        # Pre-initialize transition matrix to favor staying in current state (smoothing)
        # Transition: P(state_t | state_t-1)
        self.model.transmat_ = np.array([
            [0.95, 0.04, 0.01], # Healthy
            [0.05, 0.90, 0.05], # Degrading
            [0.01, 0.04, 0.95]  # Failing
        ])
        
    def fit(self, feature_sequences, lengths):
        """Train the HMM on historical sequences."""
        try:
            self.model.fit(feature_sequences, lengths)
            self.fitted = True
            logger.info("HMM training complete.")
        except Exception as e:
            logger.error(f"HMM training failed: {e}")
            raise
            
    def predict_states(self, feature_sequence):
        """
        Takes an array of shape (n_samples, n_features)
        Returns the Viterbi decoded state sequence.
        """
        if len(feature_sequence) == 0:
            return np.array([])
        if not self.fitted:
            raise RuntimeError("Temporal HMM is not fitted; refusing to emit synthetic healthy states.")
        
        # Viterbi decoding finds the most likely state sequence
        _, states = self.model.decode(feature_sequence)
        return states
        
    def filter_transients(self, feature_sequence, window_size=5):
        """
        If a sequence jumps to 'Failing' for just 1-2 ticks and drops back to 'Healthy',
        this identifies it as transient noise.
        """
        states = self.predict_states(feature_sequence)
        
        # Simple majority vote over a rolling window to smooth transients
        smoothed_states = np.copy(states)
        pad = window_size // 2
        for i in range(pad, len(states) - pad):
            window = states[i-pad : i+pad+1]
            smoothed_states[i] = np.bincount(window).argmax()
            
        return smoothed_states
