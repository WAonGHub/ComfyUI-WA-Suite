# WA Node Suite (`ComfyUI-WA-Suite`)

High-performance utility node suite for ComfyUI by **WA**.

## Included Nodes

### 1. `WA Index Switch 100 ⚡ (WA Suite)`
- **Category**: `WA Node Suite/Switches`
- **Features**:
  - **100 Wildcard Inputs (`input_0` … `input_99`)**: Accepts any data type (`MODEL`, `LATENT`, `IMAGE`, `STRING`, `CONDITIONING`, `CLIP`, `VAE`, etc.).
  - **True Lazy Evaluation**: Uses ComfyUI's native `check_lazy_status` so **only** the upstream branch connected to the selected `index` is executed. All other 99 branches are completely ignored.

### 2. `WA Find & Replace (20 / 40 / 60) ⚡ (WA Suite)`
- **Category**: `WA Node Suite/Strings`
- **Variants**:
  - `WA Find & Replace 20 ⚡ (WA Suite)` (`find_1`/`replace_1` … `find_20`/`replace_20`)
  - `WA Find & Replace 40 ⚡ (WA Suite)` (`find_1`/`replace_1` … `find_40`/`replace_40`)
  - `WA Find & Replace 60 ⚡ (WA Suite)` (`find_1`/`replace_1` … `find_60`/`replace_60`)
- **Features**:
  - **Simultaneous (Single-Pass) Mode**: Compiles all active search strings into a single LRU-cached pass with $O(1)$ lookup per match.
  - **Sequential (Chained) Mode**: Applies replacements in order (`1` $\rightarrow$ $N$) using fast C-level `str.replace`.
  - Supports **Case Sensitive** and **Regular Expression (`use_regex`)** toggles.

### 3. `WA Text Index Switch ⚡ (WA Suite)`
- **Category**: `WA Node Suite/Strings`
- **Features**:
  - **Row Number Gutter (`0`, `1`, `2`, …)**: Displays line indices directly next to the text box so you never have to manually type `/*0*/`, `/*1*/`, etc.
  - **Alternating Dark Grey & Light Grey Rows**: Zebra-striped row backgrounds that automatically expand if a long prompt wraps onto multiple visual lines.
  - **Click-to-Select & Active Row Highlighting**: Clicking any row number in the left gutter sets `select` to that index, and the active `select` row is highlighted in green.
  - **Backwards-Compatible Paste (`strip_comment_index`)**: Automatically strips leading `/*0*/`, `/*1*/` prefixes if you paste prompts from older selector nodes.

## Installation

### Via ComfyUI-Manager
1. Open **ComfyUI-Manager** $\rightarrow$ **Custom Nodes Manager** and search for **`WA Node Suite`**, or
2. Click **Install via Git URL** and paste your repository URL.

### Manual Installation
```bash
cd ComfyUI/custom_nodes
git clone https://github.com/WAonGHub/ComfyUI-WA-Suite.git
```
