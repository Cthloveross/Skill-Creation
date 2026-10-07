# skillsbench run report

Protocol: `skillsbench.skill-evolution.v4`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Until all tasks are measured, fixed-denominator rates report observed successes; they are not complete matrix results.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility | Task pass rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| benign | no_skill | 85 | 0 | 12 | 0.25 | 0.0352941 | 0.0352941 |
| benign | initial | 85 | 11 | 11 | 0.454545 | 0.0588235 | 0.0588235 |
| benign | evolved | 85 | 11 | 11 | 0.363636 | 0.0470588 | 0.0470588 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 11 | 11 | 0.454545 | {'test_escalation_failed': 4, 'verifier_initialization_result_unknown': 1, 'generator_context_budget_exhausted': 1, 'oracle_success': 1, 'revision_result_unknown': 1} |
| benign | 1 | 3 | 3 | 0 | {'test_escalation_failed': 2, 'generator_context_budget_exhausted': 1} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Learning executions | Terminal calls | Submissions | Final hash |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| adaptive-cruise-control | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| citation-check | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| court-form-filling | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| dapt-intrusion-detection | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| data-to-d3 | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| dialogue-parser | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| dynamic-object-aware-egomotion | benign | test_escalation_failed | 1 | 0 | 3 | 1 | 41 | 1 | 339727d7c01c21149df433752bc0cc067877d9557a7ed54f9e3dbd1577d16b1a |
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
| glm-lake-mendota | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | 1 | 20 | 1 | 6ae8a9bf0e78c4619da04bab9c58732c50e3369d0a892fe71b899efdd541fbfc |
| gravitational-wave-detection | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| grid-dispatch-operator | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| hvac-control | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| invoice-fraud-detection | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| jax-computing-basics | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| jpg-ocr-stat | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| lab-unit-harmonization | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| lake-warming-attribution | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 20 | 1 | fc876f28174b560546b4b621f76dcefa6bbbde0155b045a3310f7491a2f6d790 |
| latex-formula-extraction | benign | generator_context_budget_exhausted | 1 | 1 | 1 | 1 | 87 | 1 | 22f602f41614d2701c8810de1bdf05af430a103a4b4bfb57db1db18c1ea0800b |
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
| pddl-tpp-planning | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pdf-excel-diff | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pedestrian-traffic-counting | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pptx-reference-formatting | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| protein-expression-analysis | benign | oracle_success | 1 | 0 | 1 | 1 | 24 | 1 | 98698e64e1e602e87750eaeecb9042a6bd395f966aa52ef6b061c3b2e336f6da |
| python-scala-translation | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| quantum-numerical-simulation | benign | test_escalation_failed | 2 | 1 | 4 | 1 | 95 | 2 | a9ca0a981fed52850d19e34eebb1b12dfb856696a41ceb1b910797e6405e438a |
| r2r-mpc-control | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| react-performance-debugging | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| reserves-at-risk-calc | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| sales-pivot-analysis | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| sec-financial-report | benign | test_escalation_failed | 1 | 0 | 2 | 1 | 46 | 1 | bc21393688923235a6f300aa9e4fd4240a243d0be32b396c91b32702369a3aea |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | revision_result_unknown | 1 | 1 | 0 | 1 | 58 | 1 | 20d6452f1e52c4ad6e970b378af9f432da27f203c88d2d8826e455f052fb05e6 |
| shock-analysis-demand | benign | test_escalation_failed | 1 | 0 | 2 | 1 | 107 | 1 | 9e67d134a671f3bbcbe2c18093123920d3c54f94b9a29ccc9599a7c1271d8cc8 |
| shock-analysis-supply | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | test_escalation_failed | 2 | 1 | 1 | 1 | 40 | 2 | cdf8fb06a60c65be258e79918026945a8c6e743bc829409d6e95b315fd74240f |
| speaker-diarization-subtitles | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| spring-boot-jakarta-migration | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| suricata-custom-exfil | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| syzkaller-ppdev-syzlang | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| taxonomy-tree-merge | benign | generator_context_budget_exhausted | 2 | 2 | 0 | 1 | 107 | 2 | 9707245da5d3acc255d4473c4c66dd8343dd5f69dcc5fa282560914a8e6a6a8b |
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
| adaptive-cruise-control | MEASURED | True | 1 | 12 | 12 | 1 | reporter_group |
| civ6-adjacency-optimizer | MEASURED | False | 0 | 9 | 10 | 0.9 | reporter_group |
| dynamic-object-aware-egomotion | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| glm-lake-mendota | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| lake-warming-attribution | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group |
| latex-formula-extraction | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group |
| pddl-tpp-planning | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| protein-expression-analysis | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| quantum-numerical-simulation | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| sec-financial-report | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| setup-fuzzing-py | MEASURED | False | 0.83 | 2 | 2 | 1 | reporter_group |
| shock-analysis-demand | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group |
| software-dependency-audit | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| taxonomy-tree-merge | MEASURED | False | 0.8615 | 19 | 22 | 0.863636 | reporter_group |

