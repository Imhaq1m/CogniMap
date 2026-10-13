# CogniMap System Development Plan & Execution Order

You are building **CogniMap**, a local learning tool built for a University Final Year Project (FYP). The system scaffolds student thinking through Bloom's Taxonomy using local document parsing and an API LLM.

**CRITICAL INSTRUCTION FOR AI:** Execute the implementation strictly in the chronological phases and steps outlined below. Do not skip ahead to later phases until the prerequisite phase is fully implemented.

---

## Phase 1: Core Architecture & Main Heading Workflow

### Step 1: Initial View & Material Upload
- **UI:** Dark mode interface with a high-contrast dark gray sidebar and main workspace
- **Functionality:** Users upload learning PDFs via "Select Files" and trigger concept extraction using the "Extract Concepts" button

### Step 2: Extracted Concepts Modal & Manual Customization
- **UI & Flow:** A modal titled "Extracted Concepts" pops up showing parsed main and sub-headings with selection checkboxes and inline renaming (pen icon)
- **Manual Additions:** White lines under main headings (to add sub-headings) and at the bottom (to add main headings) turn into a `+` hover trigger
- **Styling Rule:** User-added concepts must be styled in **blue** to differentiate them from AI-extracted concepts

### Step 3: Levels 1 & 2 (Remember/Understand)
- **Transition & Workspace:** A guide modal introduces Levels 1-2. The workspace filters to show **only Main Headings** to avoid overload
- **Interaction:** Clicking a concept opens a sliding right panel with the original source definition (or LLM-generated scope definition) and a paraphrase input box
- **Evaluation:** The backend LLM checks accuracy, originality, and provides constructive hints (leniently). User-made (blue) concepts lack source definitions, have a warning label, and bypass LLM evaluation. A bottom-left progress meter tracks completion percentage

### Step 4: Level 3 (Apply)
- **Transition & Setup:** Triggers automatically at 100% on Level 1-2 with a congratulatory modal. The sidebar shows a "Generate Scenario" button
- **Scenario Flow:** Clicking "Generate Scenario" prompts the LLM to create a real-world scenario from workspace concepts
- **Validation:** Users select related concepts and type justifications. The LLM provides multi-tier feedback (explaining wrong concepts, hinting at wrong justifications, or marking correct)
- **Math Metric:** Total required scenarios = `Math.ceil(conceptCount / 3)`

### Step 5: Level 4 (Analyze)
- **Transition & Rules:** Triggers at 100% on Level 3 with a summary modal. The sidebar displays rules/recommendations (each concept must have $\ge 1$ connection, max 3 connections per concept)
- **Linking Flow:** Users drag from one concept node to another. A floating "Type of edges" selection panel appears with radio buttons (causes, leads to, depends on, includes, contrasts with, applied in, influences, consists of, custom)
- **Completion:** A dimmed "Finish" button activates only when every concept has at least one link

### Step 6: Level 5 (Evaluate)
- **Transition & Dimming:** Triggers at 100% on Level 4. Existing links render in a **dimmed** visual state.
- **Probing Analyst Modal:** Clicking any link opens a modal where the AI challenges the user from two perspectives: *"Why does this relationship exist?"* and *"When might this relationship fail?"*.
- **Evaluation & Completion:** Both answers are evaluated independently with separate feedback/hints. Once correct, the link brightens back to its normal color, and the progress meter advances to 100%

---

## Phase 2: Sub-Headings Workflow & Full Integration

### Step 7: Sub-Heading Expansion & Learning Loop
- **Transition:** Triggered after Level 5 completion with a summary modal
- **Restricted Selection Modal:** Displays the concept tree again, but **main headings are dimmed** (already completed) and **no new main headings can be added**—only sub-headings can be added or renamed
- **Recycling the Loop:** Confirming selection merges sub-headings into the workspace, running them through the exact same 5-stage learning cycle (Remember $\rightarrow$ Evaluate)

### Step 8: Historical Review System (Sliding Right Panel)
- **Dropdown Feature:** Located at the bottom right of the sliding concept details panel
- **Phase Rules:** 
  - Allows users to inspect previous stages' activities and answers (e.g., viewing Stage 1-3 inputs while in Stage 4/5)
  - Main headings (fully completed through Phase 2) allow review of Stages 1, 2, 3, and 5 (skipping Stage 4 since links are visible on the canvas). Sub-headings follow standard phase-by-phase history rules
