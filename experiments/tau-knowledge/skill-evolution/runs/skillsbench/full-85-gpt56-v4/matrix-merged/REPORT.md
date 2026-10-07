# skillsbench run report

Protocol: `skillsbench.skill-evolution.v4`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Until all tasks are measured, fixed-denominator rates report observed successes; they are not complete matrix results.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility | Task pass rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| benign | no_skill | 85 | 0 | 79 | 0.367089 | 0.341176 | 0.341176 |
| benign | initial | 85 | 78 | 77 | 0.350649 | 0.317647 | 0.317647 |
| benign | evolved | 85 | 78 | 77 | 0.441558 | 0.4 | 0.4 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 78 | 77 | 0.350649 | {'verifier_initialization_failed': 13, 'test_escalation_failed': 4, 'oracle_success': 16, 'verification_failed': 1, 'oracle_budget_exhausted': 4, 'initial_execution_result_unknown': 3, 'verification_program_error_exhausted': 2, 'learning_environment_close_failed': 2} |
| benign | 1 | 33 | 33 | 0.363636 | {'oracle_budget_exhausted': 2, 'oracle_success': 8, 'test_escalation_failed': 7, 'verification_program_error_exhausted': 2} |
| benign | 2 | 14 | 14 | 0.5 | {'oracle_success': 3, 'test_escalation_failed': 1} |
| benign | 3 | 10 | 9 | 0.333333 | {'verification_program_error_exhausted': 1, 'oracle_success': 1, 'test_escalation_failed': 1} |
| benign | 4 | 7 | 7 | 0.142857 | {'verification_program_error_exhausted': 2, 'oracle_budget_exhausted': 1, 'revision_budget_exhausted': 2} |
| benign | 5 | 2 | 2 | 0.5 | {'oracle_success': 1, 'verification_program_error_exhausted': 1} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Learning executions | Terminal calls | Submissions | Final hash |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | oracle_success | 3 | 2 | 1 | 1 | 25 | 3 | cfc7c7cc0254531504df6317df468c8df43a6766355388f7b98feeb22e549198 |
| adaptive-cruise-control | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | benign | oracle_budget_exhausted | 2 | 1 | 5 | 1 | 36 | 2 | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 |
| citation-check | benign | oracle_success | 2 | 1 | 1 | 1 | 24 | 2 | 6d22f31de36a44e6b4ec2970bbd2dfe513c21da8ae8652d432102aff830b20b3 |
| civ6-adjacency-optimizer | benign | test_escalation_failed | 2 | 1 | 2 | 1 | 41 | 2 | b1e95db2cec5fc093dc50ee70e199b1bf267749a17cf1fcfb312cc11c7ae052f |
| court-form-filling | benign | oracle_success | 6 | 6 | 2 | 1 | 100 | 7 | 7f65579269d00ba11cc32d968faceae13952a161a7d7a3cf43c05af4a0f42b5c |
| crystallographic-wyckoff-position-analysis | benign | verification_program_error_exhausted | 4 | 10 | 0 | 1 | 49 | 11 | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 |
| dapt-intrusion-detection | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 29 | 1 | 4691457a64917347eefc00df89cb9a31aacfcda68f4d708c5d376a0a6b70d982 |
| data-to-d3 | benign | oracle_success | 2 | 1 | 4 | 1 | 35 | 2 | 0ca6a1a1cc5abf8082bc397edd1ef9ce96f0fdbbfe0e4a1569145556aa89f8f9 |
| dialogue-parser | benign | test_escalation_failed | 1 | 0 | 1 | 1 | 17 | 1 | b03cd9af3f67a87f5e00cd351b6db01b36160f37f564338466dbc5bdba359d71 |
| dynamic-object-aware-egomotion | benign | test_escalation_failed | 1 | 0 | 3 | 1 | 25 | 1 | 6c91519ed751eefd7714aeddc0b2dc7f129834913a7d2ce5e4ac5492457f6946 |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | oracle_success | 1 | 0 | 1 | 1 | 8 | 1 | 8dc6d3c0a62342364c69a21ca8618dd5e0e3bc422106ae9640c540d4c245a637 |
| econ-detrending-correlation | benign | oracle_success | 1 | 0 | 1 | 1 | 17 | 1 | 5cb9aca5f43c019df576edc1fbc2c45619c506fb2bdbc55f4207573c3a9aabea |
| energy-ac-optimal-power-flow | benign | oracle_success | 1 | 0 | 1 | 1 | 14 | 1 | b2e79dc0f76b96ae2439195dab5ab0028a45df71d66e3b5df89c3d9a7a458cff |
| energy-market-pricing | benign | verification_program_error_exhausted | 2 | 2 | 0 | 1 | 54 | 3 | 161743614bf480ab03172d3edb9247f875c1e73e965be8986bae44b69de24d7c |
| enterprise-information-search | benign | verification_failed | 1 | 0 | 4 | 1 | 63 | 1 | 50b657494a3d2005b1fa9afcc77876eec5278cc294904815f672d490a9fcc7a7 |
| exceltable-in-ppt | benign | oracle_success | 3 | 2 | 1 | 1 | 35 | 3 | f2e7264c6ea38aab28507af0953ef2c7c607f5a58437672512c0ab05719392d9 |
| exoplanet-detection-period | benign | verification_program_error_exhausted | 2 | 1 | 0 | 1 | 54 | 2 | eeba115bb20bf251e66be626a595d73569a7d9d0c3ed387eaedfbf0dfba4f4b4 |
| financial-modeling-qa | benign | oracle_budget_exhausted | 1 | 0 | 5 | 1 | 87 | 1 | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c |
| find-topk-similiar-chemicals | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 11 | 1 | 474882f7e1c39dda849a82e59e9f21ac1bb9ba7d1f92fd91796b54a468ed63b4 |
| fix-build-agentops | benign | test_escalation_failed | 1 | 0 | 4 | 1 | 115 | 1 | a7213d28722786c84ac645ff3053e5b61df7e158f8a9603aa37e5355c0aaf11d |
| fix-build-google-auto | benign | oracle_success | 1 | 0 | 1 | 1 | 45 | 1 | 7dfd4e2bda712cc6f30d8c1a4dddb5f9023b7eb410779dd08aa79b7d285ac8a4 |
| fix-druid-loophole-cve | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 26 | 1 | eb0b4752e409f4b5a7a3e918b5226be566049997415524c6bdc46dbafcc6c676 |
| fix-erlang-ssh-cve | benign | oracle_success | 1 | 0 | 1 | 1 | 25 | 1 | a97574d3c90fc49c91669ecac453afcbf599da264a9cfa9a56304a01e07b1280 |
| fix-visual-stability | benign | oracle_success | 1 | 0 | 1 | 1 | 35 | 1 | 3b1d439f9fe796b28d127ffd621896f48533519080c424888d04828c1d1e08ca |
| flink-query | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 33 | 1 | 7d4ec17caa18381ea7f6c6ec19b3e0d0bc6e0774bf14dbde56232a1645059f00 |
| flood-risk-analysis | benign | oracle_budget_exhausted | 1 | 0 | 5 | 1 | 35 | 1 | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c |
| gh-repo-analytics | benign | oracle_success | 1 | 0 | 1 | 1 | 9 | 1 | bef80667dd2f615eee524ed6e8f4b62f3d5e3225219cb02cce23ce25042b0abe |
| glm-lake-mendota | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 33 | 1 | c264103d4691e66775ba8c33bb18593c8b6c9ad377fba2e5b2c1f5ce901270b3 |
| gravitational-wave-detection | benign | oracle_success | 2 | 1 | 1 | 1 | 40 | 2 | b7abb0faac41d8be637d3877197ea43459522e626acdbadc8f7ef9ed88360c22 |
| grid-dispatch-operator | benign | test_escalation_failed | 2 | 1 | 4 | 1 | 73 | 2 | 3df6709248a38e3f2d6383f55f6b959002ccfd6a096b9aac5fb059715249884c |
| hvac-control | benign | oracle_success | 2 | 1 | 1 | 1 | 34 | 2 | 816d05dff6ee9af2754780202159116afbe7707698d3f5158bd0c401b9d6b268 |
| invoice-fraud-detection | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 12 | 1 | dc3e0d70232f873c3bd6bbe1a6dc0835d5c58138e9ec5b642f117ca3364cea3f |
| jax-computing-basics | benign | test_escalation_failed | 3 | 2 | 3 | 1 | 45 | 3 | bdbf14080cabf8ccadf15635a9e7834bd42030d03b4a17d3ec5148ec4fa79aca |
| jpg-ocr-stat | benign | test_escalation_failed | 2 | 1 | 2 | 1 | 65 | 2 | 61364680d928c420f52752e4578027f032862b21824a6a93b769dbecfdea5c4c |
| lab-unit-harmonization | benign | oracle_budget_exhausted | 1 | 0 | 5 | 1 | 42 | 1 | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 |
| lake-warming-attribution | benign | oracle_budget_exhausted | 1 | 0 | 5 | 1 | 27 | 1 | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b |
| latex-formula-extraction | benign | verification_program_error_exhausted | 5 | 13 | 1 | 1 | 146 | 14 | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d |
| lean4-proof | benign | oracle_success | 1 | 0 | 1 | 1 | 24 | 1 | 41ead0e1d3fc8734d8df461bb34d2b90b88a551bb85ce881d1f635f3f5e62b8c |
| manufacturing-codebook-normalization | benign | test_escalation_failed | 2 | 1 | 4 | 1 | 86 | 2 | feb6ea42edbb538b40cf07e8e447875b67a638c99f91e5c707a2f45c95870b9b |
| manufacturing-equipment-maintenance | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 37 | 1 | e16dbd658448b7567265c801752ca784edf206b1ea43b00338578444c737fea6 |
| manufacturing-fjsp-optimization | benign | verification_program_error_exhausted | 5 | 11 | 0 | 1 | 67 | 12 | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 |
| mario-coin-counting | benign | test_escalation_failed | 1 | 0 | 2 | 1 | 36 | 1 | 45d8e35cf1d1291b49b78b669169f1035afbdef72aefe09e9646e0cda57eecb3 |
| mars-clouds-clustering | benign | oracle_success | 1 | 0 | 1 | 1 | 21 | 1 | e575d8b7e638551a03933739d25fbb97092aecee9e89037f2c5588b7704305e5 |
| multilingual-video-dubbing | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 13 | 1 | 3b91369dd8f1c8ed78c0559daf38921179c27dbd54ee19906778fded33d3afe5 |
| offer-letter-generator | benign | oracle_success | 2 | 1 | 1 | 1 | 19 | 2 | 93b73afba1fba540b6468aef721231f8e32b1fb78ea37b71ec5c5bec2611d985 |
| organize-messy-files | benign | oracle_success | 3 | 2 | 1 | 1 | 39 | 3 | e4492d2ca2c6721a2b97b4999f91b33608c404d047bf5b36c65d88c8c5a30e3c |
| paper-anonymizer | benign | oracle_budget_exhausted | 5 | 4 | 5 | 1 | 101 | 5 | 0d05be53f10055d33ce50baf5f27fcd3aba352a570134cff531fb28da6df6a56 |
| parallel-tfidf-search | benign | oracle_success | 1 | 0 | 1 | 1 | 12 | 1 | 9213db5ff59c3ae9f0bcddf7647c7d3b58080a483cd12800c8733c0b5bb2ceb5 |
| pddl-tpp-planning | benign | oracle_success | 1 | 0 | 1 | 1 | 12 | 1 | 511601c678d0d81f4b7253e157f2f0892b24c0439a2a7343d1b2a91cc75e0ab7 |
| pdf-excel-diff | benign | oracle_success | 2 | 1 | 1 | 1 | 23 | 2 | a05b25dd11513b2f6d989a08518332eca8693a3b450986cd1e8a51b8b5ef8d0b |
| pedestrian-traffic-counting | benign | initial_execution_result_unknown | 1 | 0 | 0 | 1 | 4 | 0 | 48e57982af63eee755368d996cf607de0bb50681b4f33f0b26d9e2fe3d42ac28 |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | oracle_success | 1 | 0 | 1 | 1 | 16 | 1 | bf4e639a42514c25ebdab56b51521c073ec296b9bc33639633a169bf3395efe1 |
| pptx-reference-formatting | benign | verification_program_error_exhausted | 1 | 0 | 0 | 1 | 22 | 1 | e48121b37732b73b5946ae0c415652abb65ee258ac002ecf0f194f71899391e1 |
| protein-expression-analysis | benign | oracle_success | 4 | 7 | 1 | 1 | 68 | 8 | 23620adecc6050a2c6587d671a071977484a90f36cf1d504a78849e24da2c095 |
| python-scala-translation | benign | initial_execution_result_unknown | 1 | 0 | 0 | 1 | 26 | 0 | 4df8c2cdf612d8929e21b5282a8a534100f47861d199fc0603260fc1fbc24e83 |
| quantum-numerical-simulation | benign | oracle_budget_exhausted | 2 | 1 | 5 | 1 | 61 | 2 | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a |
| r2r-mpc-control | benign | oracle_success | 2 | 1 | 1 | 1 | 19 | 2 | 38a340ea68ac9c79fe1894f4c393b4527ee0e91fde7ae401204870861102d96a |
| react-performance-debugging | benign | oracle_success | 1 | 0 | 1 | 1 | 25 | 1 | eaae4e341e857d878afc40ff5148ca5d0c7e5538fb5716491c44a420ee5f3890 |
| reserves-at-risk-calc | benign | revision_budget_exhausted | 5 | 15 | 1 | 1 | 146 | 15 | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d |
| sales-pivot-analysis | benign | verification_program_error_exhausted | 6 | 5 | 0 | 1 | 69 | 6 | 1260ef1857b1c5b47256211644dc27dbe22ddaf954cd77b4ee1e311dde8926d8 |
| sec-financial-report | benign | verification_program_error_exhausted | 1 | 0 | 0 | 1 | 38 | 1 | 91ce320fcadeb466a8337229b0cdc59cd4fc6b1ad244f228bbba19a388810b59 |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 21 | 1 | 1631882c531b733ca2692450ee4ba74b80f17ca29a6aa6d6272953825abd7fa0 |
| shock-analysis-demand | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 13 | 1 | 39a095d8a35fe77b8e5cce111d278d24f95dce54cbdfb8d67a22972542c564a4 |
| shock-analysis-supply | benign | revision_budget_exhausted | 5 | 15 | 0 | 1 | 142 | 16 | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | initial_execution_result_unknown | 1 | 0 | 0 | 1 | 4 | 0 | 0e6abe2d242579d9aaaf5fd64dd151c851c9bf7e720b64793e0388da3425378d |
| speaker-diarization-subtitles | benign | test_escalation_failed | 4 | 4 | 3 | 1 | 112 | 5 | 0a0884013e244f261e8cbea7133e57c77bcc33186b1a6bbfea8f5b281b84c335 |
| spring-boot-jakarta-migration | benign | oracle_success | 1 | 0 | 1 | 1 | 29 | 1 | 14ac963f3dabcc7459b01ba782d1b2daebca508808919e2f34ad9f892a4207cc |
| suricata-custom-exfil | benign | oracle_success | 1 | 0 | 1 | 1 | 21 | 1 | ef63919d52681e683b8a023a459ea5a87f89dd12f0a9e5fdaef234c2c10d8557 |
| syzkaller-ppdev-syzlang | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 9 | 1 | 012d37a242cd16c0c83cc38b2142dd9cf76dbbf78f99b661adabf78f90539d53 |
| taxonomy-tree-merge | benign | test_escalation_failed | 2 | 1 | 4 | 1 | 64 | 2 | 84721b028d57c8ec807157ee26bbec33b599c2517895c4e36f251eccfd5e1406 |
| threejs-structure-parser | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | invalid_package | 0 | 0 | 0 | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | oracle_success | 2 | 1 | 1 | 1 | 24 | 2 | 0214c994e0d6bcbae2f735243ce74433a0b09d71e9e97885f931af1f357bf5cd |
| trend-anomaly-causal-inference | benign | learning_environment_close_failed | 1 | 0 | 0 | 1 | 13 | 1 | 95bb5417c7b20b9e5aa215bccb9096c9f80055a48b0930a4d4a8aed99f7e111d |
| video-filler-word-remover | benign | oracle_success | 1 | 0 | 2 | 1 | 73 | 1 | 2623781ecbfa00291ba5f594a4708a5e9190efb9fe0e0b467c6dee791faf423e |
| video-silence-remover | benign | test_escalation_failed | 2 | 1 | 1 | 1 | 40 | 2 | 86b62ddbd3c5e1bb3c9568cad064c571c633be832a88d657dcc9f82f9d233ac4 |
| video-tutorial-indexer | benign | learning_environment_close_failed | 1 | 0 | 0 | 1 | 19 | 1 | 99823184cf3a795bc62a3949ebc6768f075e024d9037e171cca5b63ce244cbfd |
| virtualhome-agent-planning | benign | test_escalation_failed | 2 | 1 | 1 | 1 | 38 | 2 | 42aae521f25ce12db31646983cf4bbead757c31ddad75da6b611ee78bb3b5491 |
| weighted-gdp-calc | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 13 | 1 | c9a2ce01aaabd97e73919e4e4edb0caf5031e03a8017e988a94697236750aa57 |
| xlsx-recover-data | benign | verifier_initialization_failed | 1 | 0 | 0 | 1 | 20 | 1 | 6080d1f989a3853f76465a484b814c34dd3ffafd144fed90d8e6fdccb13bac3d |

