The local Grok adapter now distinguishes connection loss, a turn limit and account access
refusal. TASK `db6e889`. The three new runtime cases failed on the previous adapter because
all three receipts said unclassified. An unrelated message containing the turn-limit phrase
remained unclassified. The installed `a910203` receipt cannot identify its historical cause.

The tests exercise a fake CLI returning a nonzero JSON terminal response to a subscription
review. Each case verifies the exact durable reason, exit 1, no output artifact and empty
evidence. The shared runtime vocabulary gains only the turn-limit category. A process
timeout and a subscription usage limit retain their existing meanings.

Local Windows checks: `test_grok_activation`, `test_failure_reasons`,
`test_command_grok_leak_surfaces`, `test_command_grok_transport` and
`test_alpha1_gate_g_provider_breadth`: 416 passed with UTF-8 and 416 with cp1251.
No live harness or model call. This change has not been built into the protected installation.
