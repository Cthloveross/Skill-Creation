# skillsbench run report

Protocol: `skillsbench.skill-evolution.v1`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility |
| --- | --- | --- | --- | --- | --- | --- |
| benign | evolved | 85 | 40 | 36 | 0.194444 | 0.0823529 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 40 | 36 | 0.194444 | {'rollout_result_unknown': 5, 'oracle_result_unknown': 1, 'test_escalation_failed': 3, 'verifier_initialization_result_unknown': 3, 'oracle_success': 3, 'oracle_budget_exhausted': 2, 'verification_program_error_exhausted': 4} |
| benign | 1 | 19 | 18 | 0.111111 | {'verification_program_error_exhausted': 2, 'oracle_success': 1, 'oracle_budget_exhausted': 1, 'test_escalation_failed': 1} |
| benign | 2 | 14 | 13 | 0.153846 | {'rollout_result_unknown': 1, 'oracle_budget_exhausted': 3, 'test_escalation_failed': 1} |
| benign | 3 | 9 | 9 | 0.111111 | {'verification_program_error_exhausted': 1} |
| benign | 4 | 8 | 8 | 0.125 | {} |
| benign | 5 | 8 | 8 | 0.125 | {} |
| benign | 6 | 8 | 8 | 0 | {} |
| benign | 7 | 8 | 8 | 0.125 | {'rollout_result_unknown': 1} |
| benign | 8 | 7 | 7 | 0.142857 | {} |
| benign | 9 | 7 | 7 | 0.142857 | {} |
| benign | 10 | 7 | 7 | 0.142857 | {'verification_program_error_exhausted': 1, 'test_escalation_failed': 1} |
| benign | 11 | 5 | 5 | 0 | {} |
| benign | 12 | 5 | 5 | 0.2 | {} |
| benign | 13 | 5 | 5 | 0 | {} |
| benign | 14 | 5 | 5 | 0 | {'oracle_budget_exhausted': 1} |
| benign | 15 | 4 | 4 | 0 | {'revision_budget_exhausted': 4} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Final hash |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | verification_program_error_exhausted | 2 | 1 | 0 | 881af1fee74318a26631ce03146162d7aaac0e2340c7e5b2f6552da1dbce820e |
| adaptive-cruise-control | benign | rollout_result_unknown | 3 | 2 | 0 | d16e5a4867ad8a16f40f397f1fc2f551684d1727a94a0d2e65be429e20c1d1b0 |
| azure-bgp-oscillation-route-leak | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| citation-check | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | benign | oracle_budget_exhausted | 3 | 2 | 5 | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d |
| court-form-filling | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| dapt-intrusion-detection | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| data-to-d3 | benign | oracle_budget_exhausted | 3 | 2 | 5 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb |
| dialogue-parser | benign | oracle_success | 2 | 1 | 1 | 403fc0d8f4566414b6d7dc0d79186e740f6dc19c2ee255aa03b4c6537c6cb8e8 |
| dynamic-object-aware-egomotion | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| econ-detrending-correlation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| energy-ac-optimal-power-flow | benign | rollout_result_unknown | 1 | 0 | 0 | 8a64d9e2b988d35efaeb5034e650ed581cc7d49d9502f1f7c17ecb7938440175 |
| energy-market-pricing | benign | oracle_result_unknown | 1 | 0 | 1 | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 |
| enterprise-information-search | benign | test_escalation_failed | 1 | 0 | 1 | b8294f303c6a45b4e7549c51cb6fc1cb0a584fb43e4018783f99402528539bd8 |
| exceltable-in-ppt | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| exoplanet-detection-period | benign | verification_program_error_exhausted | 11 | 10 | 1 | 5872091c8e3088883d957d490050cbd17d0749af5e3e4d93a3d9694bf9401237 |
| financial-modeling-qa | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| find-topk-similiar-chemicals | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-build-agentops | benign | rollout_result_unknown | 1 | 0 | 0 | 45207d5adf392c6e202b2baf33eccedfdbca42d5057b55a73ae4d1cc00b3cafe |
| fix-build-google-auto | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | 82c14c2e249a8d8614d346fe474b133229c77081312663268c868776847bf295 |
| fix-druid-loophole-cve | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | c99985d4e8490777deac775cd36a52787745bfef70cae21ccd9e30193ba3a03e |
| fix-visual-stability | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| flink-query | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| flood-risk-analysis | benign | oracle_budget_exhausted | 2 | 1 | 5 | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd |
| gh-repo-analytics | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| glm-lake-mendota | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| gravitational-wave-detection | benign | oracle_success | 1 | 0 | 1 | cd96d1a1ffaaf5734583599d48924523d347981cc261b0c2a4e2d9a8394dfc7e |
| grid-dispatch-operator | benign | verification_program_error_exhausted | 2 | 1 | 2 | 7b479b3d1a7b01b58af81be3287a105b6650d00d429952d3fa2f4fb8c5d18db0 |
| hvac-control | benign | test_escalation_failed | 11 | 10 | 4 | b235b16f70787c45dc201a9f205d78ec511a01c4698bf55fbfce7bbf127aff14 |
| invoice-fraud-detection | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| jax-computing-basics | benign | revision_budget_exhausted | 16 | 15 | 0 | 3a86d4b45841bb55a02742464cf48e046fca8f48b1a11549237e10f0670e7648 |
| jpg-ocr-stat | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| lab-unit-harmonization | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| lake-warming-attribution | benign | oracle_budget_exhausted | 1 | 0 | 5 | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 |
| latex-formula-extraction | benign | rollout_result_unknown | 1 | 0 | 0 | 1bb6bf3586db12919309f7add09be9be4b6c1e58eb1b725714a31c9c647b3cdb |
| lean4-proof | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-codebook-normalization | benign | oracle_success | 1 | 0 | 1 | 0fc7f16b51b98904e87881ffeadeea001d071a0d5d56408bf31815d1ace1cace |
| manufacturing-equipment-maintenance | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-fjsp-optimization | benign | verification_program_error_exhausted | 1 | 0 | 0 | 98c483de4d362a175571f6f6da96f817e453b95b0a51d89bb58eaa3b39c0f995 |
| mario-coin-counting | benign | revision_budget_exhausted | 16 | 15 | 0 | 212196e5d4ed41dab1666dbbb27f67eee8562db54ae77e21616a8997e4ef6838 |
| mars-clouds-clustering | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| multilingual-video-dubbing | benign | rollout_result_unknown | 8 | 7 | 0 | fd8d15196dfbdfe65dc61b7fcc4ce7eb09f2bac7af8af66693a2893cefa901b2 |
| offer-letter-generator | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| organize-messy-files | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| paper-anonymizer | benign | revision_budget_exhausted | 16 | 15 | 0 | f620b65635c8d0d5aa87cb7688a0a139b2256545861f9dcfa3ed38309e549840 |
| parallel-tfidf-search | benign | verification_program_error_exhausted | 1 | 0 | 0 | c3d9491cb6b09fb77e075202ae6f8ed8d08565b0426a43dc54e86fa149eebe4a |
| pddl-tpp-planning | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pdf-excel-diff | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pedestrian-traffic-counting | benign | test_escalation_failed | 1 | 0 | 4 | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pptx-reference-formatting | benign | verification_program_error_exhausted | 4 | 3 | 2 | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf |
| protein-expression-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| python-scala-translation | benign | test_escalation_failed | 3 | 2 | 1 | 584cfcda19675ea1e62c769e4ced10d71dcbc543be11a0a4f4371017df9d6ca6 |
| quantum-numerical-simulation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| r2r-mpc-control | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| react-performance-debugging | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| reserves-at-risk-calc | benign | verification_program_error_exhausted | 1 | 0 | 0 | 849638183ab52285cc6bc2e69085f3d1099651ce9dc19823f4d31fad751a597e |
| sales-pivot-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| sec-financial-report | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | rollout_result_unknown | 1 | 0 | 0 | 8887217d8d19dc35d1157e26ae06c3c4b2ffffca46af6ee8c3c715bd08289557 |
| shock-analysis-demand | benign | oracle_budget_exhausted | 15 | 14 | 5 | 0facfb10ad16bacb8d5b51684a62389239530be60484638a2f5797395cfea731 |
| shock-analysis-supply | benign | rollout_result_unknown | 1 | 0 | 0 | 87b7e13f3e5541361631bb73893d18aebbc159f7129fc90d53cbb51dd354ee32 |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | oracle_budget_exhausted | 3 | 2 | 5 | ada183e6d418ac61d99705b80e65cc0218586b983c11a0cd1fd21c9d43c38b8c |
| speaker-diarization-subtitles | benign | test_escalation_failed | 1 | 0 | 2 | c87924e8b73954984f2786cf28f8ea084f24039b3cec10ded0699188182c2ee1 |
| spring-boot-jakarta-migration | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| suricata-custom-exfil | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| syzkaller-ppdev-syzlang | benign | verifier_initialization_result_unknown | 1 | 0 | 0 | bc124972c2261ef18bf568d37421fe57fad9611b166cb535a66feb47791e1001 |
| taxonomy-tree-merge | benign | test_escalation_failed | 2 | 1 | 1 | cc98678dc90e76297f2e6c446da21d731d85a84e8c20c81cc8383c8ca11c7736 |
| threejs-structure-parser | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | verification_program_error_exhausted | 1 | 0 | 0 | 05e5a5502ae53851528a907cd7eca0a989ac61454f147cb45f319dd9a3d5b98b |
| trend-anomaly-causal-inference | benign | oracle_budget_exhausted | 1 | 0 | 5 | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 |
| video-filler-word-remover | benign | oracle_success | 1 | 0 | 2 | 7a6b9c9933b749acb3788e6734a3bcb1a6401cd66b7b323b9b959ffe54f87e01 |
| video-silence-remover | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| video-tutorial-indexer | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| virtualhome-agent-planning | benign | revision_budget_exhausted | 16 | 15 | 0 | 9cfdf5b2c799dd8665c5facf2699489a70e17bb7d11cb44e33101c37bb552527 |
| weighted-gdp-calc | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| xlsx-recover-data | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 0 | S0 | 620fe576171a8e6d6f4ed5e4a3fa62aebc9b9f1a937fef0dca99dee9005022d6 | MEASURED | True | 1 | 2 | 2 | 1 |
| 3d-scan-calc | 1 | S1 / final | 881af1fee74318a26631ce03146162d7aaac0e2340c7e5b2f6552da1dbce820e | MEASURED | True | 1 | 2 | 2 | 1 |
| adaptive-cruise-control | 0 | S0 | e6e96c7bca72c892074aa312734ff23346bda26f93abd47a03c7723303bda194 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| adaptive-cruise-control | 1 | S1 | ccd7e9b2188db92642ff1aef6579d84f7a3557af0ded903cc672a439db48d2bd | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| adaptive-cruise-control | 2 | S2 / final | d16e5a4867ad8a16f40f397f1fc2f551684d1727a94a0d2e65be429e20c1d1b0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| civ6-adjacency-optimizer | 0 | S0 | 5553905f8c504e208ab24b39a8354c46e681788cf4b9fc6ae0b603ffac8150be | MEASURED | False | 0.7 | 10 | 10 | 1 |
| civ6-adjacency-optimizer | 1 | S1 | f9dcbed081bd62417f2599dbd657ce451a51a3d7f69bf3b67b833f5a2511860b | MEASURED | False | 0 | 9 | 10 | 0.9 |
| civ6-adjacency-optimizer | 2 | S2 / final | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | MEASURED | False | 0.8 | 10 | 10 | 1 |
| data-to-d3 | 0 | S0 | bc87ee4ec9408668d117e6de0ced432065ea7d163e477d244f9e586f1945b3c7 | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| data-to-d3 | 1 | S1 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| data-to-d3 | 2 | S2 / final | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | MEASURED | False | 0 | 8 | 15 | 0.533333 |
| dialogue-parser | 0 | S0 | e0f6b26461bfae15f57294363012112a54a6bb90e882288156e6030eedafa37c | MEASURED | True | 1 | 6 | 6 | 1 |
| dialogue-parser | 1 | S1 / final | 403fc0d8f4566414b6d7dc0d79186e740f6dc19c2ee255aa03b4c6537c6cb8e8 | MEASURED | True | 1 | 6 | 6 | 1 |
| energy-ac-optimal-power-flow | 0 | S0 / final | 8a64d9e2b988d35efaeb5034e650ed581cc7d49d9502f1f7c17ecb7938440175 | MEASURED | False | 0 | 16 | 24 | 0.666667 |
| energy-market-pricing | 0 | S0 / final | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 | MEASURED | False | 0 | 0 | 4 | 0 |
| enterprise-information-search | 0 | S0 / final | b8294f303c6a45b4e7549c51cb6fc1cb0a584fb43e4018783f99402528539bd8 | MEASURED | False | 0 | 1 | 3 | 0.333333 |
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
| fix-build-agentops | 0 | S0 / final | 45207d5adf392c6e202b2baf33eccedfdbca42d5057b55a73ae4d1cc00b3cafe | MEASURED | False | 0 | 1 | 3 | 0.333333 |
| fix-build-google-auto | 0 | S0 / final | 82c14c2e249a8d8614d346fe474b133229c77081312663268c868776847bf295 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-erlang-ssh-cve | 0 | S0 / final | c99985d4e8490777deac775cd36a52787745bfef70cae21ccd9e30193ba3a03e | MEASURED | False | 0 | 0 | 3 | 0 |
| flood-risk-analysis | 0 | S0 | 52639d1c25caa8f7ebcfdf5298257550dfcf444c875154bb8c616954f9eb2ca8 | MEASURED | False | 0 | 0 | 2 | 0 |
| flood-risk-analysis | 1 | S1 / final | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | MEASURED | False | 0 | 1 | 2 | 0.5 |
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
| lake-warming-attribution | 0 | S0 / final | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | MEASURED | False | 0 | 1 | 2 | 0.5 |
| latex-formula-extraction | 0 | S0 / final | 1bb6bf3586db12919309f7add09be9be4b6c1e58eb1b725714a31c9c647b3cdb | MEASURED | False | 0 | 5 | 7 | 0.714286 |
| manufacturing-codebook-normalization | 0 | S0 / final | 0fc7f16b51b98904e87881ffeadeea001d071a0d5d56408bf31815d1ace1cace | MEASURED | False | 0 | 15 | 16 | 0.9375 |
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
| multilingual-video-dubbing | 0 | S0 | 5582b38f0ac886eb25ec61d2dd88b8f928e33ae2e260389a32092f40eb9fc418 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 1 | S1 | 61977507fb71f1e6a3d99527064c8cef8df3c724b1239f304810c9634dc1908b | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 2 | S2 | 19e63b37c78cfa4fe1c7fd92e89a74670297d9ed5e1635e6fdc4321188159348 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 3 | S3 | 9f06a4ec07b6f242c8572d8f8e735c67eb1059439e8af3e8617952718ca521c2 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 4 | S4 | 8a4768a651ad76e90be7c1cd33a4f898db36f0fdc3221602560f944970a069a9 | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 5 | S5 | 7cd6c6a9c5c75f86b1933cf820be53beffa3f34622880ac83f164b82cc778c8a | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 6 | S6 | c4bfd788b65b82ab656c5802508ea09f468a069a08a2e424e11ea158cd853a7c | MEASURED | False | 0 | 0 | 8 | 0 |
| multilingual-video-dubbing | 7 | S7 / final | fd8d15196dfbdfe65dc61b7fcc4ce7eb09f2bac7af8af66693a2893cefa901b2 | MEASURED | False | 0 | 0 | 8 | 0 |
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
| pedestrian-traffic-counting | 0 | S0 / final | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | MEASURED | False | 0.1 | 0 | 1 | 0 |
| pptx-reference-formatting | 0 | S0 | 193c96607959e2f4c7093b5972beddb066fefd304bcc8152c07f8110bcccaaa4 | MEASURED | True | 1 | 12 | 12 | 1 |
| pptx-reference-formatting | 1 | S1 | 3065a4d8650ced84944c61a2e8ddb8a710f7d57080cec50893fdfd6f4ed8b023 | MEASURED | False | 0 | 7 | 12 | 0.583333 |
| pptx-reference-formatting | 2 | S2 | e9487acd4927e01c61fc51c08ece68637c9457d457020719d5298709a463e7a6 | MEASURED | False | 0 | 7 | 12 | 0.583333 |
| pptx-reference-formatting | 3 | S3 / final | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf | MEASURED | False | 0 | 0 | 12 | 0 |
| python-scala-translation | 0 | S0 | 68fbcfd02f5dd1659dcc82d043f82cfe8c3dbb09fb3c26cd43e9740845e66efc | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | 1 | S1 | 851a2a5b34fecbb902d4dbe9b99c7930955cfb744ffe675dbfce041a9db8d67e | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| python-scala-translation | 2 | S2 / final | 584cfcda19675ea1e62c769e4ced10d71dcbc543be11a0a4f4371017df9d6ca6 | MEASURED | False | 0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| reserves-at-risk-calc | 0 | S0 / final | 849638183ab52285cc6bc2e69085f3d1099651ce9dc19823f4d31fad751a597e | MEASURED | False | 0 | 3 | 5 | 0.6 |
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
| syzkaller-ppdev-syzlang | 0 | S0 / final | bc124972c2261ef18bf568d37421fe57fad9611b166cb535a66feb47791e1001 | MEASURED | False | 0 | 5 | 7 | 0.714286 |
| taxonomy-tree-merge | 0 | S0 | 0debacd82804b2212eb69f82369dc1d5e62c2ad222a7d3a0972c6eddbea4c747 | MEASURED | False | 0.85 | 19 | 22 | 0.863636 |
| taxonomy-tree-merge | 1 | S1 / final | cc98678dc90e76297f2e6c446da21d731d85a84e8c20c81cc8383c8ca11c7736 | MEASURED | False | 0.9115 | 20 | 22 | 0.909091 |
| travel-planning | 0 | S0 / final | 05e5a5502ae53851528a907cd7eca0a989ac61454f147cb45f319dd9a3d5b98b | MEASURED | False | 0 | 0 | 10 | 0 |
| trend-anomaly-causal-inference | 0 | S0 / final | 30679ab966756b1123957e4696a87d0b708d698abdfaeca13578b9ec07447ee3 | MEASURED | False | 0.6889 | 9 | 15 | 0.6 |
| video-filler-word-remover | 0 | S0 / final | 7a6b9c9933b749acb3788e6734a3bcb1a6401cd66b7b323b9b959ffe54f87e01 | MEASURED | True | 1 | 5 | 5 | 1 |
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

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | 620fe576171a8e6d6f4ed5e4a3fa62aebc9b9f1a937fef0dca99dee9005022d6 | 0 | 27bf164c5f686a70ad7ffafe3d75b85607bc1a8391bd0fb974a9c6cc9a3fc2f4 | False | 0 | NOT_MEASURED |
| 3d-scan-calc | 881af1fee74318a26631ce03146162d7aaac0e2340c7e5b2f6552da1dbce820e | 0 | 27bf164c5f686a70ad7ffafe3d75b85607bc1a8391bd0fb974a9c6cc9a3fc2f4 | False | 0 | verifier_reported_test_program_error |
| adaptive-cruise-control | e6e96c7bca72c892074aa312734ff23346bda26f93abd47a03c7723303bda194 | 0 | 9b2168ef75e0fea304548a10407730f2eac4fb16f8402b5d1a268e6fa397158b | False | 0.4 | NOT_MEASURED |
| adaptive-cruise-control | ccd7e9b2188db92642ff1aef6579d84f7a3557af0ded903cc672a439db48d2bd | 0 | 9b2168ef75e0fea304548a10407730f2eac4fb16f8402b5d1a268e6fa397158b | False | 0.8 | NOT_MEASURED |
| civ6-adjacency-optimizer | 5553905f8c504e208ab24b39a8354c46e681788cf4b9fc6ae0b603ffac8150be | 0 | 245c0ca297703d9c2ec1ec2a9c36c9c9d84e8f4a0a98cc2b9b1d97840b76dfcf | False | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | f9dcbed081bd62417f2599dbd657ce451a51a3d7f69bf3b67b833f5a2511860b | 0 | 245c0ca297703d9c2ec1ec2a9c36c9c9d84e8f4a0a98cc2b9b1d97840b76dfcf | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | f9dcbed081bd62417f2599dbd657ce451a51a3d7f69bf3b67b833f5a2511860b | 1 | 1462aafae8d86ca177eb99232b21b00e541b4662bb205dd1e86a7168cfbe4b4e | False | 0.666667 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 1 | 1462aafae8d86ca177eb99232b21b00e541b4662bb205dd1e86a7168cfbe4b4e | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 2 | f0977f81c99470856bb4373bbe72a21e0860797e9862a2f1f525c04d970773c5 | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 3 | ef8c616f3291bb47fb622bab4abd84d82c9da6c350b2805e398093b4666072df | True | 1 | NOT_MEASURED |
| civ6-adjacency-optimizer | ced911eefed6cf490070e02a28a7f18759001c72afef2ae78b07f6156903703d | 4 | e59d5c0bb7c565b160df3fa9bf507521472d7901f8c5e0d6c27259cccae283d9 | True | 1 | NOT_MEASURED |
| data-to-d3 | bc87ee4ec9408668d117e6de0ced432065ea7d163e477d244f9e586f1945b3c7 | 0 | 40595ac1b15311983f9c9be4a9e32e7233023d25f943d66da7a6daf9fb44e24f | False | 0.857143 | NOT_MEASURED |
| data-to-d3 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | 0 | 40595ac1b15311983f9c9be4a9e32e7233023d25f943d66da7a6daf9fb44e24f | True | 1 | NOT_MEASURED |
| data-to-d3 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | 1 | ecb4ea62acf9333e32310b33e79f0906cf32070f0791c0f8ea8e01db2c5a94d0 | True | 1 | NOT_MEASURED |
| data-to-d3 | f8467dd0a40de63dbce97233893caea5a599b2b9c371b5be3554ca610f2d5092 | 2 | 5d0a9a452e05d8351c72fd4de4ebf2202bb8af414ea48c7537d2af8406137dae | False | 0.933333 | NOT_MEASURED |
| data-to-d3 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | 2 | 5d0a9a452e05d8351c72fd4de4ebf2202bb8af414ea48c7537d2af8406137dae | True | 1 | NOT_MEASURED |
| data-to-d3 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | 3 | 0e56586d913596ebb31876b0b7fc0b12551bcd7b8ac84f219e88b548f23b52c3 | True | 1 | NOT_MEASURED |
| data-to-d3 | ac73687186125ec2a35b65b083edfd303e0ba26cf1080ed06f2be915ba2537bb | 4 | 73d87cdd9d1853439841126c6b4928605e03f1a13b8376a32296f5c45d2ca670 | True | 1 | NOT_MEASURED |
| dialogue-parser | e0f6b26461bfae15f57294363012112a54a6bb90e882288156e6030eedafa37c | 0 | 67337b5e992b89c084e05335dbd970b5fa090a56aa6f883da006d65625edd2d8 | False | 0 | NOT_MEASURED |
| dialogue-parser | 403fc0d8f4566414b6d7dc0d79186e740f6dc19c2ee255aa03b4c6537c6cb8e8 | 0 | 67337b5e992b89c084e05335dbd970b5fa090a56aa6f883da006d65625edd2d8 | True | 1 | NOT_MEASURED |
| energy-market-pricing | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 | 0 | 0b8eaaab326c2e4b5339874ad4373ba31660eb36632464f3a2a40f9d22e7addf | True | 1 | NOT_MEASURED |
| energy-market-pricing | c2813767a1235fcb83e458a381526839f63a8fce9b5e19656ab22ea0a8e4f634 | 1 | 7338931bfed41103a8add0971a84293ab5209ac8b7bc62da13f925d7b8fbb6e9 | True | 1 | NOT_MEASURED |
| enterprise-information-search | b8294f303c6a45b4e7549c51cb6fc1cb0a584fb43e4018783f99402528539bd8 | 0 | 79eb11466e5033d42bb2a79ca7165a863d757e0734bb3be3181c3e9e83753451 | True | 1 | NOT_MEASURED |
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
| flood-risk-analysis | 52639d1c25caa8f7ebcfdf5298257550dfcf444c875154bb8c616954f9eb2ca8 | 0 | ba279c77f330856bc0acbc4a1407cc1aa5fd0fee51ab48a3179adeb4012050f8 | False | 0 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 0 | ba279c77f330856bc0acbc4a1407cc1aa5fd0fee51ab48a3179adeb4012050f8 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 1 | 3cb9f3dcba467ada7a3e0e6288128474670f8c0af20269c90e0c13812803db52 | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 2 | 5c7e5183dda0e1e4f89b83279c642f029ef4a3b74d0f89a1297ba1817a5d691d | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 3 | c3b4f03d12de98c5512b583b812022151e39950e8a850d9cadc0cde235c43fbe | True | 1 | NOT_MEASURED |
| flood-risk-analysis | d8ce658e6624d6ed5c19432f725fd21e20347033621960659ec9b55dec6af0fd | 4 | cd720ceea66215659bb4ca14088fc16695c3a91c302c1599b253968a592a5785 | True | 1 | NOT_MEASURED |
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
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 0 | 8e287eaca8df123a398f1af4bcdf97864993567290edfc4d16f57f5e1e4e10e9 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 1 | d057178f59c3edd4e24aa59503d82918b09f06899ee799bedc5d865f20e32563 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 2 | 9d90ca6606f707c8ae3512ec4cefa420627ba20a1946b523709db17d50c94da9 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 3 | 137958bcb1ac182c74aa4536d5b4decebefe9a359e91b0d51ce19ed22ed2a273 | True | 1 | NOT_MEASURED |
| lake-warming-attribution | 7e6bf3121beafd0084e3396daadda99704e6438a6c102f8554cccc0b2eafa2f2 | 4 | 9aaebab5e4152c532471c374c3068e57e612f88c7e7fae833fd7a0505e5ea721 | True | 1 | NOT_MEASURED |
| manufacturing-codebook-normalization | 0fc7f16b51b98904e87881ffeadeea001d071a0d5d56408bf31815d1ace1cace | 0 | 7792463ae7e280c407e8be38c54cbff27e890bd255e07cfdb9285f36d9bc0c6c | True | 1 | NOT_MEASURED |
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
| multilingual-video-dubbing | 5582b38f0ac886eb25ec61d2dd88b8f928e33ae2e260389a32092f40eb9fc418 | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 61977507fb71f1e6a3d99527064c8cef8df3c724b1239f304810c9634dc1908b | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 19e63b37c78cfa4fe1c7fd92e89a74670297d9ed5e1635e6fdc4321188159348 | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 9f06a4ec07b6f242c8572d8f8e735c67eb1059439e8af3e8617952718ca521c2 | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 8a4768a651ad76e90be7c1cd33a4f898db36f0fdc3221602560f944970a069a9 | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | 7cd6c6a9c5c75f86b1933cf820be53beffa3f34622880ac83f164b82cc778c8a | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
| multilingual-video-dubbing | c4bfd788b65b82ab656c5802508ea09f468a069a08a2e424e11ea158cd853a7c | 0 | 38d72ca50a3e1d4befe83dbc6562f920a6a2b740390e6e34c680b0437f1f47d7 | False | 0 | NOT_MEASURED |
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
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 0 | ca95a6e6fcf842fdcd685a703f7199ee05f52b4674fd88b2a2e1f0670c097ebe | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 1 | cb1e5fe91d550a22f4869f9bef2ac394b357cc3c9dca1f0a7356b332d5b903d9 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 2 | 19f8440cef1647e75e98968b0a2415f55fc0e60f925bd882ec09907625a0b693 | True | 1 | NOT_MEASURED |
| pedestrian-traffic-counting | 0314a80285a4bdfadb081208576611e2c968ef9c92fc17955e1d4b9266cfb3b6 | 3 | 5ae4d544f79b6f701cb9239eb6e3b40c7aded8dd526cfedcec56fa2b756f75e9 | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 193c96607959e2f4c7093b5972beddb066fefd304bcc8152c07f8110bcccaaa4 | 0 | 06f810b7796f3777a45bb960c90428b9985ce6948899484cf350fd023e925e81 | False | 0.333333 | NOT_MEASURED |
| pptx-reference-formatting | 3065a4d8650ced84944c61a2e8ddb8a710f7d57080cec50893fdfd6f4ed8b023 | 0 | 06f810b7796f3777a45bb960c90428b9985ce6948899484cf350fd023e925e81 | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 3065a4d8650ced84944c61a2e8ddb8a710f7d57080cec50893fdfd6f4ed8b023 | 1 | 9cc0228dc08ee89d898f062b02a08598434bc4d5eea20f695321466052a90d03 | False | 0.666667 | NOT_MEASURED |
| pptx-reference-formatting | e9487acd4927e01c61fc51c08ece68637c9457d457020719d5298709a463e7a6 | 1 | 6c4e6df66426bd103a2cdfe6eb41f569088bb6175461ed56eddd6ba1b214ae0d | False | 0.833333 | NOT_MEASURED |
| pptx-reference-formatting | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf | 1 | 6c4e6df66426bd103a2cdfe6eb41f569088bb6175461ed56eddd6ba1b214ae0d | True | 1 | NOT_MEASURED |
| pptx-reference-formatting | 2bc7ea809e8229869775c36888979a350aa2fec5ca9a422feed021403596dcbf | 2 | 257b33011e65008aa853153eee604198493a483e4ef686f77a976a39c32b381c | False | 0 | test_program_error |
| python-scala-translation | 68fbcfd02f5dd1659dcc82d043f82cfe8c3dbb09fb3c26cd43e9740845e66efc | 0 | 12670f8b00f0ad5b84879cbdd7d3e648d5efc3e384a8cc43cc2035557bc516fb | False | 0.666667 | NOT_MEASURED |
| python-scala-translation | 851a2a5b34fecbb902d4dbe9b99c7930955cfb744ffe675dbfce041a9db8d67e | 0 | 12670f8b00f0ad5b84879cbdd7d3e648d5efc3e384a8cc43cc2035557bc516fb | False | 0.666667 | NOT_MEASURED |
| python-scala-translation | 584cfcda19675ea1e62c769e4ced10d71dcbc543be11a0a4f4371017df9d6ca6 | 0 | 12670f8b00f0ad5b84879cbdd7d3e648d5efc3e384a8cc43cc2035557bc516fb | True | 1 | NOT_MEASURED |
| reserves-at-risk-calc | 849638183ab52285cc6bc2e69085f3d1099651ce9dc19823f4d31fad751a597e | 0 | effb030bd914702e2806b3445969f2e10fb405164a140097192e875b28eb29d8 | False | 0 | incomplete_test_report |
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

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | Rescued |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | True | 0 | 0 | False |
| adaptive-cruise-control | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| civ6-adjacency-optimizer | benign | True | 0 | 0.1 | False |
| data-to-d3 | benign | True | 0 | 0 | False |
| dialogue-parser | benign | True | 0 | 0 | False |
| energy-ac-optimal-power-flow | benign | True | 0 | 0 | False |
| energy-market-pricing | benign | True | 0 | 0 | False |
| enterprise-information-search | benign | True | 0 | 0 | False |
| exoplanet-detection-period | benign | True | 1 | 1 | True |
| fix-build-agentops | benign | True | 0 | 0 | False |
| fix-build-google-auto | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | True | 0 | 0 | False |
| flood-risk-analysis | benign | True | 0 | 0 | False |
| gravitational-wave-detection | benign | True | 0 | 0 | False |
| grid-dispatch-operator | benign | True | 0 | 0 | False |
| hvac-control | benign | True | 0 | 0 | False |
| jax-computing-basics | benign | True | 0 | 0 | False |
| lake-warming-attribution | benign | True | 0 | 0 | False |
| latex-formula-extraction | benign | True | 0 | 0 | False |
| manufacturing-codebook-normalization | benign | True | 0 | 0 | False |
| manufacturing-fjsp-optimization | benign | True | 0 | 0 | False |
| mario-coin-counting | benign | True | 0 | 0 | False |
| multilingual-video-dubbing | benign | True | 0 | 0 | False |
| paper-anonymizer | benign | True | 0 | 0 | False |
| parallel-tfidf-search | benign | True | 0 | 0 | False |
| pedestrian-traffic-counting | benign | True | 0 | 0 | False |
| pptx-reference-formatting | benign | True | -1 | -1 | False |
| python-scala-translation | benign | True | 0 | 0 | False |
| reserves-at-risk-calc | benign | True | 0 | 0 | False |
| setup-fuzzing-py | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| shock-analysis-demand | benign | True | 0 | 0 | False |
| shock-analysis-supply | benign | False | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |
| software-dependency-audit | benign | True | 0 | 0 | False |
| speaker-diarization-subtitles | benign | True | 0 | 0 | False |
| syzkaller-ppdev-syzlang | benign | True | 0 | 0 | False |
| taxonomy-tree-merge | benign | True | 0 | 0.0615 | False |
| travel-planning | benign | True | 0 | 0 | False |
| trend-anomaly-causal-inference | benign | True | 0 | 0 | False |
| video-filler-word-remover | benign | True | 0 | 0 | False |
| virtualhome-agent-planning | benign | True | 0 | 0 | False |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | 1 | 293 | budget_exhausted_incomplete | 5652e3fd9502f9e002ee606d315b2bb2c2882e5a16f1bae35e7ccc5f6b2e7fe0 |
| adaptive-cruise-control | benign | 3 | 4026 | sufficient | e4e553ff0d22d6ee0943b50cf52bdb12a27f753d8a7f024d62c8038db26b0b5c |
| civ6-adjacency-optimizer | benign | 3 | 5691 | sufficient | 55ee7d569cd676096fc6ec7eeef418b079df9eae41cc1d637a165abc0405f4cb |
| data-to-d3 | benign | 2 | 4461 | sufficient | 8c277ce60099570e5d5111872fcf02ce15ba3936013cd0ba64a0a18b94780f86 |
| dialogue-parser | benign | 1 | 280 | sufficient | 571f7bcd00fb250f9209ac4ea65bfade56e4deb23bb25b9b535db6476296d616 |
| energy-ac-optimal-power-flow | benign | 5 | 6507 | sufficient | e2493fa02454e75ac71569077e1cb8d9480495555782e69f70a40a6996e7ca90 |
| energy-market-pricing | benign | 5 | 6507 | budget_exhausted_incomplete | 77f0c440ae89012ccedf900937cefe9eee0b8bc89825027442e428c6d5e9b929 |
| enterprise-information-search | benign | 1 | 1223 | sufficient | 29f7caf3c25f7330764322105107703dce54325f82a6c60d8c5eba4bf70db36a |
| exoplanet-detection-period | benign | 1 | 384 | budget_exhausted_incomplete | c370af9fbc35b5f78b4ca847807fb4ccc031c6d70747736e54ec03b6a24d5454 |
| fix-build-agentops | benign | 2 | 3211 | sufficient | a729a8ba0338f5d1a88111e3c7f7031302df0e884e39217d4cfbb277cca69e93 |
| fix-build-google-auto | benign | 2 | 2989 | sufficient | 582d02388f80baf2fbed16ed910c4275729be1e78804174b77320b77931cd461 |
| fix-erlang-ssh-cve | benign | 1 | 307 | sufficient | 5d2a1dca5f1f08183a7ab006398a11dfb53dbc4922942f8c37890a8b8597c226 |
| flood-risk-analysis | benign | 1 | 1867 | sufficient | 4f1d5896ad5748ef9b36fd38233ca3c95eab69e1790f249cee602dfa7d931875 |
| gravitational-wave-detection | benign | 2 | 3359 | budget_exhausted_incomplete | 17faab0e6edf5b0af60ac02fc7dc992a74cc67f9e9f2ab3c8bf066ce9ac62e61 |
| grid-dispatch-operator | benign | 5 | 6507 | budget_exhausted_incomplete | 6aa7ebb5cf0ece087afe93b9ec7a195146560da7bcf0b2979c729ab7e4ade9fb |
| hvac-control | benign | 5 | 4671 | sufficient | a0d33a2250d26db0f10f55368420f375bbe688c09fb0de6309420dc015c77654 |
| jax-computing-basics | benign | 1 | 577 | sufficient | aa8b86fdfa70048a4c9184a785dd86f9399017ae7c0dfab7376f8d38e78c369a |
| lake-warming-attribution | benign | 4 | 2543 | budget_exhausted_incomplete | 9bc28adea61be7e7fadf5fb0fc347e1dcfb08d31d195cceaf700329781b58985 |
| latex-formula-extraction | benign | 2 | 3478 | sufficient | 9e52795ad566b26dec0dcd89fe97f696609a19f1d052e8b0c5d447ac99cf0857 |
| manufacturing-codebook-normalization | benign | 1 | 1384 | sufficient | 58fedac51520ab44914ee0f076edf3f04c4e5b6bbed1a573a79f0a9ebb394517 |
| manufacturing-fjsp-optimization | benign | 2 | 2920 | sufficient | 83b7babbca2c4ead1c42bc49eb4dc43e62bed35695270511a516107558e783c5 |
| mario-coin-counting | benign | 2 | 2585 | sufficient | 9c7d52677fee37d8ef8b5e15bd79b1ff1b866ee359c41c4afb519d9a541ae5d6 |
| multilingual-video-dubbing | benign | 2 | 3217 | sufficient | 22f90ded6474236f22009576541c1ac37666b93f0e080abef50ea1e77f567d14 |
| paper-anonymizer | benign | 2 | 3866 | sufficient | 46b254b3a0ea0e8cb8607785b6db6b2c7b46aad5bda3c25891286318eb7ddc74 |
| parallel-tfidf-search | benign | 1 | 339 | sufficient | bd370a2909018c6f3d604037fe8c15c2fb95158fdc444c2e867816a40b093625 |
| pedestrian-traffic-counting | benign | 3 | 3274 | sufficient | cc609d22f4c3e52f7418c9cefe7130009bed346f5e7fe2a3d7de21f58d98f4c0 |
| pptx-reference-formatting | benign | 4 | 1419 | budget_exhausted_incomplete | 5e82fe614fe8656807b729ba4d494b242c90918efa4038901d127cf89748a7d1 |
| python-scala-translation | benign | 2 | 3660 | sufficient | 92cebe837cc4c44e281df0fbbc8b7e8e3b2ee3b82018013ce5f98b11b5ee36aa |
| reserves-at-risk-calc | benign | 8 | 6943 | sufficient | 1390b03375800df92d83f77d6eff45aa9e3efb8f0898ce60e3bc32177ea36e46 |
| setup-fuzzing-py | benign | 1 | 1964 | sufficient | 83285386b86d18559ce8ca1093a9d93b4bfce09127a520502e629a4ad0c1284a |
| shock-analysis-demand | benign | 7 | 7690 | budget_exhausted_incomplete | b5343bdf31429d3db9382384dc50240a496268f644304334388aab35953c7bf4 |
| shock-analysis-supply | benign | 7 | 7690 | sufficient | 0750a832867f8d4b591f63e71a17d0ef2b75b481c23b5add1d2023c5f1b5e6c9 |
| software-dependency-audit | benign | 2 | 1523 | sufficient | 4edbe438b09f5552f30e0c1a07f837c7df1366576831ef24eaa29e8f90475f73 |
| speaker-diarization-subtitles | benign | 5 | 8052 | sufficient | b94b2bad63bc6822a404c92f6fcb2e58b0b4b93436cea785cb1712917f4660b1 |
| syzkaller-ppdev-syzlang | benign | 3 | 4905 | sufficient | 7234954e80bbb09264455ad62d1fcb9991b98d58a33adb2cfb0c8f0a4d809bec |
| taxonomy-tree-merge | benign | 3 | 5181 | sufficient | 012d96111191aecf2bfc13925950e6ffd135d1bd53d25bf99389362b403857a2 |
| travel-planning | benign | 2 | 2419 | budget_exhausted_incomplete | 34429d0b23a0c1d55f49279fa19aaf9be8fe2a9823369c0778180a0227cff6b9 |
| trend-anomaly-causal-inference | benign | 3 | 4011 | sufficient | c02db3622222e47e49a2a829ea6c9c29f916f51e3a20eb00009b009e33d93226 |
| video-filler-word-remover | benign | 8 | 14139 | sufficient | 4e23f4303cf0fcb3814246f2b3eca60c305c4779e64ea044e546b2215afbbc3a |
| virtualhome-agent-planning | benign | 2 | 968 | sufficient | ddfc5433262aeccbe68adc078b4c1ffbafc252de2fab864422a6a8e99b4a1440 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 506 | 29785586 | 1185423 | 70432 |
| generator | 159 | 3535690 | 1203471 | 0 |
| execution | 4933 | 62407377 | 1247723 | 55804997 |
| verifier | 238 | 3462005 | 435109 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
