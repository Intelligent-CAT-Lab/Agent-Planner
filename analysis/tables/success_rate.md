# Effectiveness: success rate and average cost

## SWE-bench Pro (run-1)
Success rate = resolved / 266 (full dataset); delta vs Vanilla.

### DeepSeek-V3
| Method | Success Rate (%) | Average Cost |
|---|---|---|
| Vanilla | 21.43 | 0.04 |
| SAGE | 18.80 (-2.63) | 0.01 |
| Monitor-Only | 24.81 (+3.38) | 0.11 |
| Periodic Advisor | 28.57 (+7.14) | 0.12 |
| LivePlan | **33.83** (+12.41) | 0.15 |

### Gemini-2.5-Flash
| Method | Success Rate (%) | Average Cost |
|---|---|---|
| Vanilla | 12.03 | 0.78 |
| SAGE | 18.05 (+6.02) | 0.22 |
| Monitor-Only | 18.80 (+6.77) | 0.98 |
| Periodic Advisor | 25.94 (+13.91) | 0.84 |
| LivePlan | **28.20** (+16.17) | 1.04 |

### MiniMax-M2.5
| Method | Success Rate (%) | Average Cost |
|---|---|---|
| Vanilla | 51.88 | 0.24 |
| SAGE | 50.00 (-1.88) | 0.03 |
| Monitor-Only | 53.76 (+1.88) | 0.23 |
| Periodic Advisor | 54.14 (+2.26) | 0.32 |
| LivePlan | **57.52** (+5.64) | 0.24 |

## SWE-bench Verified (run-1)
Success rate = resolved / 500 (full dataset); delta vs Vanilla.

### DeepSeek-V3
| Method | Success Rate (%) | Average Cost |
|---|---|---|
| Vanilla | 38.20 | 0.04 |
| LivePlan | **49.40** (+11.20) | 0.08 |

### Gemini-2.5-Flash
| Method | Success Rate (%) | Average Cost |
|---|---|---|
| Vanilla | 37.80 | 0.46 |
| LivePlan | **48.40** (+10.60) | 0.59 |

### MiniMax-M2.5
| Method | Success Rate (%) | Average Cost |
|---|---|---|
| Vanilla | 74.20 | 0.30 |
| LivePlan | **79.20** (+5.00) | 0.25 |
