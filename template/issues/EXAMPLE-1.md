# Rolling maximum drawdown for strategy returns

- **Type:** feature
- **Source:** idea
- **Requested by:** PM analytics
- **Priority:** medium

## Problem / motivation

The performance report shows total-period max drawdown only. Risk wants to
see how drawdown evolves over time, per strategy, on a rolling window.

## Desired outcome

A function that takes daily simple returns (dates x strategies) and a window
length, and returns the rolling maximum drawdown per strategy, usable in the
existing report module.

## Acceptance hints

- Returns [0.10, -0.20, 0.05] with window 3: the max drawdown at the last date is -0.20.
- Drawdown is reported as a negative decimal (-0.2 = -20%).

## Constraints

- 20 years x 500 strategies daily should run in under 2 seconds.
- Must not change the existing `max_drawdown` function's output.

## Open questions

- Behaviour for the first window-1 dates (NaN or expanding window)?
- How to treat NaN returns (strategy not live yet)?