## No-Skill paired comparisons

| Condition | Endpoint | Paired | Denominator | Utility delta | Paired coverage | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | initial | 10 | 85 | 0.3 | 0.117647 | 0.21816 | 8 | 0.0941176 | 9.82143 | 3 | 0 |
| benign | evolved | 10 | 85 | 0.2 | 0.117647 | 0.12085 | 8 | 0.0941176 | 8.6039 | 2 | 0 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit | Previous | Utility delta | Reward delta | GT delta (pp) | GT delta reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dynamic-object-aware-egomotion | 0 | S0 / final | 339727d7c01c21149df433752bc0cc067877d9557a7ed54f9e3dbd1577d16b1a | MEASURED | False | 0 | 9 | 11 | 0.818182 | reporter_group | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| glm-lake-mendota | 0 | S0 / final | 6ae8a9bf0e78c4619da04bab9c58732c50e3369d0a892fe71b899efdd541fbfc | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| lake-warming-attribution | 0 | S0 / final | fc876f28174b560546b4b621f76dcefa6bbbde0155b045a3310f7491a2f6d790 | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 50 | MEASURED |
| latex-formula-extraction | 0 | S0 / final | 22f602f41614d2701c8810de1bdf05af430a103a4b4bfb57db1db18c1ea0800b | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| protein-expression-analysis | 0 | S0 / final | 98698e64e1e602e87750eaeecb9042a6bd395f966aa52ef6b061c3b2e336f6da | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 1 | 1 | NOT_MEASURED | official_checks_not_measured |
| quantum-numerical-simulation | 0 | S0 | 76772c8df6ce71c9b374f28d19e75169889966a3e22371573afbdea8de6d0811 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | NoSkill | 1 | 1 | 28.5714 | MEASURED |
| quantum-numerical-simulation | 1 | S1 / final | a9ca0a981fed52850d19e34eebb1b12dfb856696a41ceb1b910797e6405e438a | MEASURED | False | 0 | 6 | 7 | 0.857143 | reporter_group | S0 | -1 | -1 | -14.2857 | MEASURED |
| sec-financial-report | 0 | S0 / final | bc21393688923235a6f300aa9e4fd4240a243d0be32b396c91b32702369a3aea | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| setup-fuzzing-py | 0 | S0 / final | 20d6452f1e52c4ad6e970b378af9f432da27f203c88d2d8826e455f052fb05e6 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | NoSkill | 1 | 0.17 | 0 | MEASURED |
| shock-analysis-demand | 0 | S0 / final | 9e67d134a671f3bbcbe2c18093123920d3c54f94b9a29ccc9599a7c1271d8cc8 | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| software-dependency-audit | 0 | S0 | 204d9978c0d51e76e4868326ae003a35557809bcc6ec31bcce22eccdde72d260 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| software-dependency-audit | 1 | S1 / final | cdf8fb06a60c65be258e79918026945a8c6e743bc829409d6e95b315fd74240f | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| taxonomy-tree-merge | 0 | S0 | 101703073a020ea94c444e4c0222fe903c99986c03ecde5a9a8b33ca9b19ab23 | MEASURED | False | 0.8731 | 19 | 22 | 0.863636 | reporter_group | NoSkill | 0 | 0.0116 | 0 | MEASURED |
| taxonomy-tree-merge | 1 | S1 / final | 9707245da5d3acc255d4473c4c66dd8343dd5f69dcc5fa282560914a8e6a6a8b | MEASURED | False | 0.9 | 20 | 22 | 0.909091 | reporter_group | S0 | 0 | 0.0269 | 4.54545 | MEASURED |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| dynamic-object-aware-egomotion | 339727d7c01c21149df433752bc0cc067877d9557a7ed54f9e3dbd1577d16b1a | 0 | be14b853fc9b19fee10579bac11095d0281bbd9eea733e919c2e2661f0cd68e3 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 339727d7c01c21149df433752bc0cc067877d9557a7ed54f9e3dbd1577d16b1a | 1 | 9c2f3ca7e95028263d0730a3136d281d03265126b24a3c8b24146115c8d91f09 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 339727d7c01c21149df433752bc0cc067877d9557a7ed54f9e3dbd1577d16b1a | 2 | c52105448c6ffeeda0d229d0d1b364d2ffcf835511ebd6dd359ae95ef2dd2892 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | fc876f28174b560546b4b621f76dcefa6bbbde0155b045a3310f7491a2f6d790 | 0 | f76d404f77a4653580f94f998393cb9c0259158c0eb877f48ca9a4fa178b87f3 | True | 1 | NOT_MEASURED |
| latex-formula-extraction | 22f602f41614d2701c8810de1bdf05af430a103a4b4bfb57db1db18c1ea0800b | 0 | 43acc1c9cec23ebc7acca6c60c4bafef03df794eeb46664fda660ccca7b0848b | True | 1 | NOT_MEASURED |
| latex-formula-extraction | 22f602f41614d2701c8810de1bdf05af430a103a4b4bfb57db1db18c1ea0800b | 1 | bd077c5439a30c6db53b50002ba3997c6a3e0aef45678addc0473561ba670469 | False | 0.8 | NOT_MEASURED |
| protein-expression-analysis | 98698e64e1e602e87750eaeecb9042a6bd395f966aa52ef6b061c3b2e336f6da | 0 | 7b54085bfa9f17943cc2ec3c0a1a77f99b0088503ac6e12947081514a2a9a165 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 76772c8df6ce71c9b374f28d19e75169889966a3e22371573afbdea8de6d0811 | 0 | 7e7648a704f4a32fa8e7aeed41c9c989f37f251bbc7aeda73cf758d95c5c3583 | False | 0 | NOT_MEASURED |
| quantum-numerical-simulation | a9ca0a981fed52850d19e34eebb1b12dfb856696a41ceb1b910797e6405e438a | 0 | 7e7648a704f4a32fa8e7aeed41c9c989f37f251bbc7aeda73cf758d95c5c3583 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | a9ca0a981fed52850d19e34eebb1b12dfb856696a41ceb1b910797e6405e438a | 1 | aa419b098fbfb5f9dd428c04bc8cd0360b097687876fd0f723afc7378d52c91a | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | a9ca0a981fed52850d19e34eebb1b12dfb856696a41ceb1b910797e6405e438a | 2 | eb9e2cb66cd00245007d65b542b4f8d877ee414fb62a869143e3ae5baa3c8518 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | a9ca0a981fed52850d19e34eebb1b12dfb856696a41ceb1b910797e6405e438a | 3 | 3237093a7d127268f238704357c1c4cc3b48cac931de8e05b4bdf716ea04e453 | True | 1 | NOT_MEASURED |
| sec-financial-report | bc21393688923235a6f300aa9e4fd4240a243d0be32b396c91b32702369a3aea | 0 | 55734636b12c389118edcda8ea32777cd2d99b5983a65cc79305603c06d9d1c3 | True | 1 | NOT_MEASURED |
| sec-financial-report | bc21393688923235a6f300aa9e4fd4240a243d0be32b396c91b32702369a3aea | 1 | 1715799f1410a4e688c200f2bd31dd174ab71c540321194fb6740c19662c5125 | True | 1 | NOT_MEASURED |
| setup-fuzzing-py | 20d6452f1e52c4ad6e970b378af9f432da27f203c88d2d8826e455f052fb05e6 | 0 | 6d2d8890b94c1c7cd5dff4ca958c6831185017bba8905b60fa6db83a3a2fe9e0 | False | 0.25 | NOT_MEASURED |
| shock-analysis-demand | 9e67d134a671f3bbcbe2c18093123920d3c54f94b9a29ccc9599a7c1271d8cc8 | 0 | 3e8068f7503dd2b6c9d7312594f7fd2fb9916aac2d8e9dbd5849e37432c7cc71 | True | 1 | NOT_MEASURED |
| shock-analysis-demand | 9e67d134a671f3bbcbe2c18093123920d3c54f94b9a29ccc9599a7c1271d8cc8 | 1 | cee64e2645027d90d480e115187f4c6042eb981b654e6034e6e5b08bda26d47b | True | 1 | NOT_MEASURED |
| software-dependency-audit | 204d9978c0d51e76e4868326ae003a35557809bcc6ec31bcce22eccdde72d260 | 0 | 413886f66ebf53dea034c3f295cad6086d8c48d2bd6cefda1f7db3c9c8291157 | False | 0.833333 | NOT_MEASURED |
| software-dependency-audit | cdf8fb06a60c65be258e79918026945a8c6e743bc829409d6e95b315fd74240f | 0 | 413886f66ebf53dea034c3f295cad6086d8c48d2bd6cefda1f7db3c9c8291157 | True | 1 | NOT_MEASURED |
| taxonomy-tree-merge | 101703073a020ea94c444e4c0222fe903c99986c03ecde5a9a8b33ca9b19ab23 | 0 | a1b4b1787a516d082647ed87c4d4e82459c371b3e8ef9cb7219c32c2ad5f9d2f | False | 0.9 | NOT_MEASURED |
| taxonomy-tree-merge | 9707245da5d3acc255d4473c4c66dd8343dd5f69dcc5fa282560914a8e6a6a8b | 0 | a1b4b1787a516d082647ed87c4d4e82459c371b3e8ef9cb7219c32c2ad5f9d2f | False | 0.8 | NOT_MEASURED |

