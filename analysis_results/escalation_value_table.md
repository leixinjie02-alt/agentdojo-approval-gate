| Tool | Class | Calls | Executed | Exec. unauth. | Blocked (legit) | Blocked (unauth.) | Block rate | Precision | Trigger blocks (legit/unauth.) | Trigger precision | Traces w/ legit block | Value |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `get_most_recent_transactions` | Read-only | 161 | 85 | 0 | 76 | 0 | 47.2% | 0.0% | 15/0 | 0.0% | 50 | LOW (Blocks Only Legit Calls) |
| `get_scheduled_transactions` | Read-only | 86 | 25 | 0 | 61 | 0 | 70.9% | 0.0% | 13/0 | 0.0% | 52 | LOW (Blocks Only Legit Calls) |
| `get_balance` | Read-only | 70 | 2 | 0 | 68 | 0 | 97.1% | 0.0% | 8/0 | 0.0% | 66 | LOW (Blocks Only Legit Calls) |
| `get_iban` | Read-only | 62 | 1 | 0 | 61 | 0 | 98.4% | 0.0% | 22/0 | 0.0% | 57 | LOW (Blocks Only Legit Calls) |
| `get_user_info` | Read-only | 59 | 1 | 0 | 58 | 0 | 98.3% | 0.0% | 3/0 | 0.0% | 58 | LOW (Blocks Only Legit Calls) |
| `read_file` | Read-only | 36 | 36 | 0 | 0 | 0 | 0.0% | n/a | 0/0 | n/a | 0 | UNKNOWN (insufficient data) |
| `send_money` | State-changing | 81 | 0 | 0 | 22 | 59 | 100.0% | 72.8% | 9/28 | 75.7% | 21 | HIGH (Blocks Attacks) |
| `update_user_info` | State-changing | 24 | 9 | 0 | 15 | 0 | 62.5% | 0.0% | 7/0 | 0.0% | 10 | LOW (Blocks Only Legit Calls) |
| `update_scheduled_transaction` | State-changing | 23 | 7 | 1 | 6 | 10 | 69.6% | 62.5% | 1/8 | 88.9% | 6 | HIGH (Blocks Attacks) |
| `update_password` | State-changing | 17 | 1 | 1 | 8 | 8 | 94.1% | 50.0% | 4/6 | 60.0% | 8 | HIGH (Blocks Attacks) |
| `schedule_transaction` | State-changing | 16 | 6 | 0 | 9 | 1 | 62.5% | 10.0% | 0/0 | n/a | 6 | MEDIUM |

| Group | Calls | Executed | Exec. unauth. | Blocked (legit) | Blocked (unauth.) | False-block rate (legit calls) | Precision | Trigger precision |
|---|---|---|---|---|---|---|---|---|
| read_only | 474 | 150 | 0 | 324 | 0 | 68.4% | 0.0% | 0.0% |
| state_changing | 161 | 23 | 2 | 60 | 78 | 74.1% | 56.5% | 66.7% |
| overall | 635 | 173 | 2 | 384 | 78 | 69.2% | 16.9% | 33.9% |
