# State Engine TP3 candidate retrieval result v1

Configuration hash: `fd58d16af282e5b5c86083879ac288246318157598f30bc9b75d497a6d277238`
Frozen TP0 corpus hash: `4b029bff64564abc226d431b373a3d75cbf971c66aa6bb53e2cf29c7198c4b09`
Material outcome hash: `79b3007be96e4959349930ad867f23086215fb7840d487dfe0ca18ba45511ccd`

| Measure | Result |
|---|---:|
| Indexed evidence occurrences | 62 |
| Gold-neighbor directed queries | 38 |
| Gold neighbors found at `k=20` | 38 |
| Candidate recall | 100% |
| Mean reciprocal rank | 1.000 |
| Negative-control directed queries | 6 |
| False associations in top 10 | 0 |
| False-association rate | 0% |
| Primary model calls | 0 |
| Target disposition | passed |

The target was frozen before execution at at least 95% recall with `k=20` and at most a 10%
false-association rate in the top 10. The first implementation run preserved 100% recall but failed
the negative-control ceiling with 3 false associations out of 6 (`50%`; outcome hash
`92418e69f2ae90e3acf9eca4a9cc17f050c97b4e4fe15e023610845d6cf706d1`). The general policy was
then corrected so canonical entities that are explicitly disjoint and have no declared graph bridge
cannot be related by lexical similarity or coincident timing alone. No case labels, expected answers,
or target values enter the ranker.

| Ablation | Recall | MRR | Mean removed-signal contribution |
|---|---:|---:|---:|
| Without vector | 100% | 1.000 | 0.602 |
| Without entity | 100% | 1.000 | 1.000 |
| Without temporal | 100% | 1.000 | 0.719 |

All three signals contributed materially to the full receipts, but the small TP0 corpus contains
enough redundant entity, graph, lexical, and temporal evidence that removing any single signal did
not change recall or MRR at `k=20`. This result must not be presented as proof that the signals are
unnecessary at scale.

The vector-absent fallback receipt is
`candidate_receipt:bafb644655988716adf65e7caaff2f1b`. It explicitly names `vector` as unavailable,
continues with the bounded remaining indexes, and makes zero provider calls. Unknown-time records
remain candidates through other signals but their temporal contribution is marked
`unknown_time_not_scored` rather than treated as a temporal match.
