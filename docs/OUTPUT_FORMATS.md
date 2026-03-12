# Output Formats

## Terminal

The terminal formatter shows:

- log metadata
- ordered diagnoses
- evidence for each diagnosis
- decision status
- subsystem blame ranking
- similar historical cases
- runtime engine status

## JSON

The JSON formatter returns:

- `metadata`
- `runtime`
- `diagnoses`
- `decision`
- `similar_cases`
- `features_summary`

`runtime` includes whether ML was available at execution time.

## HTML

The HTML formatter mirrors the same content as terminal and JSON:

- diagnosis cards
- evidence blocks
- overall decision
- subsystem ranking
- similar historical cases
- runtime engine section
