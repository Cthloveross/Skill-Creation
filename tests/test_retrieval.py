import unittest

from r2sp.models import Resource
from r2sp.retrieval import DeterministicBM25, tokenize


class DeterministicBM25Tests(unittest.TestCase):
    def test_relevant_document_ranks_first_without_exposing_body(self) -> None:
        resources = (
            Resource("b", "email", "send", "Send email", "Send a message to a recipient"),
            Resource("a", "calendar", "create", "Create event", "Schedule a calendar meeting"),
        )
        retriever = DeterministicBM25(resources, top_k=2)

        results = retriever.search("schedule calendar meeting")

        self.assertEqual(results[0].resource_id, "a")
        for result in results:
            encoded = result.to_dict()
            self.assertNotIn("body", encoded)
            self.assertNotIn("snippet", encoded)
            self.assertNotIn("score", result.to_agent_dict())

    def test_equal_scores_use_resource_id_as_stable_tie_break(self) -> None:
        resources = (
            Resource("z", "app", "z", "Same", "identical tokens"),
            Resource("a", "app", "a", "Same", "identical tokens"),
        )
        expected = ["a", "z"]

        first = DeterministicBM25(resources, top_k=2).search("identical")
        second = DeterministicBM25(tuple(reversed(resources)), top_k=2).search("identical")

        self.assertEqual([hit.resource_id for hit in first], expected)
        self.assertEqual([hit.resource_id for hit in second], expected)

    def test_unicode_normalization_and_casefold_are_fixed(self) -> None:
        self.assertEqual(tokenize("ＣＡＬＥＮＤＡＲ_api"), ("calendar", "api"))
        self.assertEqual(tokenize("Calendar-API"), ("calendar", "api"))

    def test_empty_query_returns_no_results(self) -> None:
        resource = Resource("a", "calendar", "create", "Create", "body")
        retriever = DeterministicBM25((resource,))
        self.assertEqual(retriever.search("   "), ())
        self.assertEqual(retriever.read_doc("a"), resource)
        with self.assertRaises(KeyError):
            retriever.read_doc("missing")


if __name__ == "__main__":
    unittest.main()
