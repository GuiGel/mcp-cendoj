---
name: brainstorm-deepen
description: "Deepen exploration of specific ideas from a previous brainstorming session. Run a focused second-round analysis on selected ideas using all three perspectives."
agent: Brainstorm
argument-hint: "Paste or describe the ideas you want to explore further..."
---

Deepen the analysis of these specific ideas from a prior brainstorming session:

**Ideas to deepen:** ${input:ideas:Paste the ideas or concept you want to explore further...}

**Original context (optional):** ${input:context:Original problem statement or brainstorming context...}

Run a focused second-round analysis:
- Invoke `bs-critic` to stress-test each selected idea: what are the failure modes, hidden dependencies, and risks?
- Invoke `bs-optimist` to extend each idea: what's the amplified or recombined version?
- Invoke `bs-realist` to prototype each idea: what are the concrete first steps, required resources, and realistic timeline?

Then synthesize into a **Deepened Exploration Report** with actionable next steps for each idea.
