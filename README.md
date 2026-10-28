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

### 5. `WFA Loop Iterator ⚡`, `WFA Loop Shutdown ⚡` & `WFA Prompt Counter ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Iterators`
- **Features**:
  - **`WFA Loop Iterator ⚡`**: All-in-one `INT` counter, auto-rewinder (`reset_to` $\rightarrow$ `end_index`), multi-pass loop counter (`total_loops`), and `ImpactQueueTrigger` replacement in a single node. Stops cleanly without throwing red `RuntimeError` crashes, cancels on 1 click, and includes a **`↺ Reset Counter`** button.
  - **`WFA Loop Shutdown ⚡`**: Compact overnight power-saving copy of `WFA Loop Iterator`. Waits until the **very last image finishes generating and saving to disk**, runs a configurable safety countdown (`delay_sec`, default `60s`) with a live **`✖ ABORT SHUTDOWN`** button on the node, and then cleanly unloads GPU VRAM, closes ComfyUI, and executes your chosen `after_run` power action (`Shut Down PC`, `Sleep PC`, `Hibernate PC`, `Close ComfyUI`, or `Do Nothing`).
  - **`WFA Prompt Counter ⚡`**: Reads the total prompt count (`count`) and 0-based `end_index` (`count - 1`) from Inspire Pack Batch Prompts (`ZIPPED_PROMPT` outputs, `---` formatted prompt strings, or `.txt` files in `inspire_prompts`), multiline prompt lists, or any ComfyUI `LIST`. Connect its **`end_index`** output directly into **`WFA Loop Iterator`**'s `end_index`!

### 6. `WFA Save Prompt .txt ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/IO`
- **Features**:
  - Replaces 8+ string concat, `LoRA Stack -> String`, filename builder, and `Save Text` nodes with **one compact all-in-one node**.
  - **Automatic Sub-Subfolder & Matching `image_path` Output**: Saves to `<ComfyUI output>/<subfolder>/<character>/<character><separator><prompt_index>.txt` (when `char_folder` is enabled) and outputs **`image_path`** (`subfolder/character/character_index_`) ready to wire straight into your `Save Image` node so images and `.txt` logs always land in the same folder with matching names.
  - **Used Model Logger (`model`)**: Connect a checkpoint/model name (`STRING` / `COMBO`) **or** wire a `MODEL` / `PIPE` link directly — automatically traces the upstream loader to log the exact `.safetensors` model filename under `[MODEL]`.
  - **Built-In `LORA_STACK` Converter**: Wire your `lora_stack` directly into `lora_stack` (no external converter node needed!) — formats `<lora:name:model_wt:clip_wt>` automatically and skips `"None"` slots.
  - **Direct `INT` or `STRING` `prompt_index` Input**: Wire your `WFA Loop Iterator` `index` straight in without needing an `INT to String` node.
  - **Dedicated Prompt Inputs**: Optional sockets for `raw_prompt`, `raw_negative`, `refined_prompt`, `final_prompt`, and `final_negative` (cleanly skips any unconnected/empty inputs, with optional `[SECTION]` `headers` toggle and `overwrite` / `append` / `auto_number` modes).