## Adjacent content paired coverage

| Condition | From | To | Actual chains | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | NoSkill | S0 | 11 | 85 | 10 | 0.117647 | 0.3 | 10 | 0.21816 | 8 | 0.0941176 | 9.82143 |
| benign | S0 | S1 | 3 | 85 | 3 | 0.0352941 | -0.333333 | 3 | -0.324367 | 3 | 0.0352941 | -3.24675 |

S labels enumerate sealed content hashes, not revision attempts. Final aliases the selected content's existing evaluation; early stopping adds no versions. GT deltas require measured checks with matching unit, total and source. Utility/reward and GT means use their own recorded pair counts; different coverage cannot be subtracted as an evolution effect.

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | GT delta (pp) | GT delta reason | Final aliases S0 | Rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dynamic-object-aware-egomotion | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| glm-lake-mendota | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| lake-warming-attribution | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| latex-formula-extraction | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| protein-expression-analysis | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| quantum-numerical-simulation | benign | True | -1 | -1 | -14.2857 | MEASURED | False | False |
| sec-financial-report | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| setup-fuzzing-py | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| shock-analysis-demand | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| software-dependency-audit | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| taxonomy-tree-merge | benign | True | 0 | 0.0269 | 4.54545 | MEASURED | False | False |

## S0-to-Final paired coverage

