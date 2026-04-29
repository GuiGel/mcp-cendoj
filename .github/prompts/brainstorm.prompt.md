---
name: brainstorm
description: "Launch a multi-perspective brainstorming session. Three parallel AI agents (Critic, Optimist, Realist) independently explore a problem, then synthesize their outputs into a structured report."
agent: Brainstorm
argument-hint: "Describe the problem or topic to brainstorm..."
---

Brainstorm the following topic using three independent parallel perspectives:

**Problem / Topic:** ${input:topic:Describe the problem or topic to brainstorm...}

Run the `bs-critic`, `bs-optimist`, and `bs-realist` subagents **in parallel**.
Each agent independently explores the problem through its own lens without seeing the others' outputs.
Then synthesize all three perspective outputs into a final brainstorming report.
