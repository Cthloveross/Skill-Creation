# skillsbench run report

Protocol: `skillsbench.skill-evolution.v1`

End-to-end rates use the full 85-task arm denominator. Measured means use only valid measurements.
Missing measurements remain null in JSON and NOT_MEASURED here.
The S0 evaluation also represents the frozen control; it is not another sample.

## Final arms

| Condition | Arm | Denominator | Chains | Measured | Utility mean | End-to-end utility |
| --- | --- | --- | --- | --- | --- | --- |
| benign | evolved | 85 | 2 | 2 | 0 | 0 |

## Actual content versions

| Condition | Version | Chains | Measured | Utility mean | Stops |
| --- | --- | --- | --- | --- | --- |
| benign | 0 | 2 | 2 | 0 | {} |
| benign | 1 | 2 | 2 | 0 | {'verification_program_error_exhausted': 1} |
| benign | 2 | 1 | 1 | 0 | {} |
| benign | 3 | 1 | 1 | 0 | {} |
| benign | 4 | 1 | 1 | 0 | {} |
| benign | 5 | 1 | 1 | 0 | {} |
| benign | 6 | 1 | 1 | 0 | {} |
| benign | 7 | 1 | 1 | 0 | {} |
| benign | 8 | 1 | 1 | 0 | {} |
| benign | 9 | 1 | 1 | 0 | {} |
| benign | 10 | 1 | 1 | 0 | {} |
| benign | 11 | 1 | 1 | 0 | {} |
| benign | 12 | 1 | 1 | 0 | {} |
| benign | 13 | 1 | 1 | 0 | {} |
| benign | 14 | 1 | 1 | 0 | {} |
| benign | 15 | 1 | 1 | 0 | {'revision_budget_exhausted': 1} |

## Task stops

| Task | Condition | Stop | Versions | Revision attempts | Oracle calls | Final hash |
| --- | --- | --- | --- | --- | --- | --- |
| 3d-scan-calc | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| adaptive-cruise-control | benign | verification_program_error_exhausted | 2 | 1 | 0 | 42c584041865309b926e287d3ac82730b4d1891a8fcbdbc0b81a70ae9cfb8a95 |
| azure-bgp-oscillation-route-leak | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| citation-check | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| civ6-adjacency-optimizer | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| court-form-filling | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| crystallographic-wyckoff-position-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| dapt-intrusion-detection | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| data-to-d3 | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| dialogue-parser | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| dynamic-object-aware-egomotion | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-phase-association | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| earthquake-plate-calculation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| econ-detrending-correlation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| energy-ac-optimal-power-flow | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| energy-market-pricing | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| enterprise-information-search | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| exceltable-in-ppt | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| exoplanet-detection-period | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| financial-modeling-qa | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| find-topk-similiar-chemicals | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-build-agentops | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-build-google-auto | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-druid-loophole-cve | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-erlang-ssh-cve | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| fix-visual-stability | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| flink-query | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| flood-risk-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| gh-repo-analytics | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| glm-lake-mendota | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| gravitational-wave-detection | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| grid-dispatch-operator | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| hvac-control | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| invoice-fraud-detection | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| jax-computing-basics | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| jpg-ocr-stat | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| lab-unit-harmonization | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| lake-warming-attribution | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| latex-formula-extraction | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| lean4-proof | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-codebook-normalization | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-equipment-maintenance | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| manufacturing-fjsp-optimization | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| mario-coin-counting | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| mars-clouds-clustering | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| multilingual-video-dubbing | benign | revision_budget_exhausted | 16 | 15 | 0 | 3c584784b413a041de82416805daf7449a46cd2b595a12841823a955511daee2 |
| offer-letter-generator | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| organize-messy-files | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| paper-anonymizer | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| parallel-tfidf-search | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pddl-tpp-planning | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pdf-excel-diff | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pedestrian-traffic-counting | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pg-essay-to-audiobook | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| powerlifting-coef-calc | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| pptx-reference-formatting | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| protein-expression-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| python-scala-translation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| quantum-numerical-simulation | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| r2r-mpc-control | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| react-performance-debugging | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| reserves-at-risk-calc | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| sales-pivot-analysis | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| sec-financial-report | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| seismic-phase-picking | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| setup-fuzzing-py | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| shock-analysis-demand | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| shock-analysis-supply | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| simpo-code-reproduction | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| software-dependency-audit | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| speaker-diarization-subtitles | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| spring-boot-jakarta-migration | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| suricata-custom-exfil | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| syzkaller-ppdev-syzlang | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| taxonomy-tree-merge | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| threejs-structure-parser | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| threejs-to-obj | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| travel-planning | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| trend-anomaly-causal-inference | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| video-filler-word-remover | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| video-silence-remover | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| video-tutorial-indexer | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| virtualhome-agent-planning | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| weighted-gdp-calc | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |
| xlsx-recover-data | benign | not_started | 0 | 0 | 0 | NOT_MEASURED |

