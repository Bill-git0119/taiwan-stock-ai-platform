"""Strategy Lab — research, validate, and promote strategies.

A strategy lives in two states:
  CANDIDATE  : freshly registered, not yet validated → cannot fire signals
  PROMOTED   : passed walk-forward + Monte Carlo gates → may fire signals

Promotion rules (configurable, see validator.PROMOTION_THRESHOLDS):
  * Out-of-sample sharpe          >= 0.8
  * Out-of-sample profit factor   >= 1.3
  * Out-of-sample max drawdown    >= -25%
  * Out-of-sample trade count     >= 30
  * Monte Carlo 5%-worst equity   > starting equity (still profitable)
"""
