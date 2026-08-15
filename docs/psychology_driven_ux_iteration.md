# Iteration 3: Psychology-Driven Input Ease & Dashboard Richness
**Grounded in:** UX research on cognitive load and form psychology, Typeform's published completion-rate data, dashboard perception research (pre-attentive attributes, Gestalt principles), and the Fogg Behavior Model for compliance-driven software. Applied directly to Amara Raja's existing field set — no new inputs added.

---

## Part 1 — Making input effortless (not just "digital")

**The core psychological finding:** users judge how much effort a task will take by what's visibly in front of them right now, not by the total task size. This is exactly why Typeform's one-question-at-a-time format holds a **47.3% completion rate versus a 21.5% industry average for traditional multi-field forms** — more than double, on the same underlying questions.

Applied to Amara Raja's monthly data entry (currently: every field in a category shown at once, blank, on one screen):

- **Break each category into a short guided sequence, one field per screen**, with a visible progress bar ("Water — step 2 of 4"). The Zeigarnik effect — our tendency to keep pursuing an unfinished task once started — means a visible "3 more to go" creates gentle forward pull instead of the flat wall of a 6-field form.
- **Pre-fill with last month's value as a placeholder**, not just a reference line off to the side (as the current tool does). This does two things at once: it reduces the blank-page effect, and it turns data entry into a confirm-or-adjust action instead of a recall-from-memory action — a meaningfully lighter cognitive task.
- **Conditional hide, don't conditional show-empty.** The current tool marks Stack Air Emissions "Not Applicable" but still displays all six empty pollutant fields underneath. Progressive disclosure means the moment "Not Applicable" is selected, those fields simply aren't there — nothing to skip past, nothing to visually process.
- **Ability over motivation, per the Fogg Behavior Model.** For a task like monthly compliance entry — low intrinsic interest, high importance — research is consistent that redesigning to reduce friction (Ability) outperforms trying to make the task feel more exciting (Motivation). Every one of the changes above is an Ability lever, which is the right lever to pull here.
- **A light, dignified progress signal at the organization level** — "4 of 5 categories submitted for July" with a completion indicator per plant — gives leadership a Prompt (the third leg of Fogg's model) without turning a compliance tool into a game. Enterprise software shouldn't feel gamified, but a visible, honest sense of "almost done" is proven motivational scaffolding, not a gimmick.

---

## Part 2 — Making dashboards richer (not just "prettier")

**The core psychological finding:** the brain processes color, size, position, and orientation *before* conscious reading — in under 200 milliseconds. A dashboard that relies on someone reading and comparing numbers is working against how perception actually functions; a dashboard that uses color/position/size to pre-sort what matters is working with it.

Applied to the same metrics Amara Raja already tracks:

- **Pre-attentive color coding on every KPI**, not just in a values table — green for on-target, amber for near-threshold, red for flagged, applied consistently so a glance across the dashboard tells you what needs attention before you've read a single number.
- **Gestalt grouping**, specifically proximity and enclosure: cluster all Water metrics inside one visual boundary, all Safety metrics in another, rather than one long undifferentiated table (which is what the current "Target Dashboard" sheet-tab view does). The brain organizes grouped elements as a category automatically — it's free structure, not an extra design step.
- **Comparison baked into the card, not filed elsewhere.** Every number should carry its target and its trend direction in the same visual unit — this is what the mockup above demonstrates (71.6 KL/Mn Ah, 18% under target, in one glance) instead of the current tool's separate Previous Year / Target / Current Year columns that require manual comparison.
- **Click-to-drill as the default interaction**, not a separate report. The mockup above shows this: clicking "GHG intensity" surfaces exactly which plant and which flagged reading drove the number, in place, without navigating away.
- **Data storytelling over raw display.** A one-line annotation ("diesel generator usage spiked in July due to a grid outage") does more for a viewer's understanding in one sentence than the underlying six data points do on their own — this is the single highest-leverage, lowest-effort addition, since it's just a sentence generated from data already in the system.

---

## Why this sequencing matters

Neither of these changes asks Amara Raja's team to track anything new or work differently in principle — the categories, the approval chain, the underlying numbers are identical to what they have today. What changes is that the software does the cognitive work the human currently has to do: remembering last month's number, scanning a table for what's off-target, mentally grouping related metrics. That's the actual definition of a more valuable product from the same inputs — and it's a materially easier "yes" to get from a customer than a pitch built on new features they'd have to adopt.