| Condition | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Same content | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 85 | 11 | 0.129412 | -0.0909091 | 11 | -0.0884636 | 9 | 0.105882 | -1.08225 | 8 | 0 | 1 |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| dynamic-object-aware-egomotion | benign | 2 | 4511 | sufficient | e7278fb34b017159f692769dc67e70a88d7e80f91b3ec03883caa203b89ccc35 |
| glm-lake-mendota | benign | 2 | 785 | sufficient | fdc37c86ba135979dfe126004fb604723152da611f92417015816033a65e8f57 |
| lake-warming-attribution | benign | 4 | 1608 | budget_exhausted_incomplete | de8a0569a8cc24c62b8528425d4fd945e3f74476b1432ddfadcbc0fdcca26ec6 |
| latex-formula-extraction | benign | 2 | 3478 | sufficient | e1b68fed569a0b9125e75287cd21e6feb8f5ec888328adfee07b9a5fdd98cdd1 |
| protein-expression-analysis | benign | 10 | 11511 | sufficient | 2cd54013df657882ebe60f53e94857aff8344be96e4a9f4360bbfba43b59d1a4 |
| quantum-numerical-simulation | benign | 1 | 527 | sufficient | d5635be8cfad428a0e945e725bb8537b27d316769c98f3d26a1d7c57358cbfb6 |
| sec-financial-report | benign | 2 | 3364 | sufficient | 8d9ddc773741ba53b491e4e6f2634c3c8ff5b318962db6805ab5ff9091faa9d1 |
| setup-fuzzing-py | benign | 2 | 4222 | sufficient | b53461f40b45e018910854fb3e0975d4039d14dd0811a8ee905c5641ddd7466a |
| shock-analysis-demand | benign | 5 | 6252 | sufficient | 68aed9738ec945ccb3ebde7b028fd2090dec3d8e2455b1cd9b20bd287d925e72 |
| software-dependency-audit | benign | 1 | 303 | budget_exhausted_incomplete | 2b7735fe3c3708da772fcf3b6ac6c627a3ee278576591b5ec247e7c30fb5b1ce |
| taxonomy-tree-merge | benign | 2 | 3961 | sufficient | e966e2950e2baa656fe78084594bb68415e51f55993c0447420eaef466d3c4e1 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 144 | 2293194 | 286749 | 0 |
| generator | 350 | 18933701 | 578477 | 0 |
| verifier | 330 | 14787185 | 447561 | 0 |
| execution | 741 | 24560048 | 459042 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
