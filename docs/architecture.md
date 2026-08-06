# Architecture

The canonical six-layer architecture and dependency direction are defined in the master plan.
Phase 0 establishes package boundaries; subsequent gates add verified implementations.

```text
contracts <- layer services <- workflow <- interfaces
                     ^              |
                  adapters <--------+

agentic_text2sql_eval -> runtime public contracts/interfaces
runtime -X-> evaluator/gold data
```

