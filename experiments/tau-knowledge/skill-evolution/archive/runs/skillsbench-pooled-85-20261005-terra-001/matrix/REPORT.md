# skillsbench run report

Protocol: `skillsbench.skill-evolution.v1`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility |
| --- | --- | --- | --- | --- | --- | --- |
| benign | evolved | 85 | 61 | 55 | 0.309091 | 0.2 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 61 | 54 | 0.314815 | {'oracle_success': 12, 'oracle_budget_exhausted': 1, 'rollout_result_unknown': 11, 'verification_program_error_exhausted': 8, 'oracle_result_unknown': 2, 'verifier_initialization_result_unknown': 1} |
| benign | 1 | 26 | 25 | 0.16 | {'rollout_result_unknown': 4, 'verification_program_error_exhausted': 8, 'oracle_budget_exhausted': 1, 'test_escalation_failed': 1} |
| benign | 2 | 12 | 12 | 0.166667 | {'rollout_result_unknown': 1, 'verification_program_error_exhausted': 1} |
| benign | 3 | 10 | 10 | 0.2 | {'oracle_result_unknown': 1, 'test_escalation_failed': 1, 'verification_program_error_exhausted': 1} |
| benign | 4 | 7 | 7 | 0.142857 | {'rollout_result_unknown': 1, 'revision_result_unknown': 1} |
| benign | 5 | 5 | 5 | 0.2 | {'rollout_result_unknown': 1} |
| benign | 6 | 4 | 4 | 0.5 | {} |
| benign | 7 | 4 | 4 | 0.5 | {'verification_program_error_exhausted': 1} |
| benign | 8 | 3 | 3 | 0.666667 | {} |
| benign | 9 | 3 | 3 | 0.333333 | {} |
| benign | 10 | 3 | 3 | 0.333333 | {} |
| benign | 11 | 3 | 3 | 0.666667 | {} |
| benign | 12 | 3 | 3 | 0.333333 | {} |
| benign | 13 | 3 | 3 | 0.333333 | {'rollout_result_unknown': 1} |
| benign | 14 | 2 | 2 | 0.5 | {} |
| benign | 15 | 2 | 1 | 1 | {'revision_budget_exhausted': 2} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Final hash |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | oracle_success | 1 | 0 | 1 | adc2de9540e243c51f61f379b1382b4e3dd2757fd1abb592fbf533ea1510116b |
| adaptive-cruise-control | benign | rollout_result_unknown | 2 | 1 | 0 | 4b243c4d8c24d532c3036a223387e70d8e161f9bbe3d6f8fa6d8d64c4afacccd |
| azure-bgp-oscillation-route-leak | benign | verification_program_error_exhausted | 2 | 1 | 0 | 84353fb558720a9ea107804ff4fa971a93122cd93c64d8051fc3b251d2a1619c |
| citation-check | benign | oracle_budget_exhausted | 1 | 0 | 5 | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e |
| civ6-adjacency-optimizer | benign | rollout_result_unknown | 1 | 0 | 0 | 06efe451227355b0b1a4b6767da83a79ad5974321952c7e6230b9904b86f4c3a |
| court-form-filling | benign | rollout_result_unknown | 2 | 1 | 0 | 8099f3a2eb728c491570b180a331ad47010419ed9d07885f2a21ee81aa101b86 |
| crystallographic-wyckoff-position-analysis | benign | verification_program_error_exhausted | 1 | 0 | 0 | 5b3bf7eda064a0f0582ea359e21e480c9af4487e525aadfc55d686362cb2c72e |
| dapt-intrusion-detection | benign | oracle_success | 1 | 0 | 1 | e9b42c625e33df3052e917d2b883cf41fed9732dba540ce4c02bcc1fe4688ac1 |
| data-to-d3 | benign | rollout_result_unknown | 2 | 1 | 0 | 42196e8f0fa0774fe3553057c5086886b6033a807ecb1f2d74db35c934a674be |
| dialogue-parser | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| dynamic-object-aware-egomotion | benign | oracle_budget_exhausted | 2 | 1 | 5 | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | oracle_success | 1 | 0 | 1 | 0216041dfc3facb34a22c5dc4f490c8cf3d1646d9fc89fc4f5e7f3e952e8c791 |
| econ-detrending-correlation | benign | oracle_success | 1 | 0 | 1 | ff5dd1eb7a51acf7c1ac2e55035cd12ea0eae426b675b91fce507fb8cf4ac6a6 |
| energy-ac-optimal-power-flow | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| energy-market-pricing | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| enterprise-information-search | benign | rollout_result_unknown | 3 | 2 | 2 | ed030a8856df9f8240cd955ceeed702f95170df304e9a6696efb0c08e46934c6 |
| exceltable-in-ppt | benign | oracle_success | 1 | 0 | 1 | a63689dfa675df3f5591be97d3b3c2a8cf3191bf2f23c9c88eedc7923d0b388c |
| exoplanet-detection-period | benign | oracle_result_unknown | 4 | 3 | 3 | 8ed24e3810d4bf3212a39c67f932950ef88684ce51be06287d330e60483d0100 |
| financial-modeling-qa | benign | verification_program_error_exhausted | 2 | 1 | 0 | ac585c8f595254531b821c7df01cd3109a71077d3e07322a52bf1384bff4e938 |
| find-topk-similiar-chemicals | benign | oracle_result_unknown | 1 | 0 | 0 | 729633b70577338a0f265f8285f8e5baaae22f80049879adde0e3f906cf3df54 |
| fix-build-agentops | benign | rollout_result_unknown | 1 | 0 | 0 | a15a67eeebc99a1b5ae56dc139dae74c591e2a7cd7ba9c1d5f8820bce8383e43 |
| fix-build-google-auto | benign | rollout_result_unknown | 1 | 0 | 0 | 90c59836c60a1761917d2c44a131842fb7dcf3eec32954552cd6ff72a2e2d910 |
| fix-druid-loophole-cve | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| fix-visual-stability | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| flink-query | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | e40897d3e71647dfcffbc690d7c313cf2e3ff3b9919dfd892da88e079875ef22 |
| flood-risk-analysis | benign | rollout_result_unknown | 6 | 5 | 1 | 40d66f38a60e5165be294dd6617f03e58b7bdad74ea5d493fa9c9f481420b700 |
| gh-repo-analytics | benign | test_escalation_failed | 4 | 6 | 3 | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 |
| glm-lake-mendota | benign | verification_program_error_exhausted | 1 | 0 | 0 | b348552eee916a8f3913169a237eb6f542e9f530ab04d315d83a9d5b26a10b64 |
| gravitational-wave-detection | benign | generation_result_unknown | 0 | 0 | 0 | NOT_MEASURED |
| grid-dispatch-operator | benign | rollout_result_unknown | 1 | 0 | 0 | ff6364e0e8a984b2333d9264fef15fdc62f4f7119d172bba28cd799c91632c8e |
| hvac-control | benign | generation_result_unknown | 0 | 0 | 0 | NOT_MEASURED |
| invoice-fraud-detection | benign | verification_program_error_exhausted | 2 | 1 | 0 | b050cd48e09673ca7174db69763cb2b8641f3ce877176e9a135c25bea94f7fa6 |
| jax-computing-basics | benign | rollout_result_unknown | 5 | 4 | 0 | a2e8d57e65f5ad324c3cea605a010a1af92a73e4a50e722c6c2294e3fd7597f5 |
| jpg-ocr-stat | benign | verification_program_error_exhausted | 8 | 7 | 2 | 2aa5ab15befc5b458a687fb1c610d27e59e67971bc90948f7eec2f765b734698 |
| lab-unit-harmonization | benign | verification_program_error_exhausted | 2 | 1 | 0 | c3e771c0d801771780e0638b947e2fc68e7d12ff864cdac84c5bf9cacc436dec |
| lake-warming-attribution | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| latex-formula-extraction | benign | rollout_result_unknown | 1 | 0 | 3 | 6af057de1f2d23dc5db7f455ebcbfa0dfc0f4fd111567067f11b3a111becd103 |
| lean4-proof | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-codebook-normalization | benign | rollout_result_unknown | 1 | 0 | 3 | bf8507ac5e08bd2570accce8c15be104f3d11b6e44f8d7e14adad0b6070a89e4 |
| manufacturing-equipment-maintenance | benign | verification_program_error_exhausted | 1 | 0 | 0 | 764f343771dc6bf60579278fed9d359ea921be48fb70951199702182d9d9c775 |
| manufacturing-fjsp-optimization | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| mario-coin-counting | benign | verification_program_error_exhausted | 1 | 0 | 0 | 1c53a92c93580e99d765001d78972e8b7ba29754996e1deb46273021beacf5e7 |
| mars-clouds-clustering | benign | oracle_success | 1 | 0 | 1 | 93f4ddbafd7036ca603a0c10a3ea60b2c672412ad4382726acd522306cc0bc30 |
| multilingual-video-dubbing | benign | rollout_result_unknown | 2 | 1 | 0 | c85d685bb86dcdcc80f26f7b940af17ee02df11372971686e4162d084e2855ca |
| offer-letter-generator | benign | oracle_success | 1 | 0 | 1 | b88ef1cf3fec5ad48b78b803cdef728220deb8d57c125ead7fde78aa9c966c58 |
| organize-messy-files | benign | verification_program_error_exhausted | 1 | 0 | 0 | cacae0885f711115c4478e4bcdec6285e5acafb70799fcdefcfbc5dbb42b5d66 |
| paper-anonymizer | benign | revision_result_unknown | 5 | 5 | 0 | 78d7939e1b218215240c761bf4711af1b06d4be45b4694819af86917fedbcb96 |
| parallel-tfidf-search | benign | verification_program_error_exhausted | 1 | 0 | 0 | 735fb562c019642a8242514e1258718d399b14f0bd424022a84f446ba548c0d9 |
| pddl-tpp-planning | benign | revision_budget_exhausted | 16 | 15 | 0 | 7152074006f163983f8969d0bf7828036e1312afc6f9ffd6698b68b66d968896 |
| pdf-excel-diff | benign | oracle_success | 1 | 0 | 1 | 61f54aabeba443a389b2f881713a6ed0649add89034da5e247f9e13929d7cff8 |
| pedestrian-traffic-counting | benign | rollout_result_unknown | 1 | 0 | 0 | eb27a71401068eed162fa3e50b7a0aaff4e07df5bf901bafd85393c3dbef213b |
| pg-essay-to-audiobook | benign | verification_program_error_exhausted | 1 | 0 | 0 | e42184e8ba74a7f6428624e3d77ffda35458009b071b220f9ad8b2e3c179d13c |
| powerlifting-coef-calc | benign | oracle_success | 1 | 0 | 1 | e4fd00e7635033ac7196bcd594c105cdab37793ab6ea3ef784b5d2cb3c222705 |
| pptx-reference-formatting | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| protein-expression-analysis | benign | verification_program_error_exhausted | 3 | 2 | 2 | bee995358c90d6c33940013b7bf6d862fdb877604ec3f9a58856af8bdaa4dae6 |
| python-scala-translation | benign | rollout_result_unknown | 1 | 0 | 0 | 57facf3726ae553a06581618bfbcc13491cdf41549ceeb749e70c17770172f6a |
| quantum-numerical-simulation | benign | oracle_success | 1 | 0 | 1 | 42ae9edfe8e9722839712c2f5a107271dd647310ce1ecdaaf4ba07277687dc7a |
| r2r-mpc-control | benign | oracle_success | 1 | 0 | 2 | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 |
| react-performance-debugging | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| reserves-at-risk-calc | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| sales-pivot-analysis | benign | verification_program_error_exhausted | 2 | 1 | 0 | ab69736cd9864fbb9b80ec18e9dcb711aed1a0f0a4722814c6ec19813efed7e0 |
| sec-financial-report | benign | verification_program_error_exhausted | 4 | 3 | 0 | 8ab2820acce4c0137315e6f6f09d9109e317b709ef77652ab874121b2997f2ec |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | rollout_result_unknown | 1 | 0 | 0 | 5e873d7c20a644fa1bbf96702c7548d41a56d20169b793f448cee7b83233cada |
| shock-analysis-demand | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| shock-analysis-supply | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| speaker-diarization-subtitles | benign | rollout_result_unknown | 1 | 0 | 0 | ba17756aab4074f36310871d41e2ae71ee8e4a44419bb9537fc77ed1964601d2 |
| spring-boot-jakarta-migration | benign | verification_program_error_exhausted | 1 | 0 | 0 | 29725d02098f1982993f513c5cfadf9392dda5a1584a573a6e2331c2ec5c8f48 |
| suricata-custom-exfil | benign | verification_program_error_exhausted | 2 | 1 | 0 | dc680618440eb1f0831e3a84ed6b10eb1ca94a1c4242cf2a770c1ea62facd149 |
| syzkaller-ppdev-syzlang | benign | generation_result_unknown | 0 | 0 | 0 | NOT_MEASURED |
| taxonomy-tree-merge | benign | rollout_result_unknown | 1 | 0 | 0 | f47b0f9851251163166c6ccc16f5c5463c914e5461018d38d3c10269f24035ab |
| threejs-structure-parser | benign | invalid_package | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | invalid_package | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | rollout_result_unknown | 14 | 13 | 0 | 9d0c6f4a3847a4e6a98f2d54af82d858990f4d909539cadef2548ad0d1612413 |
| trend-anomaly-causal-inference | benign | operation 'collect-base' has an unknown result | 0 | 0 | 0 | NOT_MEASURED |
| video-filler-word-remover | benign | oracle_result_unknown | 1 | 0 | 0 | 3f60d2db313bc6cd29d2018c481131978033bda52d020081a8a7d97c931db5bc |
| video-silence-remover | benign | test_escalation_failed | 2 | 1 | 1 | 37daf18a9bd4e7d6050fd48409f674927c7bb5f8819027af147963217771c2c1 |
| video-tutorial-indexer | benign | oracle_success | 1 | 0 | 1 | 402e669dc43ddd24fde377f59c6313ba8ac1ab9e6554044f2b58cbed08372f1f |
| virtualhome-agent-planning | benign | revision_budget_exhausted | 16 | 15 | 0 | 15577dea207abe88417cc3704ed30f4e6b1d07574527e922e70d1279109dd26e |
| weighted-gdp-calc | benign | verification_program_error_exhausted | 2 | 1 | 0 | 4e0899dcbec0e49368aa83053bf9c2a65bf4c36bb989ade5294a9a20ebad4bb6 |
| xlsx-recover-data | benign | verification_program_error_exhausted | 2 | 1 | 0 | 581c002f98e88bb436e651ed8eaa6f97107457f6ed484655f9b60a952db1a963 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 0 | S0 / final | adc2de9540e243c51f61f379b1382b4e3dd2757fd1abb592fbf533ea1510116b | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| adaptive-cruise-control | 0 | S0 | 792fb123e9d21d40c8c135f301685d5fb86226812086958cdc621c91e0ab3e84 | MEASURED | False | 0 | 5 | 12 | 0.416667 |
| adaptive-cruise-control | 1 | S1 / final | 4b243c4d8c24d532c3036a223387e70d8e161f9bbe3d6f8fa6d8d64c4afacccd | MEASURED | False | 0 | 5 | 12 | 0.416667 |
| azure-bgp-oscillation-route-leak | 0 | S0 | 3c25629b743fb4ce99399c137cab86fb1eff2a5bde0913673b2431c669cb7ab8 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| azure-bgp-oscillation-route-leak | 1 | S1 / final | 84353fb558720a9ea107804ff4fa971a93122cd93c64d8051fc3b251d2a1619c | MEASURED | False | 0 | 3 | 4 | 0.75 |
| citation-check | 0 | S0 / final | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | MEASURED | False | 0 | 7 | 9 | 0.777778 |
| civ6-adjacency-optimizer | 0 | S0 / final | 06efe451227355b0b1a4b6767da83a79ad5974321952c7e6230b9904b86f4c3a | MEASURED | False | 0 | 9 | 10 | 0.9 |
| court-form-filling | 0 | S0 | 5996be3695a051917ec707cb87ed570f1f8dbf417a316927dd352f4a1078c79d | MEASURED | False | 0 | 4 | 5 | 0.8 |
| court-form-filling | 1 | S1 / final | 8099f3a2eb728c491570b180a331ad47010419ed9d07885f2a21ee81aa101b86 | MEASURED | False | 0 | 4 | 5 | 0.8 |
| crystallographic-wyckoff-position-analysis | 0 | S0 / final | 5b3bf7eda064a0f0582ea359e21e480c9af4487e525aadfc55d686362cb2c72e | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | 0 | S0 / final | e9b42c625e33df3052e917d2b883cf41fed9732dba540ce4c02bcc1fe4688ac1 | MEASURED | True | 1 | 14 | 14 | 1 |
| data-to-d3 | 0 | S0 | e63679e1934572d850d2eae4dd52e53d96b01e2974f587dc842fac6a054ba073 | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| data-to-d3 | 1 | S1 / final | 42196e8f0fa0774fe3553057c5086886b6033a807ecb1f2d74db35c934a674be | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| dynamic-object-aware-egomotion | 0 | S0 | 51dd9315930811cf1d93c722202a0c98da6ef9f072fb7a57df71c8a4a8e7585d | MEASURED | False | 0 | 9 | 11 | 0.818182 |
| dynamic-object-aware-egomotion | 1 | S1 / final | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | MEASURED | False | 0 | 10 | 11 | 0.909091 |
| earthquake-plate-calculation | 0 | S0 / final | 0216041dfc3facb34a22c5dc4f490c8cf3d1646d9fc89fc4f5e7f3e952e8c791 | MEASURED | True | 1 | 8 | 8 | 1 |
| econ-detrending-correlation | 0 | S0 / final | ff5dd1eb7a51acf7c1ac2e55035cd12ea0eae426b675b91fce507fb8cf4ac6a6 | MEASURED | True | 1 | 4 | 4 | 1 |
| enterprise-information-search | 0 | S0 | fb009b9dc5993a41e4c47a343b53a5c5b3eda8f53c05522d64be32d3a8fd82d7 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| enterprise-information-search | 1 | S1 | 19a3950c81ee8b09b1fdfb7a5d47110cede7a8de841365338fe0b8c09eeccb6c | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| enterprise-information-search | 2 | S2 / final | ed030a8856df9f8240cd955ceeed702f95170df304e9a6696efb0c08e46934c6 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| exceltable-in-ppt | 0 | S0 / final | a63689dfa675df3f5591be97d3b3c2a8cf3191bf2f23c9c88eedc7923d0b388c | MEASURED | True | 1 | 8 | 8 | 1 |
| exoplanet-detection-period | 0 | S0 | 5714e32515b0f26d22b4aac91c257ab212a0617c9715d974da22b91e129a5299 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| exoplanet-detection-period | 1 | S1 | 34b809f3b3efc2b8414c106c16a0360b306956287eb7033f85f65419807c5128 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| exoplanet-detection-period | 2 | S2 | edeace9b50250f9d5d842cf7dcb666339e9e1228bb8300a2f238448ce7a289fd | MEASURED | False | 0 | 3 | 4 | 0.75 |
| exoplanet-detection-period | 3 | S3 / final | 8ed24e3810d4bf3212a39c67f932950ef88684ce51be06287d330e60483d0100 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| financial-modeling-qa | 0 | S0 | 98b7ce8203742a09455af33b9b796809ce965cefe8e9885e607da55689daba89 | MEASURED | False | 0 | 1 | 4 | 0.25 |
| financial-modeling-qa | 1 | S1 / final | ac585c8f595254531b821c7df01cd3109a71077d3e07322a52bf1384bff4e938 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| find-topk-similiar-chemicals | 0 | S0 / final | 729633b70577338a0f265f8285f8e5baaae22f80049879adde0e3f906cf3df54 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-build-agentops | 0 | S0 / final | a15a67eeebc99a1b5ae56dc139dae74c591e2a7cd7ba9c1d5f8820bce8383e43 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| fix-build-google-auto | 0 | S0 / final | 90c59836c60a1761917d2c44a131842fb7dcf3eec32954552cd6ff72a2e2d910 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| flink-query | 0 | S0 / final | e40897d3e71647dfcffbc690d7c313cf2e3ff3b9919dfd892da88e079875ef22 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| flood-risk-analysis | 0 | S0 | 98c61977bdacf10086415d0ce9a9af4bd4b8f3e2074efdf2ae149c7c5a602648 | MEASURED | False | 0 | 0 | 2 | 0 |
| flood-risk-analysis | 1 | S1 | 70f4e401e4a0e0f8d2eade998dc87d1ae20004f1b197f6dd3c73779597248595 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| flood-risk-analysis | 2 | S2 | ebdcb62343adfa84bc7ea755260b699e526ab8f9890264df94b0ef5b60993f19 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| flood-risk-analysis | 3 | S3 | cc78245232ca0dc733841c20b768adbbc252d7a729b593f1d592ba83e9a1b61c | MEASURED | False | 0 | 1 | 2 | 0.5 |
| flood-risk-analysis | 4 | S4 | 66db99613e2c35a11870ff3842bf9d0ccf879b0133b9937b5a19654ed2fe216f | MEASURED | False | 0 | 1 | 2 | 0.5 |
| flood-risk-analysis | 5 | S5 / final | 40d66f38a60e5165be294dd6617f03e58b7bdad74ea5d493fa9c9f481420b700 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| gh-repo-analytics | 0 | S0 | 6821a404d3a03608625e46fd6c90bb51ae94414a1bc26cbb6f8c59ea9b8dd318 | MEASURED | False | 0 | 0 | 8 | 0 |
| gh-repo-analytics | 1 | S1 | 7a7d43d2290ba34fe062f18d704a73dce05f2e4de250407db1f216db01926d57 | MEASURED | False | 0 | 0 | 8 | 0 |
| gh-repo-analytics | 2 | S2 | bf53ee2ffa021ed594309964b680bddc74aa532bcf4f8a61e9c61dbf590f7cd3 | MEASURED | False | 0 | 0 | 8 | 0 |
| gh-repo-analytics | 3 | S3 / final | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 | MEASURED | False | 0 | 0 | 8 | 0 |
| glm-lake-mendota | 0 | S0 / final | b348552eee916a8f3913169a237eb6f542e9f530ab04d315d83a9d5b26a10b64 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| grid-dispatch-operator | 0 | S0 / final | ff6364e0e8a984b2333d9264fef15fdc62f4f7119d172bba28cd799c91632c8e | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| invoice-fraud-detection | 0 | S0 | 7cca4b5d880d7d99c5b46f261216fb50281c5580f196a0a38ac5e3283d7b93f0 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| invoice-fraud-detection | 1 | S1 / final | b050cd48e09673ca7174db69763cb2b8641f3ce877176e9a135c25bea94f7fa6 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| jax-computing-basics | 0 | S0 | ff63bbc1422d567a14e2e90a1a6fb4e50db2f3925e1138a81ddeca451e7cee02 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 1 | S1 | 8817b890f02a90e273fb3620ea2232b84658c0fbb328b6241d3dc88c85509969 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 2 | S2 | 661816e75d837a08e77900e019ff8b763a398edfcf92f82b42b1f4e7bd85e764 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 3 | S3 | af4a2b8697bedf28a6175819bc6e48ebd4bdf784c73960444d25227aea80908c | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 4 | S4 / final | a2e8d57e65f5ad324c3cea605a010a1af92a73e4a50e722c6c2294e3fd7597f5 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jpg-ocr-stat | 0 | S0 | e8f00ea5009546e8c91f8b793e4e816b0428c4817f0f8950be4049ed9bc3c3dd | MEASURED | True | 1 | 1 | 1 | 1 |
| jpg-ocr-stat | 1 | S1 | dae5d4147359ef0fec7ee7c8035b6efc9f3debbaba12a38c4fb53025a5580ff4 | MEASURED | True | 1 | 1 | 1 | 1 |
| jpg-ocr-stat | 2 | S2 | 6f6f58428de9b8a1fe5108d4f74dff4c315f3aed4f8f65df944e1406500a47a4 | MEASURED | True | 1 | 1 | 1 | 1 |
| jpg-ocr-stat | 3 | S3 | 9a0f20859951a38f4e575841b6ea4502e70c9061e407d085989a0d0227bc1ccb | MEASURED | True | 1 | 1 | 1 | 1 |
| jpg-ocr-stat | 4 | S4 | 19e43f128917c200bd1f0994a2061b047d403d3a273fc31fd636b328ddd2d478 | MEASURED | False | 0 | 0 | 1 | 0 |
| jpg-ocr-stat | 5 | S5 | 417a1aef8d0989ee2b05fbb7e9eebd14f1dba0f4e33996cf1f4664bc9d989188 | MEASURED | False | 0 | 0 | 1 | 0 |
| jpg-ocr-stat | 6 | S6 | 031f92bd400bd287b7931e238913ac3d8e68d4f9ad29c1b49c90db4150673afd | MEASURED | True | 1 | 1 | 1 | 1 |
| jpg-ocr-stat | 7 | S7 / final | 2aa5ab15befc5b458a687fb1c610d27e59e67971bc90948f7eec2f765b734698 | MEASURED | True | 1 | 1 | 1 | 1 |
| lab-unit-harmonization | 0 | S0 | 7cc1de6dacd479cc6aabcc55b4524fa8628fb26a4ba7a27a2d80879972dcf0ca | MEASURED | False | 0.604 | 29 | 48 | 0.604167 |
| lab-unit-harmonization | 1 | S1 / final | c3e771c0d801771780e0638b947e2fc68e7d12ff864cdac84c5bf9cacc436dec | MEASURED | False | 0.396 | 19 | 48 | 0.395833 |
| latex-formula-extraction | 0 | S0 / final | 6af057de1f2d23dc5db7f455ebcbfa0dfc0f4fd111567067f11b3a111becd103 | MEASURED | False | 0 | 5 | 7 | 0.714286 |
| manufacturing-codebook-normalization | 0 | S0 / final | bf8507ac5e08bd2570accce8c15be104f3d11b6e44f8d7e14adad0b6070a89e4 | MEASURED | False | 0 | 12 | 16 | 0.75 |
| manufacturing-equipment-maintenance | 0 | S0 / final | 764f343771dc6bf60579278fed9d359ea921be48fb70951199702182d9d9c775 | MEASURED | False | 0 | 4 | 7 | 0.571429 |
| mario-coin-counting | 0 | S0 / final | 1c53a92c93580e99d765001d78972e8b7ba29754996e1deb46273021beacf5e7 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| mars-clouds-clustering | 0 | S0 / final | 93f4ddbafd7036ca603a0c10a3ea60b2c672412ad4382726acd522306cc0bc30 | MEASURED | True | 1 | 8 | 8 | 1 |
| multilingual-video-dubbing | 0 | S0 | 4fefcf4873fe9706ab1fc2a8dd247d0e6b0a0836666ab566f92b03ad0cd7bcf6 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| multilingual-video-dubbing | 1 | S1 / final | c85d685bb86dcdcc80f26f7b940af17ee02df11372971686e4162d084e2855ca | MEASURED | False | 0 | 0 | 8 | 0 |
| offer-letter-generator | 0 | S0 / final | b88ef1cf3fec5ad48b78b803cdef728220deb8d57c125ead7fde78aa9c966c58 | MEASURED | True | 1 | 4 | 4 | 1 |
| organize-messy-files | 0 | S0 / final | cacae0885f711115c4478e4bcdec6285e5acafb70799fcdefcfbc5dbb42b5d66 | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| paper-anonymizer | 0 | S0 | be97e59a2d67322b7b090a09fa04ab9aa06745bfe2739004e24518d8952f25de | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 1 | S1 | 0376a250429c2ef725b1fdf3b6865bfb7e3317206a1afa93b477d745109967e1 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 2 | S2 | 43df03ecd0b38c2d96e0a9bf44c748cb6912cf5d6d15e8d5ffc4f8880a80e852 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 3 | S3 | de41954a0f3ad0c59ba645a0506b70646034a01f9a449fb0286a5312efc273f3 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 4 | S4 / final | 78d7939e1b218215240c761bf4711af1b06d4be45b4694819af86917fedbcb96 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| parallel-tfidf-search | 0 | S0 / final | 735fb562c019642a8242514e1258718d399b14f0bd424022a84f446ba548c0d9 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| pddl-tpp-planning | 0 | S0 | 2908fdda3185718f62c3bec07423add6eb170b409e54a6789d0eae53db41c47b | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 1 | S1 | 6e9b2389b98bbd37b63f8a5af29f814291b632594eca1dfd4a5695e963d067eb | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 2 | S2 | 52c8a97b73806778822eed741c332498d14b530447b09f534bb945dcb23207b5 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 3 | S3 | 54c190840bb7fdfae0ca68e03c601f34c3328dd8a1524fd22a84b3319a4edea6 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 4 | S4 | 7281092b77e3624a7bf87dbc0e30d5d13375bb0c2615bb462387b0a47d9bcc5c | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 5 | S5 | 82bd37622057cfa08ef0d5ebe63a4ebbcc3538033bb54a5e7bef0173ad419a6d | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 6 | S6 | d8249271bab35c2ae77959fa23aa3980232cedf1ad45693f5b0ad7167a724c89 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 7 | S7 | 605c5bb944d9b6f96269b1a5d757de0dd8a4a030320ed1a4078b15acd4e7187b | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 8 | S8 | e0a0eeb5a3b84741daa9a2758772c01c5a5220977498240a5f337d55247cc3f3 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 9 | S9 | c22cd738bea70a9b6e92af2385e4b6aae9ca030ad60e812eac66bf8d741c9752 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 10 | S10 | f4a3ad3809069ae0b1577da61d5b999974728e6becc899b99bec6014695fda2f | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 11 | S11 | a77456ccfd927821a211adb674f5ef1108d1e1b70751f47f9c64e7ffc7eef9c3 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 12 | S12 | c5fc7edd978153274dad82dfe95d2450cdccb07ed84820045dd77600578e71f9 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 13 | S13 | 53d1386ab16886743d05f362cac45c557d7be2bce6dbad98fe06a5a7752f30f3 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 14 | S14 | 17772fc7341d856c20ca6e0d09117a56bccb781f41e6cea4900f0e042da0bdd1 | MEASURED | True | 1 | 2 | 2 | 1 |
| pddl-tpp-planning | 15 | S15 / final | 7152074006f163983f8969d0bf7828036e1312afc6f9ffd6698b68b66d968896 | MEASURED | True | 1 | 2 | 2 | 1 |
| pdf-excel-diff | 0 | S0 / final | 61f54aabeba443a389b2f881713a6ed0649add89034da5e247f9e13929d7cff8 | MEASURED | True | 1 | 11 | 11 | 1 |
| pedestrian-traffic-counting | 0 | S0 / final | eb27a71401068eed162fa3e50b7a0aaff4e07df5bf901bafd85393c3dbef213b | MEASURED | False | 0.305556 | 0 | 1 | 0 |
| pg-essay-to-audiobook | 0 | S0 / final | e42184e8ba74a7f6428624e3d77ffda35458009b071b220f9ad8b2e3c179d13c | MEASURED | False | 0 | 0 | 4 | 0 |
| powerlifting-coef-calc | 0 | S0 / final | e4fd00e7635033ac7196bcd594c105cdab37793ab6ea3ef784b5d2cb3c222705 | MEASURED | True | 1 | 11 | 11 | 1 |
| protein-expression-analysis | 0 | S0 | f85f675b623d849d009a360aca48214a1ee273b90a02f7877ed2bfe81f882cb0 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| protein-expression-analysis | 1 | S1 | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| protein-expression-analysis | 2 | S2 / final | bee995358c90d6c33940013b7bf6d862fdb877604ec3f9a58856af8bdaa4dae6 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | 0 | S0 / final | 57facf3726ae553a06581618bfbcc13491cdf41549ceeb749e70c17770172f6a | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| quantum-numerical-simulation | 0 | S0 / final | 42ae9edfe8e9722839712c2f5a107271dd647310ce1ecdaaf4ba07277687dc7a | MEASURED | True | 1 | 7 | 7 | 1 |
| r2r-mpc-control | 0 | S0 / final | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| sales-pivot-analysis | 0 | S0 | 3a41dbfaf5743fa05dc9d988b77b90fc8b1f13c6aa35e7dcf4fb15bfe61a83b7 | MEASURED | False | 0 | 7 | 10 | 0.7 |
| sales-pivot-analysis | 1 | S1 / final | ab69736cd9864fbb9b80ec18e9dcb711aed1a0f0a4722814c6ec19813efed7e0 | MEASURED | False | 0 | 7 | 10 | 0.7 |
| sec-financial-report | 0 | S0 | 5e13dee0d4ea02852837afe17fa596f148bc35a16d47882a0ab56c0520e27660 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| sec-financial-report | 1 | S1 | 549caf0e1b330eb55f052ccaf300fc7db0338b24657917ba96a6ef48c805da99 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| sec-financial-report | 2 | S2 | 8b22df93b475a331fe2e3d0d86861548f3cc216432ad0fa0d380fd3ed7f2a91b | MEASURED | False | 0 | 1 | 2 | 0.5 |
| sec-financial-report | 3 | S3 / final | 8ab2820acce4c0137315e6f6f09d9109e317b709ef77652ab874121b2997f2ec | MEASURED | False | 0 | 1 | 2 | 0.5 |
| setup-fuzzing-py | 0 | S0 / final | 5e873d7c20a644fa1bbf96702c7548d41a56d20169b793f448cee7b83233cada | MEASURED | False | 0.16 | 2 | 2 | 1 |
| speaker-diarization-subtitles | 0 | S0 / final | ba17756aab4074f36310871d41e2ae71ee8e4a44419bb9537fc77ed1964601d2 | MEASURED | False | 0 | 6 | 10 | 0.6 |
| spring-boot-jakarta-migration | 0 | S0 / final | 29725d02098f1982993f513c5cfadf9392dda5a1584a573a6e2331c2ec5c8f48 | MEASURED | False | 0 | 8 | 10 | 0.8 |
| suricata-custom-exfil | 0 | S0 | bd8bf172bbdbc93b9a87f843c1c6f1a7348e3545c77ef26ae592ee733b1515b3 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| suricata-custom-exfil | 1 | S1 / final | dc680618440eb1f0831e3a84ed6b10eb1ca94a1c4242cf2a770c1ea62facd149 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| taxonomy-tree-merge | 0 | S0 / final | f47b0f9851251163166c6ccc16f5c5463c914e5461018d38d3c10269f24035ab | MEASURED | False | 0.7231 | 16 | 22 | 0.727273 |
| travel-planning | 0 | S0 | 8a390ff10eff8e0cd7edcd2da4e91a6cbf9e68aaccd6d34eee3d91f3433b28f2 | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 1 | S1 | a382d2d3d15a8c25651a452c3aca71f19f24284cff3c89ab6b6f7699be28b34f | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 2 | S2 | 1c152c7e7565903110893cabf3c8c4a10b30b8537dc8af240ad51b572b062da7 | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 3 | S3 | cbf54ee2560103bc9fc6b7a889652f424ee286efa734b63037834cf15412d5b8 | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 4 | S4 | 4f1e862c0d5aa7bccf81448686d695ced4e7ba550c871a13d5477d989b3a4a8f | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 5 | S5 | 4f1f4b34a6561dda7e78a4589c57522f68e46b95934e9e0dfda83480f5de20ca | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 6 | S6 | 59c67e0975a77e7c5dae18ad8a3758d0e5c99def68ea4448c2eb395d7922c0f0 | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 7 | S7 | 16047dbcb9be6bde1f8c5fa752cfc643741e92647ff72331b9572ada78ede8da | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 8 | S8 | b27fea7714810b9e9472d3639c15d8287b558ff5e2aa7c3d801a56e90d235496 | MEASURED | True | 1 | 10 | 10 | 1 |
| travel-planning | 9 | S9 | e5d4586110151d54f0d6753bd607b15da2647ecc38cb65b07cb7e9a76c47aeba | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 10 | S10 | e063257cc8549ab804903beb1a4ba0b6a0f869728b22a20c730606c17576e20a | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 11 | S11 | 289836a7a515b41cdff35745b39d31efc0fb287256942d9044ea8cdee9ed7da4 | MEASURED | True | 1 | 10 | 10 | 1 |
| travel-planning | 12 | S12 | 6566b8952b7a22658ea42ed6fa921ed04bb40d490804587b476c1dd9f3dd1c8e | MEASURED | False | 0 | 0 | 10 | 0 |
| travel-planning | 13 | S13 / final | 9d0c6f4a3847a4e6a98f2d54af82d858990f4d909539cadef2548ad0d1612413 | MEASURED | False | 0 | 9 | 10 | 0.9 |
| video-filler-word-remover | 0 | S0 / final | 3f60d2db313bc6cd29d2018c481131978033bda52d020081a8a7d97c931db5bc | MEASURED | True | 1 | 5 | 5 | 1 |
| video-silence-remover | 0 | S0 | e6e808a56358cfb7df11ee836bfd0255abebe90d67735d63130786264389baf8 | MEASURED | False | 0 | 4 | 9 | 0.444444 |
| video-silence-remover | 1 | S1 / final | 37daf18a9bd4e7d6050fd48409f674927c7bb5f8819027af147963217771c2c1 | MEASURED | False | 0 | 5 | 9 | 0.555556 |
| video-tutorial-indexer | 0 | S0 / final | 402e669dc43ddd24fde377f59c6313ba8ac1ab9e6554044f2b58cbed08372f1f | MEASURED | True | 1 | 2 | 2 | 1 |
| virtualhome-agent-planning | 0 | S0 | 4bca12ca7e84c21def18719b408a456e29f226a5a845d1dad291d0cd5043a582 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 1 | S1 | 62a271675e7991373d7e4c935bff4e8915e36db14d78860b9ecf4b4207900798 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 2 | S2 | 4b8b9b4cca79375a5a7e4317c1061069eb79eadf8a0a5ba4b7eeb1944ed8588b | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 3 | S3 | 25fc6ebfbd56aaa7852edf1c9c08b53b44905931527c97b214633d7107f571fa | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 4 | S4 | b941832c612f614d67e23fbdc655a2b57e90588d8ce0ca1ee41771b05a110fd4 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 5 | S5 | 9105135bf4d942948245d04da7f51248cc55bc64c0687a53090bb6e65f924488 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 6 | S6 | 66c0c80cb4681be504b8dae955d49360b10c6ebb48b62a565fa8dc4ceab49281 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 7 | S7 | 0c5df2de9449b5648a99e7f3842e837adeff86187edb86204d44150ae1679e55 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 8 | S8 | a4e47cd83eda897f48842b892539ef0de052cbd3080b6ff45256b5ed435a4e83 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 9 | S9 | 148cc366d5d249fba764399248ad500472a41a111a931f87a13e9a53e06db2fc | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 10 | S10 | 069140f2ba6f17a01a75bbac09eb75fc7014cf846ec4d7d42720a083f8c794db | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 11 | S11 | dcd7d2a0e76d852cf7271035bcc76e8650688f6625df0bff2c82315d575fa26f | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 12 | S12 | 5e131f661d3644b76ea54d21e8b754ba8832ec83902a4005e67c399f4cdeb975 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 13 | S13 | b8aa0438250a35362142537ea6545d7770f2648e6e489a459d14874e094423b2 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 14 | S14 | 1ad1cf4acee59dd4dde34a757b127348284a41a1e3bbedbff62afa5062af7119 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 15 | S15 / final | 15577dea207abe88417cc3704ed30f4e6b1d07574527e922e70d1279109dd26e | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| weighted-gdp-calc | 0 | S0 | 88f54ce629f0560c3f8c6c13451f5a7dbe0d1cf9d532e821d37b0b4b82e98b29 | MEASURED | False | 0 | 15 | 27 | 0.555556 |
| weighted-gdp-calc | 1 | S1 / final | 4e0899dcbec0e49368aa83053bf9c2a65bf4c36bb989ade5294a9a20ebad4bb6 | MEASURED | False | 0 | 15 | 27 | 0.555556 |
| xlsx-recover-data | 0 | S0 | 20607bc31ebb37472acaba2ae4f9586133b8a1770c416c32e5b7b11fd37487cd | MEASURED | True | 1 | 8 | 8 | 1 |
| xlsx-recover-data | 1 | S1 / final | 581c002f98e88bb436e651ed8eaa6f97107457f6ed484655f9b60a952db1a963 | MEASURED | True | 1 | 8 | 8 | 1 |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | adc2de9540e243c51f61f379b1382b4e3dd2757fd1abb592fbf533ea1510116b | 0 | 71d0b3f19a0249b12ada9b840dce2cbd20f64f458448a3c571c18a5a5b484f25 | True | 1 | NOT_MEASURED |
| adaptive-cruise-control | 792fb123e9d21d40c8c135f301685d5fb86226812086958cdc621c91e0ab3e84 | 0 | 49905cc9516a9730e79079ff2475f3944c617e802c6f8d9b1bc61a0df11806a8 | False | 0.888889 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 3c25629b743fb4ce99399c137cab86fb1eff2a5bde0913673b2431c669cb7ab8 | 0 | 17f21610e8d9494ee05b396989ca7c19c028873f59819be5de9ba1a57aa325c0 | False | 0.333333 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 84353fb558720a9ea107804ff4fa971a93122cd93c64d8051fc3b251d2a1619c | 0 | 17f21610e8d9494ee05b396989ca7c19c028873f59819be5de9ba1a57aa325c0 | False | 0.333333 | verifier_reported_test_program_error |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 0 | f8d2b80898102e71b15dda1851fe4b7150249115a8e458628af5e4dd4a549e25 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 1 | 12c2fb0cf9dc7bf0d64a7e26b94895fc9b66662b22db14b9421d0f99b03d6ca2 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 2 | 421945c17a62b2784320fc4ce1323345d7b0868f53f2614ef094ffe256f3c1a2 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 3 | 630f3626261349299ec2ffaa103b7383758dc49cd679e8b2468c6a459a38e787 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 4 | 17f4825071e787106794c6fd751c38a70993f7d0185faddd0aa240e55ce6be91 | True | 1 | NOT_MEASURED |
| court-form-filling | 5996be3695a051917ec707cb87ed570f1f8dbf417a316927dd352f4a1078c79d | 0 | 24329a764dd8ac016d1dbc114f4a59d57611b6ec81b135cb6902412fb148a52b | False | 0.6 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | 5b3bf7eda064a0f0582ea359e21e480c9af4487e525aadfc55d686362cb2c72e | 0 | 1231eeae24510c8dc3218ab3d4d4e053cc10e43fbda32aece9012648049a10ac | False | 0 | test_program_error |
| dapt-intrusion-detection | e9b42c625e33df3052e917d2b883cf41fed9732dba540ce4c02bcc1fe4688ac1 | 0 | 84db098bd8d6bb074ffe1cef9476e703732aa3aa8e0d98b92386d077e1081b2d | True | 1 | NOT_MEASURED |
| data-to-d3 | e63679e1934572d850d2eae4dd52e53d96b01e2974f587dc842fac6a054ba073 | 0 | ada27cb16be086ef02addd46976f391883d22a7503b6348b217739f93a89d6f7 | False | 0.666667 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 51dd9315930811cf1d93c722202a0c98da6ef9f072fb7a57df71c8a4a8e7585d | 0 | ba0c2fea64259b20ba7a1326d764fc6edea196b35175ed7f50f23ecebb429f8f | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 51dd9315930811cf1d93c722202a0c98da6ef9f072fb7a57df71c8a4a8e7585d | 1 | 1ea0ea150d455e87344e0f6fe1a7697d7f08ff5be262753e1354f603456f5564 | False | 0.8 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 1 | 1ea0ea150d455e87344e0f6fe1a7697d7f08ff5be262753e1354f603456f5564 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 2 | 9046381c72bd4a5b716959c7e310c3edcaf703bdd4b96e9bc872a402aad52cbd | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 3 | a59801a086a39517c5b701ce5c6ee8be283d290752fb8a7360184823e484d472 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 4 | 21c4beca896ae971e844882eb9b9f6b2c1fec75eadc5433302391df6d3600223 | True | 1 | NOT_MEASURED |
| earthquake-plate-calculation | 0216041dfc3facb34a22c5dc4f490c8cf3d1646d9fc89fc4f5e7f3e952e8c791 | 0 | b239fef387872e9a84df88811bffa34a5ce951e06a1e8789d2b0430822bb7324 | True | 1 | NOT_MEASURED |
| econ-detrending-correlation | ff5dd1eb7a51acf7c1ac2e55035cd12ea0eae426b675b91fce507fb8cf4ac6a6 | 0 | 0311ab71ed6ead07052f234652de1971f652430ed93ca7dc9b2017c6218baf60 | True | 1 | NOT_MEASURED |
| enterprise-information-search | fb009b9dc5993a41e4c47a343b53a5c5b3eda8f53c05522d64be32d3a8fd82d7 | 0 | ac7fa9d0d28f4336834145539af36ff55144e633d645a408e51255f04ccb227c | False | 0.666667 | NOT_MEASURED |
| enterprise-information-search | 19a3950c81ee8b09b1fdfb7a5d47110cede7a8de841365338fe0b8c09eeccb6c | 0 | ac7fa9d0d28f4336834145539af36ff55144e633d645a408e51255f04ccb227c | True | 1 | NOT_MEASURED |
| enterprise-information-search | 19a3950c81ee8b09b1fdfb7a5d47110cede7a8de841365338fe0b8c09eeccb6c | 1 | 2565cb37406b6c8afa22847a38e85a059f5de03c037c8977af3d321d87ff3400 | True | 1 | NOT_MEASURED |
| enterprise-information-search | 19a3950c81ee8b09b1fdfb7a5d47110cede7a8de841365338fe0b8c09eeccb6c | 2 | ed646ffa65237dd0b08b56ef9ff364fca5101afe3a6de2905739c2dd02da41a2 | False | 0.857143 | NOT_MEASURED |
| exceltable-in-ppt | a63689dfa675df3f5591be97d3b3c2a8cf3191bf2f23c9c88eedc7923d0b388c | 0 | c3cd66a0c65eb8032034c664424807ce0fb962e3997b7cc5ceeaa9d286f825ce | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | 5714e32515b0f26d22b4aac91c257ab212a0617c9715d974da22b91e129a5299 | 0 | e1c15351afe07dd23b330a8f333a1c242e55ef8cb397f761ff8e503e0c63047e | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | 5714e32515b0f26d22b4aac91c257ab212a0617c9715d974da22b91e129a5299 | 1 | 1c67bd2265fe69112bf33cb421fac18d37fbbf8ec9e4667c434b5a95c5253a75 | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | 34b809f3b3efc2b8414c106c16a0360b306956287eb7033f85f65419807c5128 | 1 | 1c67bd2265fe69112bf33cb421fac18d37fbbf8ec9e4667c434b5a95c5253a75 | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | edeace9b50250f9d5d842cf7dcb666339e9e1228bb8300a2f238448ce7a289fd | 1 | 2117b21d372e0d4cda672128ea57ba0e699996daf56be4752597279266612f2e | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | edeace9b50250f9d5d842cf7dcb666339e9e1228bb8300a2f238448ce7a289fd | 2 | b9dd12111846fb04c0b06e4e461ac5c68b6a42d24cffb62a28e0fdf152852faf | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | edeace9b50250f9d5d842cf7dcb666339e9e1228bb8300a2f238448ce7a289fd | 3 | ee6de18be764b930a89adaff5b73793d401cb47e17fb2070ff1f85775530cfc4 | False | 0.833333 | NOT_MEASURED |
| exoplanet-detection-period | 8ed24e3810d4bf3212a39c67f932950ef88684ce51be06287d330e60483d0100 | 3 | ee6de18be764b930a89adaff5b73793d401cb47e17fb2070ff1f85775530cfc4 | True | 1 | NOT_MEASURED |
| financial-modeling-qa | 98b7ce8203742a09455af33b9b796809ce965cefe8e9885e607da55689daba89 | 0 | 9aad2faeee47e8e85694b712a759477288e8e3ded825dcbdd864ae99b548a53c | False | 0.5 | NOT_MEASURED |
| financial-modeling-qa | ac585c8f595254531b821c7df01cd3109a71077d3e07322a52bf1384bff4e938 | 0 | 9aad2faeee47e8e85694b712a759477288e8e3ded825dcbdd864ae99b548a53c | False | 0.5 | verifier_reported_test_program_error |
| find-topk-similiar-chemicals | 729633b70577338a0f265f8285f8e5baaae22f80049879adde0e3f906cf3df54 | 0 | 69311479af7590d65cab4a64662211378ea247490d770b668ceef540a73e7879 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 98c61977bdacf10086415d0ce9a9af4bd4b8f3e2074efdf2ae149c7c5a602648 | 0 | 019b8910b150a6d8a7bb1d1e9e775a2938fc835d43e032e639875e437c2880db | False | 0 | NOT_MEASURED |
| flood-risk-analysis | 70f4e401e4a0e0f8d2eade998dc87d1ae20004f1b197f6dd3c73779597248595 | 0 | 019b8910b150a6d8a7bb1d1e9e775a2938fc835d43e032e639875e437c2880db | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 70f4e401e4a0e0f8d2eade998dc87d1ae20004f1b197f6dd3c73779597248595 | 1 | a62e54af03042ca849d73ce0de502a8d64e907d9ad589b16738a3f693862fedd | False | 0.5 | NOT_MEASURED |
| flood-risk-analysis | ebdcb62343adfa84bc7ea755260b699e526ab8f9890264df94b0ef5b60993f19 | 1 | a62e54af03042ca849d73ce0de502a8d64e907d9ad589b16738a3f693862fedd | False | 0.5 | NOT_MEASURED |
| flood-risk-analysis | cc78245232ca0dc733841c20b768adbbc252d7a729b593f1d592ba83e9a1b61c | 1 | a62e54af03042ca849d73ce0de502a8d64e907d9ad589b16738a3f693862fedd | False | 0.5 | NOT_MEASURED |
| flood-risk-analysis | 66db99613e2c35a11870ff3842bf9d0ccf879b0133b9937b5a19654ed2fe216f | 1 | a62e54af03042ca849d73ce0de502a8d64e907d9ad589b16738a3f693862fedd | False | 0.5 | NOT_MEASURED |
| gh-repo-analytics | 6821a404d3a03608625e46fd6c90bb51ae94414a1bc26cbb6f8c59ea9b8dd318 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | False | 0 | NOT_MEASURED |
| gh-repo-analytics | 7a7d43d2290ba34fe062f18d704a73dce05f2e4de250407db1f216db01926d57 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | False | 0 | NOT_MEASURED |
| gh-repo-analytics | bf53ee2ffa021ed594309964b680bddc74aa532bcf4f8a61e9c61dbf590f7cd3 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | False | 0 | NOT_MEASURED |
| gh-repo-analytics | bf53ee2ffa021ed594309964b680bddc74aa532bcf4f8a61e9c61dbf590f7cd3 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | False | 0 | NOT_MEASURED |
| gh-repo-analytics | bf53ee2ffa021ed594309964b680bddc74aa532bcf4f8a61e9c61dbf590f7cd3 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | False | 0 | NOT_MEASURED |
| gh-repo-analytics | bf53ee2ffa021ed594309964b680bddc74aa532bcf4f8a61e9c61dbf590f7cd3 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | False | 0 | NOT_MEASURED |
| gh-repo-analytics | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 | 0 | 02f4b3dd1107d16aad47ab00ec3117ca4a439839d9f6fa2a83e5a857ce33884b | True | 1 | NOT_MEASURED |
| gh-repo-analytics | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 | 1 | d88c43944f17b52d9b8fb463149d5aebfac31da6b60481543a8cb0bef9928bf3 | True | 1 | NOT_MEASURED |
| gh-repo-analytics | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 | 2 | 7fbd4735137af91a3b4c8e9c19bbcf8735691b82f20c10cc058a5c351f16194f | True | 1 | NOT_MEASURED |
| glm-lake-mendota | b348552eee916a8f3913169a237eb6f542e9f530ab04d315d83a9d5b26a10b64 | 0 | 01935840f612ba9d816eb6c66eb34283b1f9de7e56235316576e06d5be369997 | False | 0 | empty_or_invalid_tests |
| invoice-fraud-detection | 7cca4b5d880d7d99c5b46f261216fb50281c5580f196a0a38ac5e3283d7b93f0 | 0 | 81626aea26cb4d551539c7efe351195b2c66f12da0abf0d3e83795b67b5bf443 | False | 0 | NOT_MEASURED |
| invoice-fraud-detection | b050cd48e09673ca7174db69763cb2b8641f3ce877176e9a135c25bea94f7fa6 | 0 | 81626aea26cb4d551539c7efe351195b2c66f12da0abf0d3e83795b67b5bf443 | False | 0 | verifier_reported_test_program_error |
| jax-computing-basics | ff63bbc1422d567a14e2e90a1a6fb4e50db2f3925e1138a81ddeca451e7cee02 | 0 | ed0121f0ed7ec8994bd59dccd9df215da83637afc7280d7fcae32e8317b0d923 | False | 0 | NOT_MEASURED |
| jax-computing-basics | 8817b890f02a90e273fb3620ea2232b84658c0fbb328b6241d3dc88c85509969 | 0 | ed0121f0ed7ec8994bd59dccd9df215da83637afc7280d7fcae32e8317b0d923 | False | 0 | NOT_MEASURED |
| jax-computing-basics | 661816e75d837a08e77900e019ff8b763a398edfcf92f82b42b1f4e7bd85e764 | 0 | ed0121f0ed7ec8994bd59dccd9df215da83637afc7280d7fcae32e8317b0d923 | False | 0 | NOT_MEASURED |
| jax-computing-basics | af4a2b8697bedf28a6175819bc6e48ebd4bdf784c73960444d25227aea80908c | 0 | ed0121f0ed7ec8994bd59dccd9df215da83637afc7280d7fcae32e8317b0d923 | False | 0 | NOT_MEASURED |
| jpg-ocr-stat | e8f00ea5009546e8c91f8b793e4e816b0428c4817f0f8950be4049ed9bc3c3dd | 0 | ed63aab5b90fae4bb70edad498d167ee4376a6a5adb9b8d08e9221e7b26521a2 | False | 0.666667 | NOT_MEASURED |
| jpg-ocr-stat | dae5d4147359ef0fec7ee7c8035b6efc9f3debbaba12a38c4fb53025a5580ff4 | 0 | ed63aab5b90fae4bb70edad498d167ee4376a6a5adb9b8d08e9221e7b26521a2 | False | 0.666667 | NOT_MEASURED |
| jpg-ocr-stat | 6f6f58428de9b8a1fe5108d4f74dff4c315f3aed4f8f65df944e1406500a47a4 | 0 | ed63aab5b90fae4bb70edad498d167ee4376a6a5adb9b8d08e9221e7b26521a2 | False | 0.666667 | NOT_MEASURED |
| jpg-ocr-stat | 9a0f20859951a38f4e575841b6ea4502e70c9061e407d085989a0d0227bc1ccb | 0 | ed63aab5b90fae4bb70edad498d167ee4376a6a5adb9b8d08e9221e7b26521a2 | False | 0.666667 | NOT_MEASURED |
| jpg-ocr-stat | 19e43f128917c200bd1f0994a2061b047d403d3a273fc31fd636b328ddd2d478 | 0 | ed63aab5b90fae4bb70edad498d167ee4376a6a5adb9b8d08e9221e7b26521a2 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 19e43f128917c200bd1f0994a2061b047d403d3a273fc31fd636b328ddd2d478 | 1 | 59e3cb7e796a09e3b20bb02c5410b1dcdc8467da0c12be992c64a01c594ec625 | False | 0.5 | NOT_MEASURED |
| jpg-ocr-stat | 417a1aef8d0989ee2b05fbb7e9eebd14f1dba0f4e33996cf1f4664bc9d989188 | 1 | 59e3cb7e796a09e3b20bb02c5410b1dcdc8467da0c12be992c64a01c594ec625 | True | 1 | NOT_MEASURED |
| jpg-ocr-stat | 417a1aef8d0989ee2b05fbb7e9eebd14f1dba0f4e33996cf1f4664bc9d989188 | 2 | 189e56505df38c000e969a800d0dcb7b5a01901e0b8b1e3ec74fc7c3c164bc74 | False | 0.8 | NOT_MEASURED |
| jpg-ocr-stat | 031f92bd400bd287b7931e238913ac3d8e68d4f9ad29c1b49c90db4150673afd | 2 | 189e56505df38c000e969a800d0dcb7b5a01901e0b8b1e3ec74fc7c3c164bc74 | False | 0.6 | NOT_MEASURED |
| jpg-ocr-stat | 2aa5ab15befc5b458a687fb1c610d27e59e67971bc90948f7eec2f765b734698 | 2 | 189e56505df38c000e969a800d0dcb7b5a01901e0b8b1e3ec74fc7c3c164bc74 | False | 0.6 | test_repair_failed |
| lab-unit-harmonization | 7cc1de6dacd479cc6aabcc55b4524fa8628fb26a4ba7a27a2d80879972dcf0ca | 0 | 709b0fa1af73f278363353494b68ea2a278248afb3ab6b0948815a8c9828ca07 | False | 0.5 | NOT_MEASURED |
| lab-unit-harmonization | c3e771c0d801771780e0638b947e2fc68e7d12ff864cdac84c5bf9cacc436dec | 0 | 709b0fa1af73f278363353494b68ea2a278248afb3ab6b0948815a8c9828ca07 | False | 0.5 | verifier_reported_test_program_error |
| latex-formula-extraction | 6af057de1f2d23dc5db7f455ebcbfa0dfc0f4fd111567067f11b3a111becd103 | 0 | 39a334e4f64a88a090734cdb16540cd985c5d907010ea424a9d422b9ce419bba | True | 1 | NOT_MEASURED |
| latex-formula-extraction | 6af057de1f2d23dc5db7f455ebcbfa0dfc0f4fd111567067f11b3a111becd103 | 1 | b48e27215bc89248a3caa8a06f115774b656dd67c300c4a876b282c6dfc02b14 | True | 1 | NOT_MEASURED |
| latex-formula-extraction | 6af057de1f2d23dc5db7f455ebcbfa0dfc0f4fd111567067f11b3a111becd103 | 2 | 43b31164cd9397fbaa7087e8d4d44e51c397c73559d1e88951457cb225aee49e | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | bf8507ac5e08bd2570accce8c15be104f3d11b6e44f8d7e14adad0b6070a89e4 | 0 | ecaa8bef194f1f1857b78fec75e7e1f1d84683b112e2569617aa010798110b4f | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | bf8507ac5e08bd2570accce8c15be104f3d11b6e44f8d7e14adad0b6070a89e4 | 1 | 03106bf9b672f35a7faf7a97acbff42dc506115eaaf816f2247ef1450eb52d67 | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | bf8507ac5e08bd2570accce8c15be104f3d11b6e44f8d7e14adad0b6070a89e4 | 2 | b51fff2db1fdeb79b1f2f5791005793a27a8d18a79ced5a18571d8eff4a4467d | True | 1 | NOT_MEASURED |
| manufacturing-equipment-maintenance | 764f343771dc6bf60579278fed9d359ea921be48fb70951199702182d9d9c775 | 0 | 05a5331a59b4712fba0866319d8ef1b53d204a75b5564ea0f03be4e5fd9c018b | False | 0.666667 | test_program_error |
| mario-coin-counting | 1c53a92c93580e99d765001d78972e8b7ba29754996e1deb46273021beacf5e7 | 0 | feaf7b39a8e23641f5d65ca835d85aae0914a54521d57b660cfeda8b08047f0a | False | 0 | empty_or_invalid_tests |
| mars-clouds-clustering | 93f4ddbafd7036ca603a0c10a3ea60b2c672412ad4382726acd522306cc0bc30 | 0 | ea0e4b3f70f8463b7bd451a4eb038bd528d03394526fc5924dc62b65dbe63044 | True | 1 | NOT_MEASURED |
| multilingual-video-dubbing | 4fefcf4873fe9706ab1fc2a8dd247d0e6b0a0836666ab566f92b03ad0cd7bcf6 | 0 | af4f4aa95aeee17f14dfe30af6f76834ca883ac4a726bc39fa13816879eb216e | False | 0 | NOT_MEASURED |
| offer-letter-generator | b88ef1cf3fec5ad48b78b803cdef728220deb8d57c125ead7fde78aa9c966c58 | 0 | 44e70148d47f0083053fb14fe47afacf6b7af8e685c9ec662fbb6e151aa697e5 | True | 1 | NOT_MEASURED |
| organize-messy-files | cacae0885f711115c4478e4bcdec6285e5acafb70799fcdefcfbc5dbb42b5d66 | 0 | 1b9aefb09f2b64e98326bea059202bfa9fd5834a4c9af3003f0aa2ec5875c8f9 | False | 0 | incomplete_test_report |
| paper-anonymizer | be97e59a2d67322b7b090a09fa04ab9aa06745bfe2739004e24518d8952f25de | 0 | 10f535eec4ff515686631f63aee50b93a06bbdba4502d5df7580662d9b271d29 | False | 0 | NOT_MEASURED |
| paper-anonymizer | 0376a250429c2ef725b1fdf3b6865bfb7e3317206a1afa93b477d745109967e1 | 0 | 10f535eec4ff515686631f63aee50b93a06bbdba4502d5df7580662d9b271d29 | False | 0 | NOT_MEASURED |
| paper-anonymizer | 43df03ecd0b38c2d96e0a9bf44c748cb6912cf5d6d15e8d5ffc4f8880a80e852 | 0 | 10f535eec4ff515686631f63aee50b93a06bbdba4502d5df7580662d9b271d29 | False | 0 | NOT_MEASURED |
| paper-anonymizer | de41954a0f3ad0c59ba645a0506b70646034a01f9a449fb0286a5312efc273f3 | 0 | 10f535eec4ff515686631f63aee50b93a06bbdba4502d5df7580662d9b271d29 | False | 0 | NOT_MEASURED |
| paper-anonymizer | 78d7939e1b218215240c761bf4711af1b06d4be45b4694819af86917fedbcb96 | 0 | 10f535eec4ff515686631f63aee50b93a06bbdba4502d5df7580662d9b271d29 | False | 0 | NOT_MEASURED |
| parallel-tfidf-search | 735fb562c019642a8242514e1258718d399b14f0bd424022a84f446ba548c0d9 | 0 | 230081297e773ae9327c4c238158281e92fc511ace939722bfc81fd69cd95db0 | False | 0 | test_program_error |
| pddl-tpp-planning | 2908fdda3185718f62c3bec07423add6eb170b409e54a6789d0eae53db41c47b | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 6e9b2389b98bbd37b63f8a5af29f814291b632594eca1dfd4a5695e963d067eb | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 52c8a97b73806778822eed741c332498d14b530447b09f534bb945dcb23207b5 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 54c190840bb7fdfae0ca68e03c601f34c3328dd8a1524fd22a84b3319a4edea6 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 7281092b77e3624a7bf87dbc0e30d5d13375bb0c2615bb462387b0a47d9bcc5c | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 82bd37622057cfa08ef0d5ebe63a4ebbcc3538033bb54a5e7bef0173ad419a6d | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | d8249271bab35c2ae77959fa23aa3980232cedf1ad45693f5b0ad7167a724c89 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 605c5bb944d9b6f96269b1a5d757de0dd8a4a030320ed1a4078b15acd4e7187b | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | e0a0eeb5a3b84741daa9a2758772c01c5a5220977498240a5f337d55247cc3f3 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | c22cd738bea70a9b6e92af2385e4b6aae9ca030ad60e812eac66bf8d741c9752 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | f4a3ad3809069ae0b1577da61d5b999974728e6becc899b99bec6014695fda2f | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | a77456ccfd927821a211adb674f5ef1108d1e1b70751f47f9c64e7ffc7eef9c3 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | c5fc7edd978153274dad82dfe95d2450cdccb07ed84820045dd77600578e71f9 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 53d1386ab16886743d05f362cac45c557d7be2bce6dbad98fe06a5a7752f30f3 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 17772fc7341d856c20ca6e0d09117a56bccb781f41e6cea4900f0e042da0bdd1 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pddl-tpp-planning | 7152074006f163983f8969d0bf7828036e1312afc6f9ffd6698b68b66d968896 | 0 | 34535b81c361abbde310fad3a123d58df10be4fc19c4f7f6a5507916640ffa3c | False | 0 | NOT_MEASURED |
| pdf-excel-diff | 61f54aabeba443a389b2f881713a6ed0649add89034da5e247f9e13929d7cff8 | 0 | 4b86c77855b3acd9a532ccea2e5539d210bc0d93e77f43bae58a2118d96b7ab8 | True | 1 | NOT_MEASURED |
| pg-essay-to-audiobook | e42184e8ba74a7f6428624e3d77ffda35458009b071b220f9ad8b2e3c179d13c | 0 | 938c3dc44cc2ad4b66d7c9cf644bd05292bad5db5baca1c6bb47bee5eef5a73e | False | 0 | test_program_error |
| powerlifting-coef-calc | e4fd00e7635033ac7196bcd594c105cdab37793ab6ea3ef784b5d2cb3c222705 | 0 | 800a0b65a6be7dc0037559616a84a4dcf9feeba7d59965e055c64e277aaa0afe | True | 1 | NOT_MEASURED |
| protein-expression-analysis | f85f675b623d849d009a360aca48214a1ee273b90a02f7877ed2bfe81f882cb0 | 0 | 445365f1dd0b702a8f0baf206f2591d8646563223e7b9bdfd05ad01ffc077625 | False | 0.25 | NOT_MEASURED |
| protein-expression-analysis | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | 0 | 445365f1dd0b702a8f0baf206f2591d8646563223e7b9bdfd05ad01ffc077625 | True | 1 | NOT_MEASURED |
| protein-expression-analysis | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | 1 | 90d506789a528a2907362907a5a8d4e6778ec07f2e4c49447f0b3a7882ba4e8c | True | 1 | NOT_MEASURED |
| protein-expression-analysis | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | 2 | 2430678ba9449bdb7dc173b37ba1eaba75caab56b4f3383fa0037c4612d1dc14 | False | 0.857143 | NOT_MEASURED |
| protein-expression-analysis | bee995358c90d6c33940013b7bf6d862fdb877604ec3f9a58856af8bdaa4dae6 | 2 | 2430678ba9449bdb7dc173b37ba1eaba75caab56b4f3383fa0037c4612d1dc14 | False | 0.857143 | verifier_reported_test_program_error |
| quantum-numerical-simulation | 42ae9edfe8e9722839712c2f5a107271dd647310ce1ecdaaf4ba07277687dc7a | 0 | 869d5d41e604d3d1adff1c6fcc52526636b5314e721c2e3d53f98ca77e1376cf | True | 1 | NOT_MEASURED |
| r2r-mpc-control | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 | 0 | 971e23d0167d817eeca6fea08f770f1dc3bdce1edf43179feef41ab385aa0405 | True | 1 | NOT_MEASURED |
| r2r-mpc-control | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 | 1 | d4db7f45726984450dc552be98e6f0b031830ec47a713d9414706970bf7308c1 | True | 1 | NOT_MEASURED |
| sales-pivot-analysis | 3a41dbfaf5743fa05dc9d988b77b90fc8b1f13c6aa35e7dcf4fb15bfe61a83b7 | 0 | 59695039e358273f32e34e8d8e617c136c062d464c4cb4d3cda3e75f1e44b53b | False | 0.333333 | NOT_MEASURED |
| sales-pivot-analysis | ab69736cd9864fbb9b80ec18e9dcb711aed1a0f0a4722814c6ec19813efed7e0 | 0 | 59695039e358273f32e34e8d8e617c136c062d464c4cb4d3cda3e75f1e44b53b | False | 0.666667 | verifier_reported_test_program_error |
| sec-financial-report | 5e13dee0d4ea02852837afe17fa596f148bc35a16d47882a0ab56c0520e27660 | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0.5 | NOT_MEASURED |
| sec-financial-report | 549caf0e1b330eb55f052ccaf300fc7db0338b24657917ba96a6ef48c805da99 | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0.5 | NOT_MEASURED |
| sec-financial-report | 8b22df93b475a331fe2e3d0d86861548f3cc216432ad0fa0d380fd3ed7f2a91b | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0 | NOT_MEASURED |
| sec-financial-report | 8ab2820acce4c0137315e6f6f09d9109e317b709ef77652ab874121b2997f2ec | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0.5 | verifier_reported_test_program_error |
| spring-boot-jakarta-migration | 29725d02098f1982993f513c5cfadf9392dda5a1584a573a6e2331c2ec5c8f48 | 0 | 1da83bc62538cd2885a47dcdde11c585f69d72d59e8193cda0b1bd18df65a6db | False | 0.666667 | test_program_error |
| suricata-custom-exfil | bd8bf172bbdbc93b9a87f843c1c6f1a7348e3545c77ef26ae592ee733b1515b3 | 0 | 88fe29ba4c5f95defdd3789612a1c4ff1dbe47fca135cf13140a04a94cce898b | False | 0 | NOT_MEASURED |
| suricata-custom-exfil | dc680618440eb1f0831e3a84ed6b10eb1ca94a1c4242cf2a770c1ea62facd149 | 0 | 88fe29ba4c5f95defdd3789612a1c4ff1dbe47fca135cf13140a04a94cce898b | False | 0 | verifier_reported_test_program_error |
| travel-planning | 8a390ff10eff8e0cd7edcd2da4e91a6cbf9e68aaccd6d34eee3d91f3433b28f2 | 0 | 016a5fc08527591a4a7ac6713f544fa6b892c135baa1464fb19216d8e148d34c | False | 0.833333 | NOT_MEASURED |
| travel-planning | a382d2d3d15a8c25651a452c3aca71f19f24284cff3c89ab6b6f7699be28b34f | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | 1c152c7e7565903110893cabf3c8c4a10b30b8537dc8af240ad51b572b062da7 | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | cbf54ee2560103bc9fc6b7a889652f424ee286efa734b63037834cf15412d5b8 | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | 4f1e862c0d5aa7bccf81448686d695ced4e7ba550c871a13d5477d989b3a4a8f | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | 4f1f4b34a6561dda7e78a4589c57522f68e46b95934e9e0dfda83480f5de20ca | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | 59c67e0975a77e7c5dae18ad8a3758d0e5c99def68ea4448c2eb395d7922c0f0 | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | 16047dbcb9be6bde1f8c5fa752cfc643741e92647ff72331b9572ada78ede8da | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0.833333 | NOT_MEASURED |
| travel-planning | b27fea7714810b9e9472d3639c15d8287b558ff5e2aa7c3d801a56e90d235496 | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | e5d4586110151d54f0d6753bd607b15da2647ecc38cb65b07cb7e9a76c47aeba | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| travel-planning | e063257cc8549ab804903beb1a4ba0b6a0f869728b22a20c730606c17576e20a | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0.833333 | NOT_MEASURED |
| travel-planning | 289836a7a515b41cdff35745b39d31efc0fb287256942d9044ea8cdee9ed7da4 | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0.666667 | NOT_MEASURED |
| travel-planning | 6566b8952b7a22658ea42ed6fa921ed04bb40d490804587b476c1dd9f3dd1c8e | 0 | 712ba6d02a609d1276a0c34cf217c1d0a092e13753cb4e346228f349b89e02e5 | False | 0 | NOT_MEASURED |
| video-filler-word-remover | 3f60d2db313bc6cd29d2018c481131978033bda52d020081a8a7d97c931db5bc | 0 | f5571313f9c073790494bbfc7ecdef97fcd2b77ee25a552ffdf710730f3a374f | True | 1 | NOT_MEASURED |
| video-silence-remover | e6e808a56358cfb7df11ee836bfd0255abebe90d67735d63130786264389baf8 | 0 | f1256e46bd47ae2db401b05a54c395822dfe552952ff26eb0e9153591b11c2b7 | False | 0.75 | NOT_MEASURED |
| video-silence-remover | 37daf18a9bd4e7d6050fd48409f674927c7bb5f8819027af147963217771c2c1 | 0 | f1256e46bd47ae2db401b05a54c395822dfe552952ff26eb0e9153591b11c2b7 | True | 1 | NOT_MEASURED |
| video-tutorial-indexer | 402e669dc43ddd24fde377f59c6313ba8ac1ab9e6554044f2b58cbed08372f1f | 0 | cfb2841b8f39ae5ee60413294d3a9a7f2faef37f7972edc2f05e514819cf6be1 | True | 1 | NOT_MEASURED |
| virtualhome-agent-planning | 4bca12ca7e84c21def18719b408a456e29f226a5a845d1dad291d0cd5043a582 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 62a271675e7991373d7e4c935bff4e8915e36db14d78860b9ecf4b4207900798 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 4b8b9b4cca79375a5a7e4317c1061069eb79eadf8a0a5ba4b7eeb1944ed8588b | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 25fc6ebfbd56aaa7852edf1c9c08b53b44905931527c97b214633d7107f571fa | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | b941832c612f614d67e23fbdc655a2b57e90588d8ce0ca1ee41771b05a110fd4 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 9105135bf4d942948245d04da7f51248cc55bc64c0687a53090bb6e65f924488 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 66c0c80cb4681be504b8dae955d49360b10c6ebb48b62a565fa8dc4ceab49281 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 0c5df2de9449b5648a99e7f3842e837adeff86187edb86204d44150ae1679e55 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | a4e47cd83eda897f48842b892539ef0de052cbd3080b6ff45256b5ed435a4e83 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 148cc366d5d249fba764399248ad500472a41a111a931f87a13e9a53e06db2fc | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 069140f2ba6f17a01a75bbac09eb75fc7014cf846ec4d7d42720a083f8c794db | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | dcd7d2a0e76d852cf7271035bcc76e8650688f6625df0bff2c82315d575fa26f | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 5e131f661d3644b76ea54d21e8b754ba8832ec83902a4005e67c399f4cdeb975 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | b8aa0438250a35362142537ea6545d7770f2648e6e489a459d14874e094423b2 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 1ad1cf4acee59dd4dde34a757b127348284a41a1e3bbedbff62afa5062af7119 | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 15577dea207abe88417cc3704ed30f4e6b1d07574527e922e70d1279109dd26e | 0 | e9e30b06c6bc73559fefbac9e5c5ed8b098e54024f4166594cd3934c8dafc957 | False | 0 | NOT_MEASURED |
| weighted-gdp-calc | 88f54ce629f0560c3f8c6c13451f5a7dbe0d1cf9d532e821d37b0b4b82e98b29 | 0 | a89523a005fb1aaa6f298eb9f8ab8046407e0063f05930d0a336a2bb37094572 | False | 0.5 | NOT_MEASURED |
| weighted-gdp-calc | 4e0899dcbec0e49368aa83053bf9c2a65bf4c36bb989ade5294a9a20ebad4bb6 | 0 | a89523a005fb1aaa6f298eb9f8ab8046407e0063f05930d0a336a2bb37094572 | False | 0.75 | verifier_reported_test_program_error |
| xlsx-recover-data | 20607bc31ebb37472acaba2ae4f9586133b8a1770c416c32e5b7b11fd37487cd | 0 | 54e32b90a65d514610735d17f6b3694fa1437da2f5f7369be9e0fb0238b88913 | False | 0.5 | NOT_MEASURED |
| xlsx-recover-data | 581c002f98e88bb436e651ed8eaa6f97107457f6ed484655f9b60a952db1a963 | 0 | 54e32b90a65d514610735d17f6b3694fa1437da2f5f7369be9e0fb0238b88913 | False | 0.5 | verifier_reported_test_program_error |

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | Rescued |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| adaptive-cruise-control | benign | True | 0 | 0 | False |
| azure-bgp-oscillation-route-leak | benign | True | 0 | 0 | False |
| citation-check | benign | True | 0 | 0 | False |
| civ6-adjacency-optimizer | benign | True | 0 | 0 | False |
| court-form-filling | benign | True | 0 | 0 | False |
| crystallographic-wyckoff-position-analysis | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | benign | True | 0 | 0 | False |
| data-to-d3 | benign | True | 0 | 0 | False |
| dynamic-object-aware-egomotion | benign | True | 0 | 0 | False |
| earthquake-plate-calculation | benign | True | 0 | 0 | False |
| econ-detrending-correlation | benign | True | 0 | 0 | False |
| enterprise-information-search | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| exceltable-in-ppt | benign | True | 0 | 0 | False |
| exoplanet-detection-period | benign | True | 0 | 0 | False |
| financial-modeling-qa | benign | True | 0 | 0 | False |
| find-topk-similiar-chemicals | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-build-agentops | benign | True | 0 | 0 | False |
| fix-build-google-auto | benign | True | 0 | 0 | False |
| flink-query | benign | True | 0 | 0 | False |
| flood-risk-analysis | benign | True | 0 | 0 | False |
| gh-repo-analytics | benign | True | 0 | 0 | False |
| glm-lake-mendota | benign | True | 0 | 0 | False |
| grid-dispatch-operator | benign | True | 0 | 0 | False |
| invoice-fraud-detection | benign | True | 0 | 0 | False |
| jax-computing-basics | benign | True | 0 | 0 | False |
| jpg-ocr-stat | benign | True | 0 | 0 | False |
| lab-unit-harmonization | benign | True | 0 | -0.208 | False |
| latex-formula-extraction | benign | True | 0 | 0 | False |
| manufacturing-codebook-normalization | benign | True | 0 | 0 | False |
| manufacturing-equipment-maintenance | benign | True | 0 | 0 | False |
| mario-coin-counting | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| mars-clouds-clustering | benign | True | 0 | 0 | False |
| multilingual-video-dubbing | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| offer-letter-generator | benign | True | 0 | 0 | False |
| organize-messy-files | benign | True | 0 | 0 | False |
| paper-anonymizer | benign | True | 0 | 0 | False |
| parallel-tfidf-search | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| pddl-tpp-planning | benign | True | 0 | 0 | False |
| pdf-excel-diff | benign | True | 0 | 0 | False |
| pedestrian-traffic-counting | benign | True | 0 | 0 | False |
| pg-essay-to-audiobook | benign | True | 0 | 0 | False |
| powerlifting-coef-calc | benign | True | 0 | 0 | False |
| protein-expression-analysis | benign | True | 0 | 0 | False |
| python-scala-translation | benign | True | 0 | 0 | False |
| quantum-numerical-simulation | benign | True | 0 | 0 | False |
| r2r-mpc-control | benign | True | 0 | 0 | False |
| sales-pivot-analysis | benign | True | 0 | 0 | False |
| sec-financial-report | benign | True | 0 | 0 | False |
| setup-fuzzing-py | benign | True | 0 | 0 | False |
| speaker-diarization-subtitles | benign | True | 0 | 0 | False |
| spring-boot-jakarta-migration | benign | True | 0 | 0 | False |
| suricata-custom-exfil | benign | True | 0 | 0 | False |
| taxonomy-tree-merge | benign | True | 0 | 0 | False |
| travel-planning | benign | True | 0 | 0 | False |
| video-filler-word-remover | benign | True | 0 | 0 | False |
| video-silence-remover | benign | True | 0 | 0 | False |
| video-tutorial-indexer | benign | True | 0 | 0 | False |
| virtualhome-agent-planning | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| weighted-gdp-calc | benign | True | 0 | 0 | False |
| xlsx-recover-data | benign | True | 0 | 0 | False |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | 1 | 293 | sufficient | 37d27d6e811214a69dfa91e4bf375e2952a614e82ed95ebd92755679cd6274f2 |
| adaptive-cruise-control | benign | 4 | 4349 | sufficient | bd60e7e34ab00e38a90fb6adb71314585db146e49688db3aa96103f09adbccc9 |
| azure-bgp-oscillation-route-leak | benign | 3 | 3814 | sufficient | 4cfb874e8cca881fcff90f2119b0d5340a3e71655f60625f66e0eb855b3f8130 |
| citation-check | benign | 2 | 2960 | sufficient | 00599d7bfb3680eb6920ee5c4c8b49ade5bd7d5fec9693c2843e3de4df56f4b4 |
| civ6-adjacency-optimizer | benign | 3 | 5691 | budget_exhausted_incomplete | 3ccb220e91257b6e408c03c3d4723b7f3ff4d55bb8e4f2595b789e5c658e30a5 |
| court-form-filling | benign | 1 | 236 | sufficient | fdafe1f5b364a53b77d2191aa204fe370d09f8db7025640a291ae6c56ed0c6d8 |
| crystallographic-wyckoff-position-analysis | benign | 1 | 427 | budget_exhausted_incomplete | 88c17bf9956cbe9cfbab3aa3925dc9cff72c12773a16c323fa729ba2af218baa |
| dapt-intrusion-detection | benign | 2 | 3632 | sufficient | f1fc79830f81d0fadf562b8c68e13d8731ebefab1386156b9dcaead84d9cc4c2 |
| data-to-d3 | benign | 2 | 4461 | sufficient | fb4178d639f06816aedee19e26b1f1907c47dc3ef803a973eb96fb767ad32191 |
| dynamic-object-aware-egomotion | benign | 2 | 4511 | sufficient | c3bd1be3a45a5c31f4e632789068b581112f90494d12376a7a9efb5fbacfb831 |
| earthquake-plate-calculation | benign | 2 | 3074 | sufficient | 0f815b073ad7015fc6fa142c44467e9c0d8e2f47aa8cae85a29691af237dee64 |
| econ-detrending-correlation | benign | 8 | 11881 | sufficient | 77bfb89d321ec15c185f1b4656f9e7ea8914be833990ad4ac5e3d538281da623 |
| enterprise-information-search | benign | 1 | 1223 | sufficient | 1ce62b085f6df059b32eb9d409db028af653257377d9691d66df4d4041cbbf74 |
| exceltable-in-ppt | benign | 10 | 9487 | sufficient | 787a2fb51be21a5317cc2f561197542bdb725ce5e1b6101db98d7c37a0b35f99 |
| exoplanet-detection-period | benign | 1 | 384 | sufficient | 23a5ea0206d8ba41fe68af711e3a8d38f277dd506b0e3cb163943b766441f9af |
| financial-modeling-qa | benign | 2 | 1815 | sufficient | b22a30eecab89e86a8bad69667b194c672aac2c12ac5d80d1240ff8dde428372 |
| find-topk-similiar-chemicals | benign | 4 | 3622 | budget_exhausted_incomplete | 3f851b456a875b7b5033a935edb6b8afd3243dfe9b5e1383d1d0d0e4c1da6ccc |
| fix-build-agentops | benign | 2 | 3211 | sufficient | b25414f4b2e9b0f6acf4e67182f42788108fe6b067b7ffa8ae50deeb2d98812a |
| fix-build-google-auto | benign | 2 | 2989 | sufficient | dba1b2a067441ee30f83e6be9883db9c79d43a744058b59fa3d8f0afd2b34b0c |
| flink-query | benign | 1 | 561 | sufficient | e6112fa643125ebc085fb466d08e2edd6c76fa543ad145686b91a1e86da960af |
| flood-risk-analysis | benign | 2 | 3087 | sufficient | d36c49759109d84b31bf5618950a36804b1a04995cd22d31374c5b22ecebe53b |
| gh-repo-analytics | benign | 2 | 1956 | budget_exhausted_incomplete | 3b9c9492d5a9ef5ca0d54ef79932c75dc9a2eb448e70024b4154af6212331c32 |
| glm-lake-mendota | benign | 2 | 785 | budget_exhausted_incomplete | 2f6641203f09dc93c8d83e6ef59c04ea2f67b998c326694cb7937afbbe918777 |
| grid-dispatch-operator | benign | 5 | 6507 | sufficient | 4c06b04bb03098427dbbe0213a1939846e238f6f1baa26c189fef1471190539e |
| invoice-fraud-detection | benign | 4 | 6068 | sufficient | cf3aa258f8c620318b56619903449410df87d70e31d813cc0a7c11fbbf6958ff |
| jax-computing-basics | benign | 1 | 577 | sufficient | e73d07c86f83a368e7f550fcd937ab8bda8332cbbb3cf9b3881b424e78bdabec |
| jpg-ocr-stat | benign | 5 | 8550 | sufficient | 125c4e21c2e4f2237ff1ecf8d38a459f5fd90c548bade8da025b80570372ff6c |
| lab-unit-harmonization | benign | 1 | 1360 | budget_exhausted_incomplete | f6d9373fa78f1cfa3948d1bb11562af4cb6c743ca1f1a32a7524c7c1494c17f5 |
| latex-formula-extraction | benign | 2 | 3478 | sufficient | d9319f0927b9f11e76eff92cac3690cf62df402278a85b30c5250b883f2de19e |
| manufacturing-codebook-normalization | benign | 1 | 1384 | sufficient | 9aab9ed29dd78b08d1cb530ceb4ae0a0ce39138f501ca1f3f7624eec749a9e11 |
| manufacturing-equipment-maintenance | benign | 5 | 5663 | sufficient | 7ba48192a5c8a6475d4f668b22cfa9f3744b6e95065eed5c9881df50032a015c |
| mario-coin-counting | benign | 2 | 2585 | sufficient | b52babaccbee57c23bd0a99153879bc7419abffe1671b5ef754ea8759818dbf6 |
| mars-clouds-clustering | benign | 2 | 3055 | sufficient | 7190d9a719fba0babb7e18e0e0b5889a77001f7939548dd56ee0a8419585a05b |
| multilingual-video-dubbing | benign | 4 | 5129 | sufficient | 22591898417ddce087f9a3f4421328f1e0f430956d3737491074d1e535c2c00f |
| offer-letter-generator | benign | 1 | 284 | sufficient | b65afeb84f8e10f7e8e70ff0b475e19fc6b114fe03c92b6f1eb99acbea26f91a |
| organize-messy-files | benign | 6 | 5106 | sufficient | 3666ae6597eaef7e1dfd79afdfc76b52064449c6db8112805104a28183dbf469 |
| paper-anonymizer | benign | 2 | 3866 | sufficient | 87acac4e7bf973c0433199c5770d6d2f4aaf27add9617a1a06cbf0d8ec84b058 |
| parallel-tfidf-search | benign | 1 | 339 | sufficient | ba8bd9e4a5b62a981ca0fe1553e782df0b5716f799d428aa2a6d3b3c4e508fd7 |
| pddl-tpp-planning | benign | 2 | 968 | sufficient | 7d8b6cfa07cf58b895802546a373e4164a2d41edb04df313c928da8cd9133039 |
| pdf-excel-diff | benign | 2 | 2960 | sufficient | 673fd620a1e172b32e6eb2bdcece026ae1b54161bcd688e7e50467e01d9373ca |
| pedestrian-traffic-counting | benign | 2 | 2931 | sufficient | 35f67c4a0b0bb936327b6b3eb755ed65bf3f22dd2fda848de3d2d0f6db6f74d4 |
| pg-essay-to-audiobook | benign | 4 | 5129 | sufficient | b672909775d289abbcacb311bad7132dcc92347de75acdf6df008d1fe2a059da |
| powerlifting-coef-calc | benign | 6 | 4318 | budget_exhausted_incomplete | 1a6efba0950d47ba8c409920409e4cb40de5a1481efbd9a3e62ac715f7ad5629 |
| protein-expression-analysis | benign | 8 | 9648 | sufficient | 02b5668eb1bb4a7c6fb2ca355d3ad4592172453f3b6e6293f1bcbbb7ebb28668 |
| python-scala-translation | benign | 2 | 3660 | sufficient | 0070a4ca8a9b03c2a1c8cf4a910e652870db8865c858424bafa3401710234d9e |
| quantum-numerical-simulation | benign | 1 | 527 | budget_exhausted_incomplete | ef3c1ab07d95286091c1ef219f7047878b7fdaa47a32642ca3bce8a99f2e47cd |
| r2r-mpc-control | benign | 2 | 632 | sufficient | e2a0731ca0c130eb2d5c14f7c5fa0191f0778eb0c7c6caad932014622d616099 |
| sales-pivot-analysis | benign | 5 | 7551 | sufficient | 482861288d274db5fb0eb64bb03010fbb72b621278d53a48350ff73ce032bca7 |
| sec-financial-report | benign | 3 | 4584 | sufficient | fb583bc10c23093b17758ccb9dc7d599f51ca07ef928e86b134d823eb8c1a7dd |
| setup-fuzzing-py | benign | 1 | 1964 | sufficient | da1cf90f2094997f2524423d865fd427a39d6d0c0e786fdae813d56777f00680 |
| speaker-diarization-subtitles | benign | 4 | 7327 | sufficient | cf20c1443400ad0efe1841cc0eddad3b4534c359c420ccfc8584c36975cd403a |
| spring-boot-jakarta-migration | benign | 3 | 3331 | sufficient | 4632b1fd09c678e67cfab9f8df5aa9d508dd06f851bb452107fdcc60de427385 |
| suricata-custom-exfil | benign | 1 | 444 | budget_exhausted_incomplete | e255399c6457a050bcb5e9b8ba0a79e6a0204cdad767bd199f67627b1c6dcd25 |
| taxonomy-tree-merge | benign | 2 | 3961 | sufficient | 4ae3ce6ab077cfecd4ce989ae557d5a528f3fc58413fd04a5a474a96c045d318 |
| travel-planning | benign | 2 | 2419 | sufficient | 2438d75e2ec535586b5caf367e3baeb542dbe5918048df17e14c448e9e0ba5f3 |
| video-filler-word-remover | benign | 6 | 9677 | sufficient | 8c178c8e1822a823a4332760dcad49ba3cadb439e8db8cd264c720a135fd463f |
| video-silence-remover | benign | 2 | 2353 | sufficient | bb11771cf20a517c8794f21709df18a5d79a8c7fe58899f9a755f973b9793b4d |
| video-tutorial-indexer | benign | 2 | 3096 | sufficient | 45379ab09c5364a0962946579e960a3b637eaccab10ba1b146d489a43b3110e2 |
| virtualhome-agent-planning | benign | 2 | 968 | sufficient | 326e761a47c44d745d20c316967a403eef0e7f18f41cd2f7d95dd1034259bf5b |
| weighted-gdp-calc | benign | 4 | 3670 | sufficient | 91ade6fe0ec6f3670afd6590e80631bc6caf7342eee655ed6a150576017efc23 |
| xlsx-recover-data | benign | 1 | 1151 | sufficient | ff80610566f270f010d5b06e26604712f112f9b7ce5eb817e12927156edae4bc |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 796 | 46663049 | 1827046 | 478663 |
| generator | 156 | 2742429 | 1136371 | 0 |
| execution | 3475 | 45141996 | 802374 | 39969082 |
| verifier | 231 | 3212856 | 460341 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
