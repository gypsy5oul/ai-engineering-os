---
name: rag-engineering
description: Design and evaluate retrieval-augmented generation - what gets indexed, how it is chunked, how it is retrieved, and how retrieval quality is measured separately from answer quality. Use when a model needs to answer from a corpus it was not trained on.
---

# RAG engineering

Retrieval-augmented generation is two systems wearing one name: a **retrieval**
system that finds candidate context, and a **generation** system that answers
from it. Almost every RAG failure is a retrieval failure being debugged as a
generation failure, because the symptom appears in the answer.

So the first rule is the one everything else depends on: **measure retrieval
separately from generation.** If you cannot say whether the right document was in
the context, you cannot tell a prompt problem from an index problem, and you will
tune the prompt for weeks.

## Do you need it

Retrieval is a component, an index, an embedding model, a re-indexing job and a
second failure mode. Before adding it, say what the alternatives fail:

- The corpus fits in the context window → put it in the context window.
- The corpus is small and structured → a query is more precise than a similarity
  search and it cannot half-match.
- The answer is always from one known document → fetch that document.
- The corpus changes rarely and the questions are known → cache the answers.

RAG earns its place when the corpus is too large to send, unstructured enough
that queries do not capture intent, and changes often enough that answers cannot
be precomputed. That is a real and common situation; it is just not every
situation. This is a `${CLAUDE_PLUGIN_ROOT}/policies/simplicity-policy.json` entry like any other.

## What gets indexed

**Decide what a retrievable unit is before deciding how to split one.** The unit
is whatever fully answers a question on its own: a section, a procedure, a table
row with its header. Chunking is how you approximate that when documents do not
come in those shapes.

- **Fixed-size chunking is a starting point, not a design.** It splits mid-
  sentence, mid-table and mid-procedure, and the chunk that gets retrieved is the
  half without the answer.
- **Prefer structural boundaries** — headings, sections, list items, rows —
  because those are the boundaries the author already chose.
- **Carry the context down.** A chunk that says "it must be rotated every 90
  days" without saying what "it" is retrieves well and answers nothing. Prefix
  each chunk with its document title and heading path.
- **Overlap is a patch, not a fix.** It reduces boundary loss and doubles the
  index. Use it when structure genuinely is not available.
- **Index what is searchable, return what is readable.** They need not be the
  same span: embed the chunk, return the section it came from.

## Retrieving

- **Hybrid beats either alone in most corpora.** Semantic search finds paraphrase
  and misses exact identifiers; keyword search finds `ERR_4021` and misses "the
  connection error". Real questions contain both.
- **Re-ranking is usually the cheapest large improvement**, because it lets you
  retrieve broadly and pass narrowly.
- **Filter before you search where you can.** Tenant, language, document status,
  recency. A permission filter applied after retrieval is a permission filter
  that has already leaked the existence of the document.
- **Decide what "nothing relevant" looks like.** A similarity search always
  returns something. Without a relevance floor, the system answers every question
  from the least-irrelevant document it has, confidently.

## Access control

Retrieval is where an AI system leaks. The index contains everything anybody
indexed; the query does not know who is asking unless you tell it.

- Filter by the **asking user's** permissions, at query time, in the query — not
  by filtering results afterwards, and never by trusting the model to withhold
  something it can see.
- Re-check at answer time if the corpus permissions can change between indexing
  and asking.
- Treat retrieved content as untrusted: it was written by someone, and it is
  about to be read by a model as if it were instructions. See
  `prompt-engineering`.

## Measuring it

Two evaluations, and the retrieval one comes first:

**Retrieval quality**, on a set of questions with known correct documents:
recall at *k* (was the right chunk in the top *k*?), precision, and the rate at
which nothing relevant was returned. This needs no model call and is cheap enough
to run on every change to chunking, embedding or the index.

**Answer quality**, on the same set: correctness given the retrieved context, and
— the one people forget — **groundedness**: did the answer come from the context,
or from the model's own knowledge? An ungrounded correct answer is a wrong system
that happens to be right today.

Attribution is what makes groundedness checkable. Have the answer cite the chunk
it used, and verify the citation exists.

## Keeping it current

An index is a cache of a corpus and it goes stale the way caches do.

- Say how a changed document gets re-indexed, and how a deleted one gets removed.
  A deleted document that stays in the index is a retrieval of something the
  organization decided nobody should see.
- **Re-embedding is a migration.** Changing the embedding model invalidates every
  vector, and a partial re-embed leaves an index where two things measure
  distance differently.
- Version the index alongside the prompt and the model. Three inputs, three
  versions, one recorded output.

## Rules

- Measure retrieval before generation, or you will debug the wrong system.
- Every chunk carries enough context to be understood alone.
- Permission filtering happens in the query, not in the results.
- Define what "nothing relevant" returns, or the system will always answer.
- The embedding model is a technology decision (AP-03), and changing it is a
  migration.
