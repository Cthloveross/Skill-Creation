# skillsbench run report

Protocol: `skillsbench.skill-evolution.v4`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Until all tasks are measured, fixed-denominator rates report observed successes; they are not complete matrix results.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility | Task pass rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| benign | no_skill | 85 | 0 | 6 | 0.5 | 0.0352941 | 0.0352941 |
| benign | initial | 85 | 6 | 4 | 0 | 0 | 0 |
| benign | evolved | 85 | 6 | 4 | 0.25 | 0.0117647 | 0.0117647 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 6 | 4 | 0 | {'oracle_result_unknown': 2, 'test_escalation_failed': 1, 'invalid_revision_response': 1, 'verifier_initialization_failed': 1} |
| benign | 1 | 1 | 1 | 1 | {'oracle_success': 1} |

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
| dialogue-parser | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
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
| latex-formula-extraction | benign | oracle_result_unknown | 1 | 0 | 0 | 1 | 61 | 1 | 8698f7e2eb07843f7ed90ff4876b7a0db4ed45911ca7ecf154ad2518e4dcb09e |
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
| pedestrian-traffic-counting | benign | oracle_result_unknown | 1 | 0 | 1 | 1 | 42 | 1 | c815cccf5b52bbee2a5208ca97444b1055ea9f55c658eaab199eee56624a15ce |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pptx-reference-formatting | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| protein-expression-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| python-scala-translation | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 42 | 1 | 907529e1eb6fc66506f1303634b219bb95f9a1e204ad5bbb5017e56f2c9386a1 |
| quantum-numerical-simulation | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| r2r-mpc-control | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| react-performance-debugging | benign | oracle_success | 2 | 1 | 2 | 1 | 43 | 2 | 20968d89467cec29e83e34e5fced9d394dacd3954b6eb7a87c7224f40c0767fb |
| reserves-at-risk-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| sales-pivot-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| sec-financial-report | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | invalid_revision_response | 1 | 0 | 0 | 1 | 4 | 0 | f271ba6642bed912bce310cabfbe0ea4b2e946e0c989c412539c6004d155d984 |
| shock-analysis-demand | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| shock-analysis-supply | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 16 | 1 | eeeae627b1eabca0891006e0ba1363c53653191aa5d21a5ccb6b9c7894697688 |
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
| latex-formula-extraction | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| pedestrian-traffic-counting | MEASURED | True | 1 | 1 | 1 | 1 | reporter_group |
| python-scala-translation | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| react-performance-debugging | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| setup-fuzzing-py | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| software-dependency-audit | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |

## No-Skill paired comparisons

| Condition | Endpoint | Paired | Denominator | Utility delta | Paired coverage | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | initial | 4 | 85 | -0.25 | 0.0470588 | -0.25 | 2 | 0.0235294 | 0 | 0 | 1 |
| benign | evolved | 4 | 85 | 0 | 0.0470588 | 0 | 2 | 0.0235294 | 0 | 0 | 0 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit | Previous | Utility delta | Reward delta | GT delta (pp) | GT delta reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| latex-formula-extraction | 0 | S0 / final | 8698f7e2eb07843f7ed90ff4876b7a0db4ed45911ca7ecf154ad2518e4dcb09e | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| pedestrian-traffic-counting | 0 | S0 / final | c815cccf5b52bbee2a5208ca97444b1055ea9f55c658eaab199eee56624a15ce | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| python-scala-translation | 0 | S0 / final | 907529e1eb6fc66506f1303634b219bb95f9a1e204ad5bbb5017e56f2c9386a1 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| react-performance-debugging | 0 | S0 | d1879f7c6919a11179ce9704131057c42d044b850e787d44504ed2c67389e0de | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | -1 | -1 | NOT_MEASURED | official_checks_not_measured |
| react-performance-debugging | 1 | S1 / final | 20968d89467cec29e83e34e5fced9d394dacd3954b6eb7a87c7224f40c0767fb | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S0 | 1 | 1 | NOT_MEASURED | official_checks_not_measured |
| setup-fuzzing-py | 0 | S0 / final | f271ba6642bed912bce310cabfbe0ea4b2e946e0c989c412539c6004d155d984 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| software-dependency-audit | 0 | S0 / final | eeeae627b1eabca0891006e0ba1363c53653191aa5d21a5ccb6b9c7894697688 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| latex-formula-extraction | 8698f7e2eb07843f7ed90ff4876b7a0db4ed45911ca7ecf154ad2518e4dcb09e | 0 | af216b453903b56372fda9522f7f9e8753644dc365c2a507c420f45e55431d73 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | c815cccf5b52bbee2a5208ca97444b1055ea9f55c658eaab199eee56624a15ce | 0 | fddeffb2c768e7b30061d327c55a6f327977cbd911cae1b8a9d5a21560c734f9 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | c815cccf5b52bbee2a5208ca97444b1055ea9f55c658eaab199eee56624a15ce | 1 | e3b151d7b3058d09cbda200ab397bb73c120421f78d75fb470d153a452c9e194 | True | 1 | NOT_MEASURED |
| python-scala-translation | 907529e1eb6fc66506f1303634b219bb95f9a1e204ad5bbb5017e56f2c9386a1 | 0 | 44e3ad3bf0d064ab07e2e4a4c2d6870f84cfd86ee838f2e8e00fe85b68e7f99c | True | 1 | NOT_MEASURED |
| react-performance-debugging | d1879f7c6919a11179ce9704131057c42d044b850e787d44504ed2c67389e0de | 0 | ca1393c13b42a72b7b25870fdc85ff23682dd9d4bb3e3692a21e86b308f7f74e | True | 1 | NOT_MEASURED |
| react-performance-debugging | d1879f7c6919a11179ce9704131057c42d044b850e787d44504ed2c67389e0de | 1 | 69cf4d77a8fffaf062a25a82b4c4c233b816e7da57faa971ddcbf459eef2d37b | False | 0.75 | NOT_MEASURED |
| react-performance-debugging | 20968d89467cec29e83e34e5fced9d394dacd3954b6eb7a87c7224f40c0767fb | 1 | 69cf4d77a8fffaf062a25a82b4c4c233b816e7da57faa971ddcbf459eef2d37b | True | 1 | NOT_MEASURED |