No-Skill runs use no package and do not create S0. Baseline comparisons require the same sealed executor identity; evaluations do not enter learning.

## No-Skill independent measurements

| Task | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| adaptive-cruise-control | MEASURED | True | 1 | 12 | 12 | 1 | reporter_group |
| azure-bgp-oscillation-route-leak | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| citation-check | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group |
| civ6-adjacency-optimizer | MEASURED | False | 0.5 | 10 | 10 | 1 | reporter_group |
| court-form-filling | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group |
| crystallographic-wyckoff-position-analysis | MEASURED | False | 0.55 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | MEASURED | False | 0 | 5 | 14 | 0.357143 | reporter_group |
| data-to-d3 | MEASURED | False | 0 | 14 | 15 | 0.933333 | reporter_group |
| dialogue-parser | MEASURED | False | 0.833 | 5 | 6 | 0.833333 | reporter_group |
| dynamic-object-aware-egomotion | MEASURED | False | 0 | 10 | 11 | 0.909091 | reporter_group |
| earthquake-plate-calculation | MEASURED | False | 0 | 7 | 8 | 0.875 | reporter_group |
| econ-detrending-correlation | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| energy-ac-optimal-power-flow | MEASURED | True | 1 | 23 | 24 | 0.958333 | reporter_group |
| energy-market-pricing | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| enterprise-information-search | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group |
| exceltable-in-ppt | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |
| exoplanet-detection-period | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| financial-modeling-qa | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| find-topk-similiar-chemicals | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-build-agentops | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group |
| fix-build-google-auto | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group |
| fix-druid-loophole-cve | MEASURED | False | 0 | 2 | 4 | 0.5 | reporter_group |
| fix-erlang-ssh-cve | MEASURED | False | 0 | 0 | 3 | 0 | reporter_group |
| fix-visual-stability | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group |
| flink-query | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group |
| flood-risk-analysis | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group |
| gh-repo-analytics | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |
| glm-lake-mendota | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| gravitational-wave-detection | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group |
| grid-dispatch-operator | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group |
| hvac-control | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group |
| invoice-fraud-detection | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| jax-computing-basics | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group |
| jpg-ocr-stat | MEASURED | True | 1 | 1 | 1 | 1 | reporter_group |
| lab-unit-harmonization | MEASURED | False | 0.604 | 29 | 48 | 0.604167 | reporter_group |
| lake-warming-attribution | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| latex-formula-extraction | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| lean4-proof | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| manufacturing-codebook-normalization | MEASURED | False | 0 | 14 | 16 | 0.875 | reporter_group |
| manufacturing-equipment-maintenance | MEASURED | False | 0 | 6 | 7 | 0.857143 | reporter_group |
| manufacturing-fjsp-optimization | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group |
| mario-coin-counting | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group |
| mars-clouds-clustering | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |
| multilingual-video-dubbing | MEASURED | False | 0 | 7 | 8 | 0.875 | reporter_group |
| offer-letter-generator | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group |
| organize-messy-files | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group |
| paper-anonymizer | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group |
| parallel-tfidf-search | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group |
| pddl-tpp-planning | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| pdf-excel-diff | MEASURED | False | 0 | 8 | 11 | 0.727273 | reporter_group |
| pedestrian-traffic-counting | MEASURED | False | 0.75 | 0 | 1 | 0 | reporter_group |
| powerlifting-coef-calc | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group |
| pptx-reference-formatting | MEASURED | True | 1 | 12 | 12 | 1 | reporter_group |
| protein-expression-analysis | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| quantum-numerical-simulation | MEASURED | False | 0 | 0 | 7 | 0 | reporter_group |
| r2r-mpc-control | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group |
| react-performance-debugging | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| reserves-at-risk-calc | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group |
| sales-pivot-analysis | MEASURED | False | 0 | 6 | 10 | 0.6 | reporter_group |
| sec-financial-report | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| setup-fuzzing-py | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| shock-analysis-demand | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group |
| shock-analysis-supply | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group |
| software-dependency-audit | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group |
| speaker-diarization-subtitles | MEASURED | False | 0 | 0 | 10 | 0 | reporter_group |
| spring-boot-jakarta-migration | MEASURED | True | 1 | 10 | 10 | 1 | reporter_group |
| suricata-custom-exfil | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| syzkaller-ppdev-syzlang | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group |
| taxonomy-tree-merge | MEASURED | False | 0.8615 | 19 | 22 | 0.863636 | reporter_group |
| threejs-structure-parser | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group |
| threejs-to-obj | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group |
| travel-planning | MEASURED | True | 1 | 10 | 10 | 1 | reporter_group |
| trend-anomaly-causal-inference | MEASURED | False | 0.8944 | 13 | 15 | 0.866667 | reporter_group |
| video-filler-word-remover | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group |
| video-silence-remover | MEASURED | False | 0 | 5 | 9 | 0.555556 | reporter_group |
| video-tutorial-indexer | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group |
| virtualhome-agent-planning | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group |
| weighted-gdp-calc | MEASURED | False | 0 | 15 | 27 | 0.555556 | reporter_group |
| xlsx-recover-data | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group |

## No-Skill paired comparisons

