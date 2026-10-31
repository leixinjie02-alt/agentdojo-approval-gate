## TCR@k, attack success and HITL load

| Policy | k | Attacked runs | Safe completions | TCR@k (95% CI) | TCR@k, action tasks (95% CI) | Attack success | Escalations, all tasks | Escalations per task | Escalations in safely completed tasks |
|---|---|---|---|---|---|---|---|---|---|
| Full-approve (baseline) | – | 144 | 36 | 0.250 (0.186–0.327) | 0.222 (0.154–0.309) | 0.472 | 0 | 0.00 | 0 |
| Full-escalate (baseline) | 0 | 144 | 36 | 0.250 (0.186–0.327) | 0.000 (0.000–0.034) | 0.000 | 0 | 0.00 | 0 |
| Full-escalate (baseline) | 1 | 144 | 47 | 0.326 (0.255–0.407) | 0.102 (0.058–0.173) | 0.000 | 142 | 0.99 | 47 |
| Full-escalate (baseline) | 2 | 144 | 39 | 0.271 (0.205–0.349) | 0.093 (0.051–0.162) | 0.000 | 274 | 1.90 | 68 |
| Full-escalate (baseline) | 3 | 144 | 39 | 0.271 (0.205–0.349) | 0.102 (0.058–0.173) | 0.000 | 386 | 2.68 | 95 |
| Full-escalate (baseline) | 5 | 144 | 34 | 0.236 (0.174–0.312) | 0.093 (0.051–0.162) | 0.000 | 553 | 3.84 | 109 |
| Rules + semantic (ours) | 0 | 144 | 38 | 0.264 (0.199–0.341) | 0.093 (0.051–0.162) | 0.000 | 0 | 0.00 | 0 |
| Rules + semantic (ours) | 1 | 144 | 38 | 0.264 (0.199–0.341) | 0.093 (0.051–0.162) | 0.000 | 116 | 0.81 | 25 |
| Rules + semantic (ours) | 2 | 144 | 41 | 0.285 (0.217–0.363) | 0.130 (0.079–0.206) | 0.007 | 207 | 1.44 | 44 |
| Rules + semantic (ours) | 3 | 144 | 37 | 0.257 (0.193–0.334) | 0.102 (0.058–0.173) | 0.007 | 261 | 1.81 | 44 |
| Rules + semantic (ours) | 5 | 144 | 39 | 0.271 (0.205–0.349) | 0.130 (0.079–0.206) | 0.007 | 341 | 2.37 | 46 |

## API cost per component (USD per run)

| Policy | k | Agent | Policy | Reviewer | Total | Cost per safe completion |
|---|---|---|---|---|---|---|
| Full-approve (baseline) | – | 0.1176 | 0.0000 | 0.0000 | 0.1176 | 0.0033 |
| Full-escalate (baseline) | 0 | 0.1043 | 0.0000 | 0.0000 | 0.1043 | 0.0029 |
| Full-escalate (baseline) | 1 | 0.1299 | 0.0000 | 0.0212 | 0.1511 | 0.0032 |
| Full-escalate (baseline) | 2 | 0.1230 | 0.0000 | 0.0493 | 0.1723 | 0.0044 |
| Full-escalate (baseline) | 3 | 0.1346 | 0.0000 | 0.0758 | 0.2103 | 0.0054 |
| Full-escalate (baseline) | 5 | 0.1328 | 0.0000 | 0.1171 | 0.2500 | 0.0074 |
| Rules + semantic (ours) | 0 | 0.1266 | 0.1316 | 0.0000 | 0.2582 | 0.0068 |
| Rules + semantic (ours) | 1 | 0.1279 | 0.1321 | 0.0247 | 0.2847 | 0.0075 |
| Rules + semantic (ours) | 2 | 0.1285 | 0.1350 | 0.0469 | 0.3104 | 0.0076 |
| Rules + semantic (ours) | 3 | 0.1226 | 0.1217 | 0.0592 | 0.3036 | 0.0082 |
| Rules + semantic (ours) | 5 | 0.1324 | 0.1367 | 0.0803 | 0.3494 | 0.0090 |
