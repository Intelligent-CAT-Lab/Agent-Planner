# Resolution Transition Matrix

Comparing configurations against Vanilla actor baseline:
- **RR**: Both resolved
- **RU**: Baseline resolved only
- **UR**: Config resolved only
- **UU**: Both unresolved

Incomplete instances are treated as unresolved.
Total: 264 for SWE-bench Pro, 500 for SWE-bench Verified.

| Config | Metric | SWE-bench Pro / DeepSeek-V3 | SWE-bench Pro / Gemini-2.5-Flash | SWE-bench Pro / MiniMax-M2.5 | SWE-bench Verified / DeepSeek-V3 | SWE-bench Verified / Gemini-2.5-Flash | SWE-bench Verified / MiniMax-M2.5 |
|--------|--------|---------|---------|---------|---------|---------|---------|
| SAGE | RR | 31 | 20 | 116 | 132 | -- | -- |
|  | RU | 26 | 12 | 22 | 59 | -- | -- |
|  | UR | 19 | 28 | 17 | 30 | -- | -- |
|  | UU | 188 | 204 | 109 | 279 | -- | -- |
|--------|--------|---------|---------|---------|---------|---------|---------|
| Monitor-Only | RR | 38 | 17 | 122 | 153 | -- | -- |
|  | RU | 19 | 15 | 16 | 38 | -- | -- |
|  | UR | 28 | 33 | 21 | 46 | -- | -- |
|  | UU | 179 | 199 | 105 | 263 | -- | -- |
|--------|--------|---------|---------|---------|---------|---------|---------|
| Periodic Advisor | RR | 41 | 19 | 120 | 171 | -- | -- |
|  | RU | 16 | 13 | 18 | 20 | -- | -- |
|  | UR | 35 | 50 | 24 | 90 | -- | -- |
|  | UU | 172 | 182 | 102 | 219 | -- | -- |
|--------|--------|---------|---------|---------|---------|---------|---------|
| LivePlan | RR | 54 | 29 | 128 | 170 | 169 | 364 |
|  | RU | 3 | 3 | 10 | 21 | 20 | 7 |
|  | UR | 36 | 46 | 25 | 77 | 73 | 32 |
|  | UU | 171 | 186 | 101 | 232 | 238 | 97 |
|--------|--------|---------|---------|---------|---------|---------|---------|