# WFA Node Suite (`ComfyUI-WA-Suite`)

High-performance utility & refiner node suite for ComfyUI by **WA (WaifuArchitect)**.
Search **`wfa`** in ComfyUI to quickly bring up all nodes in this suite without colliding with `WAS Node Suite`.

## Included Nodes

### 1. `WFA Index Switch 100 ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Switches`
- **Features**:
  - **100 Wildcard Inputs (`input_0` … `input_99`)**: Accepts any data type (`MODEL`, `LATENT`, `IMAGE`, `STRING`, `CONDITIONING`, `CLIP`, `VAE`, etc.).
  - **True Lazy Evaluation**: Uses ComfyUI's native `check_lazy_status` so **only** the upstream branch connected to the selected `index` is executed. All other 99 branches are completely ignored.

### 2. `WFA Find & Replace (20 / 40 / 60) ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Strings`
- **Variants**:
  - `WFA Find & Replace 20 ⚡ (WFA Suite)` (`find_1`/`replace_1` … `find_20`/`replace_20`)
  - `WFA Find & Replace 40 ⚡ (WFA Suite)` (`find_1`/`replace_1` … `find_40`/`replace_40`)
  - `WFA Find & Replace 60 ⚡ (WFA Suite)` (`find_1`/`replace_1` … `find_60`/`replace_60`)
- **Features**:
  - **Simultaneous (Single-Pass) Mode**: Compiles all active search strings into a single LRU-cached pass with $O(1)$ lookup per match.
  - **Sequential (Chained) Mode**: Applies replacements in order (`1` $\rightarrow$ $N$) using fast C-level `str.replace`.
  - Supports **Case Sensitive** and **Regular Expression (`use_regex`)** toggles.

### 3. `WFA Text Index Switch ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Strings`
- **Features**:
  - **Row Number Gutter (`0`, `1`, `2`, …)**: Displays line indices directly next to the text box so you never have to manually type `/*0*/`, `/*1*/`, etc.
  - **Alternating Dark Grey & Light Grey Rows**: Zebra-striped row backgrounds that automatically expand if a long prompt wraps onto multiple visual lines.
  - **Click-to-Select, Insert & Delete Rows**:
    - **Click** a row number in the left gutter to set `select` to that index.
    - **Ctrl + Click** a row number to insert a new blank row there and push all rows below it down by 1.
    - **Shift + Click** (or **Alt + Click**) a row number to delete that row and pull all rows below it up by 1.
  - **Backwards-Compatible Paste (`strip_comment_index`)**: Automatically strips leading `/*0*/`, `/*1*/` prefixes if you paste prompts from older selector nodes.

### 4. `WFA Full Image Refiners ⚡ (WFA Suite)`
- **Category**: `WFA Node Suite/Refiners`
- **Included Refiner Nodes (Standard + `BASIC_PIPE` Variants)**:
  - `WFA Full Image Refiner ⚡ (WFA Suite)` & `(Pipe)`
  - `WFA Advanced Full Image Refiner ⚡ (WFA Suite)` & `(Pipe)` — Adds pre-sharpening (unsharp mask) and pre-refinement bicubic upscale/downscale.
  - `WFA Exact Impact Refiner ⚡ (WFA Suite)` & `(Pipe)` — Emulates Impact Pack's full-image crop refinement with differential diffusion and `InpaintModelConditioning` support.
  - `WFA Edge-Targeted Refiner ⚡ (WFA Suite)` & `(Pipe)` — Generates a Sobel edge mask (`EDGE_MASK`) to focus refinement on edges and details.
  - `WFA Smart Mask Refiner ⚡ (WFA Suite)` & `(Pipe)` — Combines Sobel edge detection, morphological dilation, base mask level, and Gaussian blur (`SMART_MASK`).

## Installation

### Via ComfyUI-Manager
1. Open **ComfyUI-Manager** $\rightarrow$ **Custom Nodes Manager** and search for **`WA Node Suite`**, or
2. Click **Install via Git URL** and paste your repository URL.

### Manual Installation
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/WAonGHub/ComfyUI-WA-Suite.git
```
