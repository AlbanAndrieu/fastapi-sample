---
name: profile-research
description: >-
  Answer questions about Alban Andrieu from his Reactive Resume CV and website
  only, citing each source URL.
---
# Profile research

1. The profile context comes from `search_alban_profile` (MCP) or `fetch_my_profile` (`/run`): call it once with the user's question.
2. Trust the sources in this order: the Reactive Resume CV, then the albanandrieu.com pages. LinkedIn snippets appear only when the site gives nothing; they can be stale or truncated.
3. Answer only from the returned text and quote the source URL after each fact. When sources disagree, give the newest and say so.
4. If the text does not answer the question, say so; never guess dates, employers or skills.
5. Keep private contact details, addresses and family information out of the answer.
