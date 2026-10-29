# Demo Video Script (10-15 min)

Record with real keys for best output (or `CONTENTBLITZ_MOCK=1` to show the flow offline).
Keep the Settings sidebar visible so provider chains and usage are on screen; point at the six-station pipeline as it lights up.

| # | Time | Show | Say / point out |
|---|---|---|---|
| 1 | 0:00 | Landing page, Settings sidebar | Six agents, LangGraph, provider chains, offline mode toggle |
| 2 | 1:00 | *"Research the latest trends in sustainable packaging for e-commerce"* | Live progress per agent; Research tab: 10 sources, `[n]` citations, research quality, strategist report |
| 3 | 3:00 | *"Now write an SEO blog post about it"* | Router reuses research (no new search); Content → Blog post: keyword density, meta length, H-structure, Flesch, internal links, quality dimensions |
| 4 | 5:00 | *"Make it shorter"* | Multi-turn refinement → revision 2, re-scored |
| 5 | 6:00 | *"Turn it into a LinkedIn post"* | 1,300-1,600 chars, 8-12 hashtags, hook + CTA, LinkedIn preview card |
| 6 | 7:00 | *"Make it more casual"* | Context-aware routing to the LinkedIn agent |
| 7 | 7:45 | *"Create an image for the LinkedIn post"* | Prompt enhancement shown, DALL-E 3 image, saved PNG + metadata |
| 8 | 8:45 | Settings: untick offline mode, enter an invalid OpenAI key under API keys, re-run an image request | Fallback chain: `dalle3` auth error (not retried) → next provider; the attempts table shows it. Chat shows graceful handling |
| 9 | 10:00 | *"Create a campaign about urban beekeeping"* | All six agents in one turn |
| 10 | 11:00 | *"Write a 3-part blog series about B2B podcast marketing"* | Content series → Export → WordPress XML |
| 11 | 12:00 | Content tab edit + "Save and re-score" | Human-in-the-loop; Export: MD / HTML / TXT / PDF / WXR / scheduler JSON / PNG |
| 12 | 13:00 | Settings → Brand voice → paste samples → **Learn voice from samples** | Voice learning; next post follows it |
| 13 | 14:00 | Terminal: `pytest --cov` and `make test-ui` | 129 Python tests (95% coverage, incl. real-browser e2e) + 16 frontend tests; CI workflow |
