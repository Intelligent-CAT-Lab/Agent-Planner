# Inefficiency Pattern Analysis

| Pattern | SWE-bench Pro<br>DeepSeek-V3<br>Vanilla actor | SWE-bench Pro<br>DeepSeek-V3<br>LivePlan | SWE-bench Pro<br>Gemini-2.5-Flash<br>Vanilla actor | SWE-bench Pro<br>Gemini-2.5-Flash<br>LivePlan | SWE-bench Pro<br>MiniMax-M2.5<br>Vanilla actor | SWE-bench Pro<br>MiniMax-M2.5<br>LivePlan | SWE-bench Verified<br>DeepSeek-V3<br>Vanilla actor | SWE-bench Verified<br>DeepSeek-V3<br>LivePlan | SWE-bench Verified<br>Gemini-2.5-Flash<br>Vanilla actor | SWE-bench Verified<br>Gemini-2.5-Flash<br>LivePlan | SWE-bench Verified<br>MiniMax-M2.5<br>Vanilla actor | SWE-bench Verified<br>MiniMax-M2.5<br>LivePlan |
|:-------|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|-------:|
| **Blocking** |  |  |  |  |  |  |  |  |  |  |  |  |
| &nbsp;&nbsp;Plan Violation | 229 (86.7%) | 157 (59.5%) | 95 (35.7%) | 87 (32.7%) | 1 (0.4%) | 0 (0.0%) | 127 (25.4%) | 73 (14.6%) | 31 (6.2%) | 23 (4.6%) | 31 (6.2%) | 7 (1.4%) |
| &nbsp;&nbsp;Oscillation | 229 (86.7%) | 46 (17.4%) | 165 (62.0%) | 36 (13.5%) | 20 (7.6%) | 2 (0.8%) | 252 (50.4%) | 10 (2.0%) | 271 (54.2%) | 105 (21.0%) | 25 (5.0%) | 4 (0.8%) |
| &nbsp;&nbsp;*Total* | 244 (92.4%) | 165 (62.5%) | 178 (66.9%) | 106 (39.8%) | 20 (7.6%) | 2 (0.8%) | 270 (54.0%) | 78 (15.6%) | 278 (55.6%) | 116 (23.2%) | 56 (11.2%) | 11 (2.2%) |
| **Non-blocking** |  |  |  |  |  |  |  |  |  |  |  |  |
| &nbsp;&nbsp;Long Stagnation | 70 (26.5%) | 111 (42.0%) | 135 (50.8%) | 163 (61.3%) | 163 (61.7%) | 160 (60.6%) | 142 (28.4%) | 190 (38.0%) | 263 (52.6%) | 244 (48.8%) | 386 (77.2%) | 370 (74.0%) |
| &nbsp;&nbsp;Repeated Action | 42 (15.9%) | 69 (26.1%) | 142 (53.4%) | 161 (60.5%) | 112 (42.4%) | 116 (43.9%) | 51 (10.2%) | 64 (12.8%) | 174 (34.8%) | 165 (33.0%) | 294 (58.8%) | 234 (46.8%) |
| &nbsp;&nbsp;*Total* | 92 (34.8%) | 148 (56.1%) | 193 (72.6%) | 222 (83.5%) | 209 (79.2%) | 216 (81.8%) | 167 (33.4%) | 217 (43.4%) | 302 (60.4%) | 291 (58.2%) | 441 (88.2%) | 434 (86.8%) |
| **Any Pattern** | 250 (94.7%) | 225 (85.2%) | 221 (83.1%) | 242 (91.0%) | 213 (80.7%) | 216 (81.8%) | 353 (70.6%) | 256 (51.2%) | 369 (73.8%) | 340 (68.0%) | 453 (90.6%) | 436 (87.2%) |