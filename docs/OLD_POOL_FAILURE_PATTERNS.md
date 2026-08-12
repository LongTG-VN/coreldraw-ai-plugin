# V0.4 Phase 1 old-pool failure patterns

This document keeps human evidence separate from deterministic structural measurements.

## Human-observed evidence

- 44 explicit UI reviews were preserved in the immutable `diagnostic_generation_v1` snapshot.
- Choices: A wins 11, B wins 5, ties 2, both bad 26.
- The both-bad rate is 59.09%.
- No optional numeric ratings and no written notes were present, so no detailed human complaint is inferred.
- The reviewer separately reported the old pool at approximately 4/10. This is pool-level diagnostic feedback, not a per-candidate label.

The human data therefore supports only the conclusion that the pool frequently offered two unacceptable choices. It does not, by itself, attribute that result to typography, assets, hierarchy, or any other specific subsystem.

## Automatically measured evidence

The deterministic audit covered 20 four-candidate groups admitted to the Phase 1 queue:

- exact text/content consistency: 10%
- asset consistency: 100%
- business-value consistency: 90%
- canvas consistency: 100%
- mean inferred layout-family count: 1.0 per brief
- mean pairwise structural diversity: 0.010871
- minimum pairwise structural diversity: 0.0
- placeholder count: 204
- mean placeholder-area ratio: 0.179000
- technical pass rate: 100%

These measurements support three generator-level diagnoses: copy was not locked, layout families were effectively not varied, and placeholder use remained high. They are not human aesthetic labels and are not exported as preferences.

## Dataset policy

The 44 records remain tagged `diagnostic_generation_v1`. Pilot records are tagged `candidate_generation_v2_pilot`. They must not be merged blindly for future reranker training.
