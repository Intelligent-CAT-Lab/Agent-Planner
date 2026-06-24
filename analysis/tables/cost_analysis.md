# Cost Analysis Comparison

| Dataset | Model | Method | Steps | Executor Cost ($) | Advisor Cost ($) | Total Cost ($) | Monitor Latency (s) | Refiner Latency (s) |
|---------|-------|--------|------:|------------------:|-----------------:|---------------:|--------------------:|--------------------:|
| SWE-bench Verified | DeepSeek-V3 | Vanilla actor | 21 | 0.04 | -- | 0.04 | -- | -- |
| | | LivePlan | 24 | 0.06 | 0.02 | 0.08 | 0.0 | 5.8 |
| SWE-bench Verified | Gemini-2.5-Flash | Vanilla actor | 52 | 0.46 | -- | 0.46 | -- | -- |
| | | LivePlan | 38 | 0.55 | 0.04 | 0.59 | 0.0 | 8.1 |
| SWE-bench Verified | MiniMax-M2.5 | Vanilla actor | 70 | 0.30 | -- | 0.30 | -- | -- |
| | | LivePlan | 58 | 0.23 | 0.02 | 0.25 | 0.0 | 39.5 |
| SWE-bench Pro | DeepSeek-V3 | Vanilla actor | 16 | 0.04 | -- | 0.04 | -- | -- |
| | | LivePlan | 30 | 0.12 | 0.04 | 0.15 | 0.0 | 10.9 |
| SWE-bench Pro | Gemini-2.5-Flash | Vanilla actor | 75 | 0.78 | -- | 0.78 | -- | -- |
| | | LivePlan | 47 | 0.98 | 0.06 | 1.04 | 0.0 | 9.6 |
| SWE-bench Pro | MiniMax-M2.5 | Vanilla actor | 47 | 0.24 | -- | 0.24 | -- | -- |
| | | LivePlan | 47 | 0.24 | 0.01 | 0.24 | 0.0 | 29.1 |

## Summary Statistics


### SWE-bench Verified

**Vanilla actor**: Avg Steps: 47.6, Avg Total Cost: $0.27, Avg Executor Cost: $0.27, Avg Advisor Cost: $0.00
**LivePlan**: Avg Steps: 39.8, Avg Total Cost: $0.31, Avg Executor Cost: $0.28, Avg Advisor Cost: $0.03

### SWE-bench Pro

**Vanilla actor**: Avg Steps: 45.9, Avg Total Cost: $0.35, Avg Executor Cost: $0.35, Avg Advisor Cost: $0.00
**LivePlan**: Avg Steps: 41.1, Avg Total Cost: $0.48, Avg Executor Cost: $0.44, Avg Advisor Cost: $0.04