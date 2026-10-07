# Background: GitHub repository activity counting (frozen evidence summary)

Key rules this Skill follows (from the task background document):

- Separate the cohort (records created in a half-open UTC window `[start, end)`)
  from the event being measured. Creation uses `createdAt`; merge timing uses
  `mergedAt`; closure during a period uses `closedAt`; current status uses
  `state`. A record created in one month and closed later belongs to the
  creation cohort but not to an earlier month's closure count.
- GitHub exposes merged PRs distinctly from unmerged closed PRs. When a schema
  lists `merged` and `closed` separately, do not assume `closed` includes
  merged; document the choice. This Skill defaults `closed` = unmerged-closed.
- Time-to-merge for a merged PR = `mergedAt - createdAt`, computed in UTC with
  full precision, averaged only over records with a valid merge timestamp, and
  rounded only at the final aggregate.
- Top contributor: group by a stable author login, exclude null authors from
  deleted accounts, and apply a documented deterministic tie rule (here:
  alphabetically smallest login).
- Bug issues: substring match on label names (case-insensitive `bug`), counting
  each issue once even if multiple labels match; keep this independent of the
  closure-event rule.
- Retrieval completeness: list/search operations are paginated and may default
  to open records only. Request all states, follow pagination to the end,
  dedupe by node ID or repo-local number, and check boundary timestamps so
  midnight records are counted once. The GraphQL `search` connection caps at
  1000 results; narrow the window and sum if that cap is hit.

References:
- PullRequest object: https://docs.github.com/en/graphql/reference/objects#pullrequest
- Issue object: https://docs.github.com/en/graphql/reference/objects#issue
- Pagination: https://docs.github.com/en/graphql/guides/using-pagination-in-the-graphql-api