| Condition | Endpoint | Paired | Denominator | Utility delta | Paired coverage | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | initial | 75 | 85 | -0.0266667 | 0.882353 | -0.0431787 | 69 | 0.811765 | -6.23357 | 8 | 10 |
| benign | evolved | 75 | 85 | 0.0666667 | 0.882353 | 0.0501547 | 69 | 0.811765 | 1.36791 | 10 | 5 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate | Official check unit | Previous | Utility delta | Reward delta | GT delta (pp) | GT delta reason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 0 | S0 | bff6fae0fd072978bb4629c9ac4d12ce961d8ce7129eb92375752f662a7c7719 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| 3d-scan-calc | 1 | S1 | 343d4ed35a785abe79638a536a887add8f61c9ee464b38f51678b0ccbb192684 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| 3d-scan-calc | 2 | S2 / final | cfc7c7cc0254531504df6317df468c8df43a6766355388f7b98feeb22e549198 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| azure-bgp-oscillation-route-leak | 0 | S0 | 2ba1f557587815b13fb3e4422b4ce3684bc6a67681058aaaae30b6dd0a18f404 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| azure-bgp-oscillation-route-leak | 1 | S1 / final | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| citation-check | 0 | S0 | bfdb6bbda7a618d5fd80f1f1c8aae6f1314e779afc8319fc427fb49c0c0080e8 | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| citation-check | 1 | S1 / final | 6d22f31de36a44e6b4ec2970bbd2dfe513c21da8ae8652d432102aff830b20b3 | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| civ6-adjacency-optimizer | 0 | S0 | a75306aba64a101d90fc87e6181afb41cf5b9dfce610fe02d915adda09f40fcf | MEASURED | False | 0.8 | 10 | 10 | 1 | reporter_group | NoSkill | 0 | 0.3 | 0 | MEASURED |
| civ6-adjacency-optimizer | 1 | S1 / final | b1e95db2cec5fc093dc50ee70e199b1bf267749a17cf1fcfb312cc11c7ae052f | MEASURED | False | 0.8 | 10 | 10 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| court-form-filling | 0 | S0 | 9510098a7db74e4b93ae80c7d5e77cf0f1e2715b447dcb1a5a331e66d9336212 | MEASURED | True | 1 | 3 | 5 | 0.6 | reporter_group | NoSkill | 1 | 1 | 20 | MEASURED |
| court-form-filling | 1 | S1 | 95e0e3a784c7c6c28c2831f7b6d501113b37739833af82ad7fe770c00c56f6b5 | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | S0 | -1 | -1 | -20 | MEASURED |
| court-form-filling | 2 | S2 | 9e2dc62c1e223ee9dcfcc3d38e14e35fd90fb124300f27b3f7b718f2685e4e6d | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group | S1 | 1 | 1 | 60 | MEASURED |
| court-form-filling | 3 | S3 | 59958fa295054af4783c1b38754e7d4dd13ed87b6335ba55af5a946c1e765aac | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | S2 | -1 | -1 | -20 | MEASURED |
| court-form-filling | 4 | S4 | 211cdb9cff698ae0e5f25c6ad9a4feda472ce44cb660c4aee9636baad08727a4 | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| court-form-filling | 5 | S5 / final | 7f65579269d00ba11cc32d968faceae13952a161a7d7a3cf43c05af4a0f42b5c | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group | S4 | 1 | 1 | 20 | MEASURED |
| crystallographic-wyckoff-position-analysis | 0 | S0 | 729954f5e053fec3d923ea388dbf347123713d1d171fc8d625a7eaa65a56562e | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 1 | 0.45 | NOT_MEASURED | official_checks_not_measured |
| crystallographic-wyckoff-position-analysis | 1 | S1 | 94077ec300b500d2e6af1cbfbb02efa223adabfca765b020d41bda39c1b75712 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S0 | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| crystallographic-wyckoff-position-analysis | 2 | S2 | a016f9fad4e2b7cab53605ca2eaf59ed8dec5f31186a1f90705a3bfd055c679d | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S1 | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| crystallographic-wyckoff-position-analysis | 3 | S3 / final | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S2 | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| dapt-intrusion-detection | 0 | S0 / final | 4691457a64917347eefc00df89cb9a31aacfcda68f4d708c5d376a0a6b70d982 | MEASURED | False | 0 | 5 | 14 | 0.357143 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| data-to-d3 | 0 | S0 | 3415926e072e1604a3bb4dca4bbaf425dd77244357685c1fb0d6a32c5505983f | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group | NoSkill | 0 | 0 | -6.66667 | MEASURED |
| data-to-d3 | 1 | S1 / final | 0ca6a1a1cc5abf8082bc397edd1ef9ce96f0fdbbfe0e4a1569145556aa89f8f9 | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| dialogue-parser | 0 | S0 / final | b03cd9af3f67a87f5e00cd351b6db01b36160f37f564338466dbc5bdba359d71 | MEASURED | False | 0.833 | 5 | 6 | 0.833333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| dynamic-object-aware-egomotion | 0 | S0 / final | 6c91519ed751eefd7714aeddc0b2dc7f129834913a7d2ce5e4ac5492457f6946 | MEASURED | False | 0 | 9 | 11 | 0.818182 | reporter_group | NoSkill | 0 | 0 | -9.09091 | MEASURED |
| earthquake-plate-calculation | 0 | S0 / final | 8dc6d3c0a62342364c69a21ca8618dd5e0e3bc422106ae9640c540d4c245a637 | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 1 | 1 | 12.5 | MEASURED |
| econ-detrending-correlation | 0 | S0 / final | 5cb9aca5f43c019df576edc1fbc2c45619c506fb2bdbc55f4207573c3a9aabea | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| energy-ac-optimal-power-flow | 0 | S0 / final | b2e79dc0f76b96ae2439195dab5ab0028a45df71d66e3b5df89c3d9a7a458cff | MEASURED | True | 1 | 23 | 24 | 0.958333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| energy-market-pricing | 0 | S0 | f2ea4f415d4b67869d8461e0681b2b564ff30bcec9566b3ab3e8a5b15702c418 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| energy-market-pricing | 1 | S1 / final | 161743614bf480ab03172d3edb9247f875c1e73e965be8986bae44b69de24d7c | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| enterprise-information-search | 0 | S0 / final | 50b657494a3d2005b1fa9afcc77876eec5278cc294904815f672d490a9fcc7a7 | MEASURED | False | 0 | 1 | 3 | 0.333333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| exceltable-in-ppt | 0 | S0 | 7de92832cbf2476ffdce9550f5d1f1167c2c2d4ea9eb44cd85c26bac50e46e23 | MEASURED | False | 0 | 6 | 8 | 0.75 | reporter_group | NoSkill | -1 | -1 | -25 | MEASURED |
| exceltable-in-ppt | 1 | S1 | 1fa4871a70b3b25fa71fe0bbda9776141649a644de91239c77e1e5d51ed38e2d | MEASURED | False | 0 | 6 | 8 | 0.75 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| exceltable-in-ppt | 2 | S2 / final | f2e7264c6ea38aab28507af0953ef2c7c607f5a58437672512c0ab05719392d9 | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | S1 | 1 | 1 | 25 | MEASURED |
| exoplanet-detection-period | 0 | S0 | 5bf54e8fae2bd432f251475999615baf4f6d700ebe82a11833951a6e5d4e46a3 | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | -1 | -1 | -25 | MEASURED |
| exoplanet-detection-period | 1 | S1 / final | eeba115bb20bf251e66be626a595d73569a7d9d0c3ed387eaedfbf0dfba4f4b4 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | S0 | 1 | 1 | 25 | MEASURED |
| financial-modeling-qa | 0 | S0 / final | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c | MEASURED | False | 0 | 1 | 4 | 0.25 | reporter_group | NoSkill | 0 | 0 | -50 | MEASURED |
| find-topk-similiar-chemicals | 0 | S0 / final | 474882f7e1c39dda849a82e59e9f21ac1bb9ba7d1f92fd91796b54a468ed63b4 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| fix-build-agentops | 0 | S0 / final | a7213d28722786c84ac645ff3053e5b61df7e158f8a9603aa37e5355c0aaf11d | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group | NoSkill | -1 | -1 | -33.3333 | MEASURED |
| fix-build-google-auto | 0 | S0 / final | 7dfd4e2bda712cc6f30d8c1a4dddb5f9023b7eb410779dd08aa79b7d285ac8a4 | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group | NoSkill | 1 | 1 | 33.3333 | MEASURED |
| fix-druid-loophole-cve | 0 | S0 / final | eb0b4752e409f4b5a7a3e918b5226be566049997415524c6bdc46dbafcc6c676 | MEASURED | False | 0 | 2 | 4 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| fix-erlang-ssh-cve | 0 | S0 / final | a97574d3c90fc49c91669ecac453afcbf599da264a9cfa9a56304a01e07b1280 | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group | NoSkill | 1 | 1 | 100 | MEASURED |
| fix-visual-stability | 0 | S0 / final | 3b1d439f9fe796b28d127ffd621896f48533519080c424888d04828c1d1e08ca | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | NoSkill | 1 | 1 | 16.6667 | MEASURED |
| flink-query | 0 | S0 / final | 7d4ec17caa18381ea7f6c6ec19b3e0d0bc6e0774bf14dbde56232a1645059f00 | MEASURED | True | 1 | 3 | 3 | 1 | reporter_group | NoSkill | 1 | 1 | 33.3333 | MEASURED |
| flood-risk-analysis | 0 | S0 / final | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 50 | MEASURED |
| gh-repo-analytics | 0 | S0 / final | bef80667dd2f615eee524ed6e8f4b62f3d5e3225219cb02cce23ce25042b0abe | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| glm-lake-mendota | 0 | S0 / final | c264103d4691e66775ba8c33bb18593c8b6c9ad377fba2e5b2c1f5ce901270b3 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| gravitational-wave-detection | 0 | S0 | e2e42e5efa72f05da4e8f48a755fb3f8131d6baaf97e3129bc24d21a46a5dfe5 | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| gravitational-wave-detection | 1 | S1 / final | b7abb0faac41d8be637d3877197ea43459522e626acdbadc8f7ef9ed88360c22 | MEASURED | True | 1 | 9 | 9 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| grid-dispatch-operator | 0 | S0 | 600ca610344f8e6b59fc4117b5b665b2fd1435e603a3de42e361d131ea2b1d0a | MEASURED | False | 0 | 4 | 6 | 0.666667 | reporter_group | NoSkill | 0 | 0 | -16.6667 | MEASURED |
| grid-dispatch-operator | 1 | S1 / final | 3df6709248a38e3f2d6383f55f6b959002ccfd6a096b9aac5fb059715249884c | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group | S0 | 0 | 0 | 16.6667 | MEASURED |
| hvac-control | 0 | S0 | b07b1cf7b9b9966fbfcaa45c81ac00fc4733c09edb88a81284f2841cb4b2d7b9 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| hvac-control | 1 | S1 / final | 816d05dff6ee9af2754780202159116afbe7707698d3f5158bd0c401b9d6b268 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| invoice-fraud-detection | 0 | S0 / final | dc3e0d70232f873c3bd6bbe1a6dc0835d5c58138e9ec5b642f117ca3364cea3f | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | -1 | -1 | -50 | MEASURED |
| jax-computing-basics | 0 | S0 | 660c77324767dbca9e559f67f492b929b5927b2afed702c0d0e342c9dd3a6012 | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| jax-computing-basics | 1 | S1 | 16235310c757f0cb5589532f0a3a23ca203c6b4997e931cd2b4b00bfe9bed2da | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| jax-computing-basics | 2 | S2 / final | bdbf14080cabf8ccadf15635a9e7834bd42030d03b4a17d3ec5148ec4fa79aca | MEASURED | False | 0 | 4 | 5 | 0.8 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| jpg-ocr-stat | 0 | S0 | 4d70ff93860353cf2b7c32d0cf4d4039f5830c7097749a6b2a5a580e5d12528d | MEASURED | False | 0 | 0 | 1 | 0 | reporter_group | NoSkill | -1 | -1 | -100 | MEASURED |
| jpg-ocr-stat | 1 | S1 / final | 61364680d928c420f52752e4578027f032862b21824a6a93b769dbecfdea5c4c | MEASURED | False | 0 | 0 | 1 | 0 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| lab-unit-harmonization | 0 | S0 / final | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 | MEASURED | False | 0.354 | 17 | 48 | 0.354167 | reporter_group | NoSkill | 0 | -0.25 | -25 | MEASURED |
| lake-warming-attribution | 0 | S0 / final | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| latex-formula-extraction | 0 | S0 | cbef3317c6e3115d03df68b07dd1e53689e69f81572df126a7e466b213e3fd94 | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| latex-formula-extraction | 1 | S1 | a7d4d5a3cd61a00fe681fcf841aa39b49ccb0fac46eddb299f669e1655cf9c60 | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| latex-formula-extraction | 2 | S2 | 6424400c0a54a2717bb0435e199754f3c886984d2596bdb4889f01511c44b8ae | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| latex-formula-extraction | 3 | S3 | 0613b981bf7180aed8274b295e421b4388c42d90898b10bf4cbedf75e81f6e75 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S2 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| latex-formula-extraction | 4 | S4 / final | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | S3 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| lean4-proof | 0 | S0 / final | 41ead0e1d3fc8734d8df461bb34d2b90b88a551bb85ce881d1f635f3f5e62b8c | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| manufacturing-codebook-normalization | 0 | S0 | 465abeb489bac48794ca901bfff11bcae08defffe11f9dcba7d5f9a7099e4d78 | MEASURED | False | 0 | 14 | 16 | 0.875 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| manufacturing-codebook-normalization | 1 | S1 / final | feb6ea42edbb538b40cf07e8e447875b67a638c99f91e5c707a2f45c95870b9b | MEASURED | False | 0 | 14 | 16 | 0.875 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| manufacturing-equipment-maintenance | 0 | S0 / final | e16dbd658448b7567265c801752ca784edf206b1ea43b00338578444c737fea6 | MEASURED | True | 1 | 7 | 7 | 1 | reporter_group | NoSkill | 1 | 1 | 14.2857 | MEASURED |
| manufacturing-fjsp-optimization | 0 | S0 | 1faff32c8adcac80b91cee9dbb31d2ae6bb9714a891372fffb2aa55202138b3f | MEASURED | False | 0 | 1 | 15 | 0.0666667 | reporter_group | NoSkill | 0 | 0 | -80 | MEASURED |
| manufacturing-fjsp-optimization | 1 | S1 | ba2189961a2781ca4915c7c42829fad105d167e1088cc0826f80ce65cb06aed6 | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group | S0 | 0 | 0 | 80 | MEASURED |
| manufacturing-fjsp-optimization | 2 | S2 | 9793ea768761e8e506ff138988d0bea653cc1c6bb51ee74da3ecc8cdb7b64d15 | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| manufacturing-fjsp-optimization | 3 | S3 | bc1e95f0d1d569fa97cbea52398e27fd837a2def17ace5b48e2ace2d1dccf5eb | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group | S2 | 0 | 0 | 0 | MEASURED |
| manufacturing-fjsp-optimization | 4 | S4 / final | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | MEASURED | False | 0 | 13 | 15 | 0.866667 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| mario-coin-counting | 0 | S0 / final | 45d8e35cf1d1291b49b78b669169f1035afbdef72aefe09e9646e0cda57eecb3 | MEASURED | False | 0 | 2 | 3 | 0.666667 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| mars-clouds-clustering | 0 | S0 / final | e575d8b7e638551a03933739d25fbb97092aecee9e89037f2c5588b7704305e5 | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| multilingual-video-dubbing | 0 | S0 / final | 3b91369dd8f1c8ed78c0559daf38921179c27dbd54ee19906778fded33d3afe5 | MEASURED | False | 0 | 7 | 8 | 0.875 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| offer-letter-generator | 0 | S0 | 3196793c4e1f5b3c5633a271d4b22ca9ff683025c81f4b1ec45d91d4683e11f0 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| offer-letter-generator | 1 | S1 / final | 93b73afba1fba540b6468aef721231f8e32b1fb78ea37b71ec5c5bec2611d985 | MEASURED | True | 1 | 4 | 4 | 1 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| organize-messy-files | 0 | S0 | 27021ff8cf53a42ff1a9ca3af4bd36e6ed1c643ef4412ee59434b6f9543ed94e | MEASURED | False | 0 | 4 | 6 | 0.666667 | reporter_group | NoSkill | -1 | -1 | -33.3333 | MEASURED |
| organize-messy-files | 1 | S1 | f657f8ffd62765dc955588d9fbdbc48c111000c2024c05cdc2166abe6e76cc64 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S0 | 1 | 1 | 33.3333 | MEASURED |
| organize-messy-files | 2 | S2 / final | e4492d2ca2c6721a2b97b4999f91b33608c404d047bf5b36c65d88c8c5a30e3c | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| paper-anonymizer | 0 | S0 | 3e0242d6e8fe5d984bbe5d3cb928079e26af6c62816626a3dcb166a2455d2466 | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| paper-anonymizer | 1 | S1 | eae20ae6f4df354ee437b4c9d18fdb3db9cf5ca8035eef3b6b41d368afdab070 | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| paper-anonymizer | 2 | S2 | e8bb2fff5da5bf0c062487ae63d38057f9718284bf8f47a278bb56a7ff48d321 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S1 | 1 | 1 | 16.6667 | MEASURED |
| paper-anonymizer | 3 | S3 | ba38faaa033d8da01dbfaf470386f825b1140e4f5fa4f6e74b94a32a62ab0c00 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S2 | 0 | 0 | 0 | MEASURED |
| paper-anonymizer | 4 | S4 / final | 0d05be53f10055d33ce50baf5f27fcd3aba352a570134cff531fb28da6df6a56 | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| parallel-tfidf-search | 0 | S0 / final | 9213db5ff59c3ae9f0bcddf7647c7d3b58080a483cd12800c8733c0b5bb2ceb5 | MEASURED | True | 1 | 5 | 5 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| pddl-tpp-planning | 0 | S0 / final | 511601c678d0d81f4b7253e157f2f0892b24c0439a2a7343d1b2a91cc75e0ab7 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| pdf-excel-diff | 0 | S0 | 224fb6467b1a855d9093480be5ef1251038eb318e20fdfdf4f23712542b4b947 | MEASURED | False | 0 | 6 | 11 | 0.545455 | reporter_group | NoSkill | 0 | 0 | -18.1818 | MEASURED |
| pdf-excel-diff | 1 | S1 / final | a05b25dd11513b2f6d989a08518332eca8693a3b450986cd1e8a51b8b5ef8d0b | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group | S0 | 1 | 1 | 45.4545 | MEASURED |
| pedestrian-traffic-counting | 0 | S0 / final | 48e57982af63eee755368d996cf607de0bb50681b4f33f0b26d9e2fe3d42ac28 | MEASURED | False | 0 | 0 | 1 | 0 | reporter_group | NoSkill | 0 | -0.75 | 0 | MEASURED |
| powerlifting-coef-calc | 0 | S0 / final | bf4e639a42514c25ebdab56b51521c073ec296b9bc33639633a169bf3395efe1 | MEASURED | True | 1 | 11 | 11 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| pptx-reference-formatting | 0 | S0 / final | e48121b37732b73b5946ae0c415652abb65ee258ac002ecf0f194f71899391e1 | MEASURED | False | 0 | 11 | 12 | 0.916667 | reporter_group | NoSkill | -1 | -1 | -8.33333 | MEASURED |
| protein-expression-analysis | 0 | S0 | 81256fb72c6350a0f0659c3e336e6eceb7d60f28b16a6b0628cf7c87c08dd727 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| protein-expression-analysis | 1 | S1 | 66eb5c918aa88fe8ee6b392f9033023a55b8c8c23c1349eb13995430994f1302 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S0 | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| protein-expression-analysis | 2 | S2 | 6bdcec029c4760f5213ca01899fab3864977a8d8a070750d39ee940fc839e62e | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S1 | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| protein-expression-analysis | 3 | S3 / final | 23620adecc6050a2c6587d671a071977484a90f36cf1d504a78849e24da2c095 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | S2 | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| python-scala-translation | 0 | S0 / final | 4df8c2cdf612d8929e21b5282a8a534100f47861d199fc0603260fc1fbc24e83 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| quantum-numerical-simulation | 0 | S0 | 04a673705ff99deaa10963b508f249b29e1a28c5d75515522c45a71013ad4941 | MEASURED | False | 0 | 0 | 7 | 0 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| quantum-numerical-simulation | 1 | S1 / final | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a | MEASURED | False | 0 | 6 | 7 | 0.857143 | reporter_group | S0 | 0 | 0 | 85.7143 | MEASURED |
| r2r-mpc-control | 0 | S0 | 858bd1084ee9f0bd70d2d6260d6ee48b7da6e378a26a17768a9188734fad3043 | MEASURED | False | 0 | 5 | 6 | 0.833333 | reporter_group | NoSkill | -1 | -1 | -16.6667 | MEASURED |
| r2r-mpc-control | 1 | S1 / final | 38a340ea68ac9c79fe1894f4c393b4527ee0e91fde7ae401204870861102d96a | MEASURED | True | 1 | 6 | 6 | 1 | reporter_group | S0 | 1 | 1 | 16.6667 | MEASURED |
| react-performance-debugging | 0 | S0 / final | eaae4e341e857d878afc40ff5148ca5d0c7e5538fb5716491c44a420ee5f3890 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| reserves-at-risk-calc | 0 | S0 | c753e52b9457a796463ff14aa64cdb9e018ddd3141d8e0f0a01965caa4ec5cd9 | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| reserves-at-risk-calc | 1 | S1 | bfca50b340280f553e49f14f99fd7fe4b4e3bb411dfce2b2d452a5ba19b27bb7 | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| reserves-at-risk-calc | 2 | S2 | 61358ae426889af7e0181f8a454e2e8c0e869c4dbc1beae49ea2c821c35e66a0 | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| reserves-at-risk-calc | 3 | S3 | d4d0e7014af453348045a5095d6a1e5cf7bf51854f6c548ff42236c318d8069a | MEASURED | False | 0 | 1 | 5 | 0.2 | reporter_group | S2 | 0 | 0 | -20 | MEASURED |
| reserves-at-risk-calc | 4 | S4 / final | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | MEASURED | False | 0 | 1 | 5 | 0.2 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| sales-pivot-analysis | 0 | S0 | 66aeec8f099f18dc5f0fc7a7f900a206b15954872d52cb5b30909ec0d038d0b1 | MEASURED | False | 0 | 7 | 10 | 0.7 | reporter_group | NoSkill | 0 | 0 | 10 | MEASURED |
| sales-pivot-analysis | 1 | S1 | eb87def1e09dae0d979f173da600944f646cf607fbd68263e3eba4c332016159 | MEASURED | False | 0 | 7 | 10 | 0.7 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| sales-pivot-analysis | 2 | S2 | 9f017f1cfcdba2c09b27013572222114cc541db7c4b285813757043daf8537d7 | MEASURED | False | 0 | 7 | 10 | 0.7 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| sales-pivot-analysis | 3 | S3 | fb7e8b387fb8230135d4e889002d33034eba1333d362710cb912de94289ecb8c | MEASURED | False | 0 | 7 | 10 | 0.7 | reporter_group | S2 | 0 | 0 | 0 | MEASURED |
| sales-pivot-analysis | 4 | S4 | 76caf2887be9030d4d91e8b04f942943cb1770c1e7dab420328db316187e048a | MEASURED | False | 0 | 7 | 10 | 0.7 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| sales-pivot-analysis | 5 | S5 / final | 1260ef1857b1c5b47256211644dc27dbe22ddaf954cd77b4ee1e311dde8926d8 | MEASURED | False | 0 | 7 | 10 | 0.7 | reporter_group | S4 | 0 | 0 | 0 | MEASURED |
| sec-financial-report | 0 | S0 / final | 91ce320fcadeb466a8337229b0cdc59cd4fc6b1ad244f228bbba19a388810b59 | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| setup-fuzzing-py | 0 | S0 / final | 1631882c531b733ca2692450ee4ba74b80f17ca29a6aa6d6272953825abd7fa0 | MEASURED | True | 1 | 2 | 2 | 1 | reporter_group | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| shock-analysis-demand | 0 | S0 / final | 39a095d8a35fe77b8e5cce111d278d24f95dce54cbdfb8d67a22972542c564a4 | MEASURED | False | 0 | 2 | 5 | 0.4 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| shock-analysis-supply | 0 | S0 | 5ab3e34ddfbaff5e0a828b1dc99189d138aa26ef26fe773862c1e4fffe9c97f0 | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| shock-analysis-supply | 1 | S1 | c2961840af68d13e46ba1f5e57d02003adb6e99ae292cc007543f9929b082089 | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| shock-analysis-supply | 2 | S2 | 7a02bab913191b567bb7a9d68463c5caad883f9d6c207b627598ce1147ad5b64 | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| shock-analysis-supply | 3 | S3 | 227d67baf85397c2b2642545f700894d3b273598997364bf48ee4e07b974b6e3 | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group | S2 | 0 | 0 | 0 | MEASURED |
| shock-analysis-supply | 4 | S4 / final | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | MEASURED | False | 0 | 1 | 9 | 0.111111 | reporter_group | S3 | 0 | 0 | 0 | MEASURED |
| software-dependency-audit | 0 | S0 / final | 0e6abe2d242579d9aaaf5fd64dd151c851c9bf7e720b64793e0388da3425378d | MEASURED | False | 0 | 3 | 4 | 0.75 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| speaker-diarization-subtitles | 0 | S0 | d85695c5a88f60b7131b6875b5a040f0a57fb0feb598e4f821e74ef0953115cf | MEASURED | False | 0 | 0 | 10 | 0 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| speaker-diarization-subtitles | 1 | S1 | 72ee2f7e3df1cebbd31705f067eb1495487f9a86f71db9e3fe609884031e1d61 | MEASURED | False | 0 | 6 | 10 | 0.6 | reporter_group | S0 | 0 | 0 | 60 | MEASURED |
| speaker-diarization-subtitles | 2 | S2 | 5b5241805e5d6698b6d42964326eca88156bfed6820f8bedd6000cccae3c2f9d | MEASURED | False | 0 | 6 | 10 | 0.6 | reporter_group | S1 | 0 | 0 | 0 | MEASURED |
| speaker-diarization-subtitles | 3 | S3 / final | 0a0884013e244f261e8cbea7133e57c77bcc33186b1a6bbfea8f5b281b84c335 | MEASURED | False | 0 | 6 | 10 | 0.6 | reporter_group | S2 | 0 | 0 | 0 | MEASURED |
| spring-boot-jakarta-migration | 0 | S0 / final | 14ac963f3dabcc7459b01ba782d1b2daebca508808919e2f34ad9f892a4207cc | MEASURED | True | 1 | 10 | 10 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| suricata-custom-exfil | 0 | S0 / final | ef63919d52681e683b8a023a459ea5a87f89dd12f0a9e5fdaef234c2c10d8557 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | 0 | 0 | NOT_MEASURED | official_checks_not_measured |
| syzkaller-ppdev-syzlang | 0 | S0 / final | 012d37a242cd16c0c83cc38b2142dd9cf76dbbf78f99b661adabf78f90539d53 | MEASURED | False | 0 | 5 | 7 | 0.714286 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| taxonomy-tree-merge | 0 | S0 | 75f929e7aa4f4608e62e3263c893b5e0b54c611caf60663850c5942effaa9966 | MEASURED | False | 0.8731 | 19 | 22 | 0.863636 | reporter_group | NoSkill | 0 | 0.0116 | 0 | MEASURED |
| taxonomy-tree-merge | 1 | S1 / final | 84721b028d57c8ec807157ee26bbec33b599c2517895c4e36f251eccfd5e1406 | MEASURED | False | 0.8731 | 19 | 22 | 0.863636 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| travel-planning | 0 | S0 | aa2939439a7419dcb40724ba3ea3ec86541da4c01a07be5a9bcaf273bc97ce14 | MEASURED | False | 0 | 0 | 10 | 0 | reporter_group | NoSkill | -1 | -1 | -100 | MEASURED |
| travel-planning | 1 | S1 / final | 0214c994e0d6bcbae2f735243ce74433a0b09d71e9e97885f931af1f357bf5cd | MEASURED | True | 1 | 10 | 10 | 1 | reporter_group | S0 | 1 | 1 | 100 | MEASURED |
| trend-anomaly-causal-inference | 0 | S0 / final | 95bb5417c7b20b9e5aa215bccb9096c9f80055a48b0930a4d4a8aed99f7e111d | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NoSkill | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |
| video-filler-word-remover | 0 | S0 / final | 2623781ecbfa00291ba5f594a4708a5e9190efb9fe0e0b467c6dee791faf423e | MEASURED | False | 0 | 1 | 5 | 0.2 | reporter_group | NoSkill | 0 | 0 | -60 | MEASURED |
| video-silence-remover | 0 | S0 | fc4e71f6b51c20ad78bf4c4299321f3f84e0881eaf749e7275fc946e702c5741 | MEASURED | False | 0 | 5 | 9 | 0.555556 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| video-silence-remover | 1 | S1 / final | 86b62ddbd3c5e1bb3c9568cad064c571c633be832a88d657dcc9f82f9d233ac4 | MEASURED | False | 0 | 5 | 9 | 0.555556 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| video-tutorial-indexer | 0 | S0 / final | 99823184cf3a795bc62a3949ebc6768f075e024d9037e171cca5b63ce244cbfd | MEASURED | False | 0 | 0 | 2 | 0 | reporter_group | NoSkill | -1 | -1 | -100 | MEASURED |
| virtualhome-agent-planning | 0 | S0 | 6091ff79f098ab4cca7f09525a811ec9689482a9c37abfd1a7dd9f0e71506f79 | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |
| virtualhome-agent-planning | 1 | S1 / final | 42aae521f25ce12db31646983cf4bbead757c31ddad75da6b611ee78bb3b5491 | MEASURED | False | 0 | 1 | 2 | 0.5 | reporter_group | S0 | 0 | 0 | 0 | MEASURED |
| weighted-gdp-calc | 0 | S0 / final | c9a2ce01aaabd97e73919e4e4edb0caf5031e03a8017e988a94697236750aa57 | MEASURED | False | 0 | 25 | 27 | 0.925926 | reporter_group | NoSkill | 0 | 0 | 37.037 | MEASURED |
| xlsx-recover-data | 0 | S0 / final | 6080d1f989a3853f76465a484b814c34dd3ffafd144fed90d8e6fdccb13bac3d | MEASURED | True | 1 | 8 | 8 | 1 | reporter_group | NoSkill | 0 | 0 | 0 | MEASURED |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | bff6fae0fd072978bb4629c9ac4d12ce961d8ce7129eb92375752f662a7c7719 | 0 | fa887fcc079ef85069ec4d55b9c4f3168799816c9cdffdd5f5f22cdfc8574e4e | False | 0 | NOT_MEASURED |
| 3d-scan-calc | 343d4ed35a785abe79638a536a887add8f61c9ee464b38f51678b0ccbb192684 | 0 | fa887fcc079ef85069ec4d55b9c4f3168799816c9cdffdd5f5f22cdfc8574e4e | False | 0.5 | NOT_MEASURED |
| 3d-scan-calc | cfc7c7cc0254531504df6317df468c8df43a6766355388f7b98feeb22e549198 | 0 | fa887fcc079ef85069ec4d55b9c4f3168799816c9cdffdd5f5f22cdfc8574e4e | True | 1 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 2ba1f557587815b13fb3e4422b4ce3684bc6a67681058aaaae30b6dd0a18f404 | 0 | 1eec6a3cd72f9dd7c0be8fd2c7596d8cfaf4be724012b11d4e4e0ffd667dc3c1 | False | 0 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 | 0 | 1eec6a3cd72f9dd7c0be8fd2c7596d8cfaf4be724012b11d4e4e0ffd667dc3c1 | True | 1 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 | 1 | ff5a96acca8e3f44f7b2bc94ade4f623385364d541aadc1fbcb154cf9d8d0ee8 | True | 1 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 | 2 | 351a0239849cb6b2fe922d713dcffe87eb72aaf9aa56722c195d78d025227820 | True | 1 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 | 3 | b98ae012a61cca207b06ee964ebacf9b45b063e5ccf54fe4b9874167940441db | True | 1 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 4001514e82dbc183d3c4a3ae4726f8e09e27c47188dd2659bc7fb66e97ac8a68 | 4 | 1633aface502873cc6548acd78f0ec5ff7f4104bed6e1d80a6dff5278e0be5bc | True | 1 | NOT_MEASURED |
| citation-check | bfdb6bbda7a618d5fd80f1f1c8aae6f1314e779afc8319fc427fb49c0c0080e8 | 0 | d0584a7aee854323489db254d9bb4c9e5271c9f6298cea0e56435fbdf9d15328 | False | 0 | NOT_MEASURED |
| citation-check | 6d22f31de36a44e6b4ec2970bbd2dfe513c21da8ae8652d432102aff830b20b3 | 0 | d0584a7aee854323489db254d9bb4c9e5271c9f6298cea0e56435fbdf9d15328 | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | a75306aba64a101d90fc87e6181afb41cf5b9dfce610fe02d915adda09f40fcf | 0 | 29cde8384c510da1d17045cfa8f56f63210a97c783ce04984a25ca6e523e7fc9 | False | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | b1e95db2cec5fc093dc50ee70e199b1bf267749a17cf1fcfb312cc11c7ae052f | 0 | 29cde8384c510da1d17045cfa8f56f63210a97c783ce04984a25ca6e523e7fc9 | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | b1e95db2cec5fc093dc50ee70e199b1bf267749a17cf1fcfb312cc11c7ae052f | 1 | 3d6d6b71db4baebbf7a434ac7e2361afecb667b06bccb3f3d359aa5a0e64a430 | True | 1 | NOT_MEASURED |
| court-form-filling | 9510098a7db74e4b93ae80c7d5e77cf0f1e2715b447dcb1a5a331e66d9336212 | 0 | 7714f0b4d19eee36d5cd70fc48ed27487ee25e883a4f4dbf4ad92fbe3b84c5ba | True | 1 | NOT_MEASURED |
| court-form-filling | 9510098a7db74e4b93ae80c7d5e77cf0f1e2715b447dcb1a5a331e66d9336212 | 1 | 5b96d7ad2611d72282881e6589bc21788a659fb377af874995051663523c0c86 | False | 0.8 | NOT_MEASURED |
| court-form-filling | 95e0e3a784c7c6c28c2831f7b6d501113b37739833af82ad7fe770c00c56f6b5 | 1 | 5b96d7ad2611d72282881e6589bc21788a659fb377af874995051663523c0c86 | False | 0.8 | NOT_MEASURED |
| court-form-filling | 9e2dc62c1e223ee9dcfcc3d38e14e35fd90fb124300f27b3f7b718f2685e4e6d | 1 | 5b96d7ad2611d72282881e6589bc21788a659fb377af874995051663523c0c86 | False | 0.8 | NOT_MEASURED |
| court-form-filling | 59958fa295054af4783c1b38754e7d4dd13ed87b6335ba55af5a946c1e765aac | 1 | 5b96d7ad2611d72282881e6589bc21788a659fb377af874995051663523c0c86 | False | 0.8 | NOT_MEASURED |
| court-form-filling | 59958fa295054af4783c1b38754e7d4dd13ed87b6335ba55af5a946c1e765aac | 1 | 2695fbf3cbfe1419b2c6d1a59406889c9a8cab1c18707be92c16064201383f7e | False | 0.8 | NOT_MEASURED |
| court-form-filling | 211cdb9cff698ae0e5f25c6ad9a4feda472ce44cb660c4aee9636baad08727a4 | 1 | 2695fbf3cbfe1419b2c6d1a59406889c9a8cab1c18707be92c16064201383f7e | False | 0.8 | NOT_MEASURED |
| court-form-filling | 7f65579269d00ba11cc32d968faceae13952a161a7d7a3cf43c05af4a0f42b5c | 1 | 2695fbf3cbfe1419b2c6d1a59406889c9a8cab1c18707be92c16064201383f7e | True | 1 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | 729954f5e053fec3d923ea388dbf347123713d1d171fc8d625a7eaa65a56562e | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | 94077ec300b500d2e6af1cbfbb02efa223adabfca765b020d41bda39c1b75712 | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | a016f9fad4e2b7cab53605ca2eaf59ed8dec5f31186a1f90705a3bfd055c679d | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | a016f9fad4e2b7cab53605ca2eaf59ed8dec5f31186a1f90705a3bfd055c679d | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | a016f9fad4e2b7cab53605ca2eaf59ed8dec5f31186a1f90705a3bfd055c679d | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | a016f9fad4e2b7cab53605ca2eaf59ed8dec5f31186a1f90705a3bfd055c679d | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | d120e9917709156738a1446b7b6526c7fa8a167b00f8262be05fa5528c8ab0a5 | 0 | 0f73dd4cd7753f650e11ba18d810e5982703360315ca2b6e8a8fd4eea6adeb16 | False | 0 | test_repair_failed |
| data-to-d3 | 3415926e072e1604a3bb4dca4bbaf425dd77244357685c1fb0d6a32c5505983f | 0 | 235d00cdb0b9efb3aed12808970b5a8558bdd08111bbf2c3cc9e29171040153d | False | 0.5 | NOT_MEASURED |
| data-to-d3 | 0ca6a1a1cc5abf8082bc397edd1ef9ce96f0fdbbfe0e4a1569145556aa89f8f9 | 0 | 235d00cdb0b9efb3aed12808970b5a8558bdd08111bbf2c3cc9e29171040153d | True | 1 | NOT_MEASURED |
| data-to-d3 | 0ca6a1a1cc5abf8082bc397edd1ef9ce96f0fdbbfe0e4a1569145556aa89f8f9 | 1 | eebdf5430ca355913af068f3a8625295823d1ce3dd929a83a94ccc5fdfe36ddc | True | 1 | NOT_MEASURED |
| data-to-d3 | 0ca6a1a1cc5abf8082bc397edd1ef9ce96f0fdbbfe0e4a1569145556aa89f8f9 | 2 | 53cf276efbb84a44dfa238ae5ea81fd529355f009af6fdb21ab8a1b36c49d1bc | True | 1 | NOT_MEASURED |
| data-to-d3 | 0ca6a1a1cc5abf8082bc397edd1ef9ce96f0fdbbfe0e4a1569145556aa89f8f9 | 3 | d0764e3fd922e1804df38180a3e2097568177d8a2f4630b0da694e3916d8f5cd | True | 1 | NOT_MEASURED |
| dialogue-parser | b03cd9af3f67a87f5e00cd351b6db01b36160f37f564338466dbc5bdba359d71 | 0 | b1df59568145a09d52d9a79b87e9c381c5250db1c07917f82b2b196e8effeeea | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 6c91519ed751eefd7714aeddc0b2dc7f129834913a7d2ce5e4ac5492457f6946 | 0 | 39383839fde2cf3563a4f7b47959355e9f531f7cec958339fdfea8104169a368 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 6c91519ed751eefd7714aeddc0b2dc7f129834913a7d2ce5e4ac5492457f6946 | 1 | 8c7603304cd0da8801ca4db8ccd5bbbd0a1fd8c4539ca555aae21a641532f12e | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 6c91519ed751eefd7714aeddc0b2dc7f129834913a7d2ce5e4ac5492457f6946 | 2 | c77859a3a908b604d4e8b1d1c693ef17eec6ae6917705d3aabf21ce1c20e4fbf | True | 1 | NOT_MEASURED |
| earthquake-plate-calculation | 8dc6d3c0a62342364c69a21ca8618dd5e0e3bc422106ae9640c540d4c245a637 | 0 | bff25f5e0942bd038c0ffe76a424e7ab2c89d16eeebbefd72ebb8dae3f92cc56 | True | 1 | NOT_MEASURED |
| econ-detrending-correlation | 5cb9aca5f43c019df576edc1fbc2c45619c506fb2bdbc55f4207573c3a9aabea | 0 | 59761c0f1a40d0383a708617953273ba29f44cc5d75687a528021c661942f863 | True | 1 | NOT_MEASURED |
| energy-ac-optimal-power-flow | b2e79dc0f76b96ae2439195dab5ab0028a45df71d66e3b5df89c3d9a7a458cff | 0 | b0af09b441c9233cc15c6b74be1eca9af57c5a7794170930d4010bfedd32e98e | True | 1 | NOT_MEASURED |
| energy-market-pricing | f2ea4f415d4b67869d8461e0681b2b564ff30bcec9566b3ab3e8a5b15702c418 | 0 | 418e0fa165a12a70b3925aeaac043e5ba21e029db424f738339d27b593ba558c | False | 0 | NOT_MEASURED |
| energy-market-pricing | 161743614bf480ab03172d3edb9247f875c1e73e965be8986bae44b69de24d7c | 0 | 418e0fa165a12a70b3925aeaac043e5ba21e029db424f738339d27b593ba558c | False | 0.75 | NOT_MEASURED |
| energy-market-pricing | 161743614bf480ab03172d3edb9247f875c1e73e965be8986bae44b69de24d7c | 0 | 418e0fa165a12a70b3925aeaac043e5ba21e029db424f738339d27b593ba558c | False | 0 | timeout |
| enterprise-information-search | 50b657494a3d2005b1fa9afcc77876eec5278cc294904815f672d490a9fcc7a7 | 0 | abfe1b645a7d05f3cd6628c2c5680469f32e7eb6481018dd2328c62c3f454dca | True | 1 | NOT_MEASURED |
| enterprise-information-search | 50b657494a3d2005b1fa9afcc77876eec5278cc294904815f672d490a9fcc7a7 | 1 | e871673136b1a27f12bc3cf6360662d43a9968ebb02c97ae584125414c73a37f | True | 1 | NOT_MEASURED |
| enterprise-information-search | 50b657494a3d2005b1fa9afcc77876eec5278cc294904815f672d490a9fcc7a7 | 2 | 930ab22daba105b031c578f34361166f323b9f64213a0818e8d9d8c12560c7b7 | True | 1 | NOT_MEASURED |
| enterprise-information-search | 50b657494a3d2005b1fa9afcc77876eec5278cc294904815f672d490a9fcc7a7 | 3 | f03d530baff395f986a1108b801f19e87abc363d44df7c0c40bb503366ec807f | True | 1 | NOT_MEASURED |
| exceltable-in-ppt | 7de92832cbf2476ffdce9550f5d1f1167c2c2d4ea9eb44cd85c26bac50e46e23 | 0 | 1e1b672c9fc0d78c1502156ee9a0e8bc277f38e6129608017ffee3d3bb336ffd | False | 0 | NOT_MEASURED |
| exceltable-in-ppt | 1fa4871a70b3b25fa71fe0bbda9776141649a644de91239c77e1e5d51ed38e2d | 0 | 1e1b672c9fc0d78c1502156ee9a0e8bc277f38e6129608017ffee3d3bb336ffd | False | 0.333333 | NOT_MEASURED |
| exceltable-in-ppt | f2e7264c6ea38aab28507af0953ef2c7c607f5a58437672512c0ab05719392d9 | 0 | 1e1b672c9fc0d78c1502156ee9a0e8bc277f38e6129608017ffee3d3bb336ffd | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | 5bf54e8fae2bd432f251475999615baf4f6d700ebe82a11833951a6e5d4e46a3 | 0 | fce6f28e35efe45ef4353af04aea84542d93f625b2e030d9f35a99dd8d1bc99a | False | 0 | NOT_MEASURED |
| exoplanet-detection-period | eeba115bb20bf251e66be626a595d73569a7d9d0c3ed387eaedfbf0dfba4f4b4 | 0 | fce6f28e35efe45ef4353af04aea84542d93f625b2e030d9f35a99dd8d1bc99a | False | 0 | timeout |
| financial-modeling-qa | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c | 0 | 7cb4a7a3d2de4f3b1b5eeaa3958e3232f60eccefd82252b5d73755ba81cd71be | True | 1 | NOT_MEASURED |
| financial-modeling-qa | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c | 1 | a593bb9377e4493ae33e211ab1062606c5b5d2250b69f0ff1e93512644ce8217 | True | 1 | NOT_MEASURED |
| financial-modeling-qa | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c | 2 | 69eba60510bfde530fac7a9c8eaaead17170b526be6c4f4a86bd93187a33420d | True | 1 | NOT_MEASURED |
| financial-modeling-qa | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c | 3 | 1ae75aabb2fce83a6f5473206a7c539ba579dc9295c6a7463bf55b3d47948c2d | True | 1 | NOT_MEASURED |
| financial-modeling-qa | 8cbaa50e66d7191f26fb08d1dd910148d9d28b06aaec8cf13c2ea9975b62934c | 4 | 19822bdadefb4908f49b85cf304e8acc78478c2e910134481789055a33c365a0 | True | 1 | NOT_MEASURED |
| fix-build-agentops | a7213d28722786c84ac645ff3053e5b61df7e158f8a9603aa37e5355c0aaf11d | 0 | 290d1c21789ff087c95e899fd0ea50ff9a38714f70044ecf164487fe644f7cc0 | True | 1 | NOT_MEASURED |
| fix-build-agentops | a7213d28722786c84ac645ff3053e5b61df7e158f8a9603aa37e5355c0aaf11d | 1 | 700badc107684cfad5bbdcb95959abfb0c281cef513d7aa3c89f4eac9fc025fc | True | 1 | NOT_MEASURED |
| fix-build-agentops | a7213d28722786c84ac645ff3053e5b61df7e158f8a9603aa37e5355c0aaf11d | 2 | 70deaee2acbdad1980a41c4e62d9333bafd5669739dece1fdb6b54aa42f4473c | True | 1 | NOT_MEASURED |
| fix-build-agentops | a7213d28722786c84ac645ff3053e5b61df7e158f8a9603aa37e5355c0aaf11d | 3 | a7b49d0152e3e7632af7630cf11fdbbe3dd35feaa2ba371abb4c4505412ff6cf | True | 1 | NOT_MEASURED |
| fix-build-google-auto | 7dfd4e2bda712cc6f30d8c1a4dddb5f9023b7eb410779dd08aa79b7d285ac8a4 | 0 | 3501c343551634a1e7e6e5cb0706675941e7554aea3d81c7093c206b9d5406a4 | True | 1 | NOT_MEASURED |
| fix-erlang-ssh-cve | a97574d3c90fc49c91669ecac453afcbf599da264a9cfa9a56304a01e07b1280 | 0 | d7f1e4376034303ab2fe8f2951ee693f12a69a13ed72e13537d788e6fd68882c | True | 1 | NOT_MEASURED |
| fix-visual-stability | 3b1d439f9fe796b28d127ffd621896f48533519080c424888d04828c1d1e08ca | 0 | 7bca703a488b92d006c6a0d65ef23fca4016f0f68c3ded47f1436f250e0b088a | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c | 0 | fab29e8826ccc57c962f671ea2fcf668dccdf54c0e1af91a44118cb4e9359927 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c | 1 | 9fc082d371e5cb84c72a7f6d2e3639c3887f561472409704481583f88edcaced | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c | 2 | 7cfc0a453c9a3f3d16f755654e5133177991bffb9ff0b75d16dd4cdb46d5a3f7 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c | 3 | ae58c5e1f641e4f0ef84a052b64787d8a9303a4b508731756ce3db027650893d | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 7b8c914cbf99a65d91f5ed924f35a5c20f10dcb63af591f4fba0fd225e43848c | 4 | 4b8e67d379de9a482eccb2d3e8c0b3220cb2cb2a163e732757bcd72a2613474f | True | 1 | NOT_MEASURED |
| gh-repo-analytics | bef80667dd2f615eee524ed6e8f4b62f3d5e3225219cb02cce23ce25042b0abe | 0 | dc6ccf8cc9258009c5cd783869b0d47de8f14fc37890c4fc3a099be2ca67c856 | True | 1 | NOT_MEASURED |
| gravitational-wave-detection | e2e42e5efa72f05da4e8f48a755fb3f8131d6baaf97e3129bc24d21a46a5dfe5 | 0 | 4e45a27963e7b5e3aeafd913cf1ba0a19c645d027c8fbc8ee719c59ef5dbe59c | False | 0 | NOT_MEASURED |
| gravitational-wave-detection | b7abb0faac41d8be637d3877197ea43459522e626acdbadc8f7ef9ed88360c22 | 0 | 4e45a27963e7b5e3aeafd913cf1ba0a19c645d027c8fbc8ee719c59ef5dbe59c | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 600ca610344f8e6b59fc4117b5b665b2fd1435e603a3de42e361d131ea2b1d0a | 0 | 18c489ac8095acd24c88b760777947f10ff9387e9ac8553283b5293a6bbd9dda | False | 0 | NOT_MEASURED |
| grid-dispatch-operator | 3df6709248a38e3f2d6383f55f6b959002ccfd6a096b9aac5fb059715249884c | 0 | 18c489ac8095acd24c88b760777947f10ff9387e9ac8553283b5293a6bbd9dda | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 3df6709248a38e3f2d6383f55f6b959002ccfd6a096b9aac5fb059715249884c | 1 | 5f33b11cf8dedec2c89853d08efa963790dfa5d67714d52eeb804d6472dc6ebe | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 3df6709248a38e3f2d6383f55f6b959002ccfd6a096b9aac5fb059715249884c | 2 | b8f03fcf424daf4c3469290c0e9d4388201aae972195ad6f99e6565c5db64d07 | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 3df6709248a38e3f2d6383f55f6b959002ccfd6a096b9aac5fb059715249884c | 3 | d85d87693ed4c5eb83728002ab5ca9567b1fb4ddc1e755b699720ea6e95523f7 | True | 1 | NOT_MEASURED |
| hvac-control | b07b1cf7b9b9966fbfcaa45c81ac00fc4733c09edb88a81284f2841cb4b2d7b9 | 0 | a2d2dc1a160c6dd6b9c1c83481c68f1cbc7fed344f215a084b44000967cfab8c | False | 0.5 | NOT_MEASURED |
| hvac-control | 816d05dff6ee9af2754780202159116afbe7707698d3f5158bd0c401b9d6b268 | 0 | a2d2dc1a160c6dd6b9c1c83481c68f1cbc7fed344f215a084b44000967cfab8c | True | 1 | NOT_MEASURED |
| jax-computing-basics | 660c77324767dbca9e559f67f492b929b5927b2afed702c0d0e342c9dd3a6012 | 0 | 65f9d40112cbe22a18d66669cb188470331a28250acdf9359477e40cc5a68bf3 | True | 1 | NOT_MEASURED |
| jax-computing-basics | 660c77324767dbca9e559f67f492b929b5927b2afed702c0d0e342c9dd3a6012 | 1 | d05853bcba696351e2c9ba585daae6c8cbfdc772856d404e157fdb902b02c81c | False | 0.833333 | NOT_MEASURED |
| jax-computing-basics | 16235310c757f0cb5589532f0a3a23ca203c6b4997e931cd2b4b00bfe9bed2da | 1 | d05853bcba696351e2c9ba585daae6c8cbfdc772856d404e157fdb902b02c81c | False | 0.833333 | NOT_MEASURED |
| jax-computing-basics | bdbf14080cabf8ccadf15635a9e7834bd42030d03b4a17d3ec5148ec4fa79aca | 1 | d05853bcba696351e2c9ba585daae6c8cbfdc772856d404e157fdb902b02c81c | True | 1 | NOT_MEASURED |
| jax-computing-basics | bdbf14080cabf8ccadf15635a9e7834bd42030d03b4a17d3ec5148ec4fa79aca | 2 | ab0c8c9fbca458fb8cbba75fcf7374976f8197152fd6c59cd5941019a4f145c2 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 4d70ff93860353cf2b7c32d0cf4d4039f5830c7097749a6b2a5a580e5d12528d | 0 | 9e7b2a3cff78cdadc492a1bb0404e88c2c3907ec86128660ab0133b8ed08769b | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 4d70ff93860353cf2b7c32d0cf4d4039f5830c7097749a6b2a5a580e5d12528d | 1 | ead7ed2adba66cd27b77ad070fd8cf21c199e56baac2302babe91975a7e24187 | False | 0.666667 | NOT_MEASURED |
| jpg-ocr-stat | 61364680d928c420f52752e4578027f032862b21824a6a93b769dbecfdea5c4c | 1 | ead7ed2adba66cd27b77ad070fd8cf21c199e56baac2302babe91975a7e24187 | True | 1 | NOT_MEASURED |
| lab-unit-harmonization | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 | 0 | 076717be488e6845ac8da3ae06863a03c595d8caa3a944f3a07a7fadcb9679c0 | True | 1 | NOT_MEASURED |
| lab-unit-harmonization | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 | 1 | 8e5c58ca103fbebafda4e28371e4a7313c4e2ef099301e24fb4d2f8736e290eb | True | 1 | NOT_MEASURED |
| lab-unit-harmonization | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 | 2 | d9748ea6c3384fc3d6f8aefa8ade53b177351c6be52a3e8e7be9858d0c62158e | True | 1 | NOT_MEASURED |
| lab-unit-harmonization | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 | 3 | d988b7475e6255b34267e41072f1fed73581f824ad1c3a19dec689e24ed1229c | True | 1 | NOT_MEASURED |
| lab-unit-harmonization | af1be77fda655f84295ab9cf64dedf4110f9f3e976d867ec916458d6372f43e1 | 4 | 2f4864b582db175184bcbbb4259bceee67b9e58500f13f43aae2a675f33ca97a | True | 1 | NOT_MEASURED |
| lake-warming-attribution | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b | 0 | a3410233453051fa62d9778c3663276c721b5b04add0505b0eb3d9f26aa3476f | True | 1 | NOT_MEASURED |
| lake-warming-attribution | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b | 1 | 3c1f699e392f8895eb3fde69144880503186b40175d481faef0c44ffc426814a | True | 1 | NOT_MEASURED |
| lake-warming-attribution | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b | 2 | ea31291e8689d486b150e31d126192aa3db4526c0e695b7f7c0ee17f99925205 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b | 3 | eb51f4e6105d5a78a9c7e32ebb18148c8861db98c7a532dff106ee1f67d9af92 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | c9d76509da6cf23122bfb0b9f1c3d20702513cf2ba8f8228839b7e2084b9ff6b | 4 | 2d6303e7190c3d160241e382261f03cb81f9756d84eb903c45bab93f87500ad8 | True | 1 | NOT_MEASURED |
| latex-formula-extraction | cbef3317c6e3115d03df68b07dd1e53689e69f81572df126a7e466b213e3fd94 | 0 | 7ee62d0b07b6f73ad8686538dd8e1b8b48c9e6a6ff6025d16158366dc3a8888a | True | 1 | NOT_MEASURED |
| latex-formula-extraction | cbef3317c6e3115d03df68b07dd1e53689e69f81572df126a7e466b213e3fd94 | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | a7d4d5a3cd61a00fe681fcf841aa39b49ccb0fac46eddb299f669e1655cf9c60 | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | a7d4d5a3cd61a00fe681fcf841aa39b49ccb0fac46eddb299f669e1655cf9c60 | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 6424400c0a54a2717bb0435e199754f3c886984d2596bdb4889f01511c44b8ae | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 6424400c0a54a2717bb0435e199754f3c886984d2596bdb4889f01511c44b8ae | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 0613b981bf7180aed8274b295e421b4388c42d90898b10bf4cbedf75e81f6e75 | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0.75 | NOT_MEASURED |
| latex-formula-extraction | 96b1e2f962fe554b0014e62bdc81e3ad753d3c420aa6da4cd876e2562bc9512d | 1 | 0e42f46ae580926b128d3a9cba4f3c8f50735deafde7c985c2e13949764fdd06 | False | 0 | test_repair_failed |
| lean4-proof | 41ead0e1d3fc8734d8df461bb34d2b90b88a551bb85ce881d1f635f3f5e62b8c | 0 | 62e863b50bae7fb20a4bf30aa457a708ad88a23a54e3bb7453d0cf94aee4f806 | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | 465abeb489bac48794ca901bfff11bcae08defffe11f9dcba7d5f9a7099e4d78 | 0 | 27ac87eaf9f793c2453af5e917f59ce79be840a65fe772fb1d8381d6310092ac | False | 0 | NOT_MEASURED |
| manufacturing-codebook-normalization | feb6ea42edbb538b40cf07e8e447875b67a638c99f91e5c707a2f45c95870b9b | 0 | 27ac87eaf9f793c2453af5e917f59ce79be840a65fe772fb1d8381d6310092ac | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | feb6ea42edbb538b40cf07e8e447875b67a638c99f91e5c707a2f45c95870b9b | 1 | e979ffd74d193b2896a7adf4967c2baab0c0b857940ac66948cf0836e6d53a1d | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | feb6ea42edbb538b40cf07e8e447875b67a638c99f91e5c707a2f45c95870b9b | 2 | b34103a49c525bb1ef7d70c807333cefc3d2e270d7e4ccbce2cc67f2f3141fe9 | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | feb6ea42edbb538b40cf07e8e447875b67a638c99f91e5c707a2f45c95870b9b | 3 | 872a735e20dfca7d6d77822c04382776bef213560353cf0b311db17c370d77ff | True | 1 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 1faff32c8adcac80b91cee9dbb31d2ae6bb9714a891372fffb2aa55202138b3f | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0 | NOT_MEASURED |
| manufacturing-fjsp-optimization | ba2189961a2781ca4915c7c42829fad105d167e1088cc0826f80ce65cb06aed6 | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 9793ea768761e8e506ff138988d0bea653cc1c6bb51ee74da3ecc8cdb7b64d15 | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | bc1e95f0d1d569fa97cbea52398e27fd837a2def17ace5b48e2ace2d1dccf5eb | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | fe6ce9c14b0e20c3d576a7fc52a656c9aec73766c758d89fdf83afda751b0b8f | False | 0.333333 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | b97886a0a8d151bac311f643674e30223a8372f332924509cd5a3935a67613fc | False | 0.5 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | b97886a0a8d151bac311f643674e30223a8372f332924509cd5a3935a67613fc | False | 0.5 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | b97886a0a8d151bac311f643674e30223a8372f332924509cd5a3935a67613fc | False | 0.5 | NOT_MEASURED |
| manufacturing-fjsp-optimization | 23e07606cc4e8c5113fcb4f46bf904288cd18e09ed4f62616ddf782b7c305581 | 0 | b97886a0a8d151bac311f643674e30223a8372f332924509cd5a3935a67613fc | False | 0 | timeout |
| mario-coin-counting | 45d8e35cf1d1291b49b78b669169f1035afbdef72aefe09e9646e0cda57eecb3 | 0 | 626aadba3f24c70d4c28ade7ae25af97f668ca4c2c61f5a1efb21af42479e581 | True | 1 | NOT_MEASURED |
| mario-coin-counting | 45d8e35cf1d1291b49b78b669169f1035afbdef72aefe09e9646e0cda57eecb3 | 1 | c4a735a04aba259110c3ffddc35b1d17df2def90dae0aa4b494b94872a2b5e5f | True | 1 | NOT_MEASURED |
| mars-clouds-clustering | e575d8b7e638551a03933739d25fbb97092aecee9e89037f2c5588b7704305e5 | 0 | 1d297484c1973d719b6133f9d6d8c7f5926ce8b5633a8d52d497db60bf1a69b0 | True | 1 | NOT_MEASURED |
| offer-letter-generator | 3196793c4e1f5b3c5633a271d4b22ca9ff683025c81f4b1ec45d91d4683e11f0 | 0 | 99dad84606c5da94a7e4ed5453e9273b2bc34283752ae83ed72d80e28b389cbb | False | 0 | NOT_MEASURED |
| offer-letter-generator | 93b73afba1fba540b6468aef721231f8e32b1fb78ea37b71ec5c5bec2611d985 | 0 | 99dad84606c5da94a7e4ed5453e9273b2bc34283752ae83ed72d80e28b389cbb | True | 1 | NOT_MEASURED |
| organize-messy-files | 27021ff8cf53a42ff1a9ca3af4bd36e6ed1c643ef4412ee59434b6f9543ed94e | 0 | 43af3dc9c7e632b4e18d60ec47808c26f672e5eeb3542d1da211185134c5cd75 | False | 0.6 | NOT_MEASURED |
| organize-messy-files | f657f8ffd62765dc955588d9fbdbc48c111000c2024c05cdc2166abe6e76cc64 | 0 | 43af3dc9c7e632b4e18d60ec47808c26f672e5eeb3542d1da211185134c5cd75 | False | 0.8 | NOT_MEASURED |
| organize-messy-files | e4492d2ca2c6721a2b97b4999f91b33608c404d047bf5b36c65d88c8c5a30e3c | 0 | 43af3dc9c7e632b4e18d60ec47808c26f672e5eeb3542d1da211185134c5cd75 | True | 1 | NOT_MEASURED |
| paper-anonymizer | 3e0242d6e8fe5d984bbe5d3cb928079e26af6c62816626a3dcb166a2455d2466 | 0 | d484f558f4cbc1219819941aa3b852b3fe3fbe6aee9afbc6dc47b8923444c37a | False | 0 | NOT_MEASURED |
| paper-anonymizer | eae20ae6f4df354ee437b4c9d18fdb3db9cf5ca8035eef3b6b41d368afdab070 | 0 | d484f558f4cbc1219819941aa3b852b3fe3fbe6aee9afbc6dc47b8923444c37a | True | 1 | NOT_MEASURED |
| paper-anonymizer | eae20ae6f4df354ee437b4c9d18fdb3db9cf5ca8035eef3b6b41d368afdab070 | 1 | 13e52978a86aca2e3a36a5b9c16a201045fa9ca67c9d5a1a59a023ebaa493562 | True | 1 | NOT_MEASURED |
| paper-anonymizer | eae20ae6f4df354ee437b4c9d18fdb3db9cf5ca8035eef3b6b41d368afdab070 | 2 | de3469df011a54a4697a5b44ea90501f4288a9bea470b367c355b56681b03545 | True | 1 | NOT_MEASURED |
| paper-anonymizer | eae20ae6f4df354ee437b4c9d18fdb3db9cf5ca8035eef3b6b41d368afdab070 | 3 | a73b03dc3746ebf49f37d96cb1c31634e3a6343a49ca7772a2178ab5c9f3c5e2 | True | 1 | NOT_MEASURED |
| paper-anonymizer | eae20ae6f4df354ee437b4c9d18fdb3db9cf5ca8035eef3b6b41d368afdab070 | 4 | 39a094ffb015d3f0b9aa3231fdcdcbfb6016b7bd49741bd0ccf079766c277fe5 | False | 0.857143 | NOT_MEASURED |
| paper-anonymizer | e8bb2fff5da5bf0c062487ae63d38057f9718284bf8f47a278bb56a7ff48d321 | 4 | 39a094ffb015d3f0b9aa3231fdcdcbfb6016b7bd49741bd0ccf079766c277fe5 | False | 0.857143 | NOT_MEASURED |
| paper-anonymizer | ba38faaa033d8da01dbfaf470386f825b1140e4f5fa4f6e74b94a32a62ab0c00 | 4 | 39a094ffb015d3f0b9aa3231fdcdcbfb6016b7bd49741bd0ccf079766c277fe5 | False | 0.857143 | NOT_MEASURED |
| paper-anonymizer | 0d05be53f10055d33ce50baf5f27fcd3aba352a570134cff531fb28da6df6a56 | 4 | 39a094ffb015d3f0b9aa3231fdcdcbfb6016b7bd49741bd0ccf079766c277fe5 | True | 1 | NOT_MEASURED |
| parallel-tfidf-search | 9213db5ff59c3ae9f0bcddf7647c7d3b58080a483cd12800c8733c0b5bb2ceb5 | 0 | 40173a7ac86fd8bbea61aa7e60c776c22286c3c396113a940e621966a9b74186 | True | 1 | NOT_MEASURED |
| pddl-tpp-planning | 511601c678d0d81f4b7253e157f2f0892b24c0439a2a7343d1b2a91cc75e0ab7 | 0 | 35e6eee8b2c8b50dd191f0f5eac6ad4dc31d6a9256da4f509b94fab990fbf30f | True | 1 | NOT_MEASURED |
| pdf-excel-diff | 224fb6467b1a855d9093480be5ef1251038eb318e20fdfdf4f23712542b4b947 | 0 | ba25df2d948c2df1a1e2f420cc6485c3284375a51a56ed97bbe4efad137e0980 | False | 0.5 | NOT_MEASURED |
| pdf-excel-diff | a05b25dd11513b2f6d989a08518332eca8693a3b450986cd1e8a51b8b5ef8d0b | 0 | ba25df2d948c2df1a1e2f420cc6485c3284375a51a56ed97bbe4efad137e0980 | True | 1 | NOT_MEASURED |
| powerlifting-coef-calc | bf4e639a42514c25ebdab56b51521c073ec296b9bc33639633a169bf3395efe1 | 0 | 20bc1ebda11062426c77a0864c3bf16fea26f4cb9f512da0b34a124485259a44 | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | e48121b37732b73b5946ae0c415652abb65ee258ac002ecf0f194f71899391e1 | 0 | 156d0c4a639b8525f9e651523ec49264a699c3c96b017f649c95185da56b84bd | False | 0 | test_repair_failed |
| protein-expression-analysis | 81256fb72c6350a0f0659c3e336e6eceb7d60f28b16a6b0628cf7c87c08dd727 | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0 | NOT_MEASURED |
| protein-expression-analysis | 66eb5c918aa88fe8ee6b392f9033023a55b8c8c23c1349eb13995430994f1302 | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0.666667 | NOT_MEASURED |
| protein-expression-analysis | 6bdcec029c4760f5213ca01899fab3864977a8d8a070750d39ee940fc839e62e | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0.666667 | NOT_MEASURED |
| protein-expression-analysis | 6bdcec029c4760f5213ca01899fab3864977a8d8a070750d39ee940fc839e62e | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0.666667 | NOT_MEASURED |
| protein-expression-analysis | 6bdcec029c4760f5213ca01899fab3864977a8d8a070750d39ee940fc839e62e | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0.666667 | NOT_MEASURED |
| protein-expression-analysis | 6bdcec029c4760f5213ca01899fab3864977a8d8a070750d39ee940fc839e62e | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0.666667 | NOT_MEASURED |
| protein-expression-analysis | 6bdcec029c4760f5213ca01899fab3864977a8d8a070750d39ee940fc839e62e | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | False | 0.666667 | NOT_MEASURED |
| protein-expression-analysis | 23620adecc6050a2c6587d671a071977484a90f36cf1d504a78849e24da2c095 | 0 | bf7455b68fd5ad1fe51e40c8e05ebe61d449adcdebe965d66e82cda18951aaf5 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 04a673705ff99deaa10963b508f249b29e1a28c5d75515522c45a71013ad4941 | 0 | 5c9107773bbd0bf72493979341bb8414d2518e654eb7e18a169987f88a142f2f | False | 0 | NOT_MEASURED |
| quantum-numerical-simulation | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a | 0 | 5c9107773bbd0bf72493979341bb8414d2518e654eb7e18a169987f88a142f2f | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a | 1 | 4c1afcd79ee1411f0ad7b284a7559d9ce3f7db288fc136445da2edad28c588a4 | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a | 2 | ff65335cfd358e04fed36755d6a264db657ca130e30e37b769127a64a06d784f | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a | 3 | cace28005433d1666ee4641d913b57225d7f4e92e81543cf24c8990312abc4aa | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | ef1624e3e63b1e241b83d34e0ff74a708f7a4e3bacf1c50ec79c8db314c8643a | 4 | 9d99ba7cc9fa678edc394518851cc614d66d549f96751574a7615192b6c4ad5f | True | 1 | NOT_MEASURED |
| r2r-mpc-control | 858bd1084ee9f0bd70d2d6260d6ee48b7da6e378a26a17768a9188734fad3043 | 0 | 093802ae03d8fc04817b9b672136f6b7f764bb2113a5d6ab20c6e4cd0df41426 | False | 0 | NOT_MEASURED |
| r2r-mpc-control | 38a340ea68ac9c79fe1894f4c393b4527ee0e91fde7ae401204870861102d96a | 0 | 093802ae03d8fc04817b9b672136f6b7f764bb2113a5d6ab20c6e4cd0df41426 | True | 1 | NOT_MEASURED |
| react-performance-debugging | eaae4e341e857d878afc40ff5148ca5d0c7e5538fb5716491c44a420ee5f3890 | 0 | bce2397e1d6a1dd4f4c54984253f91c1c8d230df2b78fe75f7e75e71e15f8693 | True | 1 | NOT_MEASURED |
| reserves-at-risk-calc | c753e52b9457a796463ff14aa64cdb9e018ddd3141d8e0f0a01965caa4ec5cd9 | 0 | aa7f24f7d630a2fb84ec7a4bb3ddce034ab1dd5d8f3d29ee68b9bba284547b0f | False | 0 | NOT_MEASURED |
| reserves-at-risk-calc | bfca50b340280f553e49f14f99fd7fe4b4e3bb411dfce2b2d452a5ba19b27bb7 | 0 | 8173ebbd7b66b99620c80329fd82be9418d451ca413cdb4c1d337a9b929ee54f | False | 0.5 | NOT_MEASURED |
| reserves-at-risk-calc | 61358ae426889af7e0181f8a454e2e8c0e869c4dbc1beae49ea2c821c35e66a0 | 0 | 8173ebbd7b66b99620c80329fd82be9418d451ca413cdb4c1d337a9b929ee54f | False | 0.5 | NOT_MEASURED |
| reserves-at-risk-calc | d4d0e7014af453348045a5095d6a1e5cf7bf51854f6c548ff42236c318d8069a | 0 | 8173ebbd7b66b99620c80329fd82be9418d451ca413cdb4c1d337a9b929ee54f | True | 1 | NOT_MEASURED |
| reserves-at-risk-calc | d4d0e7014af453348045a5095d6a1e5cf7bf51854f6c548ff42236c318d8069a | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| reserves-at-risk-calc | 722faabfcd5efa54eb0436fec5bded26441cf48c6a5bdef3ccbc715170483c2d | 1 | b8acc2a2b0237910b78f1b42d3ea1e726c38b53d4b5d088231a29bf7d65137e5 | False | 0.75 | NOT_MEASURED |
| sales-pivot-analysis | 66aeec8f099f18dc5f0fc7a7f900a206b15954872d52cb5b30909ec0d038d0b1 | 0 | 5c8845dbc70863eb2a035ddaacffdedd2a429d7b87aa0a81f222b0ba3644fb77 | False | 0 | NOT_MEASURED |
| sales-pivot-analysis | eb87def1e09dae0d979f173da600944f646cf607fbd68263e3eba4c332016159 | 0 | 5c8845dbc70863eb2a035ddaacffdedd2a429d7b87aa0a81f222b0ba3644fb77 | False | 0.333333 | NOT_MEASURED |
| sales-pivot-analysis | 9f017f1cfcdba2c09b27013572222114cc541db7c4b285813757043daf8537d7 | 0 | b3e706b520589d87a7930188fd46f5c7420ef9632fabb6391184bdf64f8c6c00 | False | 0.5 | NOT_MEASURED |
| sales-pivot-analysis | fb7e8b387fb8230135d4e889002d33034eba1333d362710cb912de94289ecb8c | 0 | b3e706b520589d87a7930188fd46f5c7420ef9632fabb6391184bdf64f8c6c00 | False | 0.5 | NOT_MEASURED |
| sales-pivot-analysis | 76caf2887be9030d4d91e8b04f942943cb1770c1e7dab420328db316187e048a | 0 | b3e706b520589d87a7930188fd46f5c7420ef9632fabb6391184bdf64f8c6c00 | False | 0.5 | NOT_MEASURED |
| sales-pivot-analysis | 1260ef1857b1c5b47256211644dc27dbe22ddaf954cd77b4ee1e311dde8926d8 | 0 | b3e706b520589d87a7930188fd46f5c7420ef9632fabb6391184bdf64f8c6c00 | False | 0 | timeout |
| sec-financial-report | 91ce320fcadeb466a8337229b0cdc59cd4fc6b1ad244f228bbba19a388810b59 | 0 | 0901f29c95b48933ac1984fd3121dce233f4dde787dd4d1a777b6db28f690577 | False | 0 | test_repair_failed |
| shock-analysis-supply | 5ab3e34ddfbaff5e0a828b1dc99189d138aa26ef26fe773862c1e4fffe9c97f0 | 0 | e346a518213af436ec5c41ddafd3f0fe1c3d3d9bb0dc5737b1f2050bf16631de | False | 0 | NOT_MEASURED |
| shock-analysis-supply | c2961840af68d13e46ba1f5e57d02003adb6e99ae292cc007543f9929b082089 | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 7a02bab913191b567bb7a9d68463c5caad883f9d6c207b627598ce1147ad5b64 | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 7a02bab913191b567bb7a9d68463c5caad883f9d6c207b627598ce1147ad5b64 | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 227d67baf85397c2b2642545f700894d3b273598997364bf48ee4e07b974b6e3 | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| shock-analysis-supply | 3c7ba612dcd94cf5b7392ebdbd6d763e69865abfe2cb4e8bfc0447daaf5f32cf | 0 | f1d88b58fa3afcc4c0765cc99124e20808aa640cd24c6177ad7aff2b2636d25a | False | 0 | NOT_MEASURED |
| speaker-diarization-subtitles | d85695c5a88f60b7131b6875b5a040f0a57fb0feb598e4f821e74ef0953115cf | 0 | b92c627e4cadb7137abaa58e60e63393d6ab2d46e6b78085d91e84bb5dbe9e5e | False | 0 | NOT_MEASURED |
| speaker-diarization-subtitles | 72ee2f7e3df1cebbd31705f067eb1495487f9a86f71db9e3fe609884031e1d61 | 0 | b92c627e4cadb7137abaa58e60e63393d6ab2d46e6b78085d91e84bb5dbe9e5e | False | 0.75 | NOT_MEASURED |
| speaker-diarization-subtitles | 5b5241805e5d6698b6d42964326eca88156bfed6820f8bedd6000cccae3c2f9d | 0 | b92c627e4cadb7137abaa58e60e63393d6ab2d46e6b78085d91e84bb5dbe9e5e | False | 0.75 | NOT_MEASURED |
| speaker-diarization-subtitles | 5b5241805e5d6698b6d42964326eca88156bfed6820f8bedd6000cccae3c2f9d | 0 | b92c627e4cadb7137abaa58e60e63393d6ab2d46e6b78085d91e84bb5dbe9e5e | False | 0.75 | NOT_MEASURED |
| speaker-diarization-subtitles | 0a0884013e244f261e8cbea7133e57c77bcc33186b1a6bbfea8f5b281b84c335 | 0 | b92c627e4cadb7137abaa58e60e63393d6ab2d46e6b78085d91e84bb5dbe9e5e | True | 1 | NOT_MEASURED |
| speaker-diarization-subtitles | 0a0884013e244f261e8cbea7133e57c77bcc33186b1a6bbfea8f5b281b84c335 | 1 | ed5aba7b1f352793d19e3b98f8579e261b969d733ae5fc7c91e88ed296f7a1ce | True | 1 | NOT_MEASURED |
| speaker-diarization-subtitles | 0a0884013e244f261e8cbea7133e57c77bcc33186b1a6bbfea8f5b281b84c335 | 2 | 21902c2b1e6a7ced79ce4982632eaedfadea1135a121fb5efaf571d0627cdfa7 | True | 1 | NOT_MEASURED |
| spring-boot-jakarta-migration | 14ac963f3dabcc7459b01ba782d1b2daebca508808919e2f34ad9f892a4207cc | 0 | 5e4fc6e04a510ddecb221550e4cdb425bed202bcf56c8515e68e7d62339e9659 | True | 1 | NOT_MEASURED |
| suricata-custom-exfil | ef63919d52681e683b8a023a459ea5a87f89dd12f0a9e5fdaef234c2c10d8557 | 0 | 1ed24efb99f811046f0bd1743aa5d98a978efb6f8eb35cc158a6412743b55496 | True | 1 | NOT_MEASURED |
| taxonomy-tree-merge | 75f929e7aa4f4608e62e3263c893b5e0b54c611caf60663850c5942effaa9966 | 0 | 42a829b47030094ea30491ffb65ee99f8a8ca29f1ca70569cce6338451bb9431 | False | 0 | NOT_MEASURED |
| taxonomy-tree-merge | 84721b028d57c8ec807157ee26bbec33b599c2517895c4e36f251eccfd5e1406 | 0 | 42a829b47030094ea30491ffb65ee99f8a8ca29f1ca70569cce6338451bb9431 | True | 1 | NOT_MEASURED |
| taxonomy-tree-merge | 84721b028d57c8ec807157ee26bbec33b599c2517895c4e36f251eccfd5e1406 | 1 | c00a4fa279587b8e225fac8e91eaccc3fa7e70ace91e8d3fb29e7db25d377fd1 | True | 1 | NOT_MEASURED |
| taxonomy-tree-merge | 84721b028d57c8ec807157ee26bbec33b599c2517895c4e36f251eccfd5e1406 | 2 | 0b73ccec5420125a581895966241dc188ab7667417bee94a8a3c53f6ef0de5c0 | True | 1 | NOT_MEASURED |
| taxonomy-tree-merge | 84721b028d57c8ec807157ee26bbec33b599c2517895c4e36f251eccfd5e1406 | 3 | cffce47ce16820682f4b8c48cbdaf0686e9dc48290031b5180af90b4b3fb2ccf | True | 1 | NOT_MEASURED |
| travel-planning | aa2939439a7419dcb40724ba3ea3ec86541da4c01a07be5a9bcaf273bc97ce14 | 0 | 9cd5940142191e963c59529aa4e30697b1df78b11efe94752da2692a36aa40e3 | False | 0 | NOT_MEASURED |
| travel-planning | 0214c994e0d6bcbae2f735243ce74433a0b09d71e9e97885f931af1f357bf5cd | 0 | 9cd5940142191e963c59529aa4e30697b1df78b11efe94752da2692a36aa40e3 | True | 1 | NOT_MEASURED |
| video-filler-word-remover | 2623781ecbfa00291ba5f594a4708a5e9190efb9fe0e0b467c6dee791faf423e | 0 | 766231ab598352f16baaf399e137aa546daefe2ee03efa16ce8bf747ad499901 | True | 1 | NOT_MEASURED |
| video-filler-word-remover | 2623781ecbfa00291ba5f594a4708a5e9190efb9fe0e0b467c6dee791faf423e | 1 | dcac6a17f715e786e5adddd25881386d03cc5e2d3fa7dad476e9a3bf5b953bb2 | True | 1 | NOT_MEASURED |
| video-silence-remover | fc4e71f6b51c20ad78bf4c4299321f3f84e0881eaf749e7275fc946e702c5741 | 0 | de60cb73cf7254d38f74a4e0e5dd241af7512a0f466b55d2b9847e242b56bed6 | False | 0 | NOT_MEASURED |
| video-silence-remover | 86b62ddbd3c5e1bb3c9568cad064c571c633be832a88d657dcc9f82f9d233ac4 | 0 | de60cb73cf7254d38f74a4e0e5dd241af7512a0f466b55d2b9847e242b56bed6 | True | 1 | NOT_MEASURED |
| video-tutorial-indexer | 99823184cf3a795bc62a3949ebc6768f075e024d9037e171cca5b63ce244cbfd | 0 | 0c75a0b7a6ba61d85a10c818e31097510165590b1c69d8b2f09ed0d6431a38bb | False | 0 | timeout |
| virtualhome-agent-planning | 6091ff79f098ab4cca7f09525a811ec9689482a9c37abfd1a7dd9f0e71506f79 | 0 | 111d6c4e18a27a6673808fbdcd30ed94c80b0e4357fd8d5fc8d959c097e39115 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 42aae521f25ce12db31646983cf4bbead757c31ddad75da6b611ee78bb3b5491 | 0 | 111d6c4e18a27a6673808fbdcd30ed94c80b0e4357fd8d5fc8d959c097e39115 | True | 1 | NOT_MEASURED |

