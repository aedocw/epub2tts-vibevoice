# epub2tts-vibevoice

epub2tts-vibevoice is a free and open source Python app to easily create a full-featured audiobook from an epub or text file using realistic text-to-speech by [VibeVoice](https://github.com/microsoft/VibeVoice). CUDA compatible GPU is required, or Apple Silicon.

## Features

- [x] Creates standard format M4B audiobook file
- [x] Automatic chapter break detection
- [x] Embeds cover art if specified
- [x] Resumes where it left off if interrupted
- [x] Uses VibeVoice for high-quality, natural-sounding speech
- [x] Supports paragraph-level processing (no sentence splitting needed)
- [x] NOTE: epub file must be DRM-free

## Usage

<details>
<summary>Usage instructions</summary>

*NOTE:* If you want to specify where NLTK tokenizer will be stored (about 50mb), use an environment variable: `export NLTK_DATA="your/path/to/nltk_data"`

### OPTIONAL - activate the virtual environment if using
1. `source .venv/bin/activate`

### FIRST - extract epub contents to text and cover image to png:
1. `epub2tts-vibevoice mybook.epub`
2. **edit mybook.txt**, replacing `# Part 1` etc with desired chapter names, and removing front matter like table of contents and anything else you do not want read. **Note:** First two lines can be Title: and Author: to use that in audiobook metadata.

### Read text to audiobook:

* `epub2tts-vibevoice mybook.txt --speaker Carter --cover mybook.png`
* Specify a speaker with `--speaker <name>`. Available speakers include:
  - English: Carter, Davis, Emma, Frank, Grace, Mike, Samuel
  - Other languages: Available in DE, FR, IT, JP, KR, NL, PL, PT, ES

### All options
* `-h, --help` - show this help message and exit
* `--speaker <name>` - VibeVoice speaker to use (default: Carter)
* `--model_path <path>` - Path to VibeVoice model (default: microsoft/VibeVoice-Realtime-0.5B)
* `--cover image.[jpg|png]` - Image to use for cover
* `--notitles` - Do not read chapter titles when creating audiobook

### Deactivate virtual environment
`deactivate`
</details>

## Reporting bugs

<details>
<summary>How to report bugs/issues</summary>

Thank you in advance for reporting any bugs/issues you encounter! If you are having issues, first please search existing issues to see if anyone else has run into something similar previously.

If you've found something new, please open an issue and be sure to include:
1. The full command you executed
2. The platform (Linux, Windows, OSX)
3. Your Python version if not using Docker

</details>

## Release notes

<details>
<summary>Release notes</summary>

* 20251214: Initial release with VibeVoice support

</details>

## Install

Required Python version is 3.11.

*NOTE:* If you want to specify where NLTK tokenizer will be stored (about 50mb), use an environment variable: `export NLTK_DATA="your/path/to/nltk_data"`

<details>
<summary>MAC INSTALLATION</summary>

This installation requires Python 3.11 and [Homebrew](https://brew.sh/).

```bash
# Install dependencies
brew install mecab espeak pyenv ffmpeg

# Install epub2tts-vibevoice
git clone https://github.com/aedocw/epub2tts-vibevoice
cd epub2tts-vibevoice
pyenv install 3.11
pyenv local 3.11

# Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate

# Install with uv (recommended)
pip install uv
uv pip install wheel
uv pip install .
uv pip install flash-attn --no-build-isolation

# Or install with pip
# pip install wheel
# pip install .
# pip install flash-attn --no-build-isolation
```
</details>

<details>
<summary>LINUX INSTALLATION</summary>

These instructions are for Ubuntu 22.04+ (20.04 showed some dependency issues), but should work (with appropriate package installer mods) for just about any distro. Ensure you have `ffmpeg` installed before use.

```bash
# Install dependencies
sudo apt install espeak-ng ffmpeg python3-venv

# Clone the repo
git clone https://github.com/aedocw/epub2tts-vibevoice
cd epub2tts-vibevoice

# Create and activate virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install with uv (recommended)
pip install uv
uv pip install wheel
uv pip install .
uv pip install flash-attn --no-build-isolation


# Or install with pip
# pip install wheel
# pip install .
# pip install flash-attn --no-build-isolation

```

</details>

<details>
<summary>WINDOWS INSTALLATION</summary>

Running epub2tts-vibevoice in WSL2 with Ubuntu 22 is the easiest approach.

Follow the Linux installation instructions in WSL2.

</details>

## Updating

<details>
<summary>UPDATING YOUR INSTALLATION</summary>

1. cd to repo directory
2. `git pull`
3. Activate virtual environment you installed epub2tts-vibevoice in if you installed in a virtual environment using "source .venv/bin/activate"
4. `uv pip install . --upgrade` (or `pip install . --upgrade` if not using uv)
</details>

## Requirements

- Python 3.11
- CUDA-compatible GPU (NVIDIA) or Apple Silicon for best performance
- CPU-only mode is supported but will be significantly slower
- ffmpeg (for M4B creation)

## VibeVoice Model

This application uses [Microsoft VibeVoice](https://github.com/microsoft/VibeVoice) for text-to-speech synthesis.

**What's installed automatically:**
- VibeVoice package (installed from GitHub during setup to include voice files)
- Pre-extracted voice files for 25+ speakers in multiple languages
- The VibeVoice-Realtime-0.5B model (downloaded from HuggingFace on first use)

**Note:** The PyPI vibevoice package doesn't include voice files, so we install directly from GitHub.

Voice prompts are provided in pre-extracted embedded format (.pt files) included with VibeVoice. For custom voice creation, please refer to the VibeVoice documentation.

## Author

**Christopher Aedo**

- Website: [aedo.dev](https://aedo.dev)
- GitHub: [@aedocw](https://github.com/aedocw)

## Contributing

Contributions, issues and feature requests are welcome!

## Show your support

Give a star if this project helped you!

## License

This project uses VibeVoice which is released under its own license terms. Please review the [VibeVoice license](https://github.com/microsoft/VibeVoice) for details.
