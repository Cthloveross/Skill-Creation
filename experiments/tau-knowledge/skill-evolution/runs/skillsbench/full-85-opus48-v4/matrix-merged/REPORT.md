# skillsbench run report

Protocol: `skillsbench.skill-evolution.v4`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Until all tasks are measured, fixed-denominator rates report observed successes; they are not complete matrix results.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility | Task pass rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| benign | no_skill | 85 | 0 | 78 | 0.371795 | 0.341176 | 0.341176 |
| benign | initial | 85 | 70 | 69 | 0.42029 | 0.341176 | 0.341176 |
| benign | evolved | 85 | 70 | 69 | 0.434783 | 0.352941 | 0.352941 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 70 | 69 | 0.42029 | {'oracle_success': 15, 'test_escalation_failed': 16, 'verifier_initialization_failed': 12, 'verification_failed': 2, 'test_escalation_result_unknown': 2, 'verification_program_error_exhausted': 2, 'verifier_initialization_result_unknown': 1, 'learning_environment_close_failed': 1, 'oracle_result_unknown': 3, 'initial_execution_result_unknown': 1, 'revision_timeout': 2} |
| benign | 1 | 13 | 13 | 0.461538 | {'test_escalation_failed': 3, 'oracle_success': 4, 'oracle_result_unknown': 1} |
| benign | 2 | 5 | 5 | 0.6 | {'oracle_success': 2, 'generator_context_budget_exhausted': 1} |
| benign | 3 | 2 | 2 | 0.5 | {'generator_context_budget_exhausted': 1} |
| benign | 4 | 1 | 1 | 0 | {'generator_context_budget_exhausted': 1} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Learning executions | Terminal calls | Submissions | Final hash |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | oracle_success | 1 | 0 | 1 | 1 | 12 | 1 | aa59d524d512d5f58bdb7aa8bf7e7d650c037c48f48da90c58287c0fe636ee7d |
| adaptive-cruise-control | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | benign | test_escalation_failed | 2 | 1 | 1 | 1 | 31 | 2 | d6ff5bd213ccf2c923228062199e883fcdc5f0f7fec003c29a8773188a8f29d1 |
| citation-check | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 16 | 1 | 6c7dbcaa38a84ea74fed485b9fa22e3aa51e98bf481c3a2196df2c812054083f |
| civ6-adjacency-optimizer | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| court-form-filling | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 30 | 1 | 153a30c70da53af83b0d4ba657d6f58772c616a54dd2714dacd15b4954eb7844 |
| crystallographic-wyckoff-position-analysis | benign | oracle_success | 1 | 0 | 1 | 1 | 27 | 1 | 151f18c9c203e2ffbbdaa1eaacd83ea97bf9b43a2de0e120ffe8b3543e0cdce8 |
| dapt-intrusion-detection | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 28 | 1 | 917ea892ee3de8b0f0557c64b6394de658e54aecda39826502d04c96a841d5cb |
| data-to-d3 | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 36 | 1 | dd07c42a4a605a4e296bc4dd96716dc6ed640a7844195d06f197b87e3c3e7060 |
| dialogue-parser | benign | oracle_success | 3 | 2 | 1 | 1 | 69 | 3 | 9cd61c23ef5c4a3fe792825a399da7d2b88bed95869588d488fb998d4dc46b36 |
| dynamic-object-aware-egomotion | benign | verification_failed | 1 | 0 | 1 | 1 | 28 | 1 | c690669b425bc3f98521af86c4877b376bad9e45a6f7ec7912e566196a3dc771 |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | oracle_success | 1 | 0 | 1 | 1 | 15 | 1 | 1c8589432863482517322d0d2633f021235155b04021a3dd63342dfdd6d56129 |
| econ-detrending-correlation | benign | oracle_success | 2 | 1 | 1 | 1 | 25 | 2 | aa5c741c2328f6caa29c610aa7e5a30b245a608103d26e5a4490ec8234c4e0df |
| energy-ac-optimal-power-flow | benign | oracle_success | 1 | 0 | 1 | 1 | 30 | 1 | 5388baba47e43b39f04f05539ce22978f27d101500257f67ddbae6aa31cab148 |
| energy-market-pricing | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 40 | 1 | 485a71381250cf49519440367429e6d9b17246d312c31a70493b7de639e0e460 |
| enterprise-information-search | benign | generator_context_budget_exhausted | 5 | 5 | 2 | 1 | 122 | 5 | c3ce48de70ca6b6ac65958c89e8710a312e59d76c11619760232a978f4410646 |
| exceltable-in-ppt | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 36 | 1 | 749b8f218951f3d19b528bc5275ae4b933b4d319c8137423616fa32b4729a3e2 |
| exoplanet-detection-period | benign | generator_context_budget_exhausted | 3 | 3 | 0 | 1 | 95 | 3 | 4a6656c60b876f414d7d3ea81471d19a57766abcd6611a23ad883f1ca116f879 |
| financial-modeling-qa | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 42 | 1 | d5e1ae1ad569d7704603e180a7ccae5c5b5b259742a67d9d3170d53103b42759 |
| find-topk-similiar-chemicals | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 29 | 1 | 64264c7d2521d33e2446f6391c0a3cf0da34218c88532a1be39cd46f24d8b936 |
| fix-build-agentops | benign | test_escalation_result_unknown | 1 | 0 | 1 | 1 | 75 | 1 | f67b21d051071a18e7fc6f1aa8b820703262f43fabe73bbf708caf17be549f4a |
| fix-build-google-auto | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 56 | 1 | 037e76f2e5c18afeae52ce87da8b5d056f6ee1ee319ef9dc52e7f309fca6c7bd |
| fix-druid-loophole-cve | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 22 | 1 | 5fa01fb272ac143d0256e42ad9da855968fb57f76e99bc64b354bb99d1261956 |
| fix-erlang-ssh-cve | benign | oracle_success | 1 | 0 | 1 | 1 | 38 | 1 | a6b32e426c7ee37731c67836f781b05ae565345404a8fc5837155c4c22e102ce |
| fix-visual-stability | benign | verification_program_error_exhausted | 1 | 0 | 0 | 1 | 43 | 1 | 58c4f6e450f0a575681c2fe04000cb97a582a67271c5411f9a14c7f0af15eabf |
| flink-query | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 56 | 1 | 98af280ccc5e16f30ab76aafcf25fa211371db536d9a5404647e807345020308 |
| flood-risk-analysis | benign | oracle_success | 1 | 0 | 1 | 1 | 21 | 1 | f5b7a80242dd81597061c33da6b02e52065ec9c2ef9af06863c08c9972e6a8e9 |
| gh-repo-analytics | benign | oracle_success | 1 | 0 | 1 | 1 | 15 | 1 | 1f9f20d4b305bbd1a890550c75e637257da94d1b478c863e5bdce898bdf0a0d3 |
| glm-lake-mendota | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | 1 | 20 | 1 | 72e1d1bdf368f724abce0932097a6061b9bdbd485013749d25a233c008dbb560 |
| gravitational-wave-detection | benign | oracle_success | 1 | 0 | 1 | 1 | 37 | 1 | daaaf1631af138904c287b5e9a2921da658432953042d56c2ff9961f2c3d7c3f |
| grid-dispatch-operator | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| hvac-control | benign | learning_environment_close_failed | 1 | 0 | 1 | 1 | 20 | 1 | 5236b4af2a4c234a3f5ab461aa4d86bbc2108ad06c539a2a9195cf9c9e286349 |
| invoice-fraud-detection | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 38 | 1 | 46f0d100f623e6369bdbd3ac01faa9993394023ecd1f28923d5d16e5598246f0 |
| jax-computing-basics | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 27 | 1 | f3cbea9e58a17119691fa7f177f91c7022b099a8df54b8c25e311bf19da5ce8c |
| jpg-ocr-stat | benign | test_escalation_failed | 1 | 0 | 4 | 1 | 43 | 1 | 45c03f62e53f8f7f1877316c82a0b091171bc7da37d786251246e6a83b097b87 |
| lab-unit-harmonization | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 20 | 1 | a437fd0b0dd7d7b1e9a59ffd03182400df1ea751c5845c92b27b9be01a9d6ca4 |
| lake-warming-attribution | benign | oracle_result_unknown | 2 | 1 | 2 | 1 | 42 | 2 | 282730c5f92218dd1d5d1b0ae99b6a6fd77f44a8575ea1842a99a5b8ef2c4059 |
| latex-formula-extraction | benign | oracle_result_unknown | 1 | 0 | 2 | 1 | 73 | 1 | d4edaa407f72c7b6ff3b91c2a26d5a857d6343841e1f37f8af49a972e0a7cddc |
| lean4-proof | benign | oracle_success | 1 | 0 | 1 | 1 | 29 | 1 | 493d06218ecaa35cf88b5c9d9bbf9a73881b14c2660a51149efd767a7e4b8d9f |
| manufacturing-codebook-normalization | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-equipment-maintenance | benign | verification_program_error_exhausted | 1 | 0 | 1 | 1 | 61 | 1 | c9525c72e471517e8c39ac95e29b9aab35f064a3085e3c391556fac2c7d5d0c6 |
| manufacturing-fjsp-optimization | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 26 | 1 | 84a706efbe401905f016b0b03c25e26425c4903157566a07ddd8b2d7d0a63bb7 |
| mario-coin-counting | benign | test_escalation_failed | 1 | 0 | 4 | 1 | 51 | 1 | c1b2f75a0327f4023dbbefdae9168bfb044fca56d33549489e5d41f6bffc8b9b |
| mars-clouds-clustering | benign | oracle_success | 1 | 0 | 1 | 1 | 11 | 1 | 26257072884366d5ff03076a946f09f68627e84180b7e38c3ed84daac9fb4e4e |
| multilingual-video-dubbing | benign | oracle_success | 1 | 0 | 1 | 1 | 40 | 1 | 32abda5fe70b504f112336ffd731f51a7d884aee2ff87a80a64b44963072c43b |
| offer-letter-generator | benign | oracle_success | 1 | 0 | 1 | 1 | 16 | 1 | 714b819977d60206d1890700459f1f6ffd6c3ac69aecd9024c9b4ee68525837b |
| organize-messy-files | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 48 | 1 | f85d3ef91dbd7f098c4895e02deb66e8022bbb8fb24b32bbdb41d3d0d4fd6aa7 |
| paper-anonymizer | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 52 | 1 | d716c31d0bc7dcd7584a372c5ec5b40d5155b2b2f47b4a15078834629d8b1839 |
| parallel-tfidf-search | benign | oracle_success | 2 | 1 | 1 | 1 | 36 | 2 | 3f89d9e7438b55859ef8664a5acd1b8cb83b65db0697cf050c382a628a099a2c |
| pddl-tpp-planning | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| pdf-excel-diff | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 17 | 1 | 54c5808da74b81f3afefba508c286532750c4cc6f8a705bdcd0b609ca2884308 |
| pedestrian-traffic-counting | benign | test_escalation_failed | 1 | 0 | 2 | 1 | 46 | 1 | 24a21d3a7e037cb1bbe9bba6abcfa0a1b5f625dbffefa352968224d5b5c736d0 |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | oracle_success | 2 | 1 | 1 | 1 | 69 | 2 | ab0468cbbfaf4efc47148f933df29b7372c2a0e8740e3fa7089dc0137dd2a28b |
| pptx-reference-formatting | benign | test_escalation_failed | 2 | 1 | 1 | 1 | 56 | 2 | 12af255d19ce3e9e446e3f4a4638ac51d470e867f140a8d9f62ab2534882899b |
| protein-expression-analysis | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| python-scala-translation | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 34 | 1 | 4b454c1673329bd6a40f8359ab8e36c79e510a58264354ffd79762becb4fbcf1 |
| quantum-numerical-simulation | benign | oracle_success | 3 | 2 | 5 | 1 | 155 | 3 | 89354ed2f71dac036d96a9d125497f86fc1a6311af6b341c61068e75f0db1d74 |
| r2r-mpc-control | benign | verification_failed | 1 | 0 | 0 | 1 | 31 | 1 | 97275345bdafa6194ff449cad656ac6ada67b23531baf5272e73cb4b8f2efff4 |
| react-performance-debugging | benign | test_escalation_result_unknown | 1 | 0 | 1 | 1 | 58 | 1 | de8cf4de6a0d836bd5cfce9f5d2371eff80d39aa06ad071e4dcc3eff8e1e68dd |
| reserves-at-risk-calc | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 56 | 1 | ba8e40a3df1ea22ef7be52f9b981f9d5a62c4c2d68842ae90dd12f4f01ab2a2b |
| sales-pivot-analysis | benign | oracle_success | 1 | 0 | 1 | 1 | 24 | 1 | ed471553f868b099de5724288a7aaf54daf8c466ef943923ab494b3298607f48 |
| sec-financial-report | benign | oracle_result_unknown | 1 | 0 | 0 | 1 | 29 | 1 | feb0978bb1b02b3a947fca395d8b45e0af8ab7686f849ad283fee517b9738e13 |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | initial_execution_result_unknown | 1 | 0 | 0 | 1 | 17 | 0 | 8dce736352ee29532723daf2fa582d55830a5566470a57cbab502603f3601cba |
| shock-analysis-demand | benign | oracle_result_unknown | 1 | 0 | 2 | 1 | 105 | 1 | cfa540b513704baefe44012b83b3b45adab767be00cf2b35e44e7fede5e2043c |
| shock-analysis-supply | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 54 | 1 | 0cbd90830e903353aeed3c62eed0e195ac378750292de2c0dcbbddcccccc5996 |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | model service returned HTTP 529 | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| speaker-diarization-subtitles | benign | revision_timeout | 1 | 0 | 0 | 1 | 71 | 0 | 1648c6c682b7e38df9cbf3b5ab5491602dbec5912be78e155f86b73b7cc747b9 |
| spring-boot-jakarta-migration | benign | oracle_success | 1 | 0 | 1 | 1 | 34 | 1 | beb7e1eed4d839c1f1c95711e7f31659dfb22cb197a996e6fefbb41a30461a56 |
| suricata-custom-exfil | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 44 | 1 | 27ec33701d2af6f40d01ded1de9e39484e2053cfc35378ecf2c2c307b13ad79d |
| syzkaller-ppdev-syzlang | benign | test_escalation_failed | 2 | 1 | 1 | 1 | 77 | 2 | 9bb989984935f7b4c382d32a01ea191124cddf8af564df917f7029b6710d48ed |
| taxonomy-tree-merge | benign | generation_result_unknown | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| threejs-structure-parser | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 29 | 1 | ee347963c185e87019ea6404a12b15a162d935c0ec2b5a1a5c3c836c81a73104 |
| trend-anomaly-causal-inference | benign | generator_context_budget_exhausted | 4 | 4 | 0 | 1 | 81 | 4 | 2c8da9450134aeffa1c9fa2b747bd835d02c4b0a057ee5954254dda9c957f75f |
| video-filler-word-remover | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| video-silence-remover | benign | test_escalation_failed | 1 | 0 | 2 | 1 | 30 | 1 | e6c32d11f5a2b089db1c7fccb84525652e0711c675fd610c8c330936fb587c61 |
| video-tutorial-indexer | benign | revision_timeout | 1 | 0 | 0 | 1 | 111 | 0 | fe40643c7b764015fe274efcc052325c93183d64b2ab0c7be9e30aedb87627eb |
| virtualhome-agent-planning | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 29 | 1 | c3b645b56034fb4761ac44bf5e17a8366f76a804e5fa534f3d0066178cc20fbc |
| weighted-gdp-calc | benign | oracle_success | 2 | 1 | 1 | 1 | 48 | 2 | dac71bc2819481e336e2770453b596169d81af336a2144c15459ca462853abd4 |
| xlsx-recover-data | benign | oracle_success | 1 | 0 | 1 | 1 | 21 | 1 | e38a228ba5614b6557fed64bfa1274bf9bfdc7a941a70dc86394e5c1e12deb4c |

