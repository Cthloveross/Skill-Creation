# skillsbench run report

Protocol: `skillsbench.skill-evolution.v1`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility |
| --- | --- | --- | --- | --- | --- | --- |
| benign | evolved | 85 | 76 | 71 | 0.323944 | 0.270588 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 76 | 71 | 0.323944 | {'oracle_budget_exhausted': 3, 'verification_program_error_exhausted': 10, 'oracle_success': 14, 'rollout_result_unknown': 5, 'oracle_result_unknown': 2, 'test_escalation_failed': 3, 'verifier_initialization_result_unknown': 4} |
| benign | 1 | 35 | 35 | 0.171429 | {'verification_program_error_exhausted': 11, 'rollout_result_unknown': 1, 'oracle_success': 1, 'oracle_budget_exhausted': 2, 'test_escalation_failed': 2} |
| benign | 2 | 18 | 18 | 0.222222 | {'oracle_budget_exhausted': 3, 'verification_program_error_exhausted': 1, 'test_escalation_failed': 1} |
| benign | 3 | 13 | 13 | 0.230769 | {'test_escalation_failed': 1, 'verification_program_error_exhausted': 2} |
| benign | 4 | 10 | 10 | 0.2 | {} |
| benign | 5 | 10 | 10 | 0.2 | {} |
| benign | 6 | 10 | 10 | 0.2 | {} |
| benign | 7 | 10 | 10 | 0.3 | {'verification_program_error_exhausted': 1} |
| benign | 8 | 9 | 9 | 0.222222 | {} |
| benign | 9 | 9 | 9 | 0.222222 | {} |
| benign | 10 | 9 | 9 | 0.222222 | {'verification_program_error_exhausted': 1, 'test_escalation_failed': 1} |
| benign | 11 | 7 | 7 | 0.142857 | {} |
| benign | 12 | 7 | 7 | 0.285714 | {} |
| benign | 13 | 7 | 7 | 0.142857 | {} |
| benign | 14 | 7 | 7 | 0.142857 | {'oracle_budget_exhausted': 1} |
| benign | 15 | 6 | 6 | 0.166667 | {'revision_budget_exhausted': 6} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Final hash |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | verification_program_error_exhausted | 2 | 1 | 0 | 881af1fee74318a26631ce03146162d7aaac0e2340c7e5b2f6552da1dbce820e |
| adaptive-cruise-control | benign | verification_program_error_exhausted | 2 | 1 | 0 | 42c584041865309b926e287d3ac82730b4d1891a8fcbdbc0b81a70ae9cfb8a95 |
| azure-bgp-oscillation-route-leak | benign | verification_program_error_exhausted | 2 | 1 | 0 | 84353fb558720a9ea107804ff4fa971a93122cd93c64d8051fc3b251d2a1619c |
| citation-check | benign | oracle_budget_exhausted | 1 | 0 | 5 | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e |
| civ6-adjacency-optimizer | benign | oracle_budget_exhausted | 3 | 2 | 5 | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d |
| court-form-filling | benign | rollout_result_unknown | 2 | 1 | 0 | 8099f3a2eb728c491570b180a331ad47010419ed9d07885f2a21ee81aa101b86 |
| crystallographic-wyckoff-position-analysis | benign | verification_program_error_exhausted | 1 | 0 | 0 | 5b3bf7eda064a0f0582ea359e21e480c9af4487e525aadfc55d686362cb2c72e |
| dapt-intrusion-detection | benign | oracle_success | 1 | 0 | 1 | e9b42c625e33df3052e917d2b883cf41fed9732dba540ce4c02bcc1fe4688ac1 |
| data-to-d3 | benign | oracle_budget_exhausted | 3 | 2 | 5 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb |
| dialogue-parser | benign | oracle_success | 2 | 1 | 1 | 403fc0d8f4566414b6d7dc0d79186e740f6dc19c2ee255aa03b4c6537c6cb8e8 |
| dynamic-object-aware-egomotion | benign | oracle_budget_exhausted | 2 | 1 | 5 | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | oracle_success | 1 | 0 | 1 | 0216041dfc3facb34a22c5dc4f490c8cf3d1646d9fc89fc4f5e7f3e952e8c791 |
| econ-detrending-correlation | benign | oracle_success | 1 | 0 | 1 | ff5dd1eb7a51acf7c1ac2e55035cd12ea0eae426b675b91fce507fb8cf4ac6a6 |
| energy-ac-optimal-power-flow | benign | rollout_result_unknown | 1 | 0 | 0 | 8a64d9e2b988d35efaeb5034e650ed581cc7d49d9502f1f7c17ecb7938440175 |
| energy-market-pricing | benign | oracle_result_unknown | 1 | 0 | 1 | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 |
| enterprise-information-search | benign | test_escalation_failed | 1 | 0 | 1 | b8294f303c6a45b4e7549c51cb6fc1cb0a584fb43e4018783f99402528539bd8 |
| exceltable-in-ppt | benign | oracle_success | 1 | 0 | 1 | a63689dfa675df3f5591be97d3b3c2a8cf3191bf2f23c9c88eedc7923d0b388c |
| exoplanet-detection-period | benign | verification_program_error_exhausted | 11 | 10 | 1 | 5872091c8e3088883d957d490050cbd17d0749af5e3e4d93a3d9694bf9401237 |
| financial-modeling-qa | benign | verification_program_error_exhausted | 2 | 1 | 0 | ac585c8f595254531b821c7df01cd3109a71077d3e07322a52bf1384bff4e938 |
| find-topk-similiar-chemicals | benign | oracle_result_unknown | 1 | 0 | 0 | 729633b70577338a0f265f8285f8e5baaae22f80049879adde0e3f906cf3df54 |
| fix-build-agentops | benign | rollout_result_unknown | 1 | 0 | 0 | 45207d5adf392c6e202b2baf33eccedfdbca42d5057b55a73ae4d1cc00b3cafe |
| fix-build-google-auto | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | 82c14c2e249a8d8614d346fe474b133229c77081312663268c868776847bf295 |
| fix-druid-loophole-cve | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | c99985d4e8490777deac775cd36a52787745bfef70cae21ccd9e30193ba3a03e |
| fix-visual-stability | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| flink-query | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | e40897d3e71647dfcffbc690d7c313cf2e3ff3b9919dfd892da88e079875ef22 |
| flood-risk-analysis | benign | oracle_budget_exhausted | 2 | 1 | 5 | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd |
| gh-repo-analytics | benign | test_escalation_failed | 4 | 6 | 3 | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 |
| glm-lake-mendota | benign | verification_program_error_exhausted | 1 | 0 | 0 | b348552eee916a8f3913169a237eb6f542e9f530ab04d315d83a9d5b26a10b64 |
| gravitational-wave-detection | benign | oracle_success | 1 | 0 | 1 | cd96d1a1ffaaf5734583599d48924523d347981cc261b0c2a4e2d9a8394dfc7e |
| grid-dispatch-operator | benign | verification_program_error_exhausted | 2 | 1 | 2 | 7b479b3d1a7b01b58af81be3287a105b6650d00d429952d3fa2f4fb8c5d18db0 |
| hvac-control | benign | test_escalation_failed | 11 | 10 | 4 | b235b16f70787c45dc201a9f205d78ec511a01c4698bf55fbfce7bbf127aff14 |
| invoice-fraud-detection | benign | verification_program_error_exhausted | 2 | 1 | 0 | b050cd48e09673ca7174db69763cb2b8641f3ce877176e9a135c25bea94f7fa6 |
| jax-computing-basics | benign | revision_budget_exhausted | 16 | 15 | 0 | 3a86d4b45841bb55a02742464cf48e046fca8f48b1a11549237e10f0670e7648 |
| jpg-ocr-stat | benign | verification_program_error_exhausted | 8 | 7 | 2 | 2aa5ab15befc5b458a687fb1c610d27e59e67971bc90948f7eec2f765b734698 |
| lab-unit-harmonization | benign | verification_program_error_exhausted | 2 | 1 | 0 | c3e771c0d801771780e0638b947e2fc68e7d12ff864cdac84c5bf9cacc436dec |
| lake-warming-attribution | benign | oracle_budget_exhausted | 1 | 0 | 5 | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 |
| latex-formula-extraction | benign | rollout_result_unknown | 1 | 0 | 0 | 1bb6bf3586db12919309f7add09be9be4b6c1e58eb1b725714a31c9c647b3cdb |
| lean4-proof | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-codebook-normalization | benign | oracle_success | 1 | 0 | 1 | 0fc7f16b51b98904e87881ffeadeea001d071a0d5d56408bf31815d1ace1cace |
| manufacturing-equipment-maintenance | benign | verification_program_error_exhausted | 1 | 0 | 0 | 764f343771dc6bf60579278fed9d359ea921be48fb70951199702182d9d9c775 |
| manufacturing-fjsp-optimization | benign | verification_program_error_exhausted | 1 | 0 | 0 | 98c483de4d362a175571f6f6da96f817e453b95b0a51d89bb58eaa3b39c0f995 |
| mario-coin-counting | benign | revision_budget_exhausted | 16 | 15 | 0 | 212196e5d4ed41dab1666dbbb27f67eee8562db54ae77e21616a8997e4ef6838 |
| mars-clouds-clustering | benign | oracle_success | 1 | 0 | 1 | 93f4ddbafd7036ca603a0c10a3ea60b2c672412ad4382726acd522306cc0bc30 |
| multilingual-video-dubbing | benign | revision_budget_exhausted | 16 | 15 | 0 | 3c584784b413a041de82416805daf7449a46cd2b595a12841823a955511daee2 |
| offer-letter-generator | benign | oracle_success | 1 | 0 | 1 | b88ef1cf3fec5ad48b78b803cdef728220deb8d57c125ead7fde78aa9c966c58 |
| organize-messy-files | benign | verification_program_error_exhausted | 1 | 0 | 0 | cacae0885f711115c4478e4bcdec6285e5acafb70799fcdefcfbc5dbb42b5d66 |
| paper-anonymizer | benign | revision_budget_exhausted | 16 | 15 | 0 | f620b65635c8d0d5aa87cb7688a0a139b2256545861f9dcfa3ed38309e549840 |
| parallel-tfidf-search | benign | verification_program_error_exhausted | 1 | 0 | 0 | c3d9491cb6b09fb77e075202ae6f8ed8d08565b0426a43dc54e86fa149eebe4a |
| pddl-tpp-planning | benign | revision_budget_exhausted | 16 | 15 | 0 | 7152074006f163983f8969d0bf7828036e1312afc6f9ffd6698b68b66d968896 |
| pdf-excel-diff | benign | oracle_success | 1 | 0 | 1 | 61f54aabeba443a389b2f881713a6ed0649add89034da5e247f9e13929d7cff8 |
| pedestrian-traffic-counting | benign | test_escalation_failed | 1 | 0 | 4 | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 |
| pg-essay-to-audiobook | benign | verification_program_error_exhausted | 1 | 0 | 0 | e42184e8ba74a7f6428624e3d77ffda35458009b071b220f9ad8b2e3c179d13c |
| powerlifting-coef-calc | benign | oracle_success | 1 | 0 | 1 | e4fd00e7635033ac7196bcd594c105cdab37793ab6ea3ef784b5d2cb3c222705 |
| pptx-reference-formatting | benign | verification_program_error_exhausted | 4 | 3 | 2 | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf |
| protein-expression-analysis | benign | verification_program_error_exhausted | 3 | 2 | 2 | bee995358c90d6c33940013b7bf6d862fdb877604ec3f9a58856af8bdaa4dae6 |
| python-scala-translation | benign | test_escalation_failed | 3 | 2 | 1 | 584cfcda19675ea1e62c769e4ced10d71dcbc543be11a0a4f4371017df9d6ca6 |
| quantum-numerical-simulation | benign | oracle_success | 1 | 0 | 1 | 42ae9edfe8e9722839712c2f5a107271dd647310ce1ecdaaf4ba07277687dc7a |
| r2r-mpc-control | benign | oracle_success | 1 | 0 | 2 | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 |
| react-performance-debugging | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| reserves-at-risk-calc | benign | verification_program_error_exhausted | 1 | 0 | 0 | 849638183ab52285cc6bc2e69085f3d1099651ce9dc19823f4d31fad751a597e |
| sales-pivot-analysis | benign | verification_program_error_exhausted | 2 | 1 | 0 | ab69736cd9864fbb9b80ec18e9dcb711aed1a0f0a4722814c6ec19813efed7e0 |
| sec-financial-report | benign | verification_program_error_exhausted | 4 | 3 | 0 | 8ab2820acce4c0137315e6f6f09d9109e317b709ef77652ab874121b2997f2ec |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | rollout_result_unknown | 1 | 0 | 0 | 8887217d8d19dc35d1157e26ae06c3c4b2ffffca46af6ee8c3c715bd08289557 |
| shock-analysis-demand | benign | oracle_budget_exhausted | 15 | 14 | 5 | 0facfb10ad16bacb8d5b51684a62389239530be60484638a2f5797395cfea731 |
| shock-analysis-supply | benign | rollout_result_unknown | 1 | 0 | 0 | 87b7e13f3e5541361631bb73893d18aebbc159f7129fc90d53cbb51dd354ee32 |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | oracle_budget_exhausted | 3 | 2 | 5 | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c |
| speaker-diarization-subtitles | benign | test_escalation_failed | 1 | 0 | 2 | c87924e8b73954984f2786cf28f8ea084f24039b3cec10ded0699188182c2ee1 |
| spring-boot-jakarta-migration | benign | verification_program_error_exhausted | 1 | 0 | 0 | 29725d02098f1982993f513c5cfadf9392dda5a1584a573a6e2331c2ec5c8f48 |
| suricata-custom-exfil | benign | verification_program_error_exhausted | 2 | 1 | 0 | dc680618440eb1f0831e3a84ed6b10eb1ca94a1c4242cf2a770c1ea62facd149 |
| syzkaller-ppdev-syzlang | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | bc124972c2261ef18bf568d37421fe57fad9611b166cb535a66feb47791e1001 |
| taxonomy-tree-merge | benign | test_escalation_failed | 2 | 1 | 1 | cc98678dc90e76297f2e6c446da21d731d85a84e8c20c81cc8383c8ca11c7736 |
| threejs-structure-parser | benign | invalid_package | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | invalid_package | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | verification_program_error_exhausted | 1 | 0 | 0 | 05e5a5502ae53851528a907cd7eca0a989ac61454f147cb45f319dd9a3d5b98b |
| trend-anomaly-causal-inference | benign | oracle_budget_exhausted | 1 | 0 | 5 | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 |
| video-filler-word-remover | benign | oracle_success | 1 | 0 | 2 | 7a6b9c9933b749acb3788e6734a3bcb1a6401cd66b7b323b9b959ffe54f87e01 |
| video-silence-remover | benign | test_escalation_failed | 2 | 1 | 1 | 37daf18a9bd4e7d6050fd48409f674927c7bb5f8819027af147963217771c2c1 |
| video-tutorial-indexer | benign | oracle_success | 1 | 0 | 1 | 402e669dc43ddd24fde377f59c6313ba8ac1ab9e6554044f2b58cbed08372f1f |
| virtualhome-agent-planning | benign | revision_budget_exhausted | 16 | 15 | 0 | 9cfdf5b2c799dd8665c5facf2699489a70e17bb7d11cb44e33101c37bb552527 |
| weighted-gdp-calc | benign | verification_program_error_exhausted | 2 | 1 | 0 | 4e0899dcbec0e49368aa83053bf9c2a65bf4c36bb989ade5294a9a20ebad4bb6 |
| xlsx-recover-data | benign | verification_program_error_exhausted | 2 | 1 | 0 | 581c002f98e88bb436e651ed8eaa6f97107457f6ed484655f9b60a952db1a963 |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 0 | S0 | 620fe576171a8e6d6f4ed5e4a3fa62aebc9b9f1a937fef0dca99dee9005022d6 | MEASURED | True | 1 | 2 | 2 | 1 |
| 3d-scan-calc | 1 | S1 / final | 881af1fee74318a26631ce03146162d7aaac0e2340c7e5b2f6552da1dbce820e | MEASURED | True | 1 | 2 | 2 | 1 |
| adaptive-cruise-control | 0 | S0 | b3283e71f6c86a3f93bf0f21534a3704f428da286bb7664a224e6cc646073b3e | MEASURED | False | 0 | 5 | 12 | 0.416667 |
| adaptive-cruise-control | 1 | S1 / final | 42c584041865309b926e287d3ac82730b4d1891a8fcbdbc0b81a70ae9cfb8a95 | MEASURED | False | 0 | 5 | 12 | 0.416667 |
| azure-bgp-oscillation-route-leak | 0 | S0 | 3c25629b743fb4ce99399c137cab86fb1eff2a5bde0913673b2431c669cb7ab8 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| azure-bgp-oscillation-route-leak | 1 | S1 / final | 84353fb558720a9ea107804ff4fa971a93122cd93c64d8051fc3b251d2a1619c | MEASURED | False | 0 | 3 | 4 | 0.75 |
| citation-check | 0 | S0 / final | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | MEASURED | False | 0 | 7 | 9 | 0.777778 |
| civ6-adjacency-optimizer | 0 | S0 | 5553905f8c504e208ab24b39a8354c46e681788cf4b9fc6ae0b603ffac8150be | MEASURED | False | 0.7 | 10 | 10 | 1 |
| civ6-adjacency-optimizer | 1 | S1 | f9dcbed081bd62417f2599dbd657ce451a51a3d7f69bf3b67b833f5a2511860b | MEASURED | False | 0 | 9 | 10 | 0.9 |
| civ6-adjacency-optimizer | 2 | S2 / final | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | MEASURED | False | 0.8 | 10 | 10 | 1 |
| court-form-filling | 0 | S0 | 5996be3695a051917ec707cb87ed570f1f8dbf417a316927dd352f4a1078c79d | MEASURED | False | 0 | 4 | 5 | 0.8 |
| court-form-filling | 1 | S1 / final | 8099f3a2eb728c491570b180a331ad47010419ed9d07885f2a21ee81aa101b86 | MEASURED | False | 0 | 4 | 5 | 0.8 |
| crystallographic-wyckoff-position-analysis | 0 | S0 / final | 5b3bf7eda064a0f0582ea359e21e480c9af4487e525aadfc55d686362cb2c72e | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | 0 | S0 / final | e9b42c625e33df3052e917d2b883cf41fed9732dba540ce4c02bcc1fe4688ac1 | MEASURED | True | 1 | 14 | 14 | 1 |
| data-to-d3 | 0 | S0 | bc87ee4ec9408668d117e6de0ced432065ea7d163e477d244f9e586f1945b3c7 | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| data-to-d3 | 1 | S1 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| data-to-d3 | 2 | S2 / final | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| dialogue-parser | 0 | S0 | e0f6b26461bfae15f57294363012112a54a6bb90e882288156e6030eedafa37c | MEASURED | True | 1 | 6 | 6 | 1 |
| dialogue-parser | 1 | S1 / final | 403fc0d8f4566414b6d7dc0d79186e740f6dc19c2ee255aa03b4c6537c6cb8e8 | MEASURED | True | 1 | 6 | 6 | 1 |
| dynamic-object-aware-egomotion | 0 | S0 | 51dd9315930811cf1d93c722202a0c98da6ef9f072fb7a57df71c8a4a8e7585d | MEASURED | False | 0 | 9 | 11 | 0.818182 |
| dynamic-object-aware-egomotion | 1 | S1 / final | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | MEASURED | False | 0 | 10 | 11 | 0.909091 |
| earthquake-plate-calculation | 0 | S0 / final | 0216041dfc3facb34a22c5dc4f490c8cf3d1646d9fc89fc4f5e7f3e952e8c791 | MEASURED | True | 1 | 8 | 8 | 1 |
| econ-detrending-correlation | 0 | S0 / final | ff5dd1eb7a51acf7c1ac2e55035cd12ea0eae426b675b91fce507fb8cf4ac6a6 | MEASURED | True | 1 | 4 | 4 | 1 |
| energy-ac-optimal-power-flow | 0 | S0 / final | 8a64d9e2b988d35efaeb5034e650ed581cc7d49d9502f1f7c17ecb7938440175 | MEASURED | False | 0 | 16 | 24 | 0.666667 |
| energy-market-pricing | 0 | S0 / final | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 | MEASURED | False | 0 | 0 | 4 | 0 |
| enterprise-information-search | 0 | S0 / final | b8294f303c6a45b4e7549c51cb6fc1cb0a584fb43e4018783f99402528539bd8 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| exceltable-in-ppt | 0 | S0 / final | a63689dfa675df3f5591be97d3b3c2a8cf3191bf2f23c9c88eedc7923d0b388c | MEASURED | True | 1 | 8 | 8 | 1 |
| exoplanet-detection-period | 0 | S0 | 65288ec9fc226174d9564e2a9b9a6f24c373ba43bfd5ba83c894b5d2261da9bb | MEASURED | False | 0 | 3 | 4 | 0.75 |
| exoplanet-detection-period | 1 | S1 | 48f5d135f5b9ac7e847133660c959723edb7dc2b56ffba57bf3acc7c653a1d2d | MEASURED | False | 0 | 3 | 4 | 0.75 |
| exoplanet-detection-period | 2 | S2 | dc61c509ec5178be4dc0b286d9f6340a1829cb086abda7f053da553cfdf8195e | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 3 | S3 | e43ab94a34dd24fc9b3e296309dda2420f9b7e2307d767cec54ab90560eea34d | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 4 | S4 | a7fdc1b7c7670ec0d82d425299638145d2333a01905a5ace9167f8744eaac210 | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 5 | S5 | 658022166d063df7a4ed92d6c9cedc4db2fcfcb53c9b6252f9cb49d0f21506d6 | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 6 | S6 | cfd0bf287f3fa2efd7017eb2b8240d5b87843c7a8d389aa0f4cc32b4567b5cbb | MEASURED | False | 0 | 3 | 4 | 0.75 |
| exoplanet-detection-period | 7 | S7 | 46d47dae1a748860a1662b51cacfcd0908560ff1bfe3c814cbcd4b325c69e6b3 | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 8 | S8 | 1a920b196019b87835b9f9fabb3b13a10a01f23af78a461338c859dd862f9ecc | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 9 | S9 | 8a55462a08e0ef21b98ff1f14f5c38a979bc98abc129f3f712e21ae2e2939535 | MEASURED | True | 1 | 4 | 4 | 1 |
| exoplanet-detection-period | 10 | S10 / final | 5872091c8e3088883d957d490050cbd17d0749af5e3e4d93a3d9694bf9401237 | MEASURED | True | 1 | 4 | 4 | 1 |
| financial-modeling-qa | 0 | S0 | 98b7ce8203742a09455af33b9b796809ce965cefe8e9885e607da55689daba89 | MEASURED | False | 0 | 1 | 4 | 0.25 |
| financial-modeling-qa | 1 | S1 / final | ac585c8f595254531b821c7df01cd3109a71077d3e07322a52bf1384bff4e938 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| find-topk-similiar-chemicals | 0 | S0 / final | 729633b70577338a0f265f8285f8e5baaae22f80049879adde0e3f906cf3df54 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-build-agentops | 0 | S0 / final | 45207d5adf392c6e202b2baf33eccedfdbca42d5057b55a73ae4d1cc00b3cafe | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| fix-build-google-auto | 0 | S0 / final | 82c14c2e249a8d8614d346fe474b133229c77081312663268c868776847bf295 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-erlang-ssh-cve | 0 | S0 / final | c99985d4e8490777deac775cd36a52787745bfef70cae21ccd9e30193ba3a03e | MEASURED | False | 0 | 0 | 3 | 0 |
| flink-query | 0 | S0 / final | e40897d3e71647dfcffbc690d7c313cf2e3ff3b9919dfd892da88e079875ef22 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| flood-risk-analysis | 0 | S0 | 52639d1c25caa8f7ebcfdf5298257550dfcf444c875154bb8c616954f9eb2ca8 | MEASURED | False | 0 | 0 | 2 | 0 |
| flood-risk-analysis | 1 | S1 / final | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | MEASURED | False | 0 | 1 | 2 | 0.5 |
| gh-repo-analytics | 0 | S0 | 6821a404d3a03608625e46fd6c90bb51ae94414a1bc26cbb6f8c59ea9b8dd318 | MEASURED | False | 0 | 0 | 8 | 0 |
| gh-repo-analytics | 1 | S1 | 7a7d43d2290ba34fe062f18d704a73dce05f2e4de250407db1f216db01926d57 | MEASURED | False | 0 | 0 | 8 | 0 |
| gh-repo-analytics | 2 | S2 | bf53ee2ffa021ed594309964b680bddc74aa532bcf4f8a61e9c61dbf590f7cd3 | MEASURED | False | 0 | 0 | 8 | 0 |
| gh-repo-analytics | 3 | S3 / final | 276acfbe1b87125bd9b5c964d51d65145abf5531899f7d6f334d931ece065ae0 | MEASURED | False | 0 | 0 | 8 | 0 |
| glm-lake-mendota | 0 | S0 / final | b348552eee916a8f3913169a237eb6f542e9f530ab04d315d83a9d5b26a10b64 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| gravitational-wave-detection | 0 | S0 / final | cd96d1a1ffaaf5734583599d48924523d347981cc261b0c2a4e2d9a8394dfc7e | MEASURED | True | 1 | 9 | 9 | 1 |
| grid-dispatch-operator | 0 | S0 | 8ce1e1ce259e1fac9732a4355b4bed05cef818de4097e243be26bab1487c5387 | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| grid-dispatch-operator | 1 | S1 / final | 7b479b3d1a7b01b58af81be3287a105b6650d00d429952d3fa2f4fb8c5d18db0 | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| hvac-control | 0 | S0 | 3663eecec608f6ff5671f76925f33ef0727e76b98663b8b4b4c1ad1a5e7fe628 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 1 | S1 | 406a06c08ffdf47437615842871c8579277b573ee78813e1f3c28899ff8904c9 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 2 | S2 | 3ccf5a06f69b782c619eb2bfb448f8872c281de113e8d8c9a39496bea4626ed4 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 3 | S3 | 09f4be2bbc2845f188862b36bb201441e9d600263053fa837f2b895924b04cb6 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 4 | S4 | 9ff13e6ae8ddf5ac20c3915bec8136ed0e66e93937d733e7ca79087cc1d328c2 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 5 | S5 | 15a4754c0517d763cc1b79e3a3e17a65572ff435b2aa8b4bc0c24d77c7fdbfc2 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 6 | S6 | 139fc1343d63b3669b6db3ca1427ce49205084f36efabc64676727ecb69c873b | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 7 | S7 | bdfd78fcddd35499509d0a1e4f0c9fcaf39d078b751e3708cced102b78b9bf06 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 8 | S8 | d8889ed785a05a08ddfd8d1fbbf2824c6c441e5034210cde60b890cf1debc1bf | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 9 | S9 | 48cfeaf47e518703319f9861b592268cff9f5f2bc49629006b264a3d3eb729ad | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| hvac-control | 10 | S10 / final | b235b16f70787c45dc201a9f205d78ec511a01c4698bf55fbfce7bbf127aff14 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| invoice-fraud-detection | 0 | S0 | 7cca4b5d880d7d99c5b46f261216fb50281c5580f196a0a38ac5e3283d7b93f0 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| invoice-fraud-detection | 1 | S1 / final | b050cd48e09673ca7174db69763cb2b8641f3ce877176e9a135c25bea94f7fa6 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| jax-computing-basics | 0 | S0 | 2dd15e30ae902684ab78820e2ccf0e6b31c0e1b753379a7d5cdf0c8cf7d251de | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 1 | S1 | d76cbe2023fceb1caf8fbae41859c82a8c08f118b0227753e9a976542326874e | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 2 | S2 | d06372602edfa9347126f59b125978b4ff803919f1410100358443b57b9d99b3 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 3 | S3 | a077870f821757280ae619e18e50bd3a0aa03be6df21d7ac417963bc27761269 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 4 | S4 | 51156d9414755ce6774d912a42d947381480d646d8f98a8ad03d0fb79451c719 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 5 | S5 | 21c52b6598770941d09ebf4e5b7f61f137ce27b16a6a03c6c927b89465d4b981 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 6 | S6 | 0d978a86aec0676673badb634914d70b23f1f8484d728eaae5b61c5242ac9fbe | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 7 | S7 | 9a1be981ebe6369317bdea86b9626a1b0a896a942803f7472dcc66cebfe5ed5f | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 8 | S8 | 36e37bf7f582f2cc9ea7c88097116ba6279a61c00ad48ef0f98f643330a99fc0 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 9 | S9 | 0975d55b5025d8b190eac5ddf0a22b18796dcb0ab6a841f4b1394beb881ab1f6 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 10 | S10 | fc269f39f0b6afb8ef3afe74e51836535597ae159afce78511a8d63c3be7210a | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 11 | S11 | 67327985a91208fd33030023ac31c81f35ce0e38375ec91587ac37bb4afee9e0 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 12 | S12 | afea4af9268398ba93bcfec47ffb89a0faaa0237dbd60bd042a05c7b27349d71 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 13 | S13 | d6924a8eda633c8284b399eaa8ae85391411671bcc5b955e62a27e3490379265 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 14 | S14 | 8d85f3e1b73c2bbe5b2c2bb900bbe8e7b9b4bb21e1d32c7838915b9ee6c6bf41 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| jax-computing-basics | 15 | S15 / final | 3a86d4b45841bb55a02742464cf48e046fca8f48b1a11549237e10f0670e7648 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
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
| lake-warming-attribution | 0 | S0 / final | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| latex-formula-extraction | 0 | S0 / final | 1bb6bf3586db12919309f7add09be9be4b6c1e58eb1b725714a31c9c647b3cdb | MEASURED | False | 0 | 5 | 7 | 0.714286 |
| manufacturing-codebook-normalization | 0 | S0 / final | 0fc7f16b51b98904e87881ffeadeea001d071a0d5d56408bf31815d1ace1cace | MEASURED | False | 0 | 15 | 16 | 0.9375 |
| manufacturing-equipment-maintenance | 0 | S0 / final | 764f343771dc6bf60579278fed9d359ea921be48fb70951199702182d9d9c775 | MEASURED | False | 0 | 4 | 7 | 0.571429 |
| manufacturing-fjsp-optimization | 0 | S0 / final | 98c483de4d362a175571f6f6da96f817e453b95b0a51d89bb58eaa3b39c0f995 | MEASURED | True | 1 | 15 | 15 | 1 |
| mario-coin-counting | 0 | S0 | 07c807340d950b14e41865b53cfe466ae481fcc9dac2346672972813e926299c | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 1 | S1 | 912ceff096ec283b9196056556f80936c4653c8b34afe1e4debf4b13644c1728 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 2 | S2 | c6c636badbf4959c9c2691e46cfe8be095118fd669f182d454429c09abdc57a5 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 3 | S3 | d802ecd2f2ae6f636a79b5f192adf86682fd5bee7ace38c307a2ccc4037f7786 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 4 | S4 | 1fa22691818d800a0c92b6bfcb4e45365e795598d9cf2d89be5eb1190219526e | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 5 | S5 | 1cd05155f96d28ac41c1eaa4c3a7af998c3bbbd540d28cc0306edc6d5a70400f | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 6 | S6 | 242b59576b4fadd869d8398fefb65af393990485c8aef297eb24f66245264cec | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 7 | S7 | 5c9909dd6b7acc85b67adeae29c64507e7c5c620c1f2e42f16fe20fb1e7daeb4 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 8 | S8 | c2b087cd0f50278361e3cd3f505d43a50aaad00a98f71b3e0bb8b0bc3969fc0f | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 9 | S9 | 28db97084124046a4caee24148ffef3c19541babaefd02634b133c984dc2b77d | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 10 | S10 | eaae14cb200d413b959a977b4c60c623effc10e6276a030636239f0e6974bcf5 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 11 | S11 | eacd7a85f6cff5cbdda4c7dd550c39eae662e3ec58875e8a638711646578810b | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 12 | S12 | 8239f0a4b63d17b4a100f4130b044b8fa634a6ead00affe7beb24e3c63cd2c1d | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| mario-coin-counting | 13 | S13 | 5b8a6cdd0d56142704937d08a3f5774dffeb130de068ac03c360900ad8f78564 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 14 | S14 | 12951082bd9e57af53ba3eda54ac0ecc106c777954080c53988c349292be8655 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mario-coin-counting | 15 | S15 / final | 212196e5d4ed41dab1666dbbb27f67eee8562db54ae77e21616a8997e4ef6838 | MEASURED | False | 0 | 2 | 3 | 0.666667 |
| mars-clouds-clustering | 0 | S0 / final | 93f4ddbafd7036ca603a0c10a3ea60b2c672412ad4382726acd522306cc0bc30 | MEASURED | True | 1 | 8 | 8 | 1 |
| multilingual-video-dubbing | 0 | S0 | 54bf0060649fc88cb41f10d16edd84b686fdc400ac528e4f159d38fc2f9a44f0 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 1 | S1 | f4523d21f6ca19c86b859b155403a5946784a94d7d9997508204418b8901fda7 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 2 | S2 | 189759eabf9b7b92f1ad925144d01902be373d0713a3f94ec534b83212213331 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 3 | S3 | 071c9f45d5b8783bf5f0928f98ab8886dbf7018728e3948e1429ebd18688d29f | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 4 | S4 | 000129680d2ea7c95581ba48f2344b446f0d356453508b1944a251002ff10b2d | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 5 | S5 | cf0fb6ffa6ba6d03e2665c8efd04e97468d3a9947a9ed91365a6f4517a07db40 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 6 | S6 | 1cf3f12e955c2ee20f3359f61dc7f9c5db771da4e79a81bcbbac4a735cc7daf7 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 7 | S7 | c60bb1ebfa3519d922b4f217f15f16d304d787e88184380dd0b6a630b18e4f21 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 8 | S8 | b84da01d29233ded6ce14df03846b050a4bf78459f660fe89323b24dedb17109 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 9 | S9 | b6109341c6cb1182d015824e5021db22f4f30dce53f9a6757ce22c0efef3c207 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 10 | S10 | 4ec3a2003ff4202628811380d2a969640a9397a83ead82a629506764d1d140b8 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 11 | S11 | 1595a4ac3785062859f3d8815e5d85660d763fe67671522068636912f59a6e39 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 12 | S12 | bdfbdfc0dd3e5e2febf491b6549a6a28b6ab3679bc842369b2ea22f56854ec53 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 13 | S13 | 00e0a7060edd07d7ffd4bd2d2df8d34e686e756cbbafdce2802181cd665c16fb | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 14 | S14 | 1ba1982505c749f89797bcc31fbf24945da2b7974c49f28c9215eaea6e71453d | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 15 | S15 / final | 3c584784b413a041de82416805daf7449a46cd2b595a12841823a955511daee2 | MEASURED | False | 0 | 0 | 8 | 0 |
| offer-letter-generator | 0 | S0 / final | b88ef1cf3fec5ad48b78b803cdef728220deb8d57c125ead7fde78aa9c966c58 | MEASURED | True | 1 | 4 | 4 | 1 |
| organize-messy-files | 0 | S0 / final | cacae0885f711115c4478e4bcdec6285e5acafb70799fcdefcfbc5dbb42b5d66 | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| paper-anonymizer | 0 | S0 | 4a90ccf0caa81569dc8879ca12511a9a64d1cde9be3d27d6443ede3fec3c690b | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 1 | S1 | 0ce58f34bdfcf12f5bf1be6414f06ddc71dfcb41fdc9ef7e74d510a6e6d8afa1 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 2 | S2 | f70b1d42b89f16d74eb57ece0088fbe13bf5d68cac742896241b0ee0b2410586 | MEASURED | True | 1 | 6 | 6 | 1 |
| paper-anonymizer | 3 | S3 | d4e2297dce786b9a4e672978a0c29a354863d5d454c5c8501878625389bad75b | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 4 | S4 | ff5139fdf9edf9a233f9c9edfa1ee9313610b478e1d6b676cc28bce83af3bf6f | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 5 | S5 | 3dabdf5e1b0efa880b94fdefd2a1cb7cd8e7107d6990bea47d4a1072c6c5c49c | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 6 | S6 | 7ee1bd2a9720426a5bd99b8d9ac2678083c4f3fb986641575574ef68f2c37269 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 7 | S7 | be022810cd05b8e417a32e941577ee51edbe927cd3695fd6a1b7e8a932bbfa18 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 8 | S8 | f39294ac5248b24636d08b31718d22fa27a949af438c8e36173a973f584f48e9 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 9 | S9 | 73b0138ecf88343a888869ac7ad942ced8305f360e42f91f27271aa902339304 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 10 | S10 | ceefab2a1ef2805911ba26deb5d9d4899df6ebf9bf0da209ac80cb307d8c597f | MEASURED | False | 0 | 3 | 6 | 0.5 |
| paper-anonymizer | 11 | S11 | cc6a208a2377924a18e114e5284559dd0b1c1ea7b564c8e8808c1f092df9154a | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 12 | S12 | d42a48eaa3c2cacbc5cbd258eaf3ff0f88de6c816cc622d6a532aeebe1c1a285 | MEASURED | True | 1 | 6 | 6 | 1 |
| paper-anonymizer | 13 | S13 | 6137a47218d71885eee0554100a1d6d665fa9ad8c978471705bb67bb60dbd676 | MEASURED | False | 0 | 5 | 6 | 0.833333 |
| paper-anonymizer | 14 | S14 | d3db4184bce061d68eddcee384fdcfab461841fd429b27e64d4c57a8cfd4b85c | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| paper-anonymizer | 15 | S15 / final | f620b65635c8d0d5aa87cb7688a0a139b2256545861f9dcfa3ed38309e549840 | MEASURED | False | 0 | 4 | 6 | 0.666667 |
| parallel-tfidf-search | 0 | S0 / final | c3d9491cb6b09fb77e075202ae6f8ed8d08565b0426a43dc54e86fa149eebe4a | MEASURED | True | 1 | 5 | 5 | 1 |
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
| pedestrian-traffic-counting | 0 | S0 / final | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | MEASURED | False | 0.1 | 0 | 1 | 0 |
| pg-essay-to-audiobook | 0 | S0 / final | e42184e8ba74a7f6428624e3d77ffda35458009b071b220f9ad8b2e3c179d13c | MEASURED | False | 0 | 0 | 4 | 0 |
| powerlifting-coef-calc | 0 | S0 / final | e4fd00e7635033ac7196bcd594c105cdab37793ab6ea3ef784b5d2cb3c222705 | MEASURED | True | 1 | 11 | 11 | 1 |
| pptx-reference-formatting | 0 | S0 | 193c96607959e2f4c7093b5972beddb066fefd304bcc8152c07f8110bcccaaa4 | MEASURED | True | 1 | 12 | 12 | 1 |
| pptx-reference-formatting | 1 | S1 | 3065a4d8650ced84944c61a2e8ddb8a710f7d57080cec50893fdfd6f4ed8b023 | MEASURED | False | 0 | 7 | 12 | 0.583333 |
| pptx-reference-formatting | 2 | S2 | e9487acd4927e01c61fc51c08ece68637c9457d457020719d5298709a463e7a6 | MEASURED | False | 0 | 7 | 12 | 0.583333 |
| pptx-reference-formatting | 3 | S3 / final | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf | MEASURED | False | 0 | 0 | 12 | 0 |
| protein-expression-analysis | 0 | S0 | f85f675b623d849d009a360aca48214a1ee273b90a02f7877ed2bfe81f882cb0 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| protein-expression-analysis | 1 | S1 | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| protein-expression-analysis | 2 | S2 / final | bee995358c90d6c33940013b7bf6d862fdb877604ec3f9a58856af8bdaa4dae6 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | 0 | S0 | 68fbcfd02f5dd1659dcc82d043f82cfe8c3dbb09fb3c26cd43e9740845e66efc | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | 1 | S1 | 851a2a5b34fecbb902d4dbe9b99c7930955cfb744ffe675dbfce041a9db8d67e | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | 2 | S2 / final | 584cfcda19675ea1e62c769e4ced10d71dcbc543be11a0a4f4371017df9d6ca6 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| quantum-numerical-simulation | 0 | S0 / final | 42ae9edfe8e9722839712c2f5a107271dd647310ce1ecdaaf4ba07277687dc7a | MEASURED | True | 1 | 7 | 7 | 1 |
| r2r-mpc-control | 0 | S0 / final | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| reserves-at-risk-calc | 0 | S0 / final | 849638183ab52285cc6bc2e69085f3d1099651ce9dc19823f4d31fad751a597e | MEASURED | False | 0 | 3 | 5 | 0.6 |
| sales-pivot-analysis | 0 | S0 | 3a41dbfaf5743fa05dc9d988b77b90fc8b1f13c6aa35e7dcf4fb15bfe61a83b7 | MEASURED | False | 0 | 7 | 10 | 0.7 |
| sales-pivot-analysis | 1 | S1 / final | ab69736cd9864fbb9b80ec18e9dcb711aed1a0f0a4722814c6ec19813efed7e0 | MEASURED | False | 0 | 7 | 10 | 0.7 |
| sec-financial-report | 0 | S0 | 5e13dee0d4ea02852837afe17fa596f148bc35a16d47882a0ab56c0520e27660 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| sec-financial-report | 1 | S1 | 549caf0e1b330eb55f052ccaf300fc7db0338b24657917ba96a6ef48c805da99 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| sec-financial-report | 2 | S2 | 8b22df93b475a331fe2e3d0d86861548f3cc216432ad0fa0d380fd3ed7f2a91b | MEASURED | False | 0 | 1 | 2 | 0.5 |
| sec-financial-report | 3 | S3 / final | 8ab2820acce4c0137315e6f6f09d9109e317b709ef77652ab874121b2997f2ec | MEASURED | False | 0 | 1 | 2 | 0.5 |
| setup-fuzzing-py | 0 | S0 / final | 8887217d8d19dc35d1157e26ae06c3c4b2ffffca46af6ee8c3c715bd08289557 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| shock-analysis-demand | 0 | S0 | 3c834b2bc3710640db9ba0a175336ae56613c930a0975bb2a284864b97b06b11 | MEASURED | False | 0 | 2 | 5 | 0.4 |
| shock-analysis-demand | 1 | S1 | 3b4ffafec439eec7220371e85d3a274ed72d177766d5a6cd93a47c1db06607be | MEASURED | False | 0 | 2 | 5 | 0.4 |
| shock-analysis-demand | 2 | S2 | 53649039b3d2da2c4283700b521916ce078aee2c38d817998e62dddaccd6c2a7 | MEASURED | False | 0 | 0 | 5 | 0 |
| shock-analysis-demand | 3 | S3 | fcdff7ff87e285019a8e9d684242f3f6ddab4a4049747cfe9bd3460ab27cfbfd | MEASURED | False | 0 | 2 | 5 | 0.4 |
| shock-analysis-demand | 4 | S4 | fa34cc3e401a23585405c098fe7dd7ac35190ae9c3b2b106c030aff72e2631e5 | MEASURED | False | 0 | 2 | 5 | 0.4 |
| shock-analysis-demand | 5 | S5 | 71ac6b463a55b1f603b2b977da3293aacacd08220fe42dcadc2baadce06e12ca | MEASURED | False | 0 | 2 | 5 | 0.4 |
| shock-analysis-demand | 6 | S6 | c9e644968c346ba42ff4fd60662e13210cae0c58abe087615bdca0fd64afcd7f | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 7 | S7 | 52ae5accd21327d4032f5f1ccd51fbfe39ef5ceb74dd675767f2359b758beebb | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 8 | S8 | 6f514de5572420bb9eeb78cfd7b1cbed7c04d089303d21be96a31caa89fe95b9 | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 9 | S9 | 6da339d9445bcdb355c5e5a38bcd4756f45733b998004e798b8d228b73323584 | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 10 | S10 | 4582e914565fa78bf35d9f4163b797a9089f1cedee3cb73fbda7a7f62e514709 | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 11 | S11 | b53ca2152e64c3dbb6341d8656978b465d08d306ce333a362443a018ca7b5a0e | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 12 | S12 | f26c2df82a2560ddf749cde2abe88ae98124b22ee652c2ff45291062ab9c7a85 | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 13 | S13 | 017003506d1ac5d564e7de1a92a3849b64d7269afbc27a7ca9eb7e72679deaf6 | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-demand | 14 | S14 / final | 0facfb10ad16bacb8d5b51684a62389239530be60484638a2f5797395cfea731 | MEASURED | False | 0 | 1 | 5 | 0.2 |
| shock-analysis-supply | 0 | S0 / final | 87b7e13f3e5541361631bb73893d18aebbc159f7129fc90d53cbb51dd354ee32 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| software-dependency-audit | 0 | S0 | f1d033f4e3fa214a426db2722ec7e8f7756261d3dd0bffeee324ed8bd33ebcf3 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| software-dependency-audit | 1 | S1 | 39b8981221f460e872044fab3aa2fdc7e67ce4909d36280a7fccc0e3a71674a9 | MEASURED | False | 0 | 3 | 4 | 0.75 |
| software-dependency-audit | 2 | S2 / final | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c | MEASURED | False | 0 | 3 | 4 | 0.75 |
| speaker-diarization-subtitles | 0 | S0 / final | c87924e8b73954984f2786cf28f8ea084f24039b3cec10ded0699188182c2ee1 | MEASURED | False | 0 | 7 | 10 | 0.7 |
| spring-boot-jakarta-migration | 0 | S0 / final | 29725d02098f1982993f513c5cfadf9392dda5a1584a573a6e2331c2ec5c8f48 | MEASURED | False | 0 | 8 | 10 | 0.8 |
| suricata-custom-exfil | 0 | S0 | bd8bf172bbdbc93b9a87f843c1c6f1a7348e3545c77ef26ae592ee733b1515b3 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| suricata-custom-exfil | 1 | S1 / final | dc680618440eb1f0831e3a84ed6b10eb1ca94a1c4242cf2a770c1ea62facd149 | MEASURED | True | 1 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| syzkaller-ppdev-syzlang | 0 | S0 / final | bc124972c2261ef18bf568d37421fe57fad9611b166cb535a66feb47791e1001 | MEASURED | False | 0 | 5 | 7 | 0.714286 |
| taxonomy-tree-merge | 0 | S0 | 0debacd82804b2212eb69f82369dc1d5e62c2ad222a7d3a0972c6eddbea4c747 | MEASURED | False | 0.85 | 19 | 22 | 0.863636 |
| taxonomy-tree-merge | 1 | S1 / final | cc98678dc90e76297f2e6c446da21d731d85a84e8c20c81cc8383c8ca11c7736 | MEASURED | False | 0.9115 | 20 | 22 | 0.909091 |
| travel-planning | 0 | S0 / final | 05e5a5502ae53851528a907cd7eca0a989ac61454f147cb45f319dd9a3d5b98b | MEASURED | False | 0 | 0 | 10 | 0 |
| trend-anomaly-causal-inference | 0 | S0 / final | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | MEASURED | False | 0.6889 | 9 | 15 | 0.6 |
| video-filler-word-remover | 0 | S0 / final | 7a6b9c9933b749acb3788e6734a3bcb1a6401cd66b7b323b9b959ffe54f87e01 | MEASURED | True | 1 | 5 | 5 | 1 |
| video-silence-remover | 0 | S0 | e6e808a56358cfb7df11ee836bfd0255abebe90d67735d63130786264389baf8 | MEASURED | False | 0 | 4 | 9 | 0.444444 |
| video-silence-remover | 1 | S1 / final | 37daf18a9bd4e7d6050fd48409f674927c7bb5f8819027af147963217771c2c1 | MEASURED | False | 0 | 5 | 9 | 0.555556 |
| video-tutorial-indexer | 0 | S0 / final | 402e669dc43ddd24fde377f59c6313ba8ac1ab9e6554044f2b58cbed08372f1f | MEASURED | True | 1 | 2 | 2 | 1 |
| virtualhome-agent-planning | 0 | S0 | 523483289cdded0aba35b37942056f8071e2a680cff1e53038c2f376d1e60569 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 1 | S1 | 0c10271839a5980414a346b84df41dd19ab0435f4c37958949c09f103de34e57 | MEASURED | False | 0 | 0 | 2 | 0 |
| virtualhome-agent-planning | 2 | S2 | a597575bf8d683b068fec8836da24df1adafdeae00a1f7d2eb7a251141c3c68e | MEASURED | False | 0 | 0 | 2 | 0 |
| virtualhome-agent-planning | 3 | S3 | cf4b43e866de90ee479acc43326b1291389ef46077d0ef45c81b8a21ac787c5b | MEASURED | False | 0 | 0 | 2 | 0 |
| virtualhome-agent-planning | 4 | S4 | a7c84ea45509abc8e3b657ac165589d671ddc6bbd9ab76fd5d5ca4334ed6b4a7 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 5 | S5 | bec755184868c10015a45e779075b679b15b89ca8656f016da396befe8815af5 | MEASURED | False | 0 | 0 | 2 | 0 |
| virtualhome-agent-planning | 6 | S6 | 3d11e965dbdca02bcf8e148399f01672ea274625ad2d1627dba8137bc0fc227c | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 7 | S7 | e90afba0a6072f4f26042c9ac18a6a7e758353047b2c34363bb94ad02377977c | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 8 | S8 | ff7ee89f6fa0ffafdcf76fbf601e1736a34c6f262f692993088609bf1e57ad90 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 9 | S9 | ce28fc790d2b2562b54fe13ba112ff04fe89b68c04cf21fb75858b469891cb13 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 10 | S10 | ddcc617438fa328e0574a8941055ecde4150c8640e0f0e2eb17a37304a6a4a45 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 11 | S11 | d2a4881a0989914301f46dd1c9a6c56de9eb79ab59461fea760d75e784df52da | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 12 | S12 | 6b8c5c80f0e6b25a5851a6d4bcc55bb7be96def69c6adfa69ffce584193da396 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 13 | S13 | 67416af410b13741bf4ff8891f1c9daf8bee4bc9f1d114ed5f87cb1f3994c89b | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 14 | S14 | 137feb794ac2bfcb35ac33cf8f38726c1fa1be46a12182fb95667c247a69111b | MEASURED | False | 0 | 1 | 2 | 0.5 |
| virtualhome-agent-planning | 15 | S15 / final | 9cfdf5b2c799dd8665c5facf2699489a70e17bb7d11cb44e33101c37bb552527 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| weighted-gdp-calc | 0 | S0 | 88f54ce629f0560c3f8c6c13451f5a7dbe0d1cf9d532e821d37b0b4b82e98b29 | MEASURED | False | 0 | 15 | 27 | 0.555556 |
| weighted-gdp-calc | 1 | S1 / final | 4e0899dcbec0e49368aa83053bf9c2a65bf4c36bb989ade5294a9a20ebad4bb6 | MEASURED | False | 0 | 15 | 27 | 0.555556 |
| xlsx-recover-data | 0 | S0 | 20607bc31ebb37472acaba2ae4f9586133b8a1770c416c32e5b7b11fd37487cd | MEASURED | True | 1 | 8 | 8 | 1 |
| xlsx-recover-data | 1 | S1 / final | 581c002f98e88bb436e651ed8eaa6f97107457f6ed484655f9b60a952db1a963 | MEASURED | True | 1 | 8 | 8 | 1 |

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 620fe576171a8e6d6f4ed5e4a3fa62aebc9b9f1a937fef0dca99dee9005022d6 | 0 | 27bf164c5f686a70ad7ffafe3d75b85607bc1a8391bd0fb974a9c6cc9a3fc2f4 | False | 0 | NOT_MEASURED |
| 3d-scan-calc | 881af1fee74318a26631ce03146162d7aaac0e2340c7e5b2f6552da1dbce820e | 0 | 27bf164c5f686a70ad7ffafe3d75b85607bc1a8391bd0fb974a9c6cc9a3fc2f4 | False | 0 | verifier_reported_test_program_error |
| adaptive-cruise-control | b3283e71f6c86a3f93bf0f21534a3704f428da286bb7664a224e6cc646073b3e | 0 | d7ed543072dfb68a1fe5f93080cf75cda4dce2ef6b86539453dad2c98e017b53 | False | 0.4 | NOT_MEASURED |
| adaptive-cruise-control | 42c584041865309b926e287d3ac82730b4d1891a8fcbdbc0b81a70ae9cfb8a95 | 0 | d7ed543072dfb68a1fe5f93080cf75cda4dce2ef6b86539453dad2c98e017b53 | False | 0.8 | verifier_reported_test_program_error |
| azure-bgp-oscillation-route-leak | 3c25629b743fb4ce99399c137cab86fb1eff2a5bde0913673b2431c669cb7ab8 | 0 | 17f21610e8d9494ee05b396989ca7c19c028873f59819be5de9ba1a57aa325c0 | False | 0.333333 | NOT_MEASURED |
| azure-bgp-oscillation-route-leak | 84353fb558720a9ea107804ff4fa971a93122cd93c64d8051fc3b251d2a1619c | 0 | 17f21610e8d9494ee05b396989ca7c19c028873f59819be5de9ba1a57aa325c0 | False | 0.333333 | verifier_reported_test_program_error |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 0 | f8d2b80898102e71b15dda1851fe4b7150249115a8e458628af5e4dd4a549e25 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 1 | 12c2fb0cf9dc7bf0d64a7e26b94895fc9b66662b22db14b9421d0f99b03d6ca2 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 2 | 421945c17a62b2784320fc4ce1323345d7b0868f53f2614ef094ffe256f3c1a2 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 3 | 630f3626261349299ec2ffaa103b7383758dc49cd679e8b2468c6a459a38e787 | True | 1 | NOT_MEASURED |
| citation-check | 4fcad953fd32d0b1a3e24b4350fcdf310c928496b79161df0338f3f553f51c0e | 4 | 17f4825071e787106794c6fd751c38a70993f7d0185faddd0aa240e55ce6be91 | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | 5553905f8c504e208ab24b39a8354c46e681788cf4b9fc6ae0b603ffac8150be | 0 | 245c0ca297703d9c2ec1ec2a9c36c9c9d84e8f4a0a98cc2b9b1d97840b76dfcf | False | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | f9dcbed081bd62417f2599dbd657ce451a51a3d7f69bf3b67b833f5a2511860b | 0 | 245c0ca297703d9c2ec1ec2a9c36c9c9d84e8f4a0a98cc2b9b1d97840b76dfcf | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | f9dcbed081bd62417f2599dbd657ce451a51a3d7f69bf3b67b833f5a2511860b | 1 | 1462aafae8d86ca177eb99232b21b00e541b4662bb205dd1e86a7168cfbe4b4e | False | 0.666667 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 1 | 1462aafae8d86ca177eb99232b21b00e541b4662bb205dd1e86a7168cfbe4b4e | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 2 | f0977f81c99470856bb4373bbe72a21e0860797e9862a2f1f525c04d970773c5 | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 3 | ef8c616f3291bb47fb622bab4abd84d82c9da6c350b2805e398093b4666072df | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 4 | e59d5c0bb7c565b160df3fa9bf507521472d7901f8c5e0d6c27259cccae283d9 | True | 1 | NOT_MEASURED |
| court-form-filling | 5996be3695a051917ec707cb87ed570f1f8dbf417a316927dd352f4a1078c79d | 0 | 24329a764dd8ac016d1dbc114f4a59d57611b6ec81b135cb6902412fb148a52b | False | 0.6 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | 5b3bf7eda064a0f0582ea359e21e480c9af4487e525aadfc55d686362cb2c72e | 0 | 1231eeae24510c8dc3218ab3d4d4e053cc10e43fbda32aece9012648049a10ac | False | 0 | test_program_error |
| dapt-intrusion-detection | e9b42c625e33df3052e917d2b883cf41fed9732dba540ce4c02bcc1fe4688ac1 | 0 | 84db098bd8d6bb074ffe1cef9476e703732aa3aa8e0d98b92386d077e1081b2d | True | 1 | NOT_MEASURED |
| data-to-d3 | bc87ee4ec9408668d117e6de0ced432065ea7d163e477d244f9e586f1945b3c7 | 0 | 40595ac1b15311983f9c9be4a9e32e7233023d25f943d66da7a6daf9fb44e24f | False | 0.857143 | NOT_MEASURED |
| data-to-d3 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | 0 | 40595ac1b15311983f9c9be4a9e32e7233023d25f943d66da7a6daf9fb44e24f | True | 1 | NOT_MEASURED |
| data-to-d3 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | 1 | ecb4ea62acf9333e32310b33e79f0906cf32070f0791c0f8ea8e01db2c5a94d0 | True | 1 | NOT_MEASURED |
| data-to-d3 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | 2 | 5d0a9a452e05d8351c72fd4de4ebf2202bb8af414ea48c7537d2af8406137dae | False | 0.933333 | NOT_MEASURED |
| data-to-d3 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | 2 | 5d0a9a452e05d8351c72fd4de4ebf2202bb8af414ea48c7537d2af8406137dae | True | 1 | NOT_MEASURED |
| data-to-d3 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | 3 | 0e56586d913596ebb31876b0b7fc0b12551bcd7b8ac84f219e88b548f23b52c3 | True | 1 | NOT_MEASURED |
| data-to-d3 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | 4 | 73d87cdd9d1853439841126c6b4928605e03f1a13b8376a32296f5c45d2ca670 | True | 1 | NOT_MEASURED |
| dialogue-parser | e0f6b26461bfae15f57294363012112a54a6bb90e882288156e6030eedafa37c | 0 | 67337b5e992b89c084e05335dbd970b5fa090a56aa6f883da006d65625edd2d8 | False | 0 | NOT_MEASURED |
| dialogue-parser | 403fc0d8f4566414b6d7dc0d79186e740f6dc19c2ee255aa03b4c6537c6cb8e8 | 0 | 67337b5e992b89c084e05335dbd970b5fa090a56aa6f883da006d65625edd2d8 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 51dd9315930811cf1d93c722202a0c98da6ef9f072fb7a57df71c8a4a8e7585d | 0 | ba0c2fea64259b20ba7a1326d764fc6edea196b35175ed7f50f23ecebb429f8f | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 51dd9315930811cf1d93c722202a0c98da6ef9f072fb7a57df71c8a4a8e7585d | 1 | 1ea0ea150d455e87344e0f6fe1a7697d7f08ff5be262753e1354f603456f5564 | False | 0.8 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 1 | 1ea0ea150d455e87344e0f6fe1a7697d7f08ff5be262753e1354f603456f5564 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 2 | 9046381c72bd4a5b716959c7e310c3edcaf703bdd4b96e9bc872a402aad52cbd | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 3 | a59801a086a39517c5b701ce5c6ee8be283d290752fb8a7360184823e484d472 | True | 1 | NOT_MEASURED |
| dynamic-object-aware-egomotion | 8b3eb5cbff9a49e20bd44dc0d364401721688b8a924b7f1bd7f8b42eb40946b9 | 4 | 21c4beca896ae971e844882eb9b9f6b2c1fec75eadc5433302391df6d3600223 | True | 1 | NOT_MEASURED |
| earthquake-plate-calculation | 0216041dfc3facb34a22c5dc4f490c8cf3d1646d9fc89fc4f5e7f3e952e8c791 | 0 | b239fef387872e9a84df88811bffa34a5ce951e06a1e8789d2b0430822bb7324 | True | 1 | NOT_MEASURED |
| econ-detrending-correlation | ff5dd1eb7a51acf7c1ac2e55035cd12ea0eae426b675b91fce507fb8cf4ac6a6 | 0 | 0311ab71ed6ead07052f234652de1971f652430ed93ca7dc9b2017c6218baf60 | True | 1 | NOT_MEASURED |
| energy-market-pricing | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 | 0 | 0b8eaaab326c2e4b5339874ad4373ba31660eb36632464f3a2a40f9d22e7addf | True | 1 | NOT_MEASURED |
| energy-market-pricing | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 | 1 | 7338931bfed41103a8add0971a84293ab5209ac8b7bc62da13f925d7b8fbb6e9 | True | 1 | NOT_MEASURED |
| enterprise-information-search | b8294f303c6a45b4e7549c51cb6fc1cb0a584fb43e4018783f99402528539bd8 | 0 | 79eb11466e5033d42bb2a79ca7165a863d757e0734bb3be3181c3e9e83753451 | True | 1 | NOT_MEASURED |
| exceltable-in-ppt | a63689dfa675df3f5591be97d3b3c2a8cf3191bf2f23c9c88eedc7923d0b388c | 0 | c3cd66a0c65eb8032034c664424807ce0fb962e3997b7cc5ceeaa9d286f825ce | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | 65288ec9fc226174d9564e2a9b9a6f24c373ba43bfd5ba83c894b5d2261da9bb | 0 | ad0aa9326e2afef562fdf4c9a384fcf7ea1a25a1493cda9bd59b8405049694bd | False | 0.5 | NOT_MEASURED |
| exoplanet-detection-period | 48f5d135f5b9ac7e847133660c959723edb7dc2b56ffba57bf3acc7c653a1d2d | 0 | ad0aa9326e2afef562fdf4c9a384fcf7ea1a25a1493cda9bd59b8405049694bd | True | 1 | NOT_MEASURED |
| exoplanet-detection-period | 48f5d135f5b9ac7e847133660c959723edb7dc2b56ffba57bf3acc7c653a1d2d | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.5 | NOT_MEASURED |
| exoplanet-detection-period | dc61c509ec5178be4dc0b286d9f6340a1829cb086abda7f053da553cfdf8195e | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | e43ab94a34dd24fc9b3e296309dda2420f9b7e2307d767cec54ab90560eea34d | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.5 | NOT_MEASURED |
| exoplanet-detection-period | a7fdc1b7c7670ec0d82d425299638145d2333a01905a5ace9167f8744eaac210 | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | 658022166d063df7a4ed92d6c9cedc4db2fcfcb53c9b6252f9cb49d0f21506d6 | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | cfd0bf287f3fa2efd7017eb2b8240d5b87843c7a8d389aa0f4cc32b4567b5cbb | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.5 | NOT_MEASURED |
| exoplanet-detection-period | 46d47dae1a748860a1662b51cacfcd0908560ff1bfe3c814cbcd4b325c69e6b3 | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | 1a920b196019b87835b9f9fabb3b13a10a01f23af78a461338c859dd862f9ecc | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.75 | NOT_MEASURED |
| exoplanet-detection-period | 8a55462a08e0ef21b98ff1f14f5c38a979bc98abc129f3f712e21ae2e2939535 | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.25 | NOT_MEASURED |
| exoplanet-detection-period | 5872091c8e3088883d957d490050cbd17d0749af5e3e4d93a3d9694bf9401237 | 1 | a01adf5b4e93a521072941ff929d3cb7488ac5fa4b608531f42469b905cb1eff | False | 0.75 | verifier_reported_test_program_error |
| financial-modeling-qa | 98b7ce8203742a09455af33b9b796809ce965cefe8e9885e607da55689daba89 | 0 | 9aad2faeee47e8e85694b712a759477288e8e3ded825dcbdd864ae99b548a53c | False | 0.5 | NOT_MEASURED |
| financial-modeling-qa | ac585c8f595254531b821c7df01cd3109a71077d3e07322a52bf1384bff4e938 | 0 | 9aad2faeee47e8e85694b712a759477288e8e3ded825dcbdd864ae99b548a53c | False | 0.5 | verifier_reported_test_program_error |
| find-topk-similiar-chemicals | 729633b70577338a0f265f8285f8e5baaae22f80049879adde0e3f906cf3df54 | 0 | 69311479af7590d65cab4a64662211378ea247490d770b668ceef540a73e7879 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | 52639d1c25caa8f7ebcfdf5298257550dfcf444c875154bb8c616954f9eb2ca8 | 0 | ba279c77f330856bc0acbc4a1407cc1aa5fd0fee51ab48a3179adeb4012050f8 | False | 0 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 0 | ba279c77f330856bc0acbc4a1407cc1aa5fd0fee51ab48a3179adeb4012050f8 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 1 | 3cb9f3dcba467ada7a3e0e6288128474670f8c0af20269c90e0c13812803db52 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 2 | 5c7e5183dda0e1e4f89b83279c642f029ef4a3b74d0f89a1297ba1817a5d691d | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 3 | c3b4f03d12de98c5512b583b812022151e39950e8a850d9cadc0cde235c43fbe | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 4 | cd720ceea66215659bb4ca14088fc16695c3a91c302c1599b253968a592a5785 | True | 1 | NOT_MEASURED |
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
| gravitational-wave-detection | cd96d1a1ffaaf5734583599d48924523d347981cc261b0c2a4e2d9a8394dfc7e | 0 | 5bdbc213eb35cb597c05073bce09fdfe44ce0975e8ed04cb5499502624b57b0b | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 8ce1e1ce259e1fac9732a4355b4bed05cef818de4097e243be26bab1487c5387 | 0 | e914e257a638ea0767c20d628a8df9e65ca03cd0c486d746734f2b09cb1635c6 | False | 0 | NOT_MEASURED |
| grid-dispatch-operator | 7b479b3d1a7b01b58af81be3287a105b6650d00d429952d3fa2f4fb8c5d18db0 | 0 | e914e257a638ea0767c20d628a8df9e65ca03cd0c486d746734f2b09cb1635c6 | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 7b479b3d1a7b01b58af81be3287a105b6650d00d429952d3fa2f4fb8c5d18db0 | 1 | dc54f94dd3d91a5adb55e1ab1b20c91e4031d4eaceb4bb579f7e3f289ef88e2e | True | 1 | NOT_MEASURED |
| grid-dispatch-operator | 7b479b3d1a7b01b58af81be3287a105b6650d00d429952d3fa2f4fb8c5d18db0 | 2 | bae085fb108e784647ac45ce845eeeef8ae62ec9af5bcf872d4d91dfa85950ae | False | 0.6 | test_program_error |
| hvac-control | 3663eecec608f6ff5671f76925f33ef0727e76b98663b8b4b4c1ad1a5e7fe628 | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | False | 0 | NOT_MEASURED |
| hvac-control | 406a06c08ffdf47437615842871c8579277b573ee78813e1f3c28899ff8904c9 | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | False | 0 | NOT_MEASURED |
| hvac-control | 3ccf5a06f69b782c619eb2bfb448f8872c281de113e8d8c9a39496bea4626ed4 | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | False | 0 | NOT_MEASURED |
| hvac-control | 09f4be2bbc2845f188862b36bb201441e9d600263053fa837f2b895924b04cb6 | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | False | 0 | NOT_MEASURED |
| hvac-control | 9ff13e6ae8ddf5ac20c3915bec8136ed0e66e93937d733e7ca79087cc1d328c2 | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | False | 0 | NOT_MEASURED |
| hvac-control | 15a4754c0517d763cc1b79e3a3e17a65572ff435b2aa8b4bc0c24d77c7fdbfc2 | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | False | 0 | NOT_MEASURED |
| hvac-control | 139fc1343d63b3669b6db3ca1427ce49205084f36efabc64676727ecb69c873b | 0 | e86adbdcb6b443a28fd069c8419515acb76161afea95048ddbd485aa471aeb8e | True | 1 | NOT_MEASURED |
| hvac-control | 139fc1343d63b3669b6db3ca1427ce49205084f36efabc64676727ecb69c873b | 1 | 784ca14029fe68b092ed0ffc33e2efa8f1326e9e62fe3cf9ba2e7e6ace89ef75 | False | 0 | NOT_MEASURED |
| hvac-control | bdfd78fcddd35499509d0a1e4f0c9fcaf39d078b751e3708cced102b78b9bf06 | 1 | 784ca14029fe68b092ed0ffc33e2efa8f1326e9e62fe3cf9ba2e7e6ace89ef75 | True | 1 | NOT_MEASURED |
| hvac-control | bdfd78fcddd35499509d0a1e4f0c9fcaf39d078b751e3708cced102b78b9bf06 | 2 | d03e59c78e5a97933a6b353c62ab4a4ea4304b9e0d522132d9b3f449cf8df4b1 | True | 1 | NOT_MEASURED |
| hvac-control | bdfd78fcddd35499509d0a1e4f0c9fcaf39d078b751e3708cced102b78b9bf06 | 3 | 5420dc66eb82489abf169c0bac494a436891169c655017f287eeac0aff95bded | False | 0.111111 | NOT_MEASURED |
| hvac-control | d8889ed785a05a08ddfd8d1fbbf2824c6c441e5034210cde60b890cf1debc1bf | 3 | 5420dc66eb82489abf169c0bac494a436891169c655017f287eeac0aff95bded | False | 0.111111 | NOT_MEASURED |
| hvac-control | 48cfeaf47e518703319f9861b592268cff9f5f2bc49629006b264a3d3eb729ad | 3 | 5420dc66eb82489abf169c0bac494a436891169c655017f287eeac0aff95bded | False | 0.111111 | NOT_MEASURED |
| hvac-control | b235b16f70787c45dc201a9f205d78ec511a01c4698bf55fbfce7bbf127aff14 | 3 | 5420dc66eb82489abf169c0bac494a436891169c655017f287eeac0aff95bded | True | 1 | NOT_MEASURED |
| invoice-fraud-detection | 7cca4b5d880d7d99c5b46f261216fb50281c5580f196a0a38ac5e3283d7b93f0 | 0 | 81626aea26cb4d551539c7efe351195b2c66f12da0abf0d3e83795b67b5bf443 | False | 0 | NOT_MEASURED |
| invoice-fraud-detection | b050cd48e09673ca7174db69763cb2b8641f3ce877176e9a135c25bea94f7fa6 | 0 | 81626aea26cb4d551539c7efe351195b2c66f12da0abf0d3e83795b67b5bf443 | False | 0 | verifier_reported_test_program_error |
| jax-computing-basics | 2dd15e30ae902684ab78820e2ccf0e6b31c0e1b753379a7d5cdf0c8cf7d251de | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | d76cbe2023fceb1caf8fbae41859c82a8c08f118b0227753e9a976542326874e | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | d06372602edfa9347126f59b125978b4ff803919f1410100358443b57b9d99b3 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | a077870f821757280ae619e18e50bd3a0aa03be6df21d7ac417963bc27761269 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 51156d9414755ce6774d912a42d947381480d646d8f98a8ad03d0fb79451c719 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 21c52b6598770941d09ebf4e5b7f61f137ce27b16a6a03c6c927b89465d4b981 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 0d978a86aec0676673badb634914d70b23f1f8484d728eaae5b61c5242ac9fbe | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 9a1be981ebe6369317bdea86b9626a1b0a896a942803f7472dcc66cebfe5ed5f | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 36e37bf7f582f2cc9ea7c88097116ba6279a61c00ad48ef0f98f643330a99fc0 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 0975d55b5025d8b190eac5ddf0a22b18796dcb0ab6a841f4b1394beb881ab1f6 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | fc269f39f0b6afb8ef3afe74e51836535597ae159afce78511a8d63c3be7210a | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 67327985a91208fd33030023ac31c81f35ce0e38375ec91587ac37bb4afee9e0 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | afea4af9268398ba93bcfec47ffb89a0faaa0237dbd60bd042a05c7b27349d71 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | d6924a8eda633c8284b399eaa8ae85391411671bcc5b955e62a27e3490379265 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 8d85f3e1b73c2bbe5b2c2bb900bbe8e7b9b4bb21e1d32c7838915b9ee6c6bf41 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
| jax-computing-basics | 3a86d4b45841bb55a02742464cf48e046fca8f48b1a11549237e10f0670e7648 | 0 | 2cdabe6c266eb1592b7886b5a581c782306402f58ef9f70eb5be1df6cd8fb296 | False | 0.5 | NOT_MEASURED |
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
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 0 | 8e287eaca8df123a398f1af4bcdf97864993567290edfc4d16f57f5e1e4e10e9 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 1 | d057178f59c3edd4e24aa59503d82918b09f06899ee799bedc5d865f20e32563 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 2 | 9d90ca6606f707c8ae3512ec4cefa420627ba20a1946b523709db17d50c94da9 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 3 | 137958bcb1ac182c74aa4536d5b4decebefe9a359e91b0d51ce19ed22ed2a273 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 4 | 9aaebab5e4152c532471c374c3068e57e612f88c7e7fae833fd7a0505e5ea721 | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | 0fc7f16b51b98904e87881ffeadeea001d071a0d5d56408bf31815d1ace1cace | 0 | 7792463ae7e280c407e8be38c54cbff27e890bd255e07cfdb9285f36d9bc0c6c | True | 1 | NOT_MEASURED |
| manufacturing-equipment-maintenance | 764f343771dc6bf60579278fed9d359ea921be48fb70951199702182d9d9c775 | 0 | 05a5331a59b4712fba0866319d8ef1b53d204a75b5564ea0f03be4e5fd9c018b | False | 0.666667 | test_program_error |
| manufacturing-fjsp-optimization | 98c483de4d362a175571f6f6da96f817e453b95b0a51d89bb58eaa3b39c0f995 | 0 | 88d8c80f5d76e0ddd82f3f10389aa8fad5800491ed3b8249606a9ec5127f04f1 | False | 0 | test_program_error |
| mario-coin-counting | 07c807340d950b14e41865b53cfe466ae481fcc9dac2346672972813e926299c | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 912ceff096ec283b9196056556f80936c4653c8b34afe1e4debf4b13644c1728 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | c6c636badbf4959c9c2691e46cfe8be095118fd669f182d454429c09abdc57a5 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | d802ecd2f2ae6f636a79b5f192adf86682fd5bee7ace38c307a2ccc4037f7786 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 1fa22691818d800a0c92b6bfcb4e45365e795598d9cf2d89be5eb1190219526e | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 1cd05155f96d28ac41c1eaa4c3a7af998c3bbbd540d28cc0306edc6d5a70400f | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 242b59576b4fadd869d8398fefb65af393990485c8aef297eb24f66245264cec | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 5c9909dd6b7acc85b67adeae29c64507e7c5c620c1f2e42f16fe20fb1e7daeb4 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | c2b087cd0f50278361e3cd3f505d43a50aaad00a98f71b3e0bb8b0bc3969fc0f | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 28db97084124046a4caee24148ffef3c19541babaefd02634b133c984dc2b77d | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | eaae14cb200d413b959a977b4c60c623effc10e6276a030636239f0e6974bcf5 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | eacd7a85f6cff5cbdda4c7dd550c39eae662e3ec58875e8a638711646578810b | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 8239f0a4b63d17b4a100f4130b044b8fa634a6ead00affe7beb24e3c63cd2c1d | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 5b8a6cdd0d56142704937d08a3f5774dffeb130de068ac03c360900ad8f78564 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 12951082bd9e57af53ba3eda54ac0ecc106c777954080c53988c349292be8655 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mario-coin-counting | 212196e5d4ed41dab1666dbbb27f67eee8562db54ae77e21616a8997e4ef6838 | 0 | d85cf6db5299e6c8b7400c6009dfb559b0378bda628200daeffb737878fee1cd | False | 0 | NOT_MEASURED |
| mars-clouds-clustering | 93f4ddbafd7036ca603a0c10a3ea60b2c672412ad4382726acd522306cc0bc30 | 0 | ea0e4b3f70f8463b7bd451a4eb038bd528d03394526fc5924dc62b65dbe63044 | True | 1 | NOT_MEASURED |
| multilingual-video-dubbing | 54bf0060649fc88cb41f10d16edd84b686fdc400ac528e4f159d38fc2f9a44f0 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | f4523d21f6ca19c86b859b155403a5946784a94d7d9997508204418b8901fda7 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 189759eabf9b7b92f1ad925144d01902be373d0713a3f94ec534b83212213331 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 071c9f45d5b8783bf5f0928f98ab8886dbf7018728e3948e1429ebd18688d29f | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 000129680d2ea7c95581ba48f2344b446f0d356453508b1944a251002ff10b2d | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | cf0fb6ffa6ba6d03e2665c8efd04e97468d3a9947a9ed91365a6f4517a07db40 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 1cf3f12e955c2ee20f3359f61dc7f9c5db771da4e79a81bcbbac4a735cc7daf7 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | c60bb1ebfa3519d922b4f217f15f16d304d787e88184380dd0b6a630b18e4f21 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | b84da01d29233ded6ce14df03846b050a4bf78459f660fe89323b24dedb17109 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | b6109341c6cb1182d015824e5021db22f4f30dce53f9a6757ce22c0efef3c207 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 4ec3a2003ff4202628811380d2a969640a9397a83ead82a629506764d1d140b8 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 1595a4ac3785062859f3d8815e5d85660d763fe67671522068636912f59a6e39 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | bdfbdfc0dd3e5e2febf491b6549a6a28b6ab3679bc842369b2ea22f56854ec53 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 00e0a7060edd07d7ffd4bd2d2df8d34e686e756cbbafdce2802181cd665c16fb | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 1ba1982505c749f89797bcc31fbf24945da2b7974c49f28c9215eaea6e71453d | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 3c584784b413a041de82416805daf7449a46cd2b595a12841823a955511daee2 | 0 | bac43c561ce1d305f4b6eefc2f6614c6c769d57a5b9f598b3eaabf6b880fdffc | False | 0 | NOT_MEASURED |
| offer-letter-generator | b88ef1cf3fec5ad48b78b803cdef728220deb8d57c125ead7fde78aa9c966c58 | 0 | 44e70148d47f0083053fb14fe47afacf6b7af8e685c9ec662fbb6e151aa697e5 | True | 1 | NOT_MEASURED |
| organize-messy-files | cacae0885f711115c4478e4bcdec6285e5acafb70799fcdefcfbc5dbb42b5d66 | 0 | 1b9aefb09f2b64e98326bea059202bfa9fd5834a4c9af3003f0aa2ec5875c8f9 | False | 0 | incomplete_test_report |
| paper-anonymizer | 4a90ccf0caa81569dc8879ca12511a9a64d1cde9be3d27d6443ede3fec3c690b | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | 0ce58f34bdfcf12f5bf1be6414f06ddc71dfcb41fdc9ef7e74d510a6e6d8afa1 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | f70b1d42b89f16d74eb57ece0088fbe13bf5d68cac742896241b0ee0b2410586 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | d4e2297dce786b9a4e672978a0c29a354863d5d454c5c8501878625389bad75b | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | ff5139fdf9edf9a233f9c9edfa1ee9313610b478e1d6b676cc28bce83af3bf6f | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | 3dabdf5e1b0efa880b94fdefd2a1cb7cd8e7107d6990bea47d4a1072c6c5c49c | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | 7ee1bd2a9720426a5bd99b8d9ac2678083c4f3fb986641575574ef68f2c37269 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | be022810cd05b8e417a32e941577ee51edbe927cd3695fd6a1b7e8a932bbfa18 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | f39294ac5248b24636d08b31718d22fa27a949af438c8e36173a973f584f48e9 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | 73b0138ecf88343a888869ac7ad942ced8305f360e42f91f27271aa902339304 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | ceefab2a1ef2805911ba26deb5d9d4899df6ebf9bf0da209ac80cb307d8c597f | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | cc6a208a2377924a18e114e5284559dd0b1c1ea7b564c8e8808c1f092df9154a | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | d42a48eaa3c2cacbc5cbd258eaf3ff0f88de6c816cc622d6a532aeebe1c1a285 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | 6137a47218d71885eee0554100a1d6d665fa9ad8c978471705bb67bb60dbd676 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | d3db4184bce061d68eddcee384fdcfab461841fd429b27e64d4c57a8cfd4b85c | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| paper-anonymizer | f620b65635c8d0d5aa87cb7688a0a139b2256545861f9dcfa3ed38309e549840 | 0 | e37c939a809182bc1f18e7406ec835109653fd86f98a57f19eab656e3b077bbc | False | 0 | NOT_MEASURED |
| parallel-tfidf-search | c3d9491cb6b09fb77e075202ae6f8ed8d08565b0426a43dc54e86fa149eebe4a | 0 | f9b252e994fb9da3d15f8e25c0a94a453529fe1f88b1ab4c7d5b55ede8d23e59 | False | 0 | test_program_error |
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
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 0 | ca95a6e6fcf842fdcd685a703f7199ee05f52b4674fd88b2a2e1f0670c097ebe | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 1 | cb1e5fe91d550a22f4869f9bef2ac394b357cc3c9dca1f0a7356b332d5b903d9 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 2 | 19f8440cef1647e75e98968b0a2415f55fc0e60f925bd882ec09907625a0b693 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 3 | 5ae4d544f79b6f701cb9239eb6e3b40c7aded8dd526cfedcec56fa2b756f75e9 | True | 1 | NOT_MEASURED |
| pg-essay-to-audiobook | e42184e8ba74a7f6428624e3d77ffda35458009b071b220f9ad8b2e3c179d13c | 0 | 938c3dc44cc2ad4b66d7c9cf644bd05292bad5db5baca1c6bb47bee5eef5a73e | False | 0 | test_program_error |
| powerlifting-coef-calc | e4fd00e7635033ac7196bcd594c105cdab37793ab6ea3ef784b5d2cb3c222705 | 0 | 800a0b65a6be7dc0037559616a84a4dcf9feeba7d59965e055c64e277aaa0afe | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 193c96607959e2f4c7093b5972beddb066fefd304bcc8152c07f8110bcccaaa4 | 0 | 06f810b7796f3777a45bb960c90428b9985ce6948899484cf350fd023e925e81 | False | 0.333333 | NOT_MEASURED |
| pptx-reference-formatting | 3065a4d8650ced84944c61a2e8ddb8a710f7d57080cec50893fdfd6f4ed8b023 | 0 | 06f810b7796f3777a45bb960c90428b9985ce6948899484cf350fd023e925e81 | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 3065a4d8650ced84944c61a2e8ddb8a710f7d57080cec50893fdfd6f4ed8b023 | 1 | 9cc0228dc08ee89d898f062b02a08598434bc4d5eea20f695321466052a90d03 | False | 0.666667 | NOT_MEASURED |
| pptx-reference-formatting | e9487acd4927e01c61fc51c08ece68637c9457d457020719d5298709a463e7a6 | 1 | 6c4e6df66426bd103a2cdfe6eb41f569088bb6175461ed56eddd6ba1b214ae0d | False | 0.833333 | NOT_MEASURED |
| pptx-reference-formatting | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf | 1 | 6c4e6df66426bd103a2cdfe6eb41f569088bb6175461ed56eddd6ba1b214ae0d | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf | 2 | 257b33011e65008aa853153eee604198493a483e4ef686f77a976a39c32b381c | False | 0 | test_program_error |
| protein-expression-analysis | f85f675b623d849d009a360aca48214a1ee273b90a02f7877ed2bfe81f882cb0 | 0 | 445365f1dd0b702a8f0baf206f2591d8646563223e7b9bdfd05ad01ffc077625 | False | 0.25 | NOT_MEASURED |
| protein-expression-analysis | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | 0 | 445365f1dd0b702a8f0baf206f2591d8646563223e7b9bdfd05ad01ffc077625 | True | 1 | NOT_MEASURED |
| protein-expression-analysis | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | 1 | 90d506789a528a2907362907a5a8d4e6778ec07f2e4c49447f0b3a7882ba4e8c | True | 1 | NOT_MEASURED |
| protein-expression-analysis | a9eafa8f19afb1a91701c681e42969c5f7d205843f1bab6ef064555458c08462 | 2 | 2430678ba9449bdb7dc173b37ba1eaba75caab56b4f3383fa0037c4612d1dc14 | False | 0.857143 | NOT_MEASURED |
| protein-expression-analysis | bee995358c90d6c33940013b7bf6d862fdb877604ec3f9a58856af8bdaa4dae6 | 2 | 2430678ba9449bdb7dc173b37ba1eaba75caab56b4f3383fa0037c4612d1dc14 | False | 0.857143 | verifier_reported_test_program_error |
| python-scala-translation | 68fbcfd02f5dd1659dcc82d043f82cfe8c3dbb09fb3c26cd43e9740845e66efc | 0 | 12670f8b00f0ad5b84879cbdd7d3e648d5efc3e384a8cc43cc2035557bc516fb | False | 0.666667 | NOT_MEASURED |
| python-scala-translation | 851a2a5b34fecbb902d4dbe9b99c7930955cfb744ffe675dbfce041a9db8d67e | 0 | 12670f8b00f0ad5b84879cbdd7d3e648d5efc3e384a8cc43cc2035557bc516fb | False | 0.666667 | NOT_MEASURED |
| python-scala-translation | 584cfcda19675ea1e62c769e4ced10d71dcbc543be11a0a4f4371017df9d6ca6 | 0 | 12670f8b00f0ad5b84879cbdd7d3e648d5efc3e384a8cc43cc2035557bc516fb | True | 1 | NOT_MEASURED |
| quantum-numerical-simulation | 42ae9edfe8e9722839712c2f5a107271dd647310ce1ecdaaf4ba07277687dc7a | 0 | 869d5d41e604d3d1adff1c6fcc52526636b5314e721c2e3d53f98ca77e1376cf | True | 1 | NOT_MEASURED |
| r2r-mpc-control | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 | 0 | 971e23d0167d817eeca6fea08f770f1dc3bdce1edf43179feef41ab385aa0405 | True | 1 | NOT_MEASURED |
| r2r-mpc-control | 9854543da556b9c3d496b70a4342925be6617ccc90414e5738b32185fdf648d4 | 1 | d4db7f45726984450dc552be98e6f0b031830ec47a713d9414706970bf7308c1 | True | 1 | NOT_MEASURED |
| reserves-at-risk-calc | 849638183ab52285cc6bc2e69085f3d1099651ce9dc19823f4d31fad751a597e | 0 | effb030bd914702e2806b3445969f2e10fb405164a140097192e875b28eb29d8 | False | 0 | incomplete_test_report |
| sales-pivot-analysis | 3a41dbfaf5743fa05dc9d988b77b90fc8b1f13c6aa35e7dcf4fb15bfe61a83b7 | 0 | 59695039e358273f32e34e8d8e617c136c062d464c4cb4d3cda3e75f1e44b53b | False | 0.333333 | NOT_MEASURED |
| sales-pivot-analysis | ab69736cd9864fbb9b80ec18e9dcb711aed1a0f0a4722814c6ec19813efed7e0 | 0 | 59695039e358273f32e34e8d8e617c136c062d464c4cb4d3cda3e75f1e44b53b | False | 0.666667 | verifier_reported_test_program_error |
| sec-financial-report | 5e13dee0d4ea02852837afe17fa596f148bc35a16d47882a0ab56c0520e27660 | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0.5 | NOT_MEASURED |
| sec-financial-report | 549caf0e1b330eb55f052ccaf300fc7db0338b24657917ba96a6ef48c805da99 | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0.5 | NOT_MEASURED |
| sec-financial-report | 8b22df93b475a331fe2e3d0d86861548f3cc216432ad0fa0d380fd3ed7f2a91b | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0 | NOT_MEASURED |
| sec-financial-report | 8ab2820acce4c0137315e6f6f09d9109e317b709ef77652ab874121b2997f2ec | 0 | 6babb295c3adac3aae9c0f3d4c7456d85e2c120a49c09fe221297d59381b1e00 | False | 0.5 | verifier_reported_test_program_error |
| shock-analysis-demand | 3c834b2bc3710640db9ba0a175336ae56613c930a0975bb2a284864b97b06b11 | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | False | 0.166667 | NOT_MEASURED |
| shock-analysis-demand | 3b4ffafec439eec7220371e85d3a274ed72d177766d5a6cd93a47c1db06607be | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | False | 0.166667 | NOT_MEASURED |
| shock-analysis-demand | 53649039b3d2da2c4283700b521916ce078aee2c38d817998e62dddaccd6c2a7 | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | False | 0.166667 | NOT_MEASURED |
| shock-analysis-demand | fcdff7ff87e285019a8e9d684242f3f6ddab4a4049747cfe9bd3460ab27cfbfd | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | False | 0.166667 | NOT_MEASURED |
| shock-analysis-demand | fa34cc3e401a23585405c098fe7dd7ac35190ae9c3b2b106c030aff72e2631e5 | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | False | 0.166667 | NOT_MEASURED |
| shock-analysis-demand | 71ac6b463a55b1f603b2b977da3293aacacd08220fe42dcadc2baadce06e12ca | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | False | 0.166667 | NOT_MEASURED |
| shock-analysis-demand | c9e644968c346ba42ff4fd60662e13210cae0c58abe087615bdca0fd64afcd7f | 0 | 06e706264796368c2cb8811e003c20d83aafc9b514bcb21399b61b92cdbe9636 | True | 1 | NOT_MEASURED |
| shock-analysis-demand | c9e644968c346ba42ff4fd60662e13210cae0c58abe087615bdca0fd64afcd7f | 1 | 8724e7f345d1ae057ea86f240cfa897e234a6ddde305092bd8f4a8e14a3f04f2 | False | 0.777778 | NOT_MEASURED |
| shock-analysis-demand | 52ae5accd21327d4032f5f1ccd51fbfe39ef5ceb74dd675767f2359b758beebb | 1 | 8724e7f345d1ae057ea86f240cfa897e234a6ddde305092bd8f4a8e14a3f04f2 | True | 1 | NOT_MEASURED |
| shock-analysis-demand | 52ae5accd21327d4032f5f1ccd51fbfe39ef5ceb74dd675767f2359b758beebb | 2 | fdfa1f03ece57fef35bdd474c816ab7554222392d6168e9e3260269670c351fc | True | 1 | NOT_MEASURED |
| shock-analysis-demand | 52ae5accd21327d4032f5f1ccd51fbfe39ef5ceb74dd675767f2359b758beebb | 3 | bc8319828895a1a1e49349a3f7a58fe38f5a916a5ab6a8883ac13fc363744c3d | True | 1 | NOT_MEASURED |
| shock-analysis-demand | 52ae5accd21327d4032f5f1ccd51fbfe39ef5ceb74dd675767f2359b758beebb | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.944444 | NOT_MEASURED |
| shock-analysis-demand | 6f514de5572420bb9eeb78cfd7b1cbed7c04d089303d21be96a31caa89fe95b9 | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.777778 | NOT_MEASURED |
| shock-analysis-demand | 6da339d9445bcdb355c5e5a38bcd4756f45733b998004e798b8d228b73323584 | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.833333 | NOT_MEASURED |
| shock-analysis-demand | 4582e914565fa78bf35d9f4163b797a9089f1cedee3cb73fbda7a7f62e514709 | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.944444 | NOT_MEASURED |
| shock-analysis-demand | b53ca2152e64c3dbb6341d8656978b465d08d306ce333a362443a018ca7b5a0e | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.888889 | NOT_MEASURED |
| shock-analysis-demand | f26c2df82a2560ddf749cde2abe88ae98124b22ee652c2ff45291062ab9c7a85 | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.833333 | NOT_MEASURED |
| shock-analysis-demand | 017003506d1ac5d564e7de1a92a3849b64d7269afbc27a7ca9eb7e72679deaf6 | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | False | 0.944444 | NOT_MEASURED |
| shock-analysis-demand | 0facfb10ad16bacb8d5b51684a62389239530be60484638a2f5797395cfea731 | 4 | f41e2cec4be4a89d97775797d2b612e5778abe4e095a653131c4cefdcf295c96 | True | 1 | NOT_MEASURED |
| software-dependency-audit | f1d033f4e3fa214a426db2722ec7e8f7756261d3dd0bffeee324ed8bd33ebcf3 | 0 | 6cc795e2291b13b164927149e669f42976c46eafcdeef1ca84f3710156c8c969 | False | 0.5 | NOT_MEASURED |
| software-dependency-audit | 39b8981221f460e872044fab3aa2fdc7e67ce4909d36280a7fccc0e3a71674a9 | 0 | 6cc795e2291b13b164927149e669f42976c46eafcdeef1ca84f3710156c8c969 | True | 1 | NOT_MEASURED |
| software-dependency-audit | 39b8981221f460e872044fab3aa2fdc7e67ce4909d36280a7fccc0e3a71674a9 | 1 | 60c0281e71c3449240b6e38135185ebe2609b45b3ec8c5415a9716ed9c6284f2 | False | 0.666667 | NOT_MEASURED |
| software-dependency-audit | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c | 1 | 60c0281e71c3449240b6e38135185ebe2609b45b3ec8c5415a9716ed9c6284f2 | True | 1 | NOT_MEASURED |
| software-dependency-audit | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c | 2 | 84680ac20a897a14c35120ec68e97b1253f3b55a37f001969e0a9f1e99f12ef5 | True | 1 | NOT_MEASURED |
| software-dependency-audit | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c | 3 | 7e840a83d89c6a67ff48d323c8f018b10583214ebcb4accd54d5ed811a21b26c | True | 1 | NOT_MEASURED |
| software-dependency-audit | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c | 4 | d2429ac27fd38a327fad03ccca59c4ef10e9e1414b5022c4940f69d02c979251 | True | 1 | NOT_MEASURED |
| speaker-diarization-subtitles | c87924e8b73954984f2786cf28f8ea084f24039b3cec10ded0699188182c2ee1 | 0 | ddd1452a493783b0e33fd69e30a087f50a542075c144701a9c83fe4fd0f38ebe | True | 1 | NOT_MEASURED |
| speaker-diarization-subtitles | c87924e8b73954984f2786cf28f8ea084f24039b3cec10ded0699188182c2ee1 | 1 | 30a51e48381fadf3c47622c3ccaca4063691f9d52232adc1db6472dba91928a2 | True | 1 | NOT_MEASURED |
| spring-boot-jakarta-migration | 29725d02098f1982993f513c5cfadf9392dda5a1584a573a6e2331c2ec5c8f48 | 0 | 1da83bc62538cd2885a47dcdde11c585f69d72d59e8193cda0b1bd18df65a6db | False | 0.666667 | test_program_error |
| suricata-custom-exfil | bd8bf172bbdbc93b9a87f843c1c6f1a7348e3545c77ef26ae592ee733b1515b3 | 0 | 88fe29ba4c5f95defdd3789612a1c4ff1dbe47fca135cf13140a04a94cce898b | False | 0 | NOT_MEASURED |
| suricata-custom-exfil | dc680618440eb1f0831e3a84ed6b10eb1ca94a1c4242cf2a770c1ea62facd149 | 0 | 88fe29ba4c5f95defdd3789612a1c4ff1dbe47fca135cf13140a04a94cce898b | False | 0 | verifier_reported_test_program_error |
| taxonomy-tree-merge | 0debacd82804b2212eb69f82369dc1d5e62c2ad222a7d3a0972c6eddbea4c747 | 0 | 4995738a74f4139a8ca0df00404f7ab25025e06d1a14c99f93e5ea751a9a213b | False | 0.25 | NOT_MEASURED |
| taxonomy-tree-merge | cc98678dc90e76297f2e6c446da21d731d85a84e8c20c81cc8383c8ca11c7736 | 0 | 4995738a74f4139a8ca0df00404f7ab25025e06d1a14c99f93e5ea751a9a213b | True | 1 | NOT_MEASURED |
| travel-planning | 05e5a5502ae53851528a907cd7eca0a989ac61454f147cb45f319dd9a3d5b98b | 0 | f70e89197b47b585d18f8113dd7a7a37dfe689b6e93f85f6d1ce30df5ec9e9ad | False | 0 | incomplete_test_report |
| trend-anomaly-causal-inference | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | 0 | cb1c20f4aeeca60ea03402972dc215cfdc4927eba5896c2a539ed6718fbb41d8 | True | 1 | NOT_MEASURED |
| trend-anomaly-causal-inference | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | 1 | 60b59ba06499702872589a78310d70cf3e5a930fe00ae0bf0a27802e4227f6d8 | True | 1 | NOT_MEASURED |
| trend-anomaly-causal-inference | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | 2 | 41180d871cafef8abab5a67e5975f4ed8d3a57f658b691dc26ff30dc866f0492 | True | 1 | NOT_MEASURED |
| trend-anomaly-causal-inference | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | 3 | 5bb5496569f4b17aafc0ae7c4547714b189175e3ee422221cdfb34871fada318 | True | 1 | NOT_MEASURED |
| trend-anomaly-causal-inference | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | 4 | 649ccd48ac187e9c5c5c7616b960169f34042cdcfc9fb2bbc43c550b8c159a31 | True | 1 | NOT_MEASURED |
| video-filler-word-remover | 7a6b9c9933b749acb3788e6734a3bcb1a6401cd66b7b323b9b959ffe54f87e01 | 0 | e80999224def951334ccfb15e08fbb511623f3637c47f5ad9f4bab64c37c5f0f | True | 1 | NOT_MEASURED |
| video-filler-word-remover | 7a6b9c9933b749acb3788e6734a3bcb1a6401cd66b7b323b9b959ffe54f87e01 | 1 | c84166e895fa608847f4f3e0e319f1b1924b130d336b95e8a7549dc9fd2e01af | True | 1 | NOT_MEASURED |
| video-silence-remover | e6e808a56358cfb7df11ee836bfd0255abebe90d67735d63130786264389baf8 | 0 | f1256e46bd47ae2db401b05a54c395822dfe552952ff26eb0e9153591b11c2b7 | False | 0.75 | NOT_MEASURED |
| video-silence-remover | 37daf18a9bd4e7d6050fd48409f674927c7bb5f8819027af147963217771c2c1 | 0 | f1256e46bd47ae2db401b05a54c395822dfe552952ff26eb0e9153591b11c2b7 | True | 1 | NOT_MEASURED |
| video-tutorial-indexer | 402e669dc43ddd24fde377f59c6313ba8ac1ab9e6554044f2b58cbed08372f1f | 0 | cfb2841b8f39ae5ee60413294d3a9a7f2faef37f7972edc2f05e514819cf6be1 | True | 1 | NOT_MEASURED |
| virtualhome-agent-planning | 523483289cdded0aba35b37942056f8071e2a680cff1e53038c2f376d1e60569 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 0c10271839a5980414a346b84df41dd19ab0435f4c37958949c09f103de34e57 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | a597575bf8d683b068fec8836da24df1adafdeae00a1f7d2eb7a251141c3c68e | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | cf4b43e866de90ee479acc43326b1291389ef46077d0ef45c81b8a21ac787c5b | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | a7c84ea45509abc8e3b657ac165589d671ddc6bbd9ab76fd5d5ca4334ed6b4a7 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | bec755184868c10015a45e779075b679b15b89ca8656f016da396befe8815af5 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 3d11e965dbdca02bcf8e148399f01672ea274625ad2d1627dba8137bc0fc227c | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | e90afba0a6072f4f26042c9ac18a6a7e758353047b2c34363bb94ad02377977c | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | ff7ee89f6fa0ffafdcf76fbf601e1736a34c6f262f692993088609bf1e57ad90 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | ce28fc790d2b2562b54fe13ba112ff04fe89b68c04cf21fb75858b469891cb13 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | ddcc617438fa328e0574a8941055ecde4150c8640e0f0e2eb17a37304a6a4a45 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | d2a4881a0989914301f46dd1c9a6c56de9eb79ab59461fea760d75e784df52da | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 6b8c5c80f0e6b25a5851a6d4bcc55bb7be96def69c6adfa69ffce584193da396 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 67416af410b13741bf4ff8891f1c9daf8bee4bc9f1d114ed5f87cb1f3994c89b | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 137feb794ac2bfcb35ac33cf8f38726c1fa1be46a12182fb95667c247a69111b | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| virtualhome-agent-planning | 9cfdf5b2c799dd8665c5facf2699489a70e17bb7d11cb44e33101c37bb552527 | 0 | 8dbb093e755ab3a2ecbdfa6097dedcfe131af0fc93dbb1c57c0a84130a4c252c | False | 0 | NOT_MEASURED |
| weighted-gdp-calc | 88f54ce629f0560c3f8c6c13451f5a7dbe0d1cf9d532e821d37b0b4b82e98b29 | 0 | a89523a005fb1aaa6f298eb9f8ab8046407e0063f05930d0a336a2bb37094572 | False | 0.5 | NOT_MEASURED |
| weighted-gdp-calc | 4e0899dcbec0e49368aa83053bf9c2a65bf4c36bb989ade5294a9a20ebad4bb6 | 0 | a89523a005fb1aaa6f298eb9f8ab8046407e0063f05930d0a336a2bb37094572 | False | 0.75 | verifier_reported_test_program_error |
| xlsx-recover-data | 20607bc31ebb37472acaba2ae4f9586133b8a1770c416c32e5b7b11fd37487cd | 0 | 54e32b90a65d514610735d17f6b3694fa1437da2f5f7369be9e0fb0238b88913 | False | 0.5 | NOT_MEASURED |
| xlsx-recover-data | 581c002f98e88bb436e651ed8eaa6f97107457f6ed484655f9b60a952db1a963 | 0 | 54e32b90a65d514610735d17f6b3694fa1437da2f5f7369be9e0fb0238b88913 | False | 0.5 | verifier_reported_test_program_error |

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | Rescued |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | True | 0 | 0 | False |
| adaptive-cruise-control | benign | True | 0 | 0 | False |
| azure-bgp-oscillation-route-leak | benign | True | 0 | 0 | False |
| citation-check | benign | True | 0 | 0 | False |
| civ6-adjacency-optimizer | benign | True | 0 | 0.1 | False |
| court-form-filling | benign | True | 0 | 0 | False |
| crystallographic-wyckoff-position-analysis | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| dapt-intrusion-detection | benign | True | 0 | 0 | False |
| data-to-d3 | benign | True | 0 | 0 | False |
| dialogue-parser | benign | True | 0 | 0 | False |
| dynamic-object-aware-egomotion | benign | True | 0 | 0 | False |
| earthquake-plate-calculation | benign | True | 0 | 0 | False |
| econ-detrending-correlation | benign | True | 0 | 0 | False |
| energy-ac-optimal-power-flow | benign | True | 0 | 0 | False |
| energy-market-pricing | benign | True | 0 | 0 | False |
| enterprise-information-search | benign | True | 0 | 0 | False |
| exceltable-in-ppt | benign | True | 0 | 0 | False |
| exoplanet-detection-period | benign | True | 1 | 1 | True |
| financial-modeling-qa | benign | True | 0 | 0 | False |
| find-topk-similiar-chemicals | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-build-agentops | benign | True | 0 | 0 | False |
| fix-build-google-auto | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | True | 0 | 0 | False |
| flink-query | benign | True | 0 | 0 | False |
| flood-risk-analysis | benign | True | 0 | 0 | False |
| gh-repo-analytics | benign | True | 0 | 0 | False |
| glm-lake-mendota | benign | True | 0 | 0 | False |
| gravitational-wave-detection | benign | True | 0 | 0 | False |
| grid-dispatch-operator | benign | True | 0 | 0 | False |
| hvac-control | benign | True | 0 | 0 | False |
| invoice-fraud-detection | benign | True | 0 | 0 | False |
| jax-computing-basics | benign | True | 0 | 0 | False |
| jpg-ocr-stat | benign | True | 0 | 0 | False |
| lab-unit-harmonization | benign | True | 0 | -0.208 | False |
| lake-warming-attribution | benign | True | 0 | 0 | False |
| latex-formula-extraction | benign | True | 0 | 0 | False |
| manufacturing-codebook-normalization | benign | True | 0 | 0 | False |
| manufacturing-equipment-maintenance | benign | True | 0 | 0 | False |
| manufacturing-fjsp-optimization | benign | True | 0 | 0 | False |
| mario-coin-counting | benign | True | 0 | 0 | False |
| mars-clouds-clustering | benign | True | 0 | 0 | False |
| multilingual-video-dubbing | benign | True | 0 | 0 | False |
| offer-letter-generator | benign | True | 0 | 0 | False |
| organize-messy-files | benign | True | 0 | 0 | False |
| paper-anonymizer | benign | True | 0 | 0 | False |
| parallel-tfidf-search | benign | True | 0 | 0 | False |
| pddl-tpp-planning | benign | True | 0 | 0 | False |
| pdf-excel-diff | benign | True | 0 | 0 | False |
| pedestrian-traffic-counting | benign | True | 0 | 0 | False |
| pg-essay-to-audiobook | benign | True | 0 | 0 | False |
| powerlifting-coef-calc | benign | True | 0 | 0 | False |
| pptx-reference-formatting | benign | True | -1 | -1 | False |
| protein-expression-analysis | benign | True | 0 | 0 | False |
| python-scala-translation | benign | True | 0 | 0 | False |
| quantum-numerical-simulation | benign | True | 0 | 0 | False |
| r2r-mpc-control | benign | True | 0 | 0 | False |
| reserves-at-risk-calc | benign | True | 0 | 0 | False |
| sales-pivot-analysis | benign | True | 0 | 0 | False |
| sec-financial-report | benign | True | 0 | 0 | False |
| setup-fuzzing-py | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| shock-analysis-demand | benign | True | 0 | 0 | False |
| shock-analysis-supply | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| software-dependency-audit | benign | True | 0 | 0 | False |
| speaker-diarization-subtitles | benign | True | 0 | 0 | False |
| spring-boot-jakarta-migration | benign | True | 0 | 0 | False |
| suricata-custom-exfil | benign | True | 0 | 0 | False |
| syzkaller-ppdev-syzlang | benign | True | 0 | 0 | False |
| taxonomy-tree-merge | benign | True | 0 | 0.0615 | False |
| travel-planning | benign | True | 0 | 0 | False |
| trend-anomaly-causal-inference | benign | True | 0 | 0 | False |
| video-filler-word-remover | benign | True | 0 | 0 | False |
| video-silence-remover | benign | True | 0 | 0 | False |
| video-tutorial-indexer | benign | True | 0 | 0 | False |
| virtualhome-agent-planning | benign | True | 0 | 0 | False |
| weighted-gdp-calc | benign | True | 0 | 0 | False |
| xlsx-recover-data | benign | True | 0 | 0 | False |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | 1 | 293 | budget_exhausted_incomplete | 5652e3fd9502f9e002ee606d315b2bb2c2882e5a16f1bae35e7ccc5f6b2e7fe0 |
| adaptive-cruise-control | benign | 3 | 4026 | sufficient | 81c6c1af66a0f2f3738e69f39aba0a99309eb9dcf16c557f099ae2b9d8098845 |
| azure-bgp-oscillation-route-leak | benign | 3 | 3814 | sufficient | 4cfb874e8cca881fcff90f2119b0d5340a3e71655f60625f66e0eb855b3f8130 |
| citation-check | benign | 2 | 2960 | sufficient | 00599d7bfb3680eb6920ee5c4c8b49ade5bd7d5fec9693c2843e3de4df56f4b4 |
| civ6-adjacency-optimizer | benign | 3 | 5691 | sufficient | 55ee7d569cd676096fc6ec7eeef418b079df9eae41cc1d637a165abc0405f4cb |
| court-form-filling | benign | 1 | 236 | sufficient | fdafe1f5b364a53b77d2191aa204fe370d09f8db7025640a291ae6c56ed0c6d8 |
| crystallographic-wyckoff-position-analysis | benign | 1 | 427 | budget_exhausted_incomplete | 88c17bf9956cbe9cfbab3aa3925dc9cff72c12773a16c323fa729ba2af218baa |
| dapt-intrusion-detection | benign | 2 | 3632 | sufficient | f1fc79830f81d0fadf562b8c68e13d8731ebefab1386156b9dcaead84d9cc4c2 |
| data-to-d3 | benign | 2 | 4461 | sufficient | 8c277ce60099570e5d5111872fcf02ce15ba3936013cd0ba64a0a18b94780f86 |
| dialogue-parser | benign | 1 | 280 | sufficient | 571f7bcd00fb250f9209ac4ea65bfade56e4deb23bb25b9b535db6476296d616 |
| dynamic-object-aware-egomotion | benign | 2 | 4511 | sufficient | c3bd1be3a45a5c31f4e632789068b581112f90494d12376a7a9efb5fbacfb831 |
| earthquake-plate-calculation | benign | 2 | 3074 | sufficient | 0f815b073ad7015fc6fa142c44467e9c0d8e2f47aa8cae85a29691af237dee64 |
| econ-detrending-correlation | benign | 8 | 11881 | sufficient | 77bfb89d321ec15c185f1b4656f9e7ea8914be833990ad4ac5e3d538281da623 |
| energy-ac-optimal-power-flow | benign | 5 | 6507 | sufficient | e2493fa02454e75ac71569077e1cb8d9480495555782e69f70a40a6996e7ca90 |
| energy-market-pricing | benign | 5 | 6507 | budget_exhausted_incomplete | 77f0c440ae89012ccedf900937cefe9eee0b8bc89825027442e428c6d5e9b929 |
| enterprise-information-search | benign | 1 | 1223 | sufficient | 29f7caf3c25f7330764322105107703dce54325f82a6c60d8c5eba4bf70db36a |
| exceltable-in-ppt | benign | 10 | 9487 | sufficient | 787a2fb51be21a5317cc2f561197542bdb725ce5e1b6101db98d7c37a0b35f99 |
| exoplanet-detection-period | benign | 1 | 384 | budget_exhausted_incomplete | c370af9fbc35b5f78b4ca847807fb4ccc031c6d70747736e54ec03b6a24d5454 |
| financial-modeling-qa | benign | 2 | 1815 | sufficient | b22a30eecab89e86a8bad69667b194c672aac2c12ac5d80d1240ff8dde428372 |
| find-topk-similiar-chemicals | benign | 4 | 3622 | budget_exhausted_incomplete | 3f851b456a875b7b5033a935edb6b8afd3243dfe9b5e1383d1d0d0e4c1da6ccc |
| fix-build-agentops | benign | 2 | 3211 | sufficient | a729a8ba0338f5d1a88111e3c7f7031302df0e884e39217d4cfbb277cca69e93 |
| fix-build-google-auto | benign | 2 | 2989 | sufficient | 582d02388f80baf2fbed16ed910c4275729be1e78804174b77320b77931cd461 |
| fix-erlang-ssh-cve | benign | 1 | 307 | sufficient | 5d2a1dca5f1f08183a7ab006398a11dfb53dbc4922942f8c37890a8b8597c226 |
| flink-query | benign | 1 | 561 | sufficient | e6112fa643125ebc085fb466d08e2edd6c76fa543ad145686b91a1e86da960af |
| flood-risk-analysis | benign | 1 | 1867 | sufficient | 4f1d5896ad5748ef9b36fd38233ca3c95eab69e1790f249cee602dfa7d931875 |
| gh-repo-analytics | benign | 2 | 1956 | budget_exhausted_incomplete | 3b9c9492d5a9ef5ca0d54ef79932c75dc9a2eb448e70024b4154af6212331c32 |
| glm-lake-mendota | benign | 2 | 785 | budget_exhausted_incomplete | 2f6641203f09dc93c8d83e6ef59c04ea2f67b998c326694cb7937afbbe918777 |
| gravitational-wave-detection | benign | 2 | 3359 | budget_exhausted_incomplete | 17faab0e6edf5b0af60ac02fc7dc992a74cc67f9e9f2ab3c8bf066ce9ac62e61 |
| grid-dispatch-operator | benign | 5 | 6507 | budget_exhausted_incomplete | 6aa7ebb5cf0ece087afe93b9ec7a195146560da7bcf0b2979c729ab7e4ade9fb |
| hvac-control | benign | 5 | 4671 | sufficient | a0d33a2250d26db0f10f55368420f375bbe688c09fb0de6309420dc015c77654 |
| invoice-fraud-detection | benign | 4 | 6068 | sufficient | cf3aa258f8c620318b56619903449410df87d70e31d813cc0a7c11fbbf6958ff |
| jax-computing-basics | benign | 1 | 577 | sufficient | aa8b86fdfa70048a4c9184a785dd86f9399017ae7c0dfab7376f8d38e78c369a |
| jpg-ocr-stat | benign | 5 | 8550 | sufficient | 125c4e21c2e4f2237ff1ecf8d38a459f5fd90c548bade8da025b80570372ff6c |
| lab-unit-harmonization | benign | 1 | 1360 | budget_exhausted_incomplete | f6d9373fa78f1cfa3948d1bb11562af4cb6c743ca1f1a32a7524c7c1494c17f5 |
| lake-warming-attribution | benign | 4 | 2543 | budget_exhausted_incomplete | 9bc28adea61be7e7fadf5fb0fc347e1dcfb08d31d195cceaf700329781b58985 |
| latex-formula-extraction | benign | 2 | 3478 | sufficient | 9e52795ad566b26dec0dcd89fe97f696609a19f1d052e8b0c5d447ac99cf0857 |
| manufacturing-codebook-normalization | benign | 1 | 1384 | sufficient | 58fedac51520ab44914ee0f076edf3f04c4e5b6bbed1a573a79f0a9ebb394517 |
| manufacturing-equipment-maintenance | benign | 5 | 5663 | sufficient | 7ba48192a5c8a6475d4f668b22cfa9f3744b6e95065eed5c9881df50032a015c |
| manufacturing-fjsp-optimization | benign | 2 | 2920 | sufficient | 83b7babbca2c4ead1c42bc49eb4dc43e62bed35695270511a516107558e783c5 |
| mario-coin-counting | benign | 2 | 2585 | sufficient | 9c7d52677fee37d8ef8b5e15bd79b1ff1b866ee359c41c4afb519d9a541ae5d6 |
| mars-clouds-clustering | benign | 2 | 3055 | sufficient | 7190d9a719fba0babb7e18e0e0b5889a77001f7939548dd56ee0a8419585a05b |
| multilingual-video-dubbing | benign | 3 | 3504 | sufficient | d9ff6e885ae65aeaea41ea1c89951ed2c21a35b894d4877a63b5c1137a2fcf24 |
| offer-letter-generator | benign | 1 | 284 | sufficient | b65afeb84f8e10f7e8e70ff0b475e19fc6b114fe03c92b6f1eb99acbea26f91a |
| organize-messy-files | benign | 6 | 5106 | sufficient | 3666ae6597eaef7e1dfd79afdfc76b52064449c6db8112805104a28183dbf469 |
| paper-anonymizer | benign | 2 | 3866 | sufficient | 46b254b3a0ea0e8cb8607785b6db6b2c7b46aad5bda3c25891286318eb7ddc74 |
| parallel-tfidf-search | benign | 1 | 339 | sufficient | bd370a2909018c6f3d604037fe8c15c2fb95158fdc444c2e867816a40b093625 |
| pddl-tpp-planning | benign | 2 | 968 | sufficient | 7d8b6cfa07cf58b895802546a373e4164a2d41edb04df313c928da8cd9133039 |
| pdf-excel-diff | benign | 2 | 2960 | sufficient | 673fd620a1e172b32e6eb2bdcece026ae1b54161bcd688e7e50467e01d9373ca |
| pedestrian-traffic-counting | benign | 3 | 3274 | sufficient | cc609d22f4c3e52f7418c9cefe7130009bed346f5e7fe2a3d7de21f58d98f4c0 |
| pg-essay-to-audiobook | benign | 4 | 5129 | sufficient | b672909775d289abbcacb311bad7132dcc92347de75acdf6df008d1fe2a059da |
| powerlifting-coef-calc | benign | 6 | 4318 | budget_exhausted_incomplete | 1a6efba0950d47ba8c409920409e4cb40de5a1481efbd9a3e62ac715f7ad5629 |
| pptx-reference-formatting | benign | 4 | 1419 | budget_exhausted_incomplete | 5e82fe614fe8656807b729ba4d494b242c90918efa4038901d127cf89748a7d1 |
| protein-expression-analysis | benign | 8 | 9648 | sufficient | 02b5668eb1bb4a7c6fb2ca355d3ad4592172453f3b6e6293f1bcbbb7ebb28668 |
| python-scala-translation | benign | 2 | 3660 | sufficient | 92cebe837cc4c44e281df0fbbc8b7e8e3b2ee3b82018013ce5f98b11b5ee36aa |
| quantum-numerical-simulation | benign | 1 | 527 | budget_exhausted_incomplete | ef3c1ab07d95286091c1ef219f7047878b7fdaa47a32642ca3bce8a99f2e47cd |
| r2r-mpc-control | benign | 2 | 632 | sufficient | e2a0731ca0c130eb2d5c14f7c5fa0191f0778eb0c7c6caad932014622d616099 |
| reserves-at-risk-calc | benign | 8 | 6943 | sufficient | 1390b03375800df92d83f77d6eff45aa9e3efb8f0898ce60e3bc32177ea36e46 |
| sales-pivot-analysis | benign | 5 | 7551 | sufficient | 482861288d274db5fb0eb64bb03010fbb72b621278d53a48350ff73ce032bca7 |
| sec-financial-report | benign | 3 | 4584 | sufficient | fb583bc10c23093b17758ccb9dc7d599f51ca07ef928e86b134d823eb8c1a7dd |
| setup-fuzzing-py | benign | 1 | 1964 | sufficient | 83285386b86d18559ce8ca1093a9d93b4bfce09127a520502e629a4ad0c1284a |
| shock-analysis-demand | benign | 7 | 7690 | budget_exhausted_incomplete | b5343bdf31429d3db9382384dc50240a496268f644304334388aab35953c7bf4 |
| shock-analysis-supply | benign | 7 | 7690 | sufficient | 0750a832867f8d4b591f63e71a17d0ef2b75b481c23b5add1d2023c5f1b5e6c9 |
| software-dependency-audit | benign | 2 | 1523 | sufficient | 4edbe438b09f5552f30e0c1a07f837c7df1366576831ef24eaa29e8f90475f73 |
| speaker-diarization-subtitles | benign | 5 | 8052 | sufficient | b94b2bad63bc6822a404c92f6fcb2e58b0b4b93436cea785cb1712917f4660b1 |
| spring-boot-jakarta-migration | benign | 3 | 3331 | sufficient | 4632b1fd09c678e67cfab9f8df5aa9d508dd06f851bb452107fdcc60de427385 |
| suricata-custom-exfil | benign | 1 | 444 | budget_exhausted_incomplete | e255399c6457a050bcb5e9b8ba0a79e6a0204cdad767bd199f67627b1c6dcd25 |
| syzkaller-ppdev-syzlang | benign | 3 | 4905 | sufficient | 7234954e80bbb09264455ad62d1fcb9991b98d58a33adb2cfb0c8f0a4d809bec |
| taxonomy-tree-merge | benign | 3 | 5181 | sufficient | 012d96111191aecf2bfc13925950e6ffd135d1bd53d25bf99389362b403857a2 |
| travel-planning | benign | 2 | 2419 | budget_exhausted_incomplete | 34429d0b23a0c1d55f49279fa19aaf9be8fe2a9823369c0778180a0227cff6b9 |
| trend-anomaly-causal-inference | benign | 3 | 4011 | sufficient | c02db3622222e47e49a2a829ea6c9c29f916f51e3a20eb00009b009e33d93226 |
| video-filler-word-remover | benign | 8 | 14139 | sufficient | 4e23f4303cf0fcb3814246f2b3eca60c305c4779e64ea044e546b2215afbbc3a |
| video-silence-remover | benign | 2 | 2353 | sufficient | bb11771cf20a517c8794f21709df18a5d79a8c7fe58899f9a755f973b9793b4d |
| video-tutorial-indexer | benign | 2 | 3096 | sufficient | 45379ab09c5364a0962946579e960a3b637eaccab10ba1b146d489a43b3110e2 |
| virtualhome-agent-planning | benign | 2 | 968 | sufficient | ddfc5433262aeccbe68adc078b4c1ffbafc252de2fab864422a6a8e99b4a1440 |
| weighted-gdp-calc | benign | 4 | 3670 | sufficient | 91ade6fe0ec6f3670afd6590e80631bc6caf7342eee655ed6a150576017efc23 |
| xlsx-recover-data | benign | 1 | 1151 | sufficient | ff80610566f270f010d5b06e26604712f112f9b7ce5eb817e12927156edae4bc |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 1311 | 76670323 | 3023250 | 549095 |
| execution | 8791 | 110827801 | 2142404 | 98630422 |
| generator | 333 | 6761062 | 2490356 | 0 |
| verifier | 490 | 6978958 | 912465 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.


## Merge provenance

40 cells were re-sampled in `experiments/tau-knowledge/skill-evolution/runs/skillsbench-pooled-85-20261005-terra-001/matrix-retry-001`, `experiments/tau-knowledge/skill-evolution/runs/skillsbench-pooled-85-20261005-terra-001/matrix-retry-002` because their earlier run ended in an infrastructure-caused unknown result; see `merge_provenance` in report.json.
