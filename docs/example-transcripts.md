# Example transcripts

These short examples are illustrative. The evidence excerpts below are fixtures used to demonstrate expected behavior, not real market reports.

## Sourced question

**User:** What are the latest risks facing Example Motors?

**Trace:** Plan two checks (company disclosures and independent coverage) → Exa returns 5 sources per query → evidence review sees one primary disclosure and several independent reports → Groq synthesizes.

**Agent:** The sources describe a supply constraint and a regulatory review. The company disclosure confirms the constraint; independent coverage discusses possible cost impact. The cost impact is interpretation, not a quantified company forecast. **Confidence: Moderate** because the operational issue appears in both company and independent sources, while its financial effect is not quantified. [1] [2]

## Missing evidence

**User:** Did Example Motors receive a regulatory penalty today?

**Trace:** Plan checks a current company disclosure and regulator notice → Exa returns no usable results → evidence check marks coverage low.

**Agent:** I could not verify a penalty from the sources available in this search. That does not establish that no penalty was issued. Check the regulator's latest notice or the company's exchange filing before relying on an answer. **Confidence: Low.**

## Contradictory evidence

**User:** How many units did Example Motors deliver last quarter?

**Trace:** Plan checks the company release and independent reporting → evidence excerpts show 42,100 units in the company release and 41,200 in a news report → answer preserves the discrepancy.

**Agent:** The sources disagree: the company release reports 42,100 units [1], while the news report says 41,200 [2]. The company release is the primary source, but the discrepancy should be resolved against the underlying filing and definition of “deliveries.” I would use 42,100 provisionally and flag the mismatch rather than average the figures. **Confidence: Moderate.**

## Unnecessary tool call

**User:** Tell me more.

**Trace:** Planner recognizes a short follow-up and skips external search; it relies on the existing conversation and evidence.