No-Skill runs use no package and do not create S0. Baseline comparisons require the same sealed executor identity; evaluations do not enter learning.

## No-Skill independent measurements

| Task | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| adaptive-cruise-control | MEASURED | True | 1 | 12 | 12 | 1 | reporter_group |
| azure-bgp-oscillation-route-leak | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| citation-check | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group |
| civ6-adjacency-optimizer | MEASURED | False | 0 | 9 | 10 | 0.9 | reporter_group |
| court-form-filling | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group |
| crystallographic-wyckoff-position-analysis | MEASURED | False | 0.55 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | MEASURED | False | 0 | 10 | 14 | 0.714286 | reporter_group |
| data-to-d3 | MEASURED | False | 0 | 14 | 15 | 0.933333 | reporter_group |
| dialogue-parser | MEASURED | False | 0.667 | 4 | 6 | 0.666667 | reporter_group |
| dynamic-object-aware-egomotion | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| earthquake-plate-calculation | MEASURED | False | 0 | 7 | 8 | 0.875 | reporter_group |
| econ-detrending-correlation | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| energy-ac-optimal-power-flow | MEASURED | True | 1 | 23 | 24 | 0.958333 | reporter_group |
| energy-market-pricing | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| enterprise-information-search | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group |
| exceltable-in-ppt | MEASURED | False | 0 | 6 | 8 | 0.75 | reporter_group |
| exoplanet-detection-period | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| financial-modeling-qa | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| find-topk-similiar-chemicals | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-build-agentops | MEASURED | False | 0 | 0 | 3 | 0 | reporter_group |
| fix-build-google-auto | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group |
| fix-druid-loophole-cve | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| fix-erlang-ssh-cve | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group |
| fix-visual-stability | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group |
| flink-query | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group |
| flood-risk-analysis | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| gh-repo-analytics | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |
| glm-lake-mendota | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| gravitational-wave-detection | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group |
| grid-dispatch-operator | MEASURED | False | 0 | 4 | 6 | 0.666667 | reporter_group |
| hvac-control | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group |
| invoice-fraud-detection | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| jax-computing-basics | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group |
| jpg-ocr-stat | MEASURED | False | 0 | 0 | 1 | 0 | reporter_group |
| lab-unit-harmonization | MEASURED | False | 0 | 0 | 48 | 0 | reporter_group |
| lake-warming-attribution | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group |
| latex-formula-extraction | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| lean4-proof | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| manufacturing-codebook-normalization | MEASURED | False | 0 | 15 | 16 | 0.9375 | reporter_group |
| manufacturing-equipment-maintenance | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| manufacturing-fjsp-optimization | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group |
| mario-coin-counting | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group |
| mars-clouds-clustering | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |
| multilingual-video-dubbing | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |
| offer-letter-generator | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| organize-messy-files | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group |
| paper-anonymizer | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group |
| parallel-tfidf-search | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group |
| pddl-tpp-planning | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| pdf-excel-diff | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group |
| pedestrian-traffic-counting | MEASURED | False | 0 | 0 | 1 | 0 | reporter_group |
| powerlifting-coef-calc | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group |
| pptx-reference-formatting | MEASURED | True | 1 | 12 | 12 | 1 | reporter_group |
| protein-expression-analysis | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| quantum-numerical-simulation | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| r2r-mpc-control | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group |
| react-performance-debugging | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| reserves-at-risk-calc | MEASURED | False | 0 | 3 | 5 | 0.6 | reporter_group |
| sales-pivot-analysis | MEASURED | False | 0 | 5 | 10 | 0.5 | reporter_group |
| sec-financial-report | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| setup-fuzzing-py | MEASURED | False | 0.83 | 2 | 2 | 1 | reporter_group |
| shock-analysis-demand | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| shock-analysis-supply | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group |
| software-dependency-audit | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| speaker-diarization-subtitles | MEASURED | False | 0 | 6 | 10 | 0.6 | reporter_group |
| spring-boot-jakarta-migration | MEASURED | True | 1 | 10 | 10 | 1 | reporter_group |
| suricata-custom-exfil | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| syzkaller-ppdev-syzlang | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| taxonomy-tree-merge | MEASURED | False | 0.8115 | 18 | 22 | 0.818182 | reporter_group |
| threejs-structure-parser | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group |
| threejs-to-obj | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group |
| travel-planning | MEASURED | False | 0 | 8 | 10 | 0.8 | reporter_group |
| trend-anomaly-causal-inference | MEASURED | False | 0.95 | 14 | 15 | 0.933333 | reporter_group |
| video-filler-word-remover | MEASURED | False | 0 | 1 | 5 | 0.2 | reporter_group |
| video-silence-remover | MEASURED | False | 0 | 6 | 9 | 0.666667 | reporter_group |
| video-tutorial-indexer | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group |
| virtualhome-agent-planning | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| weighted-gdp-calc | MEASURED | False | 0 | 16 | 27 | 0.592593 | reporter_group |
| xlsx-recover-data | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |

## No-Skill paired comparisons

