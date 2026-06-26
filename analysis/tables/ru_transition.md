# Resolution Transition Matrix

Comparing configurations against Vanilla actor baseline:
- **RU**: Baseline resolved only (regression)
- **UR**: Config resolved only (improvement)

Incomplete instances are treated as unresolved.
Total: 264 for SWE-bench Pro, 500 for SWE-bench Verified.

| Config | Metric | SWE-bench Pro / DeepSeek-V3 | SWE-bench Pro / Gemini-2.5-Flash | SWE-bench Pro / MiniMax-M2.5 | SWE-bench Verified / DeepSeek-V3 | SWE-bench Verified / Gemini-2.5-Flash | SWE-bench Verified / MiniMax-M2.5 |
|--------|--------|---------|---------|---------|---------|---------|---------|
| SAGE | RU | 26 | 12 | 22 | -- | -- | -- |
|  | UR | 19 | 28 | 17 | -- | -- | -- |
|--------|--------|---------|---------|---------|---------|---------|---------|
| Monitor-Only | RU | 19 | 15 | 16 | -- | -- | -- |
|  | UR | 28 | 33 | 21 | -- | -- | -- |
|--------|--------|---------|---------|---------|---------|---------|---------|
| Periodic Advisor | RU | 16 | 13 | 18 | -- | -- | -- |
|  | UR | 35 | 50 | 24 | -- | -- | -- |
|--------|--------|---------|---------|---------|---------|---------|---------|
| LivePlan | RU | 3 | 3 | 10 | 21 | 20 | 7 |
|  | UR | 36 | 46 | 25 | 77 | 73 | 32 |
|--------|--------|---------|---------|---------|---------|---------|---------|