## Independent measurements

| Task | Version | Role | Package hash | Status | Utility | Reward | Official checks passed | Official checks total | Official check rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| adaptive-cruise-control | 0 | S0 | b3283e71f6c86a3f93bf0f21534a3704f428da286bb7664a224e6cc646073b3e | MEASURED | False | 0 | 5 | 12 | 0.416667 |
| adaptive-cruise-control | 1 | S1 / final | 42c584041865309b926e287d3ac82730b4d1891a8fcbdbc0b81a70ae9cfb8a95 | MEASURED | False | 0 | 5 | 12 | 0.416667 |
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

Official reward comes from the pinned grader's reward file. Unavailable check counts remain NOT_MEASURED. Bank reference actions and canary ASR do not apply to SkillsBench.

## Surrogate checks

| Task | Package hash | Test version | Test hash | Passed | Pass rate | Failure |
| --- | --- | --- | --- | --- | --- | --- |
| adaptive-cruise-control | b3283e71f6c86a3f93bf0f21534a3704f428da286bb7664a224e6cc646073b3e | 0 | d7ed543072dfb68a1fe5f93080cf75cda4dce2ef6b86539453dad2c98e017b53 | False | 0.4 | NOT_MEASURED |
| adaptive-cruise-control | 42c584041865309b926e287d3ac82730b4d1891a8fcbdbc0b81a70ae9cfb8a95 | 0 | d7ed543072dfb68a1fe5f93080cf75cda4dce2ef6b86539453dad2c98e017b53 | False | 0.8 | verifier_reported_test_program_error |
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

## Paired evolution progress

| Task | Condition | Paired measured | Utility delta | Reward delta | Rescued |
| --- | --- | --- | --- | --- | --- |
| adaptive-cruise-control | benign | True | 0 | 0 | False |
| multilingual-video-dubbing | benign | True | 0 | 0 | False |

## Frozen acquisition

| Task | Condition | Documents | Tokens | Stop | Base hash |
| --- | --- | --- | --- | --- | --- |
| adaptive-cruise-control | benign | 3 | 4026 | sufficient | 81c6c1af66a0f2f3738e69f39aba0a99309eb9dcf16c557f099ae2b9d8098845 |
| multilingual-video-dubbing | benign | 3 | 3504 | sufficient | d9ff6e885ae65aeaea41ea1c89951ed2c21a35b894d4877a63b5c1137a2fcf24 |

## Provider token usage

| Role | Responses | Input tokens | Output tokens | Cached input tokens |
| --- | --- | --- | --- | --- |
| analyzer | 9 | 221688 | 10781 | 0 |
| generator | 18 | 482943 | 150514 | 0 |
| execution | 383 | 3278428 | 92307 | 2856343 |
| verifier | 21 | 304097 | 17015 | 0 |

Dollar cost: NOT_MEASURED; provider responses do not include billing charges. Usage includes successful responses; unknown requests may incur unreported charges.