## Adjacent content paired coverage

| Condition | From | To | Actual chains | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | NoSkill | S0 | 78 | 85 | 75 | 0.882353 | -0.0266667 | 75 | -0.0431787 | 69 | 0.811765 | -6.23357 |
| benign | S0 | S1 | 33 | 85 | 33 | 0.388235 | 0.121212 | 33 | 0.121212 | 31 | 0.364706 | 14.285 |
| benign | S1 | S2 | 14 | 85 | 14 | 0.164706 | 0.214286 | 14 | 0.214286 | 12 | 0.141176 | 8.47222 |
| benign | S2 | S3 | 10 | 85 | 9 | 0.105882 | -0.111111 | 9 | -0.111111 | 7 | 0.0823529 | -5.71429 |
| benign | S3 | S4 | 7 | 85 | 6 | 0.0705882 | 0 | 6 | 0 | 6 | 0.0705882 | 0 |
| benign | S4 | S5 | 2 | 85 | 2 | 0.0235294 | 0.5 | 2 | 0.5 | 2 | 0.0235294 | 10 |

S labels enumerate sealed content hashes, not revision attempts. Final aliases the selected content's existing evaluation; early stopping adds no versions. GT deltas require measured checks with matching unit, total and source. Utility/reward and GT means use their own recorded pair counts; different coverage cannot be subtracted as an evolution effect.

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | GT delta (pp) | GT delta reason | Final aliases S0 | Rescued |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| azure-bgp-oscillation-route-leak | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| citation-check | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| civ6-adjacency-optimizer | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| court-form-filling | benign | True | 0 | 0 | 40 | MEASURED | False | False |
| crystallographic-wyckoff-position-analysis | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | False | False |
| dapt-intrusion-detection | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| data-to-d3 | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| dialogue-parser | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| dynamic-object-aware-egomotion | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| earthquake-plate-calculation | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| econ-detrending-correlation | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| energy-ac-optimal-power-flow | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| energy-market-pricing | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| enterprise-information-search | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| exceltable-in-ppt | benign | True | 1 | 1 | 25 | MEASURED | False | True |
| exoplanet-detection-period | benign | True | 1 | 1 | 25 | MEASURED | False | True |
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
| gravitational-wave-detection | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| grid-dispatch-operator | benign | True | 0 | 0 | 16.6667 | MEASURED | False | False |
| hvac-control | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| invoice-fraud-detection | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| jax-computing-basics | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| jpg-ocr-stat | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| lab-unit-harmonization | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| lake-warming-attribution | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| latex-formula-extraction | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| lean4-proof | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| manufacturing-codebook-normalization | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| manufacturing-equipment-maintenance | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| manufacturing-fjsp-optimization | benign | True | 0 | 0 | 80 | MEASURED | False | False |
| mario-coin-counting | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| mars-clouds-clustering | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| multilingual-video-dubbing | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| offer-letter-generator | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| organize-messy-files | benign | True | 1 | 1 | 33.3333 | MEASURED | False | True |
| paper-anonymizer | benign | True | 1 | 1 | 16.6667 | MEASURED | False | True |
| parallel-tfidf-search | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| pddl-tpp-planning | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| pdf-excel-diff | benign | True | 1 | 1 | 45.4545 | MEASURED | False | True |
| pedestrian-traffic-counting | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| powerlifting-coef-calc | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| pptx-reference-formatting | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| protein-expression-analysis | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | False | False |
| python-scala-translation | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| quantum-numerical-simulation | benign | True | 0 | 0 | 85.7143 | MEASURED | False | False |
| r2r-mpc-control | benign | True | 1 | 1 | 16.6667 | MEASURED | False | True |
| react-performance-debugging | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| reserves-at-risk-calc | benign | True | 0 | 0 | -20 | MEASURED | False | False |
| sales-pivot-analysis | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| sec-financial-report | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| setup-fuzzing-py | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| shock-analysis-demand | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| shock-analysis-supply | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| software-dependency-audit | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| speaker-diarization-subtitles | benign | True | 0 | 0 | 60 | MEASURED | False | False |
| spring-boot-jakarta-migration | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| suricata-custom-exfil | benign | True | 0 | 0 | NOT_MEASURED | official_checks_not_measured | True | False |
| syzkaller-ppdev-syzlang | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| taxonomy-tree-merge | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| travel-planning | benign | True | 1 | 1 | 100 | MEASURED | False | True |
| trend-anomaly-causal-inference | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured | True | NOT_MEASURED |
| video-filler-word-remover | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| video-silence-remover | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| video-tutorial-indexer | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| virtualhome-agent-planning | benign | True | 0 | 0 | 0 | MEASURED | False | False |
| weighted-gdp-calc | benign | True | 0 | 0 | 0 | MEASURED | True | False |
| xlsx-recover-data | benign | True | 0 | 0 | 0 | MEASURED | True | False |

