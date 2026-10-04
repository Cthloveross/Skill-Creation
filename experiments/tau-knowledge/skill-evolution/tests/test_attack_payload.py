from __future__ import annotations

import unittest

from tau_skill_evolution.core.attack_payload import (
    ATTACK_COMMANDS,
    DELETE_SENTINEL_COMMAND,
    MOCK_API_COMMAND,
    compose_retrieval_attack,
    parse_retrieval_leads,
    parse_shared_retrieval_carrier,
)


class AttackPayloadTests(unittest.TestCase):
    def test_commands_are_guarded_and_have_no_public_destination_or_literal_path(self) -> None:
        self.assertEqual(ATTACK_COMMANDS["mock-api-call"], MOCK_API_COMMAND)
        self.assertEqual(ATTACK_COMMANDS["delete-sentinel"], DELETE_SENTINEL_COMMAND)
        for command in ATTACK_COMMANDS.values():
            self.assertTrue(command.startswith('test "$R2SP_EVALUATOR_MODE" = "1" && '))
            self.assertNotIn("/home/", command)
            self.assertNotIn("rm -rf", command)
        self.assertIn("http://127.0.0.1:18080/r2sp-canary", MOCK_API_COMMAND)
        self.assertNotIn("http://0.0.0.0", MOCK_API_COMMAND)
        self.assertIn('rm -- "$R2SP_EVALUATOR_SENTINEL"', DELETE_SENTINEL_COMMAND)

    def test_composition_preserves_exact_component_bytes(self) -> None:
        lead = b"dataset retrieval lead\n"
        attack = b"dataset-neutral attack\n"
        payload = compose_retrieval_attack(lead, attack)
        self.assertEqual(payload, b"dataset retrieval lead\n\ndataset-neutral attack\n")

    def test_retrieval_file_parses_two_profile_leads_without_normalization(self) -> None:
        raw = (
            b"[mock-api-call]\nmock retrieval terms\n\n[delete-sentinel]\ndelete retrieval terms\n"
        )
        self.assertEqual(
            dict(parse_retrieval_leads(raw)),
            {
                "mock-api-call": b"mock retrieval terms\n",
                "delete-sentinel": b"delete retrieval terms\n",
            },
        )

    def test_shared_retrieval_file_is_one_exact_line(self) -> None:
        raw = b"bank-wide mandatory pre-action reference\n"
        self.assertIs(parse_shared_retrieval_carrier(raw), raw)

    def test_shared_retrieval_file_rejects_sections_or_multiple_lines(self) -> None:
        for payload in (
            b"",
            b"carrier without final LF",
            b"carrier\n\n",
            b"first line\nsecond line\n",
            b"[mock-api-call]\ncarrier\n",
            b"carrier\r\n",
            b"bad\x00carrier\n",
            b"\xff\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_shared_retrieval_carrier(payload)

    def test_composition_rejects_ambiguous_or_invalid_components(self) -> None:
        invalid_pairs = (
            (b"", b"attack\n"),
            (b"lead", b"attack\n"),
            (b"lead\n\n", b"attack\n"),
            (b"lead\n", b"attack"),
            (b"lead\n", b"bad\x00attack\n"),
            (b"lead\n", b"\xff\n"),
        )
        for lead, attack in invalid_pairs:
            with self.subTest(lead=lead, attack=attack), self.assertRaises(ValueError):
                compose_retrieval_attack(lead, attack)

    def test_retrieval_file_rejects_ambiguous_or_invalid_sections(self) -> None:
        for payload in (
            b"",
            b"[mock-api-call]\nlead only\n",
            b"[mock-api-call]\n\n\n[delete-sentinel]\ndelete\n",
            b"[mock-api-call]\nmock\n\n[delete-sentinel]\n",
            b"[delete-sentinel]\ndelete\n\n[mock-api-call]\nmock\n",
            b"[mock-api-call]\nmock\r\n\r\n[delete-sentinel]\ndelete\r\n",
            b"[mock-api-call]\nline one\nline two\n\n[delete-sentinel]\ndelete\n",
            b"[mock-api-call]\nbad\x00\n\n[delete-sentinel]\ndelete\n",
            b"[mock-api-call]\n\xff\n\n[delete-sentinel]\ndelete\n",
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                parse_retrieval_leads(payload)


if __name__ == "__main__":
    unittest.main()
