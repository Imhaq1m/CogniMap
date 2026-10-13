**UI Component & Layout Specification: Initial Document Upload View (CogniMap)**

Please implement the initial layout for the CogniMap app as shown in the interface design. 

#### 1. Layout Structure
- **Global Theme:** Dark mode aesthetic with a high-contrast dark gray sidebar and a main content area taking up the rest of the screen.
- **Brand Header:** Top-left corner features the application name **"CogniMap"** in clean, bold typography.
- **Sidebar (Manage Materials Panel):** 
  - Positioned on the left side, containing a card/container titled **"Manage Materials"**.
  - Inside the card, include:
    1. A primary action button labeled **"Select Files"** (for uploading learning PDFs).
    2. A secondary action button below it labeled **"Extract Concepts"**.
- **Main Content Area:** A large, empty workspace placeholder on the right side of the screen, reserved for displaying the interactive concept graph and learning modules once processing is complete.

#### 2. Functional Flow & Behavior
- **Step 1 (Upload):** The user clicks "Select Files" to upload their learning document (PDF) as mentioned in the welcoming flow.
- **Step 2 (Processing Trigger):** Once the file is selected, the user clicks **"Extract Concepts"** to initiate backend processing (parsing the PDF, breaking down concepts, and building the foundational graph for Bloom's Taxonomy progression).
- **State Management:** Prior to extraction, the "Extract Concepts" button should be disabled or waiting until a valid PDF file is loaded.

**UI Component & Functional Specification: Extracted Concepts Selection Modal (CogniMap)**

Please implement the modal component that appears after a user uploads learning materials and triggers the concept extraction process.

#### 1. Layout & Structure
- **Sidebar Update:** In the left sidebar under "Manage Materials", show the uploaded file name (e.g., "File 1") with a close/delete icon ("x") next to it.
- **Modal Container:** A centered popup modal titled **"Extracted Concepts"** with a close button ("x") in the top-right corner.
- **Hierarchy Representation:** 
  - The modal displays extracted concepts in a structured tree or nested list format consisting of **Main Headings** and **Sub Headings**.
  - Example structure shown:
    - Main Heading: "Machine Learning"
      - Sub Heading: "Roles of Statistics"
      - Sub Heading: "Role of Computer Science"
    - Main Heading: "Applications"
      - Sub Heading: "Retail"
      - Sub Heading: "Finance"

#### 2. Interactive Features & Controls
- **Checkboxes:** Each main heading and sub-heading has a checkbox on the left, allowing users to select or deselect specific concepts they want to learn
- **Inline Editing (Rename):** A pen/edit icon is positioned on the right side of each heading row. Clicking this allows the user to rename the main heading or sub-heading inline
- **Confirmation Action:** A prominent primary button labeled **"Confirm Selection"** (styled in green) is placed at the bottom of the modal to lock in the chosen concepts and proceed

#### 3. Functional Flow (Behind the Scenes)
- When the user presses "Extract Concepts" on the sidebar, files are sent to a backend LLM API to parse headings and subheadings.
- The returned JSON structure populates this modal dynamically.
- Clicking "Confirm Selection" passes the finalized, user-edited concept list back to the system to generate the interactive learning paths and concept graph.

**UI Component & Functional Specification: Manual Concept Addition & Custom Styling (CogniMap)**

Please implement the manual concept insertion feature and visual differentiation logic within the "Extracted Concepts" modal.

#### 1. Interactive Insertion Lines (Hover Triggers)
- **Placement of Lines:** 
  - Place a horizontal white line beneath each Main Heading section (used to add sub-headings under that specific main heading).
  - Place a final horizontal white line at the very bottom of the concept list (used to add a new Main Heading).
- **Hover Behavior:** 
  - When the user hovers over any of these white lines, it smoothly transitions into a plus sign (`+`) accompanied by a clear label (**"Add Sub-Heading"** or **"Add Main Heading"**).
- **Action Trigger:** Clicking the line/plus sign opens an inline input prompt or small modal allowing the user to type the title for the new concept.

#### 2. Visual Differentiation (AI vs. User-Created)
- **AI-Extracted Concepts:** Rendered in the standard neutral/dark card theme.
- **User-Added Concepts:** Any heading or sub-heading manually added by the user must be styled with a **blue** accent (e.g., blue background, border, or highlight) to clearly distinguish user-created concepts from those parsed automatically from the uploaded PDF files.

#### 3. Data Structure Impact
- Ensure the state tracking the selected concepts correctly flags whether a concept is `source: "extracted"` or `source: "user_added"` so that the downstream concept graph and backend learning path can handle them appropriately upon clicking "Confirm Selection".

**UI Component & Functional Specification: Level 1 - 2 (Remember/Understand) Workflow (CogniMap)**

Please implement the Level 1 and Level 2 learning phase, including the introductory guide modal, workspace filtering, definition panels, LLM evaluation criteria, user-made concept handling, and progress tracking.

#### 1. Introductory Guide Modal
- **Trigger:** Immediately after the user clicks "Confirm Selection" from the concept tree modal
- **Content:** A centered popup modal titled **"Level 1 - 2: Remember/Understand"** explaining that users must explain each concept in their own words, focusing on meaning rather than rote memorization
- **Action:** Includes a **"Continue"** button to dismiss the modal and enter the workspace

#### 2. Workspace & Concept Graph Filtering
- **Display Rule:** To prevent information overload, the workspace displays **only Main Heading concepts** at this stage
- **Visual Styling:** 
  - Standard/Extracted concepts appear as neutral graph nodes
  - User-added concepts are distinctly colored in **blue**

#### 3. Definition & Paraphrase Drawer/Modal
- **Trigger:** Clicking a concept node opens a side panel or modal displaying:
  1. **Concept Title** (editable or viewable)
  2. **Original Definition box:** Shows the definition pulled from the source document (with page references if available). If no explicit definition exists in the source, the LLM generates an appropriate definition within the document's scope
  3. **Your Paraphrase box:** An input area where the user writes their own explanation/definition
  4. **"Verify" button:** Submits the paraphrase to the LLM backend

#### 4. LLM Evaluation & Feedback Logic (Extracted Concepts)
- **Evaluation Criteria:** The backend API LLM evaluates the user's input based on **Accuracy**, **Originality**, and provides constructive **Feedback**
- **Lenience & Hints:** Evaluation should not be overly strict; if incorrect, the feedback must offer helpful hints to guide the user rather than giving away the answer.
- **Success State:** If correct, the progress meter updates accordingly

#### 5. Handling User-Made (Blue) Concepts
- **No Source Definition:** Since user-made concepts lack a source definition, the Original Definition section is omitted or marked accordingly.
- **Warning Label:** Include a warning label reminding the user to ensure their self-defined concept is accurate.
- **Bypass LLM Evaluation:** User-made concepts are **not** evaluated by the LLM. Saving a valid user definition directly counts toward progress.

#### 6. Progress Tracking Meter
- **Location:** Positioned in the bottom-left sidebar area, labeled **"Level 1 - 2 [Remember/Understand]"** with a percentage bar
- **Calculation:** Tracks the total proportion of concepts (both extracted and user-made) successfully defined by the user and approved/completed

**UI Component & Functional Specification: Level 3 - Apply Phase (CogniMap)**

Please implement Level 3 (Apply), which transitions automatically upon completing Level 1-2, introduces scenario-based application challenges, concept mapping, and multi-tier evaluation.

#### 1. Transition Modal & UI State
- **Trigger:** Instantly appears when the Level 1-2 progress meter hits 100%
- **Content:** A congratulatory modal titled **"Level 1 - 2 Complete!"** followed by an introduction to **"Level 3 - Apply"**, explaining that users will face real-world scenarios and identify which concepts defend their reasoning
- **Action Button:** Includes a **"Continue to Level 3"** button
- **Sidebar Change:** The sidebar updates to display a purple **"Generate Scenario"** button and a progress meter labeled **"Level 3 [Apply]"** at 0%

#### 2. Scenario Generation Flow ("Generate Scenario")
- **Backend Trigger:** When the user clicks **"Generate Scenario"**, the system selects a subset of concepts (including blue user-made concepts) currently present in the workspace behind the scenes
- **Scenario Modal/View:** A split-panel window opens:
  - **Left Side ("Scenario"):** Displays the LLM-generated real-world scenario (e.g., a hospital medical prediction system)
  - **Right Side ("Concepts"):** Lists the available concept checkboxes (e.g., Machine Learning, Application, Types of Learning)

#### 3. Selection & Justification Interaction
- **Concept Selection:** Users check the boxes for concepts they believe relate to the scenario
- **Inline Justification:** Checking a concept reveals an input field underneath it where the user must type a justification defending why that concept applies to the scenario

#### 4. LLM Evaluation Logic & Feedback Rules
- **Submission:** The user clicks the green **"Submit"** button at the bottom of the modal
- **Multi-Tier Evaluation Criteria:**
  1. **Wrong Concept Selected:** The LLM flags it and explains why the concept is *not* related to the scenario.
  2. **Right Concept, Wrong Justification:** The LLM accepts the concept choice but provides a guiding hint to fix the reasoning.
  3. **Right Concept & Right Justification:** Marked as correct (e.g., displaying a success checkmark like "Result: 2 / 2 Correct")

#### 5. Progress Calculation Formula
- **Dynamic Scenario Count:** The total number of scenarios required to complete Level 3 depends on the total count of concepts shown in the workspace.
- **Formula:** Use JavaScript's `Math.ceil(conceptCount / 3)` to determine how many total scenarios must be successfully cleared to reach 100% on the Level 3 progress bar

**UI Component & Functional Specification: Level 4 - Analyze Phase (CogniMap)**

Please implement Level 4 (Analyze), which starts automatically after Level 3 hits 100%, introducing concept linkage, relationship typing, recommendations, and completion state logic.

#### 1. Transition Modal & UI State
- **Trigger:** Instantly pops up when the Level 3 progress bar hits 100%
- **Content:** A congratulatory modal titled **"Level 3 Complete!"** followed by an introduction to **"Level 4 - Analyze"**, explaining that users will connect concepts together, identify relationships, and build a structured understanding
- **Action Button:** Includes a **"Continue to Level 4"** button to dismiss the modal
- **Sidebar Change:** The left sidebar displays a **"Rules / Recommendations"** panel and a dimmed **"Finish"** button under **Level 4 [Analyze]**

#### 2. Rules & Recommendations Panel
- Display the following guidelines in the sidebar list:
  * Each concept must have at least one connection
  * You may create up to 3 connections per concept
  * Select a relationship type for each connection (e.g., causes, depends on, leads to)
  * Focus on the most important relationships rather than connecting everything

#### 3. Drag-to-Connect Interaction
- **Mouse Interaction:** The user drags their cursor from one concept node to another in the workspace to draw a directional line/edge between them
- **Constraint Check:** Enforce the recommendation limits behind the scenes (max 3 connections per concept).

#### 4. "Type of Edges" Floating Selection Panel
- **Trigger:** Immediately appears upon completing a drag-and-drop link between two concepts
- **Content:** A floating modal or popover titled **"Type of edges"** containing radio buttons with color-coded selections
  * causes
  * leads to
  * depends on
  * includes
  * contrasts with
  * applied in
  * influences
  * custom
- **Action:** A green **"Confirm"** button saves the chosen relationship type

#### 5. Graph Rendering & Completion Logic
- **Label Display:** Once confirmed, draw the edge line between the two concept nodes with the selected relationship text label rendered directly in the middle of the line
- **Finish Button State:** 
  * The bottom **"Finish"** button remains dimmed/disabled until **every** concept in the workspace has at least one connection linked to it
  * Once the condition is met, the button becomes active, allowing the user to finish the entire CogniMap flow.
- **No Percentage Meter:** Since this stage relies on the user's subjective structural understanding, omit the progress percentage bar

**UI Component & Functional Specification: Level 5 - Evaluate Phase (CogniMap)**

Please implement Level 5 (Evaluate), the final learning phase of CogniMap, which features an AI probing analyst challenging user-created relationship links from dual perspectives.

#### 1. Transition Modal & Initial View
- **Trigger:** Instantly pops up when the Level 4 progress or finish state is completed
- **Content:** A congratulatory modal titled **"Level 4 Complete!"** followed by an introduction to **"Level 5 - Evaluate"**, explaining that the system will challenge user connections and ask them to explain and defend selected relationships
- **Action Button:** Includes a **"Continue to Level 5"** button
- **Workspace State & Link Dimming:** 
  - All existing link relationships established in Level 4 automatically render in a **dimmed** visual style when entering Level 5 to indicate they are pending evaluation
  - The left sidebar progress bar displays **Level 5 [Evaluate]** starting at 0%

#### 2. Probing Analyst Interaction Modal
- **Trigger:** Clicking on any link/edge in the workspace opens a popup modal titled with the relationship flow (e.g., `[Concept A] → [Relationship Type] → [Concept B]`)
- **AI Persona ("Probing Analyst"):** The API LLM challenges the user's reasoning by generating specific prompt questions covering two distinct perspectives
  1. **Why this relationship exists** (e.g., *"Why does machine learning lead to real-world applications, and what must be true for this relationship to hold?"*)
  2. **When this relationship is not applied / fails**
- **Input Fields:** Two separate text boxes are provided for the user's answers:
  - `"Why does this relationship exist?"`
  - `"When might this relationship fail?"`
- **Submission:** A green **"Submit"** button sends both answers to the backend LLM API for independent analysis

#### 3. Separate Evaluation & Feedback Logic
- **Independent Assessment:** The API LLM evaluates the user's two answers **separately** and provides distinct feedback for each
- **Hint Mechanism:** If either justification is incorrect, the LLM provides a constructive hint targeted specifically at that perspective rather than rejecting the entire submission.
- **Completion Condition per Link:** Both perspectives must be answered and evaluated as correct for the link to be fully satisfied

#### 4. Visual State Restoration & Progress Tracking
- **Brightening Links:** Once both justifications for a specific link are verified as correct by the LLM, that link's visual state changes from dimmed back to its **bright/normal color** in the workspace graph
- **Progress Meter Calculation:** 
  - The Level 5 progress bar tracks completion across all links present in the workspace
  - Successfully completing a link's dual justification increases the overall stage completion percentage incrementally until it hits 100%

**UI Component & Functional Specification: Phase 2 (Sub-Headings Flow & Full Completion) (CogniMap)**

Please implement Phase 2 of the CogniMap learning cycle, which triggers after successfully completing Level 5 of Phase 1, focusing on expanding concepts into sub-headings and maintaining the full session overview.

#### 1. Phase 2 Transition Modal & Concept Selection
- **Trigger:** Instantly pops up when the Level 5 progress bar reaches 100%
- **Content:** A congratulatory modal titled **"You’ve completed the conceptual overview"** explaining that the user has mastered the core topics, and will now expand selected concepts into more detailed sub-concepts
- **Hierarchy Modal Modifications for Phase 2:**
  - Displays the same tree structure of main headings and sub-headings
  - **Dimmed Main Headings:** Main heading titles are visually **dimmed** to signify that they were already completed in Phase 1
  - **Restricted Additions:** Users are **not allowed to add new main headings** in Phase 2; only adding or renaming **sub-headings** is permitted to keep the learning flow focused
- **Confirmation Action:** Clicking **"Confirm Selection"** merges the newly chosen sub-headings with the already-completed main headings into the workspace

#### 2. Re-running the Learning Loop (Phases 1 & 2 Cycle)
- Once sub-headings are added to the workspace alongside main headings, the system restarts the learning progression for these sub-concepts
  - **Level 1–2 (Remember/Understand):** Paraphrasing sub-concepts and tracking progress
  - **Level 3 (Apply):** Scenario generation factoring in the expanded concept node pool.
  - **Level 4 (Analyze):** Drawing relationships and links between sub-headings and main headings.
  - **Level 5 (Evaluate):** Probing analyst challenges for the newly formed links until reaching 100%

#### 3. Final Completed Learning Session View
- **Overview:** The final state displays a fully robust, interconnected concept map containing both the primary main headings and their expanded sub-headings (e.g., Role of Computer Science, Roles of Statistics, Supervised/Unsupervised/Reinforcement Learning, Retail, Finance)
- **Visual Integrity:** All established relationships, customized edge labels, and color-coded nodes (neutral vs. blue user-made vs. sub-concepts) remain intact, illustrating a complete hierarchical and relational learning map for the uploaded material

**UI Component & Functional Specification: Historical Review & Stage Navigation Dropdown (CogniMap)**

Please implement the historical review functionality allowing users to inspect previous stages' activities and answers via a dropdown menu located at the bottom right of the sliding concept details panel.

#### 1. General Panel & Dropdown Mechanics
- **Trigger:** When a user clicks any concept node in the workspace, the sliding right panel opens
- **Navigation Dropdown:** Positioned at the bottom-right of the sliding panel. It features a dropdown toggle allowing users to switch views between current and past completed stages for that specific concept.
- **Default Views by Stage:**
  - In **Stage 3**, the panel defaults to showing Stage 1 & 2 data, with the dropdown available to check history.
  - In **Stage 4**, clicking a concept defaults to showing Stage 3 data, while Stage 4 link types are natively visible directly on the workspace graph
  - In **Stage 5**, clicking a concept defaults to showing the relevant previous stage history, while Stage 4 links remain visible on the workspace.

#### 2. Phase-Specific Review Availability Rules

##### **Phase 1 Rules:**
- **Stages 1 & 2:** No previous stages exist (initial activity).
- **Stage 3 Review:** Users can view the concept name, original definition (or user-defined text for user-made concepts), and AI feedback
- **Stage 4 Review:** Users can review Stage 1, 2, and 3 data. For Stage 3, the panel shows the concept name, a list of scenarios the concept was involved in (with a scenario selector dropdown if multiple), and boxes containing related concepts and user justifications
- **Stage 5 Review:** Users can review Stage 1, 2, and 3 data using the same format. Stage 4 relationship creation is omitted from the dropdown review since edge labels are explicitly visible on the workspace graph.

##### **Phase 2 Rules (Sub-Headings & Main Headings):**
- **Sub-Headings:** Follow the exact same stage-by-stage review rules as Phase 1.
- **Main Headings (Fully Completed 5-Stage Concepts):** Because main headings have completed all 5 stages by Phase 2, clicking them allows users to review **Stage 1, 2, 3, and 5** data through the right panel dropdown (skipping Stage 4 since linking is visible on the workspace graph).