### 7. `WFA Batch Prompt Loader ⚡`, `WFA Batch Prompt Switcher ⚡` & `WFA Prompt Label Filter ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Prompts`
- **Features**:
  - **`WFA Batch Prompt Loader ⚡`**: Single-node, zero-warning replacement for Inspire Pack's `Load Prompts From File` + `Unzip Prompt` + 9+ embedded regex extractor nodes:
    - **Title-Aware & Zero Console Spam**: Natively understands `----\nTITLE\n----` headers, top banners, and trailing scratchpad notes without printing `invalid prompt format` warnings in the console.
    - **Clean `key: value` Sections + 5-Character Future-Proofing**: Directly parses `width:`, `height:` (or `hight:`), `size:` (`896x1152`), `batchsize:`, `sdxl_lora:`, `sdxl_strength:`, `anima_lora:`, `anima_strength:`, and up to **5 character toggles** (`c1:`–`c5:` or `chars: C1, C2`) right out of each prompt block.
    - **100% Backwards-Compatible Legacy Parsing**: Automatically extracts existing `/*{{{width}}}[[[height]]][[{batch}]][{{sdxl_idx}}]{[{sdxl_str}]}[}{anima_idx}{]{[}anima_str{]}[{[c1]}]{[[c2]]}*/` negative metadata blocks and strips only that control block while preserving `/*AVOID, */` and all other Find & Replace placeholders.
    - **Standalone or Filter-Controlled**: Works completely standalone (`prompt_file` + `index`) OR controlled via the `label_filter` wire from **`WFA Prompt Label Filter ⚡`**. Automatically discovers `.txt` files from both `ComfyUI-WA-Suite/prompts/` and `ComfyUI-Inspire-Pack/prompts/` with sub-millisecond RAM mtime caching.
  - **`WFA Batch Prompt Switcher ⚡`**: Upgraded copy of `WFA Batch Prompt Loader ⚡` that consolidates **12–15 external Switch nodes** directly into the loader with **zero inactive-branch latency**:
    - **1-to-1 Mirrored Single-UI Input Sockets**: Mirrors `positive`, `negative`, `title`, `width`, `height`, `batch_size`, `sdxl_lora`, `sdxl_strength`, `anima_lora`, `anima_strength`, and `c1_enable`–`c5_enable` directly across from their matching output sockets.
    - **True Lazy Evaluation (`check_lazy_status`)**: When `use_batch` is `Batch File`, your Single UI upstream branches are completely skipped; when `use_batch` is `Single UI`, the batch filter upstream branch is skipped.
    - **Independent `file_batch` Switch**: Separate boolean switch (`Batch File` vs `UI Input`) lets you override `batch_size` from your UI even while running prompts & settings from the batch `.txt` file.
    - **Automatic Prefix Stripping**: Automatically strips leading `"positive:"` from the `positive` input and leading `"negative:"` from the `negative` input so pasted prompts work cleanly without extra regex nodes.
  - **`WFA Prompt Label Filter ⚡`**: Clean dark-themed cockpit UI node designed to sit directly inside your ComfyUI dashboard:
    - **Auto-Detects Extendable `[LABEL]` Tags**: Scans all prompt titles in the selected `.txt` file for bracket labels (e.g. `[CORE]`, `[MODERN]`, `[MEDIEVAL]`, `[GS]`, `[PREG]`, `[TAIL]`, `[F1]`–`[F3]`, `[M1]`–`[M2]`, or any new `[CUSTOM]` tag you invent on demand) and renders interactive checkboxes with per-label prompt counts.
    - **Live Prompt Counter & Quick Controls**: Shows real-time **`● Active: X / Y`** count before you even queue, with **`All`**, **`None`**, **`Inv`**, **`↻`** (disk rescan), and `Ctrl+Click` to solo any label.
    - **3 Filter Modes**: **`Allowed Only`** (skips any prompt carrying an unchecked label), **`Match ANY (OR)`**, and **`Match ALL (AND)`**.
    - **Zero-Cycle Wiring with Loop Iterator**: Connect `WFA Prompt Label Filter.end_index` $\rightarrow$ `WFA Loop Iterator.end_index`, `WFA Prompt Label Filter.label_filter` $\rightarrow$ `WFA Batch Prompt Loader.label_filter`, and `WFA Loop Iterator.index` $\rightarrow$ `WFA Batch Prompt Loader.index`.

#### Example `.txt` Prompt Format
```text
----
[CORE] [MODERN] [F1] Standing Outdoor Portrait
----
width: 896
height: 1152
sdxl_lora: 2
sdxl_strength: 0.5
anima_lora: 1
anima_strength: 0.5
c1: true
c2: false
c3: false
c4: false
c5: false
positive: 1girl, solo, standing, city street, soft sunlight
negative: /*AVOID, *//*SCENEneg, *//*NEGATIVE, */lowres, blurry
```

### 8. `WFA Model Upscale & Scale ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Upscaling`
- **Features**:
  - Combines **`Load Upscale Model`** + **`Upscale using Model`** + **`Upscale Image By`** into **one compact, fast node**.
  - **Supersampled Downscaling / Sharpening**: Defaults to `scale_by: 0.50` + `bicubic` so `4x` upscale models cleanly produce crisp `2x` supersampled images without bloated 4K dimensions.
  - **RAM Model Caching & OOM-Safe Tiling**: Caches the loaded `.pth`/`.safetensors` upscale model across batch loop iterations (zero repeated disk loads) and runs tiled GPU execution with automatic OOM fallback and VRAM offloading.
  - **Fused NCHW Post-Resize**: Rescales directly on the model's `(B, C, H, W)` tensor before permuting back to ComfyUI `BHWC`, eliminating two full-size 4K tensor transposes.
  - **1-Click / Wireable `enabled` Bypass Switch**: Set `enabled` to `Bypass` (or wire a dashboard boolean toggle) to pass `image` straight through in `0ms` without needing an external Switch/Bypass node.
  - **Outputs**: `image` (`IMAGE`), `width` (`INT`), `height` (`INT`), plus a live resolution status pill above the node (`896×1152 → 1792×2304 (4x × 0.50)`).

## Installation

### Via ComfyUI-Manager
1. Open **ComfyUI-Manager** $\rightarrow$ **Custom Nodes Manager** and search for **`WFA`**, or
2. Click **Install via Git URL** and paste `https://github.com/WAonGHub/ComfyUI-WA-Suite`.

### Manual Installation
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/WAonGHub/ComfyUI-WA-Suite.git
```