| Condition | Endpoint | Paired | Denominator | Utility delta | Paired coverage | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | initial | 66 | 85 | 0.030303 | 0.776471 | 0.0183604 | 60 | 0.705882 | 2.22366 | 8 | 6 |
| benign | evolved | 66 | 85 | 0.0454545 | 0.776471 | 0.019118 | 60 | 0.705882 | 2.57286 | 9 | 6 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit | Previous | Utility delta | Reward delta | GT delta (pp) | GT delta reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 0 | S0 / final | aa59d524d512d5f58bdb7aa8bf7e7d650c037c48f48da90c58287c0fe636ee7d | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| azure-bgp-oscillation-route-leak | 0 | S0 | dc6c04a7cec666154cb4315df72eaddc731438faa90f1b0d43cb3d6596e053f5 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| azure-bgp-oscillation-route-leak | 1 | S1 / final | d6ff5bd213ccf2c923228062199e883fcdc5f0f7fec003c29a8773188a8f29d1 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| citation-check | 0 | S0 / final | 6c7dbcaa38a84ea74fed485b9fa22e3aa51e98bf481c3a2196df2c812054083f | MEASURED | False | 0 | 7 | 9 | 0.777778 | reporter_group | NoSkill | -1 | -1 | -22.2222 | MEASURED |
| court-form-filling | 0 | S0 / final | 153a30c70da53af83b0d4ba657d6f58772c616a54dd2714dacd15b4954eb7844 | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | NoSkill | -1 | -1 | -20 | MEASURED |
| crystallographic-wyckoff-position-analysis | 0 | S0 / final | 151f18c9c203e2ffbbdaa1eaacd83ea97bf9b43a2de0e120ffe8b3543e0cdce8 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 1 | 0.45 | NOT_MEASURED | official_checks_not_measured |
| dapt-intrusion-detection | 0 | S0 / final | 917ea892ee3de8b0f0557c64b6394de658e54aecda39826502d04c96a841d5cb | MEASURED | False | 0 | 13 | 14 | 0.928571 | reporter_group | NoSkill | 0 | 0 | 21.4286 | MEASURED |
| data-to-d3 | 0 | S0 / final | dd07c42a4a605a4e296bc4dd96716dc6ed640a7844195d06f197b87e3c3e7060 | MEASURED | True | 1 | 15 | 15 | 1 | reporter_group | NoSkill | 1 | 1 | 6.66667 | MEASURED |
| dialogue-parser | 0 | S0 | 6f4dbff58a1d75d48d80ff45cace44aa82be179905e99d9c85c3e308b22d4ed1 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | NoSkill | 1 | 0.333 | 33.3333 | MEASURED |
| dialogue-parser | 1 | S1 | c5d8ea63a586b5849260dd06d85bd2646134e83a448e573e1aeba78819e2b3a1 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| dialogue-parser | 2 | S2 / final | 9cd61c23ef5c4a3fe792825a399da7d2b88bed95869588d488fb998d4dc46b36 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| dynamic-object-aware-egomotion | 0 | S0 / final | c690669b425bc3f98521af86c4877b376bad9e45a6f7ec7912e566196a3dc771 | MEASURED | False | 0 | 9 | 11 | 0.818182 | reporter_group | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| earthquake-plate-calculation | 0 | S0 / final | 1c8589432863482517322d0d2633f021235155b04021a3dd63342dfdd6d56129 | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 1 | 1 | 12.5 | MEASURED |
| econ-detrending-correlation | 0 | S0 | f046e7631444fe1e2f34a880688118582bdf11a9435dab49bdbef41283b15aa3 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| econ-detrending-correlation | 1 | S1 / final | aa5c741c2328f6caa29c610aa7e5a30b245a608103d26e5a4490ec8234c4e0df | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| energy-ac-optimal-power-flow | 0 | S0 / final | 5388baba47e43b39f04f05539ce22978f27d101500257f67ddbae6aa31cab148 | MEASURED | True | 1 | 23 | 24 | 0.958333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| energy-market-pricing | 0 | S0 / final | 485a71381250cf49519440367429e6d9b17246d312c31a70493b7de639e0e460 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| enterprise-information-search | 0 | S0 | 54214a9ac4047dc73b0739ac699f80594149cf92d1b0e135041773c171ab9396 | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| enterprise-information-search | 1 | S1 | e93e6707986f9a66229964ae21ed08d6d5757b7b58da79f70192a71de0b5063b | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| enterprise-information-search | 2 | S2 | ddf2aed4ef1d2ecddb0d61b9a5b60fa8135916174cc934c00a60ff691d3029bc | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| enterprise-information-search | 3 | S3 | a1f238a47550b1960cc9db37f75c96cf9fa94b820334148a4df0fda27a5c9403 | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | S2 | 0 | 0 | 0 | MEASURED |
| enterprise-information-search | 4 | S4 / final | c3ce48de70ca6b6ac65958c89e8710a312e59d76c11619760232a978f4410646 | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| exceltable-in-ppt | 0 | S0 / final | 749b8f218951f3d19b528bc5275ae4b933b4d319c8137423616fa32b4729a3e2 | MEASURED | False | 0 | 6 | 8 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| exoplanet-detection-period | 0 | S0 | 29827f8c6e2808744e31cbdc68c38d17d9c9fb6367881499b06297c2a36837f2 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| exoplanet-detection-period | 1 | S1 | ae70317d1f6cc044f45c9a3cbd9fd54273bf376e251501ed40763b660fd042d7 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| exoplanet-detection-period | 2 | S2 / final | 4a6656c60b876f414d7d3ea81471d19a57766abcd6611a23ad883f1ca116f879 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| financial-modeling-qa | 0 | S0 / final | d5e1ae1ad569d7704603e180a7ccae5c5b5b259742a67d9d3170d53103b42759 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| find-topk-similiar-chemicals | 0 | S0 / final | 64264c7d2521d33e2446f6391c0a3cf0da34218c88532a1be39cd46f24d8b936 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| fix-build-agentops | 0 | S0 / final | f67b21d051071a18e7fc6f1aa8b820703262f43fabe73bbf708caf17be549f4a | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | NoSkill | 0 | 0 | 33.3333 | MEASURED |
| fix-build-google-auto | 0 | S0 / final | 037e76f2e5c18afeae52ce87da8b5d056f6ee1ee319ef9dc52e7f309fca6c7bd | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| fix-druid-loophole-cve | 0 | S0 / final | 5fa01fb272ac143d0256e42ad9da855968fb57f76e99bc64b354bb99d1261956 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| fix-erlang-ssh-cve | 0 | S0 / final | a6b32e426c7ee37731c67836f781b05ae565345404a8fc5837155c4c22e102ce | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| fix-visual-stability | 0 | S0 / final | 58c4f6e450f0a575681c2fe04000cb97a582a67271c5411f9a14c7f0af15eabf | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| flink-query | 0 | S0 / final | 98af280ccc5e16f30ab76aafcf25fa211371db536d9a5404647e807345020308 | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| flood-risk-analysis | 0 | S0 / final | f5b7a80242dd81597061c33da6b02e52065ec9c2ef9af06863c08c9972e6a8e9 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | NoSkill | 1 | 1 | 50 | MEASURED |
| gh-repo-analytics | 0 | S0 / final | 1f9f20d4b305bbd1a890550c75e637257da94d1b478c863e5bdce898bdf0a0d3 | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| glm-lake-mendota | 0 | S0 / final | 72e1d1bdf368f724abce0932097a6061b9bdbd485013749d25a233c008dbb560 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| gravitational-wave-detection | 0 | S0 / final | daaaf1631af138904c287b5e9a2921da658432953042d56c2ff9961f2c3d7c3f | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| hvac-control | 0 | S0 / final | 5236b4af2a4c234a3f5ab461aa4d86bbc2108ad06c539a2a9195cf9c9e286349 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| invoice-fraud-detection | 0 | S0 / final | 46f0d100f623e6369bdbd3ac01faa9993394023ecd1f28923d5d16e5598246f0 | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | -1 | -1 | -50 | MEASURED |
| jax-computing-basics | 0 | S0 / final | f3cbea9e58a17119691fa7f177f91c7022b099a8df54b8c25e311bf19da5ce8c | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| jpg-ocr-stat | 0 | S0 / final | 45c03f62e53f8f7f1877316c82a0b091171bc7da37d786251246e6a83b097b87 | MEASURED | False | 0 | 0 | 1 | 0 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| lab-unit-harmonization | 0 | S0 / final | a437fd0b0dd7d7b1e9a59ffd03182400df1ea751c5845c92b27b9be01a9d6ca4 | MEASURED | False | 0.354 | 17 | 48 | 0.354167 | reporter_group | NoSkill | 0 | 0.354 | 35.4167 | MEASURED |
| lake-warming-attribution | 0 | S0 | 35afcbd7c86d1d6051c780e1bc4035e491d1d63687d6d95951a9b7037798ea83 | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| lake-warming-attribution | 1 | S1 / final | 282730c5f92218dd1d5d1b0ae99b6a6fd77f44a8575ea1842a99a5b8ef2c4059 | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| latex-formula-extraction | 0 | S0 / final | d4edaa407f72c7b6ff3b91c2a26d5a857d6343841e1f37f8af49a972e0a7cddc | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| lean4-proof | 0 | S0 / final | 493d06218ecaa35cf88b5c9d9bbf9a73881b14c2660a51149efd767a7e4b8d9f | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| manufacturing-equipment-maintenance | 0 | S0 / final | c9525c72e471517e8c39ac95e29b9aab35f064a3085e3c391556fac2c7d5d0c6 | MEASURED | False | 0 | 6 | 7 | 0.857143 | reporter_group | NoSkill | 0 | 0 | 14.2857 | MEASURED |
| manufacturing-fjsp-optimization | 0 | S0 / final | 84a706efbe401905f016b0b03c25e26425c4903157566a07ddd8b2d7d0a63bb7 | MEASURED | False | 0 | 14 | 15 | 0.933333 | reporter_group | NoSkill | 0 | 0 | 6.66667 | MEASURED |
| mario-coin-counting | 0 | S0 / final | c1b2f75a0327f4023dbbefdae9168bfb044fca56d33549489e5d41f6bffc8b9b | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| mars-clouds-clustering | 0 | S0 / final | 26257072884366d5ff03076a946f09f68627e84180b7e38c3ed84daac9fb4e4e | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| multilingual-video-dubbing | 0 | S0 / final | 32abda5fe70b504f112336ffd731f51a7d884aee2ff87a80a64b44963072c43b | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| offer-letter-generator | 0 | S0 / final | 714b819977d60206d1890700459f1f6ffd6c3ac69aecd9024c9b4ee68525837b | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 1 | 1 | 25 | MEASURED |
| organize-messy-files | 0 | S0 / final | f85d3ef91dbd7f098c4895e02deb66e8022bbb8fb24b32bbdb41d3d0d4fd6aa7 | MEASURED | False | 0 | 4 | 6 | 0.666667 | reporter_group | NoSkill | -1 | -1 | -33.3333 | MEASURED |
| paper-anonymizer | 0 | S0 / final | d716c31d0bc7dcd7584a372c5ec5b40d5155b2b2f47b4a15078834629d8b1839 | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group | NoSkill | -1 | -1 | -16.6667 | MEASURED |
| parallel-tfidf-search | 0 | S0 | c05d1c2de20e40a81cd43d7c9ad4ef5ec3fa928e328d8439d30fa9fb9ca5254c | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| parallel-tfidf-search | 1 | S1 / final | 3f89d9e7438b55859ef8664a5acd1b8cb83b65db0697cf050c382a628a099a2c | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| pdf-excel-diff | 0 | S0 / final | 54c5808da74b81f3afefba508c286532750c4cc6f8a705bdcd0b609ca2884308 | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| pedestrian-traffic-counting | 0 | S0 / final | 24a21d3a7e037cb1bbe9bba6abcfa0a1b5f625dbffefa352968224d5b5c736d0 | MEASURED | False | 0.074786 | 0 | 1 | 0 | reporter_group | NoSkill | 0 | 0.074786 | 0 | MEASURED |
| powerlifting-coef-calc | 0 | S0 | eaa3720eccd4043f74d32c8252480b3b408ecd35120f2e45b8711a65ccf4b1dd | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| powerlifting-coef-calc | 1 | S1 / final | ab0468cbbfaf4efc47148f933df29b7372c2a0e8740e3fa7089dc0137dd2a28b | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| pptx-reference-formatting | 0 | S0 | 9cc9039910c744ef2baaad8036dfd14c9f4e4dee41e369ea66fe42e34f8bae0f | MEASURED | False | 0 | 11 | 12 | 0.916667 | reporter_group | NoSkill | -1 | -1 | -8.33333 | MEASURED |
| pptx-reference-formatting | 1 | S1 / final | 12af255d19ce3e9e446e3f4a4638ac51d470e867f140a8d9f62ab2534882899b | MEASURED | False | 0 | 11 | 12 | 0.916667 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| python-scala-translation | 0 | S0 / final | 4b454c1673329bd6a40f8359ab8e36c79e510a58264354ffd79762becb4fbcf1 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| quantum-numerical-simulation | 0 | S0 | ea1e11dd9c2149ffc704758d8e6c786572ba6cf49dc24c24894b99f6c0c5c4d7 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| quantum-numerical-simulation | 1 | S1 | 8f872bd76f0c1f2b4e8a9280f1a1245dcc07fd7169f527500a208d1af45b69bf | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | S0 | -1 | -1 | -28.5714 | MEASURED |
| quantum-numerical-simulation | 2 | S2 / final | 89354ed2f71dac036d96a9d125497f86fc1a6311af6b341c61068e75f0db1d74 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | S1 | 1 | 1 | 28.5714 | MEASURED |
| r2r-mpc-control | 0 | S0 / final | 97275345bdafa6194ff449cad656ac6ada67b23531baf5272e73cb4b8f2efff4 | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| react-performance-debugging | 0 | S0 / final | de8cf4de6a0d836bd5cfce9f5d2371eff80d39aa06ad071e4dcc3eff8e1e68dd | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| reserves-at-risk-calc | 0 | S0 / final | ba8e40a3df1ea22ef7be52f9b981f9d5a62c4c2d68842ae90dd12f4f01ab2a2b | MEASURED | False | 0 | 0 | 5 | 0 | reporter_group | NoSkill | 0 | 0 | -60 | MEASURED |
| sales-pivot-analysis | 0 | S0 / final | ed471553f868b099de5724288a7aaf54daf8c466ef943923ab494b3298607f48 | MEASURED | True | 1 | 9 | 10 | 0.9 | reporter_group | NoSkill | 1 | 1 | 40 | MEASURED |
| sec-financial-report | 0 | S0 / final | feb0978bb1b02b3a947fca395d8b45e0af8ab7686f849ad283fee517b9738e13 | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| setup-fuzzing-py | 0 | S0 / final | 8dce736352ee29532723daf2fa582d55830a5566470a57cbab502603f3601cba | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| shock-analysis-demand | 0 | S0 / final | cfa540b513704baefe44012b83b3b45adab767be00cf2b35e44e7fede5e2043c | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| shock-analysis-supply | 0 | S0 / final | 0cbd90830e903353aeed3c62eed0e195ac378750292de2c0dcbbddcccccc5996 | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| speaker-diarization-subtitles | 0 | S0 / final | 1648c6c682b7e38df9cbf3b5ab5491602dbec5912be78e155f86b73b7cc747b9 | MEASURED | False | 0 | 6 | 10 | 0.6 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| spring-boot-jakarta-migration | 0 | S0 / final | beb7e1eed4d839c1f1c95711e7f31659dfb22cb197a996e6fefbb41a30461a56 | MEASURED | True | 1 | 10 | 10 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| suricata-custom-exfil | 0 | S0 / final | 27ec33701d2af6f40d01ded1de9e39484e2053cfc35378ecf2c2c307b13ad79d | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| syzkaller-ppdev-syzlang | 0 | S0 | 418091e79a22e50541e8b447fc35fafdabad96301f83f106cbb67229f8f59391 | MEASURED | False | 0 | 4 | 7 | 0.571429 | reporter_group | NoSkill | 0 | 0 | -14.2857 | MEASURED |
| syzkaller-ppdev-syzlang | 1 | S1 / final | 9bb989984935f7b4c382d32a01ea191124cddf8af564df917f7029b6710d48ed | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | S0 | 0 | 0 | 14.2857 | MEASURED |
| travel-planning | 0 | S0 / final | ee347963c185e87019ea6404a12b15a162d935c0ec2b5a1a5c3c836c81a73104 | MEASURED | False | 0 | 8 | 10 | 0.8 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| trend-anomaly-causal-inference | 0 | S0 | 0b639bf8ad4b4050ef61d6246f44e81fff6842432b7bb23ef952467549b4c17f | MEASURED | False | 0.95 | 14 | 15 | 0.933333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| trend-anomaly-causal-inference | 1 | S1 | 9bce43d450d4ea74e95a3278e42a7409bff70e46c6718bafdf7bd7d4aa73ed54 | MEASURED | False | 0.95 | 14 | 15 | 0.933333 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| trend-anomaly-causal-inference | 2 | S2 | d3cb205735602b13bb9f5646be3d5719e3a4affebada545567e2a1c21e96ff80 | MEASURED | False | 0.95 | 14 | 15 | 0.933333 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| trend-anomaly-causal-inference | 3 | S3 / final | 2c8da9450134aeffa1c9fa2b747bd835d02c4b0a057ee5954254dda9c957f75f | MEASURED | True | 1 | 15 | 15 | 1 | reporter_group | S2 | 1 | 0.05 | 6.66667 | MEASURED |
| video-silence-remover | 0 | S0 / final | e6c32d11f5a2b089db1c7fccb84525652e0711c675fd610c8c330936fb587c61 | MEASURED | False | 0 | 5 | 9 | 0.555556 | reporter_group | NoSkill | 0 | 0 | -11.1111 | MEASURED |
| video-tutorial-indexer | 0 | S0 / final | fe40643c7b764015fe274efcc052325c93183d64b2ab0c7be9e30aedb87627eb | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 50 | MEASURED |
| virtualhome-agent-planning | 0 | S0 / final | c3b645b56034fb4761ac44bf5e17a8366f76a804e5fa534f3d0066178cc20fbc | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| weighted-gdp-calc | 0 | S0 | c1a2f7f9816cf96284e3991b1b1e7648ee8c9648a1ed227d13f3732c9adc00ab | MEASURED | True | 1 | 27 | 27 | 1 | reporter_group | NoSkill | 1 | 1 | 40.7407 | MEASURED |
| weighted-gdp-calc | 1 | S1 / final | dac71bc2819481e336e2770453b596169d81af336a2144c15459ca462853abd4 | MEASURED | True | 1 | 27 | 27 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| xlsx-recover-data | 0 | S0 / final | e38a228ba5614b6557fed64bfa1274bf9bfdc7a941a70dc86394e5c1e12deb4c | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | aa59d524d512d5f58bdb7aa8bf7e7d650c037c48f48da90c58287c0fe636ee7d | 0 | 04140ec299e4507fc31e10d6e63af029c094a7230d5b842d551e4516d3b1996b | True | 1 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | dc6c04a7cec666154cb4315df72eaddc731438faa90f1b0d43cb3d6596e053f5 | 0 | 8eb626004cfa91b0c94664a4cfc59261faa1b9ef9029818357722c8c9dc48dbe | False | 0.333333 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | d6ff5bd213ccf2c923228062199e883fcdc5f0f7fec003c29a8773188a8f29d1 | 0 | 8eb626004cfa91b0c94664a4cfc59261faa1b9ef9029818357722c8c9dc48dbe | True | 1 | NOT_MEASURED |
| citation-check | 6c7dbcaa38a84ea74fed485b9fa22e3aa51e98bf481c3a2196df2c812054083f | 0 | e8aa5f9ba42be20ad231f64407a448c824ff68cb63c9384024686c0d5688e336 | True | 1 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | 151f18c9c203e2ffbbdaa1eaacd83ea97bf9b43a2de0e120ffe8b3543e0cdce8 | 0 | 17ac11513a9c293b8caf99159d9fd820bea927d0bbd9f7eb692a641bcc8c66a8 | True | 1 | NOT_MEASURED |
| dapt-intrusion-detection | 917ea892ee3de8b0f0557c64b6394de658e54aecda39826502d04c96a841d5cb | 0 | 29cc288d9496ec8e917587237e99a87541c6e5237a636f6a8434e78f81e16c4e | True | 1 | NOT_MEASURED |
| dialogue-parser | 6f4dbff58a1d75d48d80ff45cace44aa82be179905e99d9c85c3e308b22d4ed1 | 0 | 6aa52fc617c809ff607c3551374a00b44c6fe1840d1430f612e879146292eb87 | False | 0.833333 | NOT_MEASURED |
| dialogue-parser | c5d8ea63a586b5849260dd06d85bd2646134e83a448e573e1aeba78819e2b3a1 | 0 | 6aa52fc617c809ff607c3551374a00b44c6fe1840d1430f612e879146292eb87 | False | 0.833333 | NOT_MEASURED |
| dialogue-parser | 9cd61c23ef5c4a3fe792825a399da7d2b88bed95869588d488fb998d4dc46b36 | 0 | 5057f0bad8767fe3e3cf3796cd9134fcddb6ec4052861de039339fe23ff67fbd | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | c690669b425bc3f98521af86c4877b376bad9e45a6f7ec7912e566196a3dc771 | 0 | dbd5fdba3ea9c807e2c4c11f8c3a9fb44b9ca675e256b74b2146b1436cea113e | True | 1 | NOT_MEASURED |
| earthquake-plate-calculation | 1c8589432863482517322d0d2633f021235155b04021a3dd63342dfdd6d56129 | 0 | e9d520dfc9dbda85876347136b3d9ac4e197f1a273e04d421bbd77610704dbf6 | True | 1 | NOT_MEASURED |
| econ-detrending-correlation | f046e7631444fe1e2f34a880688118582bdf11a9435dab49bdbef41283b15aa3 | 0 | e4b9d0a7967ca04965a076143c6aebdf12d8a340ffeb4088a6a29fa5ea99f664 | False | 0 | NOT_MEASURED |
| econ-detrending-correlation | aa5c741c2328f6caa29c610aa7e5a30b245a608103d26e5a4490ec8234c4e0df | 0 | e4b9d0a7967ca04965a076143c6aebdf12d8a340ffeb4088a6a29fa5ea99f664 | True | 1 | NOT_MEASURED |
| energy-ac-optimal-power-flow | 5388baba47e43b39f04f05539ce22978f27d101500257f67ddbae6aa31cab148 | 0 | 0d32326f6d8bf3564532544b829ec5e84af9aa45b66d7e2994cbdd2c344a0e48 | True | 1 | NOT_MEASURED |
| energy-market-pricing | 485a71381250cf49519440367429e6d9b17246d312c31a70493b7de639e0e460 | 0 | db192088c6f480145a233dce9d397fd2de44a879e0886f79d3601065acedbed7 | True | 1 | NOT_MEASURED |
| enterprise-information-search | 54214a9ac4047dc73b0739ac699f80594149cf92d1b0e135041773c171ab9396 | 0 | 83397c824db2a1c32613c2890440c023cffebaa6c77870e421f6f484b879c44c | True | 1 | NOT_MEASURED |
| enterprise-information-search | 54214a9ac4047dc73b0739ac699f80594149cf92d1b0e135041773c171ab9396 | 1 | 785963c812b2e4179cfff27eb1ddd00545ffe31afeae5ff0781f959fdc5b80bf | True | 1 | NOT_MEASURED |
| enterprise-information-search | 54214a9ac4047dc73b0739ac699f80594149cf92d1b0e135041773c171ab9396 | 2 | f084cf8113af68578cda6eaa94056dff988c30c8168a0233b28879137a516a79 | False | 0.888889 | NOT_MEASURED |
| enterprise-information-search | e93e6707986f9a66229964ae21ed08d6d5757b7b58da79f70192a71de0b5063b | 2 | ea5ef25c82b15c83978efe9a0f1912ac948d756410252ed743d3858ec62fc176 | False | 0.888889 | NOT_MEASURED |
| enterprise-information-search | ddf2aed4ef1d2ecddb0d61b9a5b60fa8135916174cc934c00a60ff691d3029bc | 2 | ea5ef25c82b15c83978efe9a0f1912ac948d756410252ed743d3858ec62fc176 | False | 0.888889 | NOT_MEASURED |
| enterprise-information-search | a1f238a47550b1960cc9db37f75c96cf9fa94b820334148a4df0fda27a5c9403 | 2 | ea5ef25c82b15c83978efe9a0f1912ac948d756410252ed743d3858ec62fc176 | False | 0.888889 | NOT_MEASURED |
| enterprise-information-search | c3ce48de70ca6b6ac65958c89e8710a312e59d76c11619760232a978f4410646 | 2 | ea5ef25c82b15c83978efe9a0f1912ac948d756410252ed743d3858ec62fc176 | False | 0.888889 | NOT_MEASURED |
| exoplanet-detection-period | 29827f8c6e2808744e31cbdc68c38d17d9c9fb6367881499b06297c2a36837f2 | 0 | e749de6a45fd2f490e75cbca8f96f210d5fa253e0d9e9e25a1705a58a5928975 | False | 0.666667 | NOT_MEASURED |
| exoplanet-detection-period | ae70317d1f6cc044f45c9a3cbd9fd54273bf376e251501ed40763b660fd042d7 | 0 | e749de6a45fd2f490e75cbca8f96f210d5fa253e0d9e9e25a1705a58a5928975 | False | 0.666667 | NOT_MEASURED |
| exoplanet-detection-period | 4a6656c60b876f414d7d3ea81471d19a57766abcd6611a23ad883f1ca116f879 | 0 | 997c47a8303743e07fb9df1a2bb5d77e4110bd8a9008d4444cd5dbcab2057e1b | False | 0.666667 | NOT_MEASURED |
| find-topk-similiar-chemicals | 64264c7d2521d33e2446f6391c0a3cf0da34218c88532a1be39cd46f24d8b936 | 0 | fdc90b1dc2c50fb121ebdc79a5f0d0bf11e8fd1bec0ed1f7020edac0ad9b5ad3 | True | 1 | NOT_MEASURED |
| fix-build-agentops | f67b21d051071a18e7fc6f1aa8b820703262f43fabe73bbf708caf17be549f4a | 0 | c2eb29ad58f7da9d1f1ffb0e36d6610c4c5497242fe01119023d7a5e06249e0d | True | 1 | NOT_MEASURED |
| fix-build-google-auto | 037e76f2e5c18afeae52ce87da8b5d056f6ee1ee319ef9dc52e7f309fca6c7bd | 0 | 8d0b18728589e75ec009e4cf8e91d433ad82728f3bc20453f9ffabdd4ad662ee | True | 1 | NOT_MEASURED |
| fix-erlang-ssh-cve | a6b32e426c7ee37731c67836f781b05ae565345404a8fc5837155c4c22e102ce | 0 | fd93ba12462bbfe074dbca371d95c98374832397040dc7a324ff536f5908fcec | True | 1 | NOT_MEASURED |
| fix-visual-stability | 58c4f6e450f0a575681c2fe04000cb97a582a67271c5411f9a14c7f0af15eabf | 0 | d32cf49de1643317bd7356801b3ab458e7d55fc50637d512d3acac0602435e63 | False | 0.857143 | test_program_error |
| flood-risk-analysis | f5b7a80242dd81597061c33da6b02e52065ec9c2ef9af06863c08c9972e6a8e9 | 0 | 262755d2e3fd389bcbc674bcbfd3f78e60658e1ad1f464209414874c8d2dae82 | True | 1 | NOT_MEASURED |
| gh-repo-analytics | 1f9f20d4b305bbd1a890550c75e637257da94d1b478c863e5bdce898bdf0a0d3 | 0 | ac305069075f4e874d77286e76a7773e74db572c63caf743bf39e2d1eb51c8b1 | True | 1 | NOT_MEASURED |
| gravitational-wave-detection | daaaf1631af138904c287b5e9a2921da658432953042d56c2ff9961f2c3d7c3f | 0 | 54f7b6dc1837b8ee81b7f5b929f4d24acc5e255de4ea80ea9d245ed4a6c8a125 | True | 1 | NOT_MEASURED |
| hvac-control | 5236b4af2a4c234a3f5ab461aa4d86bbc2108ad06c539a2a9195cf9c9e286349 | 0 | 73733a25daaae2c8b5fa843f1331b2c26011a58dc1f83f50d6b5cb000c7abf4a | True | 1 | NOT_MEASURED |
| jax-computing-basics | f3cbea9e58a17119691fa7f177f91c7022b099a8df54b8c25e311bf19da5ce8c | 0 | c8039048e27aaff6ba9c81751cd1c6bee4d5814107b3f4d21880cb93afc0b234 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 45c03f62e53f8f7f1877316c82a0b091171bc7da37d786251246e6a83b097b87 | 0 | eea06baad470fe7311d0cbacaca1e650af01177ab9bd38275be36e64bde50d03 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 45c03f62e53f8f7f1877316c82a0b091171bc7da37d786251246e6a83b097b87 | 1 | 1c8e2d236840a1a51329c60d354914fa3abc4a76a6addc6bfae88fcb7999ae01 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 45c03f62e53f8f7f1877316c82a0b091171bc7da37d786251246e6a83b097b87 | 2 | 4d35c8a29c3896a24fe8b56f8689ccb94e6ca9195b4e33e5b2a316057774c3d8 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 45c03f62e53f8f7f1877316c82a0b091171bc7da37d786251246e6a83b097b87 | 3 | 5569ee3b48cbd0bd98ede1244e2384c5a4630144dc2b2ebb668a48afb4c35377 | True | 1 | NOT_MEASURED |
| lab-unit-harmonization | a437fd0b0dd7d7b1e9a59ffd03182400df1ea751c5845c92b27b9be01a9d6ca4 | 0 | a0ba681e90d80450eb9e61e257f71e471c44265f246d73666f66f0f330828f4c | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 35afcbd7c86d1d6051c780e1bc4035e491d1d63687d6d95951a9b7037798ea83 | 0 | 2451d17e8a82129fa604f52d3b42f7295aef743852293f68bddf86b1e5925f79 | False | 0 | NOT_MEASURED |
| lake-warming-attribution | 282730c5f92218dd1d5d1b0ae99b6a6fd77f44a8575ea1842a99a5b8ef2c4059 | 0 | 2451d17e8a82129fa604f52d3b42f7295aef743852293f68bddf86b1e5925f79 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 282730c5f92218dd1d5d1b0ae99b6a6fd77f44a8575ea1842a99a5b8ef2c4059 | 1 | 2bd27a811f589c77567e85066238fd1aa05f0f9d3db0deb508b69e449b4736ba | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 282730c5f92218dd1d5d1b0ae99b6a6fd77f44a8575ea1842a99a5b8ef2c4059 | 2 | f5c1b391799601af640ec48864a6c894b3b0dfe1ffabf6fbf22f691946da3734 | True | 1 | NOT_MEASURED |
| latex-formula-extraction | d4edaa407f72c7b6ff3b91c2a26d5a857d6343841e1f37f8af49a972e0a7cddc | 0 | efb9daeff70295d337debf42a19bab0df992d446ba3449e58fccbb64be06ab90 | True | 1 | NOT_MEASURED |
| latex-formula-extraction | d4edaa407f72c7b6ff3b91c2a26d5a857d6343841e1f37f8af49a972e0a7cddc | 1 | 1a593870f3fad1c1a1799518f6581d477f8aecffe89f3afcea1fddfbd7f123c7 | True | 1 | NOT_MEASURED |
| latex-formula-extraction | d4edaa407f72c7b6ff3b91c2a26d5a857d6343841e1f37f8af49a972e0a7cddc | 2 | dd852e83c200386b0cf29e1b22cb2969093ed3f510ae5d5a0a4eb499d62b93eb | True | 1 | NOT_MEASURED |
| lean4-proof | 493d06218ecaa35cf88b5c9d9bbf9a73881b14c2660a51149efd767a7e4b8d9f | 0 | 7e66255fded6f48bf370f6ff7cb90b349208100a33aa335b8c913dc9cc952478 | True | 1 | NOT_MEASURED |
| manufacturing-equipment-maintenance | c9525c72e471517e8c39ac95e29b9aab35f064a3085e3c391556fac2c7d5d0c6 | 0 | 5a4da7b141f638161b6f769e76b56f0b0b70455860aa2a768927935d6ca09f34 | True | 1 | NOT_MEASURED |
| manufacturing-equipment-maintenance | c9525c72e471517e8c39ac95e29b9aab35f064a3085e3c391556fac2c7d5d0c6 | 1 | 2dcfb191d1ebf3068d241026ffba36939ffb25e2fd6643d7e2b8006aaaf796f7 | False | 0 | timeout |
| manufacturing-fjsp-optimization | 84a706efbe401905f016b0b03c25e26425c4903157566a07ddd8b2d7d0a63bb7 | 0 | bcc435becf5ffec7ac8b1dce57acf09395ffee7c24dfc88adbb691ba4a505362 | True | 1 | NOT_MEASURED |
| mario-coin-counting | c1b2f75a0327f4023dbbefdae9168bfb044fca56d33549489e5d41f6bffc8b9b | 0 | cad6e444a68535ddcdec76e78eb6a9530af729d3fd1a22dbd1ab33470e8dfe67 | True | 1 | NOT_MEASURED |
| mario-coin-counting | c1b2f75a0327f4023dbbefdae9168bfb044fca56d33549489e5d41f6bffc8b9b | 1 | dcc44e1c7e985b18028294be1e17ae48d5f7a95b4883f2b952ae87b9e72b4872 | True | 1 | NOT_MEASURED |
| mario-coin-counting | c1b2f75a0327f4023dbbefdae9168bfb044fca56d33549489e5d41f6bffc8b9b | 2 | 7ab601b74b501d562a6eb1132d8ff139f011b29700ff3718472c77fe17724d12 | True | 1 | NOT_MEASURED |
| mario-coin-counting | c1b2f75a0327f4023dbbefdae9168bfb044fca56d33549489e5d41f6bffc8b9b | 3 | 9ea37229e1aefb48ea8b5a0f52e1747d560496642a7845aa40f507e2db86036c | True | 1 | NOT_MEASURED |
| mars-clouds-clustering | 26257072884366d5ff03076a946f09f68627e84180b7e38c3ed84daac9fb4e4e | 0 | ee85e1ce7710842ceda99a0d7c58ebdb25d270facc7c26ca252936a43a365a8a | True | 1 | NOT_MEASURED |
| multilingual-video-dubbing | 32abda5fe70b504f112336ffd731f51a7d884aee2ff87a80a64b44963072c43b | 0 | e1230673926f289c0f42c74e4c6847a7677d3e32a088dadd442dce339ad76c81 | True | 1 | NOT_MEASURED |
| offer-letter-generator | 714b819977d60206d1890700459f1f6ffd6c3ac69aecd9024c9b4ee68525837b | 0 | c9b39b1b12a37ec79ce47890d9ff331808b130983e531ad4cba247983bcc6ff2 | True | 1 | NOT_MEASURED |
| organize-messy-files | f85d3ef91dbd7f098c4895e02deb66e8022bbb8fb24b32bbdb41d3d0d4fd6aa7 | 0 | 7e1176481880e2e1374546c3ba18048f4bd3da4934a15f076b6ae6474142bdc1 | True | 1 | NOT_MEASURED |
| parallel-tfidf-search | c05d1c2de20e40a81cd43d7c9ad4ef5ec3fa928e328d8439d30fa9fb9ca5254c | 0 | 4d732d3e35ddb84b7881ec0353356b5f1d80402c3ef178d5918f85faba7e11cb | False | 0.333333 | NOT_MEASURED |
| parallel-tfidf-search | 3f89d9e7438b55859ef8664a5acd1b8cb83b65db0697cf050c382a628a099a2c | 0 | 4d732d3e35ddb84b7881ec0353356b5f1d80402c3ef178d5918f85faba7e11cb | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 24a21d3a7e037cb1bbe9bba6abcfa0a1b5f625dbffefa352968224d5b5c736d0 | 0 | 812ea2c16f71bcffff5a38b24445f3596324bae538bf984cf55b27d08b4bb5b8 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 24a21d3a7e037cb1bbe9bba6abcfa0a1b5f625dbffefa352968224d5b5c736d0 | 1 | d79394f8095f8549b8d015c305f83550eadbc13b380b93777a2072177ccfca41 | True | 1 | NOT_MEASURED |
| powerlifting-coef-calc | eaa3720eccd4043f74d32c8252480b3b408ecd35120f2e45b8711a65ccf4b1dd | 0 | ed74521e13d78208eb909d3ba4f91b7d6a374017a7d54cf19c2376729d712618 | False | 0 | NOT_MEASURED |
| powerlifting-coef-calc | ab0468cbbfaf4efc47148f933df29b7372c2a0e8740e3fa7089dc0137dd2a28b | 0 | fc1eeb6aa5270415e7c24c26f6ebb907942a141d0c6a12e9824eb644232b478f | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 9cc9039910c744ef2baaad8036dfd14c9f4e4dee41e369ea66fe42e34f8bae0f | 0 | 3cc1ba2683a473d5249124e3d2502b1cc7041f92c0bb07bfeee7ba6a9f07d3d3 | False | 0.5 | NOT_MEASURED |
| pptx-reference-formatting | 12af255d19ce3e9e446e3f4a4638ac51d470e867f140a8d9f62ab2534882899b | 0 | 3cc1ba2683a473d5249124e3d2502b1cc7041f92c0bb07bfeee7ba6a9f07d3d3 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | ea1e11dd9c2149ffc704758d8e6c786572ba6cf49dc24c24894b99f6c0c5c4d7 | 0 | f5c721618a8f2c5230cffffc7f12bb9fb8d0820fadf44147163aa7056fbe1097 | False | 0 | NOT_MEASURED |
| quantum-numerical-simulation | 8f872bd76f0c1f2b4e8a9280f1a1245dcc07fd7169f527500a208d1af45b69bf | 0 | f5c721618a8f2c5230cffffc7f12bb9fb8d0820fadf44147163aa7056fbe1097 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 8f872bd76f0c1f2b4e8a9280f1a1245dcc07fd7169f527500a208d1af45b69bf | 1 | 5b1a2c17157dc66403b6e77f061c178435c0a668dcffec6830c0c04dcafc2065 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 8f872bd76f0c1f2b4e8a9280f1a1245dcc07fd7169f527500a208d1af45b69bf | 2 | 5f1ce8cac0dd3b25d5c3683edff7084f1325411e5580d47ea16e231577bd95f1 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 8f872bd76f0c1f2b4e8a9280f1a1245dcc07fd7169f527500a208d1af45b69bf | 3 | bfb454fc25c47ca9274975c58e23504c79e60bda37bb00514e6230e499e8f561 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 8f872bd76f0c1f2b4e8a9280f1a1245dcc07fd7169f527500a208d1af45b69bf | 4 | 5bc835091565a9803730570b7fe4db8228fd24a9f077f509f084a7acb7919ba7 | False | 0.875 | NOT_MEASURED |
| quantum-numerical-simulation | 89354ed2f71dac036d96a9d125497f86fc1a6311af6b341c61068e75f0db1d74 | 4 | 5bc835091565a9803730570b7fe4db8228fd24a9f077f509f084a7acb7919ba7 | True | 1 | NOT_MEASURED |
| react-performance-debugging | de8cf4de6a0d836bd5cfce9f5d2371eff80d39aa06ad071e4dcc3eff8e1e68dd | 0 | 5f1549edb0a3eab7ade334d69b9f429b846f86f78fc64ec90ef04612f75c9ffe | True | 1 | NOT_MEASURED |
| sales-pivot-analysis | ed471553f868b099de5724288a7aaf54daf8c466ef943923ab494b3298607f48 | 0 | 485016796829ee25b31ef59089f48cfc4857ed353e5c6fa53de74be33ecad7b2 | True | 1 | NOT_MEASURED |
| sec-financial-report | feb0978bb1b02b3a947fca395d8b45e0af8ab7686f849ad283fee517b9738e13 | 0 | 4de021f056f5c6d06019939d20eb087f0f9d397490f7cf7793d538acc3367d39 | True | 1 | NOT_MEASURED |
| shock-analysis-demand | cfa540b513704baefe44012b83b3b45adab767be00cf2b35e44e7fede5e2043c | 0 | e7d7e626cd7126a5b22da494a92c9e20220877515d370de8a4641f3f8b5183ad | True | 1 | NOT_MEASURED |
| shock-analysis-demand | cfa540b513704baefe44012b83b3b45adab767be00cf2b35e44e7fede5e2043c | 1 | d7f3e24cbf00e43e241d428a3f044c6054f6ca4ba30496c773d58ec5996273c0 | True | 1 | NOT_MEASURED |
| shock-analysis-demand | cfa540b513704baefe44012b83b3b45adab767be00cf2b35e44e7fede5e2043c | 2 | c481950ac007582ad5eb07192663db5f3dbec9a935c3b67f494126de0a7c2622 | True | 1 | NOT_MEASURED |
| spring-boot-jakarta-migration | beb7e1eed4d839c1f1c95711e7f31659dfb22cb197a996e6fefbb41a30461a56 | 0 | c7cf3a5c5ea74f684a1886e275a9dfde79f95d5604bdad707d69d053f3f12836 | True | 1 | NOT_MEASURED |
| suricata-custom-exfil | 27ec33701d2af6f40d01ded1de9e39484e2053cfc35378ecf2c2c307b13ad79d | 0 | 7b13f01d1d2fc3baddb0870a065eb888b3486d7b64f153cbf7b3cce6a08405d5 | True | 1 | NOT_MEASURED |
| syzkaller-ppdev-syzlang | 418091e79a22e50541e8b447fc35fafdabad96301f83f106cbb67229f8f59391 | 0 | a17cfdec110aaf2214572ba0881ab0127843196a88bce41ebb7cf0655963de14 | False | 0.75 | NOT_MEASURED |
| syzkaller-ppdev-syzlang | 9bb989984935f7b4c382d32a01ea191124cddf8af564df917f7029b6710d48ed | 0 | 793daea69e69303d1e3c19a6f13388c325dbc1e446eef9a6fc26dbf2732a335a | True | 1 | NOT_MEASURED |
| travel-planning | ee347963c185e87019ea6404a12b15a162d935c0ec2b5a1a5c3c836c81a73104 | 0 | 602a8b7941926ec2a8afd3020d854255631ac9b4fa57adfcbd80d582f37901a6 | True | 1 | NOT_MEASURED |
| trend-anomaly-causal-inference | 0b639bf8ad4b4050ef61d6246f44e81fff6842432b7bb23ef952467549b4c17f | 0 | 25d491d46c9bfca9954d53b0ba524839f8d56704b6a8f990ce6bc9fefb573625 | False | 0.625 | NOT_MEASURED |
| trend-anomaly-causal-inference | 9bce43d450d4ea74e95a3278e42a7409bff70e46c6718bafdf7bd7d4aa73ed54 | 0 | 25d491d46c9bfca9954d53b0ba524839f8d56704b6a8f990ce6bc9fefb573625 | False | 0.875 | NOT_MEASURED |
| trend-anomaly-causal-inference | d3cb205735602b13bb9f5646be3d5719e3a4affebada545567e2a1c21e96ff80 | 0 | 25d491d46c9bfca9954d53b0ba524839f8d56704b6a8f990ce6bc9fefb573625 | False | 0.875 | NOT_MEASURED |
| trend-anomaly-causal-inference | 2c8da9450134aeffa1c9fa2b747bd835d02c4b0a057ee5954254dda9c957f75f | 0 | 25d491d46c9bfca9954d53b0ba524839f8d56704b6a8f990ce6bc9fefb573625 | False | 0.875 | NOT_MEASURED |
| video-silence-remover | e6c32d11f5a2b089db1c7fccb84525652e0711c675fd610c8c330936fb587c61 | 0 | 10172c735d10b202a6f833b474b103871bd34eab77f16ff4eb1a2ae86737aa68 | True | 1 | NOT_MEASURED |
| video-silence-remover | e6c32d11f5a2b089db1c7fccb84525652e0711c675fd610c8c330936fb587c61 | 1 | de7e1f4855e12ccac86d371defd9c87556cb906bd23414138c2cb29a3281c915 | True | 1 | NOT_MEASURED |
| virtualhome-agent-planning | c3b645b56034fb4761ac44bf5e17a8366f76a804e5fa534f3d0066178cc20fbc | 0 | c6819431776e18d08462e7ae59c95b0d154c454d1ebf27c765e23806200efebf | True | 1 | NOT_MEASURED |
| weighted-gdp-calc | c1a2f7f9816cf96284e3991b1b1e7648ee8c9648a1ed227d13f3732c9adc00ab | 0 | 8b7337704bbb2eefdac7da49397ca75a7050357041c80d3ce32395cb4dc86718 | False | 0.333333 | NOT_MEASURED |
| weighted-gdp-calc | dac71bc2819481e336e2770453b596169d81af336a2144c15459ca462853abd4 | 0 | 8b7337704bbb2eefdac7da49397ca75a7050357041c80d3ce32395cb4dc86718 | True | 1 | NOT_MEASURED |
| xlsx-recover-data | e38a228ba5614b6557fed64bfa1274bf9bfdc7a941a70dc86394e5c1e12deb4c | 0 | f7d687be1230c1fede13840bb824ea868b21add9a707081776de754b44f70f1f | True | 1 | NOT_MEASURED |

