# Vendor Directory

This directory contains locally modified dependencies for the `game-reader-wayland` project.

## `pipewire-capture`

The `pipewire-capture` library has been fetched and modified locally to allow capturing entire monitors in addition to individual windows.

### Setting up the local dependency

If you are setting up this project from scratch or on a new machine, you need to compile and install this local dependency into your virtual environment.

**Prerequisites:**

1.  **Rust Toolchain:** You need Rust installed. The easiest way is via `rustup` (https://rustup.rs/).
2.  **PipeWire Development Files:** You must install the system development libraries for PipeWire.
    *   **Debian/Ubuntu:** `sudo apt install libpipewire-0.3-dev`
    *   **Fedora:** `sudo dnf install pipewire-devel`
    *   **Arch Linux:** `sudo pacman -S pipewire`
3.  **Maturin:** This project uses `maturin` to build the Python bindings for the Rust library. Ensure it's installed in your virtual environment:
    ```bash
    pip install maturin
    ```

**Installation:**

Because the customized dependencies inside the `vendor` folder are ignored in version control (`.gitignore`), you must fetch and modify the repository manually.

1.  **Clone the repository:**
    ```bash
    mkdir -p vendor
    cd vendor
    git clone https://github.com/bquenin/pipewire-capture.git
    cd ..
    ```

2.  **Apply the modification:**
    Open the file `vendor/pipewire-capture/src/portal.rs` in your editor. Find the code responsible for selecting sources (around line 137), which looks like this:
    ```rust
            SourceType::Window.into(),
    ```
    Replace it with the following line to allow capturing whole monitors:
    ```rust
            (SourceType::Window | SourceType::Monitor).into(),
    ```

3.  **Compile and install:**
    Once the prerequisites are met, the repository is cloned, and the change is applied, ensure your project's virtual environment is active. Navigate to the `pipewire-capture` directory and install it in editable mode:

    ```bash
    cd vendor/pipewire-capture
    pip install -e .
    ```

Verify the installation by running `pip list` and checking that `pipewire-capture` points to the local `vendor` directory.