## S0-to-Final paired coverage

| Condition | Denominator | Paired | Paired coverage | Utility delta | Reward paired | Reward delta | GT paired | GT paired coverage | GT delta (pp) | Same content | Rescued | Degraded |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| benign | 85 | 77 | 0.905882 | 0.0909091 | 77 | 0.0909091 | 70 | 0.823529 | 7.49289 | 44 | 7 | 0 |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | 1 | 293 | budget_exhausted_incomplete | 38b4b078f45916127b1dff4c7cfbf8879a4ca7909ae024b87d4d471fac13c7e0 |
| azure-bgp-oscillation-route-leak | benign | 2 | 1565 | sufficient | 57de692705a8faa20d06fe155e660aa0f5114f35da4096b84436c57fc18aea96 |
| citation-check | benign | 2 | 2960 | sufficient | 7e8019bb2de74245eafefc0c5cb842a99aa15235ee7796fda47e6d12ac373426 |
| civ6-adjacency-optimizer | benign | 3 | 5691 | budget_exhausted_incomplete | df91a5857abe068a1264cb1b40180c725e7e7c8759f62fa1ab4b14259004fe9f |
| court-form-filling | benign | 1 | 236 | budget_exhausted_incomplete | 09fbf82c46f01eebb7e667ccceb0cb873d8ec864c8ff10235dc27f170c39dc80 |
| crystallographic-wyckoff-position-analysis | benign | 1 | 427 | budget_exhausted_incomplete | fc32d5ff03940d95e5725a010dd7ff6abd54f88e7580a71c13e8567bac2b35ec |
| dapt-intrusion-detection | benign | 2 | 3632 | budget_exhausted_incomplete | d5ec681a8099e756ab14a0100097ae0920fd8ac1e64ec59967c3bcc5c9258aa9 |
| data-to-d3 | benign | 2 | 4461 | sufficient | 6e915b10be8da86607e30130b8b1f8ce1db7dd150ebbde587dfc048bd750f093 |
| dialogue-parser | benign | 1 | 280 | sufficient | 57f02e0df7de643ae719297939c3d272cb4297fe46b2478ebc83e07e2774b20f |
| dynamic-object-aware-egomotion | benign | 2 | 4511 | sufficient | 4352779bb0036bcab7c97347782fb105bc027b1f1a9c2ade867118f877a6d0d2 |
| earthquake-plate-calculation | benign | 1 | 2264 | sufficient | e9c4ed1edea5b42afbc2b744b12c0397b375918993600d4d35b5b54a9b8f63ee |
| econ-detrending-correlation | benign | 4 | 6510 | sufficient | 3fab14753973de43da10cf7efa2df63a8944b56533cbac21d5b139cb2fd0291b |
| energy-ac-optimal-power-flow | benign | 5 | 6507 | sufficient | b5035daa4d812eb8759e3e8a9886bac52a6a3ca97ef4b4e11ab089859695e79a |
| energy-market-pricing | benign | 5 | 6507 | budget_exhausted_incomplete | 77e24f6b51ad132c1d305bde7052869b5f06f6866833e5e50d167e712f3f3a9e |
| enterprise-information-search | benign | 1 | 1223 | sufficient | 383dbf466d05fcaea7291f674c9e5a922bf0c9e614a1652db06ebe9ea4e4b8c2 |
| exceltable-in-ppt | benign | 6 | 3527 | budget_exhausted_incomplete | cf5fcc45d7a74843469703de0cfa46f1498e42acd0a14eaed8493e12d1159714 |
| exoplanet-detection-period | benign | 1 | 384 | budget_exhausted_incomplete | 8cfcba7be991b83c653dedc50c99b282f323daf50e69fcaa268d1f10a5213999 |
| financial-modeling-qa | benign | 4 | 4772 | sufficient | 66b5942132d1debbcbad14306c72c787e304043cd43abbbbf7340cd87f4837d1 |
| find-topk-similiar-chemicals | benign | 3 | 2915 | budget_exhausted_incomplete | 044d709a59b2eecda86312a117b70e9370430c5f18e4afbe9556832ceadd3d11 |
| fix-build-agentops | benign | 2 | 3211 | sufficient | 954a890164b7c8006f5c45b10ff85b2e162c461aab3c28dd625e06445edf0de9 |
| fix-build-google-auto | benign | 2 | 2989 | sufficient | ba8d4b95056f9d41a405ddfb258edc751d0209b145cc453ae1b02af8aa2701c9 |
| fix-druid-loophole-cve | benign | 4 | 6566 | sufficient | f51284c84a07ed27769b01d7f5ccb4cdca1a3fd6b6c6d6fb6e4c50cc40356845 |
| fix-erlang-ssh-cve | benign | 1 | 307 | sufficient | b331d94ee4d3a6aa680785e4d89b93fb7a6db333bfe35aeb0a27bbe40732c1a1 |
| fix-visual-stability | benign | 4 | 6734 | sufficient | 53d04d5ec1244a25c0e1507e111d8aea7ae247b2dcef8eac4bc1d0de21b64fbb |
| flink-query | benign | 3 | 3547 | sufficient | 7fef667469a0fd2c55694c2883926f2348e2c757a3e2334d1c9097ccfbe700c9 |
| flood-risk-analysis | benign | 1 | 1867 | sufficient | 25be36c2c5771f0c3b3a459d8bb6c500f903f9dee703203bfe6ce57eefaabe68 |
| gh-repo-analytics | benign | 1 | 736 | budget_exhausted_incomplete | 715a6a39716788ade7fa1d74431838e3008eaac5e2c208ac96550acec54cef30 |
| glm-lake-mendota | benign | 2 | 785 | budget_exhausted_incomplete | 1af95c9c2cda18b350c22ec8f63b77b57a91750ba0a46a32b040083a7a881b1f |
| gravitational-wave-detection | benign | 2 | 3359 | budget_exhausted_incomplete | e758abb3c10ea5d3edfd6da83063a82d07c50d0eb1cc816657f2c02c09e3f26f |
| grid-dispatch-operator | benign | 5 | 6507 | sufficient | 67eeb083148d151e972414f2d49abf9382be06565aa044655a2b580f111a4488 |
| hvac-control | benign | 6 | 6929 | sufficient | 78e45acad08bd4274d577d0b10dafb0a3d5724461111634bc16f1054b673da0f |
| invoice-fraud-detection | benign | 7 | 8342 | sufficient | 016e5a34afc0c8fae0a667eabea7c4b07bdb17af4e3f8e531f8e4a4dbf679247 |
| jax-computing-basics | benign | 1 | 577 | sufficient | 5f2ace48aeba5fe54984f0c61f4c707354432185df0e6746d4b69ce9ab406888 |
| jpg-ocr-stat | benign | 4 | 6302 | sufficient | d9a55f586d3294a14e7d48bd7c83354db2183b17a5e9d267556737a1ec4eeaf5 |
| lab-unit-harmonization | benign | 1 | 1360 | budget_exhausted_incomplete | a75f17ca17d78718375be263116072e3b9f8df92ffa03d88eb90eedbf2c28197 |
| lake-warming-attribution | benign | 2 | 1001 | budget_exhausted_incomplete | 49aa99b74de74d29f9ec0906a4bd9a6d65ffdb43d0e0dafb66369557870f9f47 |
| latex-formula-extraction | benign | 2 | 3478 | sufficient | a338a2f613eb82ebfbed5bd77df951d44dea84c14167100c02bbcdfa0d217221 |
| lean4-proof | benign | 1 | 299 | sufficient | 98f316dc46129a881f0e1fdb94145aaa8f9901128c680b94371b22bb0c0bd7e0 |
| manufacturing-codebook-normalization | benign | 1 | 1384 | sufficient | eb8967b42daf8802b2c735d68598e15d2ec0aa649de919c65beab8f92bb99b7d |
| manufacturing-equipment-maintenance | benign | 4 | 4443 | sufficient | c0f0b8ce60e57baf8bc43ce0e507f651e5c16c26d5b846066e6e08e3d90a5f44 |
| manufacturing-fjsp-optimization | benign | 2 | 2920 | budget_exhausted_incomplete | f3662e390f9b30b85f1c0fc595969fb8f3ce7cee601edb3cf61d3f388e54c476 |
| mario-coin-counting | benign | 2 | 2585 | budget_exhausted_incomplete | 14b1bdb1638d7eb63b71a1c72860659d258bebece90dbfcdd574ae3d73c0865f |
| mars-clouds-clustering | benign | 2 | 3055 | sufficient | 448690da10fda4515ded1eeedb06335de268f5a90a57a046c74a4fc5004ecbcf |
| multilingual-video-dubbing | benign | 4 | 5129 | budget_exhausted_incomplete | a2e79b232e40ea97ee2160c07470037ff6f1cf66221f7d9bab867cd2c41e1fa5 |
| offer-letter-generator | benign | 1 | 284 | budget_exhausted_incomplete | a80c132df1c2304d30265e0e36d2f37c0be4df45f90855cf5321ee2393dee646 |
| organize-messy-files | benign | 3 | 2898 | sufficient | 953ef8b5d6a836fb536252c6e60106e958b13bf047773711401164a1bb143371 |
| paper-anonymizer | benign | 2 | 3866 | budget_exhausted_incomplete | a3857800d4cdd2eba7ad13962489adf34abc45c29ea56d0ff27936657c2dc6a3 |
| parallel-tfidf-search | benign | 1 | 339 | sufficient | 13f5f26bc2e801b121b6a6eb9928ce573bbc180806f51eaa0fd2864475ec7459 |
| pddl-tpp-planning | benign | 2 | 968 | sufficient | 4d4e392df0548dc9e5704bcbad4e67d9e80a3002c831cf039737dc2316d150a9 |
| pdf-excel-diff | benign | 3 | 5191 | sufficient | 2cbc040bd74db55c162787241c1aec985280cdd40eb08121ceae5326acd12081 |
| pedestrian-traffic-counting | benign | 2 | 2931 | sufficient | 890763cf7b10d58632ca081e8dbe7abccc9831c0641ee3884724aa47a38454d6 |
| powerlifting-coef-calc | benign | 4 | 2679 | budget_exhausted_incomplete | a22f5e9c3e3585229b4cec28f74f72a1130f62de25ffe506f48526ef16d6393f |
| pptx-reference-formatting | benign | 3 | 1072 | budget_exhausted_incomplete | cb2561c57e9d6cd499e1d61dca9a7aeeb87d9ff71e58b570d0d7b7ea2055b408 |
| protein-expression-analysis | benign | 3 | 2458 | sufficient | d2300c6984fc41418e5ecf44be42be99e6d40373412b96369833ca461498b949 |
| python-scala-translation | benign | 2 | 3660 | sufficient | c63ab4f4fe271ef5daf83808e74c7863893e34f7f37cd41af38167d51fd26eeb |
| quantum-numerical-simulation | benign | 1 | 527 | budget_exhausted_incomplete | aa9eb50916e2f761650a86cdb4c033626eff2bf7d33b474785f79a98f494e840 |
| r2r-mpc-control | benign | 1 | 326 | budget_exhausted_incomplete | de25913e4772969a34ef2bd79835f2f4e616d7303412c764b1b51e3c16b1c4ae |
| react-performance-debugging | benign | 2 | 3147 | sufficient | 6669eeb03a9987290bafb7eff55adcfe50306347f1d0faa4345658bbcc6bb291 |
| reserves-at-risk-calc | benign | 3 | 3175 | budget_exhausted_incomplete | b9f23a2548abbf669e0750812abe6f35f89a0f7d5bbfe32d3e98c9aa17c8cb2a |
| sales-pivot-analysis | benign | 5 | 7551 | budget_exhausted_incomplete | c86da5171729b50b0de525c68d7479727c096f93b35caab8348ed98f47d1ae7f |
| sec-financial-report | benign | 2 | 3364 | budget_exhausted_incomplete | a5f082b9af2d142120819593631317375672970d445d83d63f85efbc7e9087b8 |
| setup-fuzzing-py | benign | 1 | 1964 | budget_exhausted_incomplete | 0b52048c50c1df7c9fa5479f55dec8c7c5e57e53704bf925912e7957fbaaa953 |
| shock-analysis-demand | benign | 4 | 5240 | budget_exhausted_incomplete | 161a612825e733295960153fb18463dfbba1125c4634843a6eea7351663ec2fe |
| shock-analysis-supply | benign | 4 | 5277 | sufficient | 37de32997d40ad3ac5c2ab8551cde8b545a2200cb46ff98073dcd57b1e3eafe8 |
| software-dependency-audit | benign | 1 | 303 | budget_exhausted_incomplete | 45f1e50096a77fee4a80acce65d79163a7f6ecfa05bdab3b4fd984951a7e3ea8 |
| speaker-diarization-subtitles | benign | 5 | 8052 | sufficient | b22c87a452b80bdfb04bb9ff87af9e8577d546b38988599887596d14191319ce |
| spring-boot-jakarta-migration | benign | 3 | 3331 | budget_exhausted_incomplete | fa16fbbbf8a16d3b47929985905b8be865a7d0abdef6f1c904a17af3e8493864 |
| suricata-custom-exfil | benign | 1 | 444 | budget_exhausted_incomplete | 8ad5cf3de114a0177e2199e4d5d19b1db26dce8de9f5fc1a2bda64fb2d5ce3e9 |
| syzkaller-ppdev-syzlang | benign | 3 | 4905 | sufficient | ae3232fa48d20a1044fc194ac8d2b7c259fe1a5e1a29947d68cca8569b8b0a5a |
| taxonomy-tree-merge | benign | 2 | 3961 | sufficient | 4e7ec6cebdb6a43a6883edd56e57bb8abd24a4fe42ab620cb84f463a4ea4532c |
| travel-planning | benign | 1 | 1199 | budget_exhausted_incomplete | 03fce62c0dffb065173bc78b15d8da7db73bbad3d87fa6f4fea3051a9e665b0a |
| trend-anomaly-causal-inference | benign | 3 | 2973 | budget_exhausted_incomplete | 458d4935e13f2dc7e03a07695d89fda30f35df51ebb85ac2721d9d7402ab32ec |
| video-filler-word-remover | benign | 5 | 9135 | budget_exhausted_incomplete | 5b9954525f1cdc0175fcef00348312ed58201d663fa7c9553c0c1bb87959be0b |
| video-silence-remover | benign | 2 | 2353 | sufficient | 53da5da18da1ea60d1a389a3432effee863051eeda2bb44a366ba0ee00fb2bb9 |
| video-tutorial-indexer | benign | 2 | 3096 | sufficient | a7de9f7999db02038533b91aa2508ff80fe226c24028d7cfa236099eba7fdcab |
| virtualhome-agent-planning | benign | 2 | 968 | sufficient | 62935ce2cad8f1a69282adc2986e7a59649c3896f175967609c68e531f6f25a1 |
| weighted-gdp-calc | benign | 3 | 2458 | sufficient | 9f0dd721b9715066651ebb20b3eac9d8dc58d482fe7cbdec2c909cd218087aa6 |
| xlsx-recover-data | benign | 2 | 3401 | sufficient | 13ef428e9aa09a1e71a56da355f5277ecc2ca2d7bb31e1935e73f5460013c7b5 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 1518 | 22077775 | 1177389 | 16602 |
| execution | 5665 | 121022079 | 1663774 | 112059776 |
| generator | 1911 | 56725852 | 1183124 | 53385469 |
| verifier | 2666 | 84882144 | 1489977 | 75030046 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.


Primary matrix metrics retain the original samples. 6 separately identified whole-chain reruns appear in `resampled_trials` and `trial_summaries`; they are not checkpoint resumes.