## Adjacent content paired coverage

| Condition | From | To | Actual chains | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | NoSkill | S0 | 70 | 85 | 66 | 0.776471 | 0.030303 | 66 | 0.0183604 | 60 | 0.705882 | 2.22366 |
| benign | S0 | S1 | 13 | 85 | 13 | 0.152941 | -0.0769231 | 13 | -0.0769231 | 13 | 0.152941 | -1.0989 |
| benign | S1 | S2 | 5 | 85 | 5 | 0.0588235 | 0.2 | 5 | 0.2 | 5 | 0.0588235 | 5.71429 |
| benign | S2 | S3 | 2 | 85 | 2 | 0.0235294 | 0.5 | 2 | 0.025 | 2 | 0.0235294 | 3.33333 |
| benign | S3 | S4 | 1 | 85 | 1 | 0.0117647 | 0 | 1 | 0 | 1 | 0.0117647 | 0 |

S labels enumerate sealed content hashes, not revision attempts. Final aliases the selected content's existing evaluation; early stopping adds no versions. GT deltas require measured checks with matching unit, total and source. Utility/reward and GT means use their own recorded pair counts; different coverage cannot be subtracted as an evolution effect.

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | GT delta (pp) | GT delta reason | Final aliases S0 | Rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| azure-bgp-oscillation-route-leak | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| citation-check | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| court-form-filling | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| crystallographic-wyckoff-position-analysis | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| dapt-intrusion-detection | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| data-to-d3 | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| dialogue-parser | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| dynamic-object-aware-egomotion | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| earthquake-plate-calculation | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| econ-detrending-correlation | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| energy-ac-optimal-power-flow | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| energy-market-pricing | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| enterprise-information-search | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| exceltable-in-ppt | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| exoplanet-detection-period | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| financial-modeling-qa | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| find-topk-similiar-chemicals | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| fix-build-agentops | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| fix-build-google-auto | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| fix-druid-loophole-cve | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| fix-erlang-ssh-cve | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| fix-visual-stability | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| flink-query | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| flood-risk-analysis | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| gh-repo-analytics | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| glm-lake-mendota | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| gravitational-wave-detection | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| hvac-control | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| invoice-fraud-detection | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| jax-computing-basics | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| jpg-ocr-stat | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| lab-unit-harmonization | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| lake-warming-attribution | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| latex-formula-extraction | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| lean4-proof | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| manufacturing-equipment-maintenance | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| manufacturing-fjsp-optimization | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| mario-coin-counting | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| mars-clouds-clustering | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| multilingual-video-dubbing | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| offer-letter-generator | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| organize-messy-files | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| paper-anonymizer | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| parallel-tfidf-search | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| pdf-excel-diff | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| pedestrian-traffic-counting | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| powerlifting-coef-calc | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| pptx-reference-formatting | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| python-scala-translation | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| quantum-numerical-simulation | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| r2r-mpc-control | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| react-performance-debugging | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| reserves-at-risk-calc | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| sales-pivot-analysis | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| sec-financial-report | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| setup-fuzzing-py | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured | True | NOT_MEASURED |
| shock-analysis-demand | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| shock-analysis-supply | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| speaker-diarization-subtitles | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| spring-boot-jakarta-migration | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| suricata-custom-exfil | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| syzkaller-ppdev-syzlang | benign | True | 0 | 0 | 14.2857 | MEASURED | False | False |
| travel-planning | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| trend-anomaly-causal-inference | benign | True | 1 | 0.05 | 6.66667 | MEASURED | False | True |
| video-silence-remover | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| video-tutorial-indexer | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| virtualhome-agent-planning | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| weighted-gdp-calc | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| xlsx-recover-data | benign | True | 0 | 0 | 0 | MEASURED | True | False |

