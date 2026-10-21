# WFA Node Suite (`ComfyUI-WA-Suite`)

High-performance utility & refiner node suite for ComfyUI by **WA (WaifuArchitect)**.
Search **`wfa`** in ComfyUI to quickly bring up all nodes in this suite without colliding with `WAS Node Suite`.

## Included Nodes

### 1. `WFA Index Switch (10 / 20 / 30 / 40 / 50 / 60 / 70 / 80 / 90 / 100) ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Switches`
- **Variants**:
  - 10 sizes from **`WFA Index Switch 10 ⚡`** up to **`WFA Index Switch 100 ⚡`** (in steps of 10).
- **Features**:
  - **1-Click Upgrade / Resize (`+10`, `-10`, or Any Size `10–100`)**: Right-click any Index Switch node to **`⚡ Expand +10 Inputs`**, **`⚡ Shrink -10 Inputs`**, or jump to any size (`10` to `100`) in-place while keeping all connected wires, custom row labels, `index` connection, title, and colors.
  - **Wildcard Inputs (`0` … $N-1$)**: Accepts any data type (`MODEL`, `LATENT`, `IMAGE`, `STRING`, `CONDITIONING`, `CLIP`, `VAE`, etc.).
  - **True Lazy Evaluation**: Uses ComfyUI's native `check_lazy_status` so **only** the upstream branch connected to the selected `index` is executed. All other branches are completely ignored.
  - **Numbered Gutter & Alternating Dark/Light Grey Rows**: Matches the visual layout of `WFA Text Index Switch` with alternating row shading and active green row indicator.
  - **Clickable & Writeable Row Labels**: Click any row to type a custom name right next to its connection dot (replaces static `input_28` labels; use `Enter`/`Up`/`Down` to move between rows).
  - **Wire & Label Reordering Shortcuts**:
    - **Click** a row number (`0–99`): Sets `index` to that slot.
    - **`Ctrl + Click`** a row number: Inserts an empty slot at that row and **shifts all connected wires & labels below it down by 1**.
    - **`Shift + Click`** (or **`Alt + Click`**) a row number: Deletes that row and **pulls all connected wires & labels below it up by 1**.

### 2. `WFA Find & Replace (10 / 20 / 30 / 40 / 50 / 60 / 70 / 80 / 90 / 100) ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Strings`
- **Variants**:
  - 10 sizes from **`WFA Find & Replace 10 ⚡`** up to **`WFA Find & Replace 100 ⚡`** (in steps of 10).
- **Features**:
  - **1-Click Upgrade / Resize (`+10`, `-10`, or Any Size `10–100`)**: Right-click any Find & Replace node to **`⚡ Expand +10 Entries`**, **`⚡ Shrink -10 Entries`**, or jump to any size (`10` to `100`) in-place while keeping all connected wires, typed text, custom slot labels, title, and colors.
  - **Direct `● text` Input Socket**: Clean connection dot at the top instead of a bulky multiline textbox.
  - **Simultaneous (Single-Pass) Mode**: Compiles all active search strings into a single LRU-cached pass with $O(1)$ lookup per match.
  - **Sequential (Chained) Mode**: Applies replacements in order (`1` $\rightarrow$ $N$) using fast C-level `str.replace`.
  - Supports **Case Sensitive** and **Regular Expression (`use_regex`)** toggles.

### 3. `WFA Text Index Switch ⚡ (WFA Suite)` & `WFA INT Index Switch ⚡ (WFA Suite)`
- **Categories**: `WFA Node Suite/Strings` (`WFA Text Index Switch`) & `WFA Node Suite/Switches` (`WFA INT Index Switch`)
- **Features**:
  - **Row Number Gutter (`0`, `1`, `2`, …)**: Displays line indices directly next to the text box so you never have to manually type `/*0*/`, `/*1*/`, etc.
  - **Alternating Dark Grey & Light Grey Rows**: Zebra-striped row backgrounds that automatically expand if a long prompt or label wraps onto multiple visual lines.
  - **Click-to-Select, Insert & Delete Rows**:
    - **Click** a row number in the left gutter to set `select` to that index.
    - **Ctrl + Click** a row number to insert a new blank row there and push all rows below it down by 1.
    - **Shift + Click** (or **Alt + Click**) a row number to delete that row and pull all rows below it up by 1.
  - **`WFA INT Index Switch ⚡`**: Dedicated INT-only version with the exact same 100-row labeled UI, outputting only `selected_index` (`INT`) without `STRING` output or `strip_comment_index`.
  - **Backwards-Compatible Paste (`strip_comment_index` on Text Index Switch)**: Automatically strips leading `/*0*/`, `/*1*/` prefixes if you paste prompts from older selector nodes.

### 4. `WFA Full Image Refiners ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Refiners`
- **Included Refiner Nodes (Standard + `BASIC_PIPE` Variants)**:
  - `WFA Full Image Refiner ⚡ (WFA Suite)` & `(Pipe)`
  - `WFA Advanced Full Image Refiner ⚡ (WFA Suite)` & `(Pipe)` — Adds pre-sharpening (unsharp mask) and pre-refinement bicubic upscale/downscale.
  - `WFA Exact Impact Refiner ⚡ (WFA Suite)` & `(Pipe)` — Emulates Impact Pack's full-image crop refinement with differential diffusion and `InpaintModelConditioning` support.
  - `WFA Edge-Targeted Refiner ⚡ (WFA Suite)` & `(Pipe)` — Generates a Sobel edge mask (`EDGE_MASK`) to focus refinement on edges and details.
  - `WFA Smart Mask Refiner ⚡ (WFA Suite)` & `(Pipe)` — Combines Sobel edge detection, morphological dilation, base mask level, and Gaussian blur (`SMART_MASK`).

### 5. `WFA Loop Iterator ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Iterators`
- **Features**:
  - **All-in-One INT Counter, Auto-Rewinder & Queue Trigger**: Combines an incrementing `INT` counter, list limit rewinder (`reset_to` $\rightarrow$ `end_index`), multi-pass loop counter (`total_loops`), and `ImpactQueueTrigger` into a single node.
  - **No Crash on Completion**: Unlike LevelPixel's `Iterator [LP]` (which stops the queue by throwing a red `RuntimeError`), `WFA Loop Iterator` cleanly stops auto-queuing when all `total_loops` passes finish and resets back to `reset_to` & `Loop 1`.
  - **1-Click Cancel & Live Switch Highlighting**: Holds the active `index` during generation so connected `WFA Text Index Switch` / `WFA Index Switch` nodes highlight the active row in green, and cancels cleanly on a single click of ComfyUI's Cancel (`X`) button.
  - **Built-in `↺ Reset Counter to Start` Button**: One click on the node resets `index` to `reset_to` and `current_loop` to `1`.

## Installation

### Via ComfyUI-Manager
1. Open **ComfyUI-Manager** $\rightarrow$ **Custom Nodes Manager** and search for **`WA Node Suite`**, or
2. Click **Install via Git URL** and paste your repository URL.

### Manual Installation
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/WAonGHub/ComfyUI-WA-Suite.git
```
