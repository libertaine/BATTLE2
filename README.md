<<<<<<< HEAD
Code and documentation are heavily produced by ChatGPT. 
Mainly a test to see the capabilities or using LLM as a tool to develop a project.


# BATTLE — Engine + Client (Draft README)

## Overview

**BATTLE** is a grid-based competitive simulation.

* The **engine** runs matches and writes results (no UI).
* The **client** is **presentation-only**: it loads engine outputs (JSONL replay + JSON summary) and renders them via pluggable renderers (headless, pygame, future web).

**Design principles**

* Client never owns simulation or scoring — it only **visualizes**.
* Clean separation: `engine/` vs `client/`.
* Modular renderers behind a stable `AbstractRenderer` interface.
* Zero third-party deps for headless; optional **pygame** for 2D visuals.
