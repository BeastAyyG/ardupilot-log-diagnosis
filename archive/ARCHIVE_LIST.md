# Archive List

This file documents files and modules that have been moved out of the main product path.

## Reason

These files were archived because they were:
- Loose test files in the repo root (not in `tests/`)
- Duplicate implementations of tools that exist elsewhere
- Unrelated modules not part of the diagnosis product

## Archived Items

### Loose Test Scripts (→ archive/loose_tests/)

| File | Original Location | Reason |
|------|-------------------|--------|
| `test_bin.py` | repo root | Duplicate of proper tests in `tests/` |
| `test_bin2.py` | repo root | Duplicate of proper tests in `tests/` |
| `test_df.py` | repo root | Duplicate of proper tests in `tests/` |
| `test_parse_bin.py` | repo root | Duplicate of proper tests in `tests/` |

### Duplicate Scripts (→ archive/duplicate_scripts/)

| File | Original Location | Kept Version |
|------|-------------------|--------------|
| `analyze_thrust.py` | `scripts/analyze_thrust.py` | `src/tools/analyze_thrust.py` |

### Unrelated Modules (→ archive/unrelated_modules/)

| File | Original Location | Reason |
|------|-------------------|--------|
| `health_monitor.py` | `src/health_monitor.py` | Companion health monitor, not part of diagnosis product |

## How to Restore

If any archived item is needed, move it back from the archive folder to its original location.

## Archive Maintenance

- Review the archive folder periodically.
- Delete items that are confirmed to be no longer needed.
- Do not add new code to archived items.