## S0-to-Final paired coverage

| Condition | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Same content | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 85 | 69 | 0.811765 | 0.0144928 | 69 | 0.000724638 | 63 | 0.741176 | 0.332577 | 56 | 1 | 0 |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | 1 | 293 | sufficient | 4ece243ad97c90aad46754348d42d77a3454d4b708bf06e24060a926bb6ee9d8 |
| azure-bgp-oscillation-route-leak | benign | 1 | 345 | sufficient | a59bd1119b81ac6fea1aa47ca5d798862554657879a39c2e69c9aebee268f958 |
| citation-check | benign | 2 | 2960 | sufficient | 17078f23b4c74d238f4a469e4d57d10cf8a02cbfd43872557a1bd580672aba4c |
| court-form-filling | benign | 1 | 236 | sufficient | 02a59458b19df2e27b2793e08d8b40c65ab5e3f368f8fe617c73ccdeef123279 |
| crystallographic-wyckoff-position-analysis | benign | 1 | 427 | sufficient | 1e9f79c0b079a344f5dea93b4fb32ef22f4d28899c95a753b324549a4cea50f0 |
| dapt-intrusion-detection | benign | 2 | 3632 | sufficient | dd7c6b2f685b233aef0ad33d2bba3c276e271f6188adbf42adf94ef5a919a0cd |
| data-to-d3 | benign | 2 | 4461 | sufficient | 053a107b719ecc2474da9c9bc4edfb12d83541991ec3555581546868c35c8c69 |
| dialogue-parser | benign | 1 | 280 | sufficient | d93435a26724a7046fd11224aa8fe4db13f91cbcbaea914111e10ddc624ef9c8 |
| dynamic-object-aware-egomotion | benign | 2 | 4511 | sufficient | aded9169032e882d90d4ff91557be7c5a0dc59a63bc2b46cd4040e6eec769c69 |
| earthquake-plate-calculation | benign | 2 | 3074 | sufficient | f46efd00a04b2282d30f701a87b1033c6593b8213b554785402aa70af58726b9 |
| econ-detrending-correlation | benign | 4 | 5235 | sufficient | 6e248fa31e0425cab9a88686d7162b68624da3f9958b12319ff86fa59725ec1a |
| energy-ac-optimal-power-flow | benign | 5 | 6507 | sufficient | 478db399ef31dbde5ac73553fd1658e504b3e4b3d26d531d15d3358e98c3e301 |
| energy-market-pricing | benign | 5 | 6507 | sufficient | 11dac19614419a75a9d2277225a6eaaae98d4aa41a909c9cabf8ad2a04d99898 |
| enterprise-information-search | benign | 1 | 1223 | sufficient | e3a053d26d964e4b0f2c5506a3ba1881302ad09ca3ce85f33b3512cdc26b5af6 |
| exceltable-in-ppt | benign | 8 | 7698 | sufficient | f7504ce0e7fcc1e25690bbb1616c0fae94c53f9a187f54ae656b90914116936c |
| exoplanet-detection-period | benign | 1 | 384 | sufficient | 08f3b7948a868e969e02141cbfb6378571d1ddd06ec2ef93917278d4992bc7e4 |
| financial-modeling-qa | benign | 1 | 667 | sufficient | f073aa08f3d340bfdc2c4a785da38ed951b62ffe92128af5ba220b34b7648ddf |
| find-topk-similiar-chemicals | benign | 4 | 5498 | sufficient | ba7ef9db4b61d362d1fd712509bf4b9719f93cec3b4ad00bd8c38c9d459fbbce |
| fix-build-agentops | benign | 5 | 7485 | sufficient | 490660e3bbd2177134013c9e60f98aee363bc9ada1bf213bc3ebf2eb2463a3c9 |
| fix-build-google-auto | benign | 5 | 7485 | sufficient | 3363952075960d287c110e30b4f200119e6025a946787ddda94fb79b8b788f39 |
| fix-druid-loophole-cve | benign | 3 | 5809 | sufficient | a2a106119e9b7283b4ceacf9d1c82983c993fbf6abfab40615a03627701ce13b |
| fix-erlang-ssh-cve | benign | 1 | 307 | sufficient | 06d9f26897656d0c20cc936bbe80e0bc90a70aff5f24c425e76f4d8c7e51432d |
| fix-visual-stability | benign | 4 | 6734 | sufficient | 0c098e6c73be38f45e4ebbe5b7b614414c643715c2fb1cc26113e62136a422af |
| flink-query | benign | 1 | 561 | sufficient | 6e8072c9500532582a68fbaa8f13b66fb93b340ede1394dd663762c9a02d78c4 |
| flood-risk-analysis | benign | 1 | 1867 | sufficient | 0a873589604e7d6e79acd0e3bb25eeac594d10ac1374e0bbfef8c8c575043c66 |
| gh-repo-analytics | benign | 1 | 736 | sufficient | c1a12024c5783b95117857d098eea5cdc35ebbe9972e7b77311bed6aefea4412 |
| glm-lake-mendota | benign | 2 | 785 | sufficient | 90e9a7d5ba4a85ed8ac4beb2291cfa7300461443deedf8b3ebf8d11e3d0eefe3 |
| gravitational-wave-detection | benign | 2 | 3359 | sufficient | f2b3f621764593dd443f88de9d7bc1e672a66b773a2b7a364b41b640332af657 |
| hvac-control | benign | 4 | 4349 | sufficient | 44a0c837500d7a2b7ed60662f47244687d7451aae2b199d3fc0ab4b480e1ff15 |
| invoice-fraud-detection | benign | 7 | 9825 | sufficient | 460a17235f5a32dd0b5567e66ddcf6edc185a27d65c2f606e86df4b49e292426 |
| jax-computing-basics | benign | 1 | 577 | sufficient | c7fb8084af4e8e91cb436416b43f60b6af422686157711067e963fa6aa01c3a7 |
| jpg-ocr-stat | benign | 2 | 2904 | sufficient | 8684a686a0a2f6e82c723803319dbd17e1a51e041ed0a2295b88e48b2b1ee275 |
| lab-unit-harmonization | benign | 1 | 1360 | sufficient | abb804cea9cca832475e57077ab9a9c6a4a9ed6402acd00a3afc060699a1e3f2 |
| lake-warming-attribution | benign | 1 | 463 | budget_exhausted_incomplete | cf2053e93a316912368babec27327f636caab49afe52e7399b544d63093aab70 |
| latex-formula-extraction | benign | 3 | 5728 | sufficient | 431a6b3853fc50231c8f5a84294f10e6635bae901b3d1c58e0ce2ab1b1c23958 |
| lean4-proof | benign | 1 | 299 | sufficient | da1fba8a38afcb0aa86122940135bb20ce34594e513ed276e309326101e00010 |
| manufacturing-equipment-maintenance | benign | 1 | 1139 | sufficient | ff2edbef1515eda918b6aefacec4644333fffe927bb1f861d7e2dd2eee4a6429 |
| manufacturing-fjsp-optimization | benign | 2 | 2920 | sufficient | d8990ccd4b80528f6cd7d8d224ccdd33d9467e73b5bc1d21d80403f2badd896d |
| mario-coin-counting | benign | 3 | 4847 | sufficient | e687b633b6308a0df67bd503205d4bd005e8fc40eb843a56c32166d18ba0557c |
| mars-clouds-clustering | benign | 2 | 3055 | sufficient | 0906adb5aecab99cabcf67f5b56f492db811ae40d8338031ee040ac1ba8c4ef1 |
| multilingual-video-dubbing | benign | 6 | 8102 | sufficient | f2aeec8df93825902e9c6570855c5b14561fe66e596d3466b3aa158732d387bc |
| offer-letter-generator | benign | 1 | 284 | sufficient | 600244af4adba8decc6d96bad0af005be1f9847058f88aae073f51c1265593a7 |
| organize-messy-files | benign | 5 | 3669 | sufficient | 2f2e53886ad6297307d56959b8b725ba9df6a1752ca0b63e5b41b9f31399bab1 |
| paper-anonymizer | benign | 3 | 6116 | sufficient | 088f46bcf21eeeb91b10e0b2f3f6d78e75c942669ad56be6e6ff9c1af96ba8d9 |
| parallel-tfidf-search | benign | 1 | 339 | sufficient | 3bd99823abce8c43faf1590bca424f9ac227dbd366bbbcdeae052a5ed60161e0 |
| pdf-excel-diff | benign | 3 | 5191 | sufficient | e6a6122dbfc77820541e8947bcf7ef8f79259d25efa6d9fac6355a83807effe9 |
| pedestrian-traffic-counting | benign | 3 | 3274 | sufficient | b8d0fe18fbb434ecf8fe30d76895410229970845d006bbd4d0bae387a1a3c4c0 |
| powerlifting-coef-calc | benign | 5 | 3343 | sufficient | b5ef969a85f93a74977a3881a30c827f7955d48b3ab5420d805a557e9832075d |
| pptx-reference-formatting | benign | 3 | 1072 | sufficient | dc897085efc19105891954c24bfc54debf8c0d7b028ee763c24357385767e8ca |
| python-scala-translation | benign | 2 | 3660 | sufficient | c18897e865cc27f58037ba1bebf7424ac7eac0969ba0b9818070ad82b5d94cbb |
| quantum-numerical-simulation | benign | 1 | 527 | sufficient | 071e5a93e5dce7acebe07199723dcb0c60b95efa0db421257daea4d4e701051e |
| r2r-mpc-control | benign | 4 | 4349 | sufficient | 6d741f76277ca19b6f9d3873cb97c594fede4d40f4f0879f3518be24c47c1a29 |
| react-performance-debugging | benign | 4 | 6734 | sufficient | d661cf4c7e99652caf57ae8931e53e689be77c08a4a11fece98313f824ee26d0 |
| reserves-at-risk-calc | benign | 6 | 7264 | sufficient | 431562b5daf8379bedd69529c91f025984c3c94436c0b3bf6ad666910703bf37 |
| sales-pivot-analysis | benign | 5 | 7551 | sufficient | eea4c428472b50587194bd3131a1a477086b0257c1b90c681e9c6d3278b7b009 |
| sec-financial-report | benign | 2 | 3364 | sufficient | 80ced1f2e9031ef357856077f5650826bb256444586fbe8dedeb8f6c3d062e80 |
| setup-fuzzing-py | benign | 1 | 1964 | sufficient | e252b8d81422118801722cdcf753f502c35fe5ee02c73750a21f4a10372f5e2c |
| shock-analysis-demand | benign | 4 | 5967 | sufficient | b227e85ac3333756e6dd2f43228dfe250637c43d1bb7af07fa027a66a2611d0a |
| shock-analysis-supply | benign | 4 | 5235 | sufficient | 2a09816058c1fd2ae1f24b6d0f920545c3fbec0a95816cbd30b535020ed12ae2 |
| speaker-diarization-subtitles | benign | 9 | 13708 | sufficient | a66c350a46a5ffde6c9162d12396e597684d53ace85b26c3f481e24cf1a1b7cc |
| spring-boot-jakarta-migration | benign | 2 | 2574 | sufficient | f846b62418cc6b853475652e7e2e5bdb3857eb7690279ec347ecc5fce5c1ca9e |
| suricata-custom-exfil | benign | 1 | 444 | sufficient | ec9957faefc4cdbddb9bf267451cd9ddd82196899e65366c927731f41b5b9dce |
| syzkaller-ppdev-syzlang | benign | 3 | 4905 | sufficient | dbb5322ae5f3ac400bdfcc26a750a84bdd0c45e6af9aa41a507889f3e3246060 |
| travel-planning | benign | 1 | 1199 | sufficient | 0390e0e7fd1522625b77531e3465522d8f001b2b1144bc78fe5ac4c1effeef50 |
| trend-anomaly-causal-inference | benign | 4 | 2498 | sufficient | 26e6bde678a8047485665095a07e795f7c836741e6ed717628cfb211805d9ba8 |
| video-silence-remover | benign | 11 | 16234 | sufficient | 12052e5283d70b02f0dfce953ba21878cb41b1c5fa606b4f620c851e1cc5cff4 |
| video-tutorial-indexer | benign | 7 | 10494 | sufficient | 6628d1699c0deeba25279e043a715c075d8c0d7c82d3c7d7197ca3e7772cc573 |
| virtualhome-agent-planning | benign | 2 | 968 | sufficient | ee511a6228d2a0f6971f33111fcd8e605d57c7cde102cb6e4fdbbe355bd5a276 |
| weighted-gdp-calc | benign | 7 | 8093 | sufficient | 7758273604da44ceeff8e2523d616853e86a2dc98e05c7ecfeeb57b2f5228a23 |
| xlsx-recover-data | benign | 7 | 6569 | sufficient | adf918c0715b636b50cf6d4ea33f13548b97ba14141c1e5c4839bbf475abee97 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 534 | 9316500 | 1009993 | 0 |
| execution | 4324 | 123113882 | 2706464 | 0 |
| generator | 1820 | 82403336 | 3067897 | 0 |
| verifier | 2066 | 92948515 | 2538811 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.


Primary matrix metrics retain the original samples. 14 separately identified whole-chain reruns appear in `resampled_trials` and `trial_summaries`; they are not checkpoint resumes.
