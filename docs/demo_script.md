# Demo Video Script (10-15 min)

Record with real keys and SMTP for best output (or `make demo` to show the flow offline, with codes on screen).
Point at the reply listing which agents ran; open the admin dashboard in a second window for provider chains and usage.

| # | Time | Show | Say / point out |
|---|---|---|---|
| 0 | 0:00 | Sign-in card: enter an unregistered email | *"… isn't registered"* error with **Sign up with this email**; sign up with name + email, enter the 6-digit code from the inbox; the sidebar shows your name, **New conversation** and recent conversations |
| 1 | 1:00 | Workspace, then `/admin` as an admin | Six agents, each a LangGraph subgraph; LangChain models with retries and fallbacks; customers see no keys or usage, admins set offline mode / provider priority / quality bar and see usage |
| 2 | 1:00 | *"Research the latest trends in sustainable packaging for e-commerce"* | Live progress per agent (the Research station shows sources and claims verified; its three searches run in parallel); Research tab: 10 sources with credibility ratings, `[n]` citations with fact-check badges, research quality, strategist report |
| 3 | 3:00 | *"Now write an SEO blog post about it"* | Router reuses research (no new search); Content → Blog post: keyword density, meta length, H-structure, Flesch, internal links, quality dimensions; if the draft scores below the threshold the blog subgraph rewrites it automatically |
| 4 | 5:00 | *"Make it shorter"* | Multi-turn refinement → revision 2, re-scored |
| 5 | 6:00 | *"Turn it into a LinkedIn post"* | 1,300-1,600 chars, 8-12 hashtags, hook + CTA, LinkedIn preview card |
| 6 | 7:00 | *"Make it more casual"* | Context-aware routing to the LinkedIn agent |
| 7 | 7:45 | *"Create an image for the LinkedIn post"* | Prompt enhancement shown, DALL-E 3 image, saved PNG + metadata |
| 8 | 8:45 | Put an invalid `OPENAI_API_KEY` in `.env`, restart, untick offline mode on `/admin`, re-run an image request | Fallbacks: the LangChain model chain skips OpenAI after one `AuthenticationError` (not retried) and the next model answers; the image chain does the same for `dalle3`, shown in the *Provider attempts* table. Chat shows graceful handling |
| 9 | 10:00 | *"Create a campaign about urban beekeeping"* | All six agents in one turn |
| 10 | 11:00 | *"Write a 3-part blog series about B2B podcast marketing"* | Content series → Export → WordPress XML |
| 11 | 12:00 | Content tab edit + "Save and re-score" | Human-in-the-loop; Export: MD / HTML / TXT / PDF / WXR / scheduler JSON / PNG |
| 12 | 13:00 | Sidebar → Brand voice → paste samples → **Learn voice from samples** | Voice learning; next post follows it |
| 12b | 13:30 | LangSmith (if enabled) | One trace per turn: each agent subgraph, its nodes, prompts, retries and fallbacks |
| 12c | 13:45 | Terminal: `make bench` | Latency, LLM calls, tokens, cost and quality per scenario; `make bench-live` for provider comparisons |
| 13 | 14:00 | Terminal: `pytest --cov` and `make test-ui` | 167 Python tests (96% coverage, incl. real-browser sign-in e2e and the real ChatOpenAI client) + 27 frontend tests; CI workflow |
