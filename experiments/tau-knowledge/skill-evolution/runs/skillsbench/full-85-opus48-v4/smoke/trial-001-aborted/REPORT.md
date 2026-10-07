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
| benign | initial | 85 | 1 | 0 | NOT_MEASURED | 0 | 0 |
| benign | evolved | 85 | 1 | 0 | NOT_MEASURED | 0 | 0 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 1 | 0 | NOT_MEASURED | {'learning_environment_close_failed': 1} |

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
| dialogue-parser | benign | learning_environment_close_failed | 1 | 0 | 0 | 1 | 18 | 1 | 32c298bda9c7bc734064a7b0612c0b4e21f987f83d45cf3950fc6e3dc3d12ae2 |
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
| dialogue-parser | MEASURED | False | 0.667 | 4 | 6 | 0.666667 | reporter_group |

## No-Skill paired comparisons

| Condition | Endpoint | Paired | Denominator | Utility delta | Paired coverage | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | initial | 0 | 85 | NOT_MEASURED | 0 | NOT_MEASURED | 0 | 0 | NOT_MEASURED | 0 | 0 |
| benign | evolved | 0 | 85 | NOT_MEASURED | 0 | NOT_MEASURED | 0 | 0 | NOT_MEASURED | 0 | 0 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit | Previous | Utility delta | Reward delta | GT delta (pp) | GT delta reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | 0 | S0 / final | 32c298bda9c7bc734064a7b0612c0b4e21f987f83d45cf3950fc6e3dc3d12ae2 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |

## Adjacent content paired coverage

| Condition | From | To | Actual chains | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | NoSkill | S0 | 1 | 85 | 0 | 0 | NOT_MEASURED | 0 | NOT_MEASURED | 0 | 0 | NOT_MEASURED |

S labels enumerate sealed content hashes, not revision attempts. Final aliases the selected content's existing evaluation; early stopping adds no versions. GT deltas require measured checks with matching unit, total and source. Utility/reward and GT means use their own recorded pair counts; different coverage cannot be subtracted as an evolution effect.

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | GT delta (pp) | GT delta reason | Final aliases S0 | Rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dialogue-parser | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured | True | NOT_MEASURED |

## S0-to-Final paired coverage

| Condition | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Same content | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 85 | 0 | 0 | NOT_MEASURED | 0 | NOT_MEASURED | 0 | 0 | NOT_MEASURED | 0 | 0 | 0 |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| dialogue-parser | benign | 1 | 280 | sufficient | c7a9d413c8d564ca941feec69375e022b902d6ff025ce5b685daa17bda44ad28 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 19 | 207887 | 24226 | 0 |
| generator | 7 | 63296 | 15200 | 0 |
| verifier | 9 | 151416 | 6751 | 0 |
| execution | 8 | 164532 | 6214 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
