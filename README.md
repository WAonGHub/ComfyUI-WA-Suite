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

### 3. `WFA Text Index Switch ⚡`, `WFA INT Index Switch ⚡` & `WFA Tag Banlist Switch ⚡ (WFA Suite)`
- **Categories**: `WFA Node Suite/Strings` (`WFA Text Index Switch`, `WFA Tag Banlist Switch`) & `WFA Node Suite/Switches` (`WFA INT Index Switch`)
- **Features**:
  - **Row Number Gutter (`0`, `1`, `2`, …)**: Displays line indices directly next to the text box so you never have to manually type `/*0*/`, `/*1*/`, etc.
  - **Alternating Dark Grey & Light Grey Rows**: Zebra-striped row backgrounds that automatically expand if a long prompt or label wraps onto multiple visual lines.
  - **Click-to-Select, Insert & Delete Rows**:
    - **Click** a row number in the left gutter to set `select` to that index.
    - **Ctrl + Click** a row number to insert a new blank row there and push all rows below it down by 1.
    - **Shift + Click** (or **Alt + Click**) a row number to delete that row and pull all rows below it up by 1.
  - **`WFA INT Index Switch ⚡`**: Dedicated INT-only version with the exact same 100-row labeled UI, outputting only `selected_index` (`INT`) without `STRING` output or `strip_comment_index`.
  - **`WFA Tag Banlist Switch ⚡`**: 100 selectable tag-banlist rows (`0–99`) in one node! Connect your main prompt to `● text`, select which banlist row to apply (e.g. Row `0` = empty/none, Row `1` = `/*LOOKING AWAY*/ *eyes*, eyelashes, smile, open mouth`, etc.), and it cleanly filters out banned tags while preserving prompt casing, weights `(tag:1.2)`, `((grouped tags))`, and `{dynamic|prompts}`.
  - **`WFA Remove Banned Tags ⚡`**: Compact file-based banned tag remover that reads any selectable `.txt` banlist inside `ComfyUI-WA-Suite/banlists/` (ships with `banned_tags.txt` and `banned_tags2.txt`, and automatically discovers any new `.txt` files you add to `banlists/`). Includes **Smart Text & Tag Filter** (handles lines with or without trailing commas, matches longest phrases first so `lips` never eats half of `red lips`, removes `(tag:1.2)` weights cleanly, and live-reloads `.txt` edits on save), plus **LP Text Mode** and **LP Tag Mode**.
  - **Backwards-Compatible Paste (`strip_comment_index` on Text Index Switch)**: Automatically strips leading `/*0*/`, `/*1*/` prefixes if you paste prompts from older selector nodes.

### 4. `WFA Full Image Refiners ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Refiners`
- **Included Refiner Nodes (Standard + `BASIC_PIPE` Variants)**:
  - `WFA Full Image Refiner ⚡ (WFA Suite)` & `(Pipe)`
  - `WFA Advanced Full Image Refiner ⚡ (WFA Suite)` & `(Pipe)` — Adds pre-sharpening (unsharp mask) and pre-refinement bicubic upscale/downscale.
  - `WFA Exact Impact Refiner ⚡ (WFA Suite)` & `(Pipe)` — Emulates Impact Pack's full-image crop refinement with differential diffusion and `InpaintModelConditioning` support.
  - `WFA Edge-Targeted Refiner ⚡ (WFA Suite)` & `(Pipe)` — Generates a Sobel edge mask (`EDGE_MASK`) to focus refinement on edges and details.
  - `WFA Smart Mask Refiner ⚡ (WFA Suite)` & `(Pipe)` — Combines Sobel edge detection, morphological dilation, base mask level, and Gaussian blur (`SMART_MASK`).

### 5. `WFA Loop Iterator ⚡` & `WFA Prompt Counter ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Iterators`
- **Features**:
  - **`WFA Loop Iterator ⚡`**: All-in-one `INT` counter, auto-rewinder (`reset_to` $\rightarrow$ `end_index`), multi-pass loop counter (`total_loops`), and `ImpactQueueTrigger` replacement in a single node. Stops cleanly without throwing red `RuntimeError` crashes, cancels on 1 click, and includes a **`↺ Reset Counter to Start`** button.
  - **`WFA Prompt Counter ⚡`**: Reads the total prompt count (`count`) and 0-based `end_index` (`count - 1`) from Inspire Pack Batch Prompts (`ZIPPED_PROMPT` outputs, `---` formatted prompt strings, or `.txt` files in `inspire_prompts`), multiline prompt lists, or any ComfyUI `LIST`. Connect its **`end_index`** output directly into **`WFA Loop Iterator`**'s `end_index`!

## Installation

### Via ComfyUI-Manager
1. Open **ComfyUI-Manager** $\rightarrow$ **Custom Nodes Manager** and search for **`WFA`**, or
2. Click **Install via Git URL** and paste `https://github.com/WAonGHub/ComfyUI-WA-Suite`.

### Manual Installation
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/WAonGHub/ComfyUI-WA-Suite.git
```