## Adjacent content paired coverage

| Condition | From | To | Actual chains | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | NoSkill | S0 | 6 | 85 | 4 | 0.0470588 | -0.25 | 4 | -0.25 | 2 | 0.0235294 | 0 |
| benign | S0 | S1 | 1 | 85 | 1 | 0.0117647 | 1 | 1 | 1 | 0 | 0 | NOT_MEASURED |

S labels enumerate sealed content hashes, not revision attempts. Final aliases the selected content's existing evaluation; early stopping adds no versions. GT deltas require measured checks with matching unit, total and source. Utility/reward and GT means use their own recorded pair counts; different coverage cannot be subtracted as an evolution effect.

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | GT delta (pp) | GT delta reason | Final aliases S0 | Rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| latex-formula-extraction | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| pedestrian-traffic-counting | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured | True | NOT_MEASURED |
| python-scala-translation | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| react-performance-debugging | benign | True | 1 | 1 | NOT_MEASURED | official_checks_not_measured | False | True |
| setup-fuzzing-py | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured | True | NOT_MEASURED |
| software-dependency-audit | benign | True | 0 | 0 | 0 | MEASURED | True | False |

## S0-to-Final paired coverage

| Condition | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Same content | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 85 | 4 | 0.0470588 | 0.25 | 4 | 0.25 | 2 | 0.0235294 | 0 | 3 | 1 | 0 |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| latex-formula-extraction | benign | 2 | 3478 | sufficient | ae96592d338084f8209a54c1f7b1968246a56941faa5d68906203da8c38cd791 |
| pedestrian-traffic-counting | benign | 2 | 2931 | budget_exhausted_incomplete | c8ade1091fb1ca14b20e04b556d29e3ef657b1cf4e47102e9748a707c66e6f48 |
| python-scala-translation | benign | 2 | 3660 | sufficient | 012e67fe9ebc16fcd9eecee598f2017e048e9a8fc32b1cab5953a8f6ecca84a7 |
| react-performance-debugging | benign | 2 | 3147 | sufficient | 1655422d0804b2c2f176ac26e8562185dc59ace9f28e00d6f9753026872dda2f |
| setup-fuzzing-py | benign | 1 | 1964 | sufficient | 6bf71e00fbafa26e660fe570854cfb90fd5a9e0612cdc5dc20b4540eed7a5526 |
| software-dependency-audit | benign | 1 | 303 | budget_exhausted_incomplete | 2554c353f0a23e3c0fe5eb9e8678e29dd940b7c6fc6c902be07af510173fcb33 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 77 | 984566 | 47882 | 0 |
| generator | 136 | 3173214 | 74409 | 2946708 |
| verifier | 125 | 4756030 | 66859 | 4313421 |
| execution | 341 | 8324168 | 127389 | 7708854 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
