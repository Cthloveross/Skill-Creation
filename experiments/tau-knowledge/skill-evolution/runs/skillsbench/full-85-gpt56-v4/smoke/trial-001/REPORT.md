# skillsbench run report

Protocol: `skillsbench.skill-evolution.v4`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Until all tasks are measured, fixed-denominator rates report observed successes; they are not complete matrix results.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility | Task pass rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| benign | no_skill | 85 | 0 | 1 | 0 | 0 | 0 |
| benign | initial | 85 | 1 | 1 | 0 | 0 | 0 |
| benign | evolved | 85 | 1 | 1 | 0 | 0 | 0 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 1 | 1 | 0 | {} |
| benign | 1 | 1 | 1 | 0 | {'oracle_success': 1} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Learning executions | Terminal calls | Submissions | Final hash |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| adaptive-cruise-control | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| citation-check | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| court-form-filling | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| dapt-intrusion-detection | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| data-to-d3 | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| dialogue-parser | benign | oracle_success | 2 | 1 | 1 | 1 | 24 | 2 | f3a1cd8c3652f8d195cae91bdb071f49c8d77ba4262a0a58e853873fe7ff2a78 |
| dynamic-object-aware-egomotion | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| econ-detrending-correlation | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| energy-ac-optimal-power-flow | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| energy-market-pricing | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| enterprise-information-search | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| exceltable-in-ppt | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| exoplanet-detection-period | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| financial-modeling-qa | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| find-topk-similiar-chemicals | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| fix-build-agentops | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| fix-build-google-auto | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| fix-druid-loophole-cve | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| fix-visual-stability | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| flink-query | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| flood-risk-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| gh-repo-analytics | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| glm-lake-mendota | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| gravitational-wave-detection | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| grid-dispatch-operator | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| hvac-control | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| invoice-fraud-detection | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| jax-computing-basics | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| jpg-ocr-stat | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| lab-unit-harmonization | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| lake-warming-attribution | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| latex-formula-extraction | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| lean4-proof | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-codebook-normalization | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-equipment-maintenance | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-fjsp-optimization | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| mario-coin-counting | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| mars-clouds-clustering | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| multilingual-video-dubbing | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| offer-letter-generator | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| organize-messy-files | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| paper-anonymizer | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| parallel-tfidf-search | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pddl-tpp-planning | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pdf-excel-diff | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pedestrian-traffic-counting | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pptx-reference-formatting | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| protein-expression-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| python-scala-translation | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| quantum-numerical-simulation | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| r2r-mpc-control | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| react-performance-debugging | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| reserves-at-risk-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| sales-pivot-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| sec-financial-report | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| shock-analysis-demand | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| shock-analysis-supply | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| speaker-diarization-subtitles | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| spring-boot-jakarta-migration | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| suricata-custom-exfil | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| syzkaller-ppdev-syzlang | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| taxonomy-tree-merge | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| threejs-structure-parser | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| trend-anomaly-causal-inference | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| video-filler-word-remover | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| video-silence-remover | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| video-tutorial-indexer | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| virtualhome-agent-planning | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| weighted-gdp-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| xlsx-recover-data | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |

No-Skill runs use no package and do not create S0. Baseline comparisons require the same sealed executor identity; evaluations do not enter learning.

## No-Skill independent measurements

| Task | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | MEASURED | False | 0.833 | 5 | 6 | 0.833333 | reporter_group |

## No-Skill paired comparisons

| Condition | Endpoint | Paired | Denominator | Utility delta | Paired coverage | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | initial | 1 | 85 | 0 | 0.0117647 | 0 | 1 | 0.0117647 | 0 | 0 | 0 |
| benign | evolved | 1 | 85 | 0 | 0.0117647 | 0 | 1 | 0.0117647 | 0 | 0 | 0 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit | Previous | Utility delta | Reward delta | GT delta (pp) | GT delta reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | 0 | S0 | 7da395c461db6766110953fed6d37c5bc4798226220a21bf6aba288de10ea2a9 | MEASURED | False | 0.833 | 5 | 6 | 0.833333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| dialogue-parser | 1 | S1 / final | f3a1cd8c3652f8d195cae91bdb071f49c8d77ba4262a0a58e853873fe7ff2a78 | MEASURED | False | 0.833 | 5 | 6 | 0.833333 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | 7da395c461db6766110953fed6d37c5bc4798226220a21bf6aba288de10ea2a9 | 0 | c1ac5972026d62f2d4accb999372d4fc686531b093ef49155304de6fab2ec34b | False | 0.5 | NOT_MEASURED |
| dialogue-parser | f3a1cd8c3652f8d195cae91bdb071f49c8d77ba4262a0a58e853873fe7ff2a78 | 0 | c1ac5972026d62f2d4accb999372d4fc686531b093ef49155304de6fab2ec34b | True | 1 | NOT_MEASURED |

## Adjacent content paired coverage

| Condition | From | To | Actual chains | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | NoSkill | S0 | 1 | 85 | 1 | 0.0117647 | 0 | 1 | 0 | 1 | 0.0117647 | 0 |
| benign | S0 | S1 | 1 | 85 | 1 | 0.0117647 | 0 | 1 | 0 | 1 | 0.0117647 | 0 |

S labels enumerate sealed content hashes, not revision attempts. Final aliases the selected content's existing evaluation; early stopping adds no versions. GT deltas require measured checks with matching unit, total and source. Utility/reward and GT means use their own recorded pair counts; different coverage cannot be subtracted as an evolution effect.

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | GT delta (pp) | GT delta reason | Final aliases S0 | Rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | benign | True | 0 | 0 | 0 | MEASURED | False | False |

## S0-to-Final paired coverage

| Condition | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Same content | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 85 | 1 | 0.0117647 | 0 | 1 | 0 | 1 | 0.0117647 | 0 | 0 | 0 | 0 |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| dialogue-parser | benign | 1 | 280 | sufficient | 931625c89ec6bb54e91abe091f3d8b10c4bf348f3317c9b1aaf3d8df02e997b3 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 39 | 431091 | 24821 | 0 |
| generator | 14 | 188329 | 11401 | 162377 |
| verifier | 20 | 431077 | 16476 | 378260 |
| execution | 39 | 531263 | 16398 | 456053 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
