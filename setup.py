from setuptools import setup, find_packages

with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="epub2tts-vibevoice",
    version="0.1.0",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "epub2tts-vibevoice=epub2tts_vibevoice.epub2tts_vibevoice:main",
        ],
    },
    python_requires=">=3.11",
    author="Christopher Aedo",
    description="Create audiobooks from epub files using VibeVoice TTS",
    long_description=open("README.md").read() if __file__ else "",
    long_description_content_type="text/markdown",
)
