import os
import sys
import argparse
import time
import copy
import re
import subprocess
import torch
import warnings
from tqdm import tqdm

from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from lxml import etree
from mutagen import mp4
import nltk
from nltk.tokenize import sent_tokenize
from PIL import Image
from pydub import AudioSegment
import zipfile

# VibeVoice imports
from vibevoice.modular.modeling_vibevoice_streaming_inference import VibeVoiceStreamingForConditionalGenerationInference
from vibevoice.processor.vibevoice_streaming_processor import VibeVoiceStreamingProcessor

warnings.filterwarnings("ignore")

namespaces = {
   "calibre":"http://calibre.kovidgoyal.net/2009/metadata",
   "dc":"http://purl.org/dc/elements/1.1/",
   "dcterms":"http://purl.org/dc/terms/",
   "opf":"http://www.idpf.org/2007/opf",
   "u":"urn:oasis:names:tc:opendocument:xmlns:container",
   "xsi":"http://www.w3.org/2001/XMLSchema-instance",
}

warnings.filterwarnings("ignore", module="ebooklib.epub")

def ensure_punkt():
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt")
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab")

def format_time_adaptive(seconds):
    """Format time in adaptive format, showing only relevant units."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def chap2text_epub(chap, item_id=None, toc=None):
    """
    Extract chapter title and paragraphs from an EPUB chapter.

    Args:
        chap: The chapter content (HTML).
        item_id: The ID of the item in the EPUB spine (for fallback naming).
        toc: The EPUB's table of contents (for fallback title extraction).

    Returns:
        tuple: (chapter_title_text, paragraphs)
    """
    blacklist = [
        "[document]",
        "noscript",
        "header",
        "html",
        "meta",
        "head",
        "input",
        "script",
    ]
    paragraphs = []
    soup = BeautifulSoup(chap, "html.parser")

    # Step 1: Try to find chapter title in heading tags (<h1>, <h2>, <h3>)
    heading_tags = ['h1', 'h2', 'h3']
    chapter_title_text = None
    for tag in heading_tags:
        heading = soup.find(tag)
        if heading and heading.text.strip():
            chapter_title_text = heading.text.strip()
            print(f"Found title in <{tag}>: '{chapter_title_text}'")
            break

    # Step 2: If no heading found, try elements with common class names
    if not chapter_title_text:
        common_classes = ['chapter', 'chapter-title', 'title', 'heading']
        for class_name in common_classes:
            element = soup.find(class_=class_name)
            if element and element.text.strip():
                chapter_title_text = element.text.strip()
                print(f"Found title in class '{class_name}': '{chapter_title_text}'")
                break

    # Step 3: Fallback to TOC if provided
    if not chapter_title_text and toc and item_id:
        for toc_item in toc:
            if toc_item.href.split('#')[0] == item_id:
                chapter_title_text = toc_item.title
                print(f"Found title in TOC for item '{item_id}': '{chapter_title_text}'")
                break

    # Step 4: Fallback to item ID or generic name
    if not chapter_title_text:
        chapter_title_text = item_id.replace('.xhtml', '').replace('_', ' ').title() if item_id else None
        print(f"No title found, using fallback: '{chapter_title_text}'")

    # Remove footnotes (links with only numbers)
    for a in soup.findAll("a", href=True):
        if not any(char.isalpha() for char in a.text):
            a.extract()

    # Remove superscript numbers (e.g., footnote markers)
    for sup in soup.findAll("sup"):
        if sup.text.isdigit():
            sup.extract()

    # Extract paragraphs
    chapter_paragraphs = soup.find_all("p")
    if not chapter_paragraphs:
        print(f"No <p> tags found in '{chapter_title_text or item_id}'. Trying <div>.")
        chapter_paragraphs = soup.find_all("div")

    for p in chapter_paragraphs:
        paragraph_text = "".join(p.strings).strip()
        if paragraph_text:
            paragraphs.append(paragraph_text)

    return chapter_title_text, paragraphs

def get_epub_cover(epub_path):
    try:
        with zipfile.ZipFile(epub_path) as z:
            t = etree.fromstring(z.read("META-INF/container.xml"))
            rootfile_path =  t.xpath("/u:container/u:rootfiles/u:rootfile",
                                        namespaces=namespaces)[0].get("full-path")

            t = etree.fromstring(z.read(rootfile_path))
            cover_meta = t.xpath("//opf:metadata/opf:meta[@name='cover']",
                                        namespaces=namespaces)
            if not cover_meta:
                print("No cover image found.")
                return None
            cover_id = cover_meta[0].get("content")

            cover_item = t.xpath("//opf:manifest/opf:item[@id='" + cover_id + "']",
                                            namespaces=namespaces)
            if not cover_item:
                print("No cover image found.")
                return None
            cover_href = cover_item[0].get("href")
            cover_path = os.path.join(os.path.dirname(rootfile_path), cover_href)
            if os.name == 'nt' and '\\' in cover_path:
                cover_path = cover_path.replace("\\", "/")
            return z.open(cover_path)
    except FileNotFoundError:
        print(f"Could not get cover image of {epub_path}")

def export(book, sourcefile):
    book_contents = []
    cover_image = get_epub_cover(sourcefile)
    image_path = None

    if cover_image is not None:
        image = Image.open(cover_image)
        image_filename = sourcefile.replace(".epub", ".png")
        image_path = os.path.join(image_filename)
        image.save(image_path)
        print(f"Cover image saved to {image_path}")

    # Get the table of contents
    toc = book.get_toc() if hasattr(book, 'get_toc') else []

    spine_ids = [spine_tuple[0] for spine_tuple in book.spine if spine_tuple[1] == 'yes']
    items = {item.get_id(): item for item in book.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT}

    for id in spine_ids:
        item = items.get(id)
        if item is None:
            continue
        # Pass item_id and toc to chap2text_epub
        chapter_title, chapter_paragraphs = chap2text_epub(item.get_content(), item_id=id, toc=toc)
        book_contents.append({"title": chapter_title, "paragraphs": chapter_paragraphs})

    outfile = sourcefile.replace(".epub", ".txt")
    check_for_file(outfile)
    print(f"Exporting {sourcefile} to {outfile}")
    author = book.get_metadata("DC", "creator")[0][0]
    booktitle = book.get_metadata("DC", "title")[0][0]

    with open(outfile, "w", encoding='utf-8') as file:
        file.write(f"Title: {booktitle}\n")
        file.write(f"Author: {author}\n\n")
        file.write(f"# Title\n")
        file.write(f"{booktitle}, by {author}\n\n")
        for i, chapter in enumerate(book_contents, start=1):
            if not chapter["paragraphs"] or chapter["paragraphs"] == ['']:
                continue
            else:
                # Use chapter title if available, otherwise fallback to "Part {i}"
                title = chapter["title"] if chapter["title"] else f"Part {i}"
                file.write(f"# {title}\n\n")
                for paragraph in chapter["paragraphs"]:
                    clean = re.sub(r'[\s\n]+', ' ', paragraph)
                    # Normalize common curly quotes to straight quotes using simple replacements
                    clean = clean.replace('“', '"').replace('”', '"')
                    clean = clean.replace('‘', "'").replace('’', "'")
                    clean = clean.replace('--', ', ').replace('—', ', ')
                    clean = re.sub(r'[""]', '"', clean)  # Curly double quotes to standard double quotes
                    clean = re.sub(r'[‘’]', "'", clean)  # Curly single quotes to standard single quotes
                    clean = re.sub(r'--', ', ', clean)
                    clean = re.sub(r'—', ', ', clean)
                    file.write(f"{clean}\n\n")

    return book_contents

def get_book(sourcefile):
    book_contents = []
    book_title = sourcefile
    book_author = "Unknown"
    chapter_titles = []

    with open(sourcefile, "r", encoding="utf-8") as file:
        current_chapter = {"title": "blank", "paragraphs": []}
        initialized_first_chapter = False
        lines_skipped = 0
        for line in file:

            if lines_skipped < 2 and (line.startswith("Title") or line.startswith("Author")):
                lines_skipped += 1
                if line.startswith('Title: '):
                    book_title = line.replace('Title: ', '').strip()
                elif line.startswith('Author: '):
                    book_author = line.replace('Author: ', '').strip()
                continue

            line = line.strip()
            if line.startswith("#"):
                if current_chapter["paragraphs"] or not initialized_first_chapter:
                    if initialized_first_chapter:
                        book_contents.append(current_chapter)
                    current_chapter = {"title": None, "paragraphs": []}
                    initialized_first_chapter = True
                chapter_title = line[1:].strip()
                if any(c.isalnum() for c in chapter_title):
                    current_chapter["title"] = chapter_title
                    chapter_titles.append(current_chapter["title"])
                else:
                    current_chapter["title"] = "blank"
                    chapter_titles.append("blank")
            elif line:
                if not initialized_first_chapter:
                    chapter_titles.append("blank")
                    initialized_first_chapter = True
                if any(char.isalnum() for char in line):
                    current_chapter["paragraphs"].append(line)

        # Append the last chapter if it contains any paragraphs.
        if current_chapter["paragraphs"]:
            book_contents.append(current_chapter)

    return book_contents, book_title, book_author, chapter_titles

def sort_key(s):
    # extract number from the string
    return int(re.findall(r'\d+', s)[0])

def check_for_file(filename):
    if os.path.isfile(filename):
        print(f"The file '{filename}' already exists.")
        overwrite = input("Do you want to overwrite the file? (y/n): ")
        if overwrite.lower() != 'y':
            print("Exiting without overwriting the file.")
            sys.exit()
        else:
            os.remove(filename)

def append_silence(tempfile, duration=1200):
    # if tempfile does not exist, return
    if not os.path.isfile(tempfile):
        print(f"File {tempfile} does not exist, skipping silence append.")
        return
    audio = AudioSegment.from_file(tempfile)
    # Create a silence segment
    silence = AudioSegment.silent(duration)
    # Append the silence segment to the audio
    combined = audio + silence
    # Save the combined audio back to file
    combined.export(tempfile, format="wav")

def combine_short_paragraphs(paragraphs, min_words=6):
    """
    Combine paragraphs that consist of a single sentence <min_words with next paragraph.
    """
    if not paragraphs:
        return []

    result = []
    i = 0

    while i < len(paragraphs):
        paragraph = paragraphs[i]

        # Check if this is a single short sentence
        sentences = sent_tokenize(paragraph)
        if len(sentences) == 1 and len(paragraph.split()) < min_words:
            # Combine with next paragraph if available
            if i + 1 < len(paragraphs):
                combined = paragraph + " " + paragraphs[i + 1]
                result.append(combined)
                i += 2  # Skip next paragraph
            else:
                # Last paragraph, just add it
                result.append(paragraph)
                i += 1
        else:
            result.append(paragraph)
            i += 1

    return result

def vibevoice_read_paragraph(paragraph, model, processor, all_prefilled_outputs, device, cfg_scale=1.5):
    """
    Generate audio for a single paragraph using VibeVoice.

    Args:
        paragraph: The text to convert to speech
        model: VibeVoice model instance
        processor: VibeVoice processor instance
        all_prefilled_outputs: Pre-extracted voice embeddings (.pt file content)
        device: torch device (cuda/mps/cpu)
        cfg_scale: CFG scale for generation (default: 1.5)

    Returns:
        Audio tensor (numpy array)
    """
    # Clean and normalize the text
    clean_text = paragraph.strip()
    clean_text = clean_text.replace("'", "'").replace('"', '"').replace('"', '"')

    # Prepare inputs for the model
    inputs = processor.process_input_with_cached_prompt(
        text=clean_text,
        cached_prompt=all_prefilled_outputs,
        padding=True,
        return_tensors="pt",
        return_attention_mask=True,
    )

    # Move tensors to target device
    for k, v in inputs.items():
        if torch.is_tensor(v):
            inputs[k] = v.to(device)

    # Generate audio
    outputs = model.generate(
        **inputs,
        max_new_tokens=None,
        cfg_scale=cfg_scale,
        tokenizer=processor.tokenizer,
        generation_config={'do_sample': False},
        verbose=False,
        all_prefilled_outputs=copy.deepcopy(all_prefilled_outputs) if all_prefilled_outputs is not None else None,
    )

    return outputs.speech_outputs[0]

def read_book(book_contents, speaker_name, model_path, notitles, forced_device=None):
    """
    Read the book contents and generate per-chapter WAV files using VibeVoice.

    If `forced_device` is provided it will be used instead of auto-detection.
    """
    # Determine device: prefer forced_device when provided
    if forced_device:
        device = forced_device
    else:
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    print(f"Using device: {device}")

    # Load VibeVoice model and processor
    print(f"Loading VibeVoice processor & model from {model_path}")
    processor = VibeVoiceStreamingProcessor.from_pretrained(model_path)

    # Decide dtype & attention implementation
    if device == "mps":
        load_dtype = torch.float32  # MPS requires float32
        attn_impl_primary = "sdpa"  # flash_attention_2 not supported on MPS
    elif device == "cuda":
        load_dtype = torch.bfloat16
        attn_impl_primary = "flash_attention_2"
    else:  # cpu
        load_dtype = torch.float32
        attn_impl_primary = "sdpa"

    print(f"Using torch_dtype: {load_dtype}, attn_implementation: {attn_impl_primary}")

    # Load model with device-specific logic
    try:
        if device == "mps":
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                attn_implementation=attn_impl_primary,
                device_map=None,  # load then move
            )
            model.to("mps")
        elif device == "cuda":
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map="cuda",
                attn_implementation=attn_impl_primary,
            )
        else:  # cpu
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map="cpu",
                attn_implementation=attn_impl_primary,
            )
    except Exception as e:
        if attn_impl_primary == 'flash_attention_2':
            print(f"Error loading model with flash_attention_2: {e}")
            print("Trying to use SDPA. Note: flash_attention_2 is recommended for best quality.")
            model = VibeVoiceStreamingForConditionalGenerationInference.from_pretrained(
                model_path,
                torch_dtype=load_dtype,
                device_map=(device if device in ("cuda", "cpu") else None),
                attn_implementation='sdpa'
            )
            if device == "mps":
                model.to("mps")
        else:
            raise e

    model.eval()
    model.set_ddpm_inference_steps(num_steps=5)

    # Load voice embeddings
    voice_path = get_voice_path(speaker_name)
    print(f"Loading voice: {voice_path}")
    target_device = device if device != "cpu" else "cpu"
    all_prefilled_outputs = torch.load(voice_path, map_location=target_device, weights_only=False)

    # Initialize timing and progress tracking
    start_time = time.time()
    total_chars = sum(len(''.join(chapter['paragraphs'])) for chapter in book_contents)
    processed_chars = 0

    segments = []
    for i, chapter in enumerate(book_contents, start=1):
        paragraphpause = 600  # default pause between paragraphs in ms
        files = []
        partname = f"part{i}.wav"
        print(f"\n\n")

        if os.path.isfile(partname):
            print(f"{partname} exists, skipping to next chapter")
            segments.append(partname)
            # Track characters even for skipped chapters
            processed_chars += len(''.join(chapter['paragraphs']))
        else:
            # Calculate timing info before processing this chapter
            elapsed_time = time.time() - start_time
            elapsed_str = format_time_adaptive(elapsed_time)

            # Calculate ETA based on text processed
            if processed_chars > 0:
                time_per_char = elapsed_time / processed_chars
                remaining_chars = total_chars - processed_chars
                eta_seconds = remaining_chars * time_per_char
                eta_str = format_time_adaptive(eta_seconds)
                timing_info = f" | Elapsed: {elapsed_str} | ETA: {eta_str}"
            else:
                timing_info = f" | Elapsed: {elapsed_str}"

            print(f"Chapter ({i}/{len(book_contents)}): {chapter['title']}{timing_info}\n")
            print(f"Section name: \"{chapter['title']}\"")
            if chapter["title"] == "":
                chapter["title"] = "blank"
            if chapter["title"] != "Title" and notitles != True:
                chapter['paragraphs'][0] = chapter['title'] + ". " + chapter['paragraphs'][0]

            # Combine short paragraphs
            combined_paragraphs = combine_short_paragraphs(chapter["paragraphs"])

            for pindex, paragraph in enumerate(combined_paragraphs):
                ptemp = f"pgraph{pindex}.wav"
                if os.path.isfile(ptemp):
                    print(f"{ptemp} exists, skipping to next paragraph")
                else:
                    # Generate audio for entire paragraph with VibeVoice
                    print(f"Generating audio for paragraph {pindex+1}/{len(combined_paragraphs)}")
                    audio_tensor = vibevoice_read_paragraph(
                        paragraph,
                        model,
                        processor,
                        all_prefilled_outputs,
                        device,
                        cfg_scale=1.5
                    )

                    # Save audio using processor
                    processor.save_audio(audio_tensor, output_path=ptemp)

                    # Add silence at end of paragraph
                    if pindex < len(combined_paragraphs) - 1:
                        append_silence(ptemp, paragraphpause)

                files.append(ptemp)

            # Combine paragraphs into chapter
            append_silence(files[-1], 2000)
            combined = AudioSegment.empty()
            for file in files:
                combined += AudioSegment.from_file(file)
            combined.export(partname, format="wav")
            for file in files:
                os.remove(file)
            segments.append(partname)
            # Track processed characters for this chapter
            processed_chars += len(''.join(chapter['paragraphs']))

    return segments

def get_voice_path(speaker_name):
    """
    Get the path to a VibeVoice voice file (.pt).
    Looks in the VibeVoice installation directory.
    """
    # Try to find VibeVoice installation
    import vibevoice
    vibevoice_dir = os.path.dirname(vibevoice.__file__)
    voices_dir = os.path.join(os.path.dirname(vibevoice_dir), "demo", "voices", "streaming_model")

    if not os.path.exists(voices_dir):
        # Fallback: check if user has VibeVoice in ~/repos
        voices_dir = os.path.expanduser("~/repos/VibeVoice/demo/voices/streaming_model")

    if not os.path.exists(voices_dir):
        raise FileNotFoundError(
            f"Could not find VibeVoice voices directory at {voices_dir}.\n"
            f"The PyPI vibevoice package may not include voice files.\n"
            f"Please install VibeVoice from GitHub:\n"
            f"  pip uninstall vibevoice\n"
            f"  pip install git+https://github.com/microsoft/VibeVoice.git"
        )

    # List available voices
    pt_files = [f for f in os.listdir(voices_dir) if f.endswith('.pt')]

    if not pt_files:
        raise FileNotFoundError(f"No voice files found in {voices_dir}")

    # Try exact match first
    for pt_file in pt_files:
        name = os.path.splitext(pt_file)[0]
        if speaker_name.lower() == name.lower():
            voice_path = os.path.join(voices_dir, pt_file)
            print(f"Found exact voice match: {name}")
            return voice_path

        # Also check for partial matches (e.g., "Carter" matches "en-Carter_man")
        if speaker_name.lower() in name.lower():
            voice_path = os.path.join(voices_dir, pt_file)
            print(f"Found voice match: {name}")
            return voice_path

    # If no match, show available voices and use first one
    available = [os.path.splitext(f)[0] for f in pt_files]
    print(f"Voice '{speaker_name}' not found. Available voices: {', '.join(available)}")
    print(f"Using default voice: {available[0]}")
    return os.path.join(voices_dir, pt_files[0])

def generate_metadata(files, author, title, chapter_titles):
    chap = 0
    start_time = 0
    with open("FFMETADATAFILE", "w") as file:
        file.write(";FFMETADATA1\n")
        file.write(f"ARTIST={author}\n")
        file.write(f"ALBUM={title}\n")
        file.write(f"TITLE={title}\n")
        file.write("DESCRIPTION=Made with https://github.com/aedocw/epub2tts-vibevoice\n")
        for file_name in files:
            duration = get_duration(file_name)
            file.write("[CHAPTER]\n")
            file.write("TIMEBASE=1/1000\n")
            file.write(f"START={start_time}\n")
            file.write(f"END={start_time + duration}\n")
            file.write(f"title={chapter_titles[chap]}\n")
            chap += 1
            start_time += duration

def get_duration(file_path):
    audio = AudioSegment.from_file(file_path)
    duration_milliseconds = len(audio)
    return duration_milliseconds

def make_m4b(files, sourcefile, speaker):
    filelist = "filelist.txt"
    basefile = sourcefile.replace(".txt", "")
    outputm4a = f"{basefile}.m4a"
    outputm4b = f"{basefile} ({speaker}).m4b"
    with open(filelist, "w") as f:
        for filename in files:
            filename = filename.replace("'", "'\\''")
            f.write(f"file '{filename}'\n")
    ffmpeg_command = [
        "ffmpeg",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        filelist,
        "-codec:a",
        "aac",
        "-f",
        "mp4",
        "-strict",
        "-2",
        outputm4a,
    ]
    subprocess.run(ffmpeg_command)
    ffmpeg_command = [
        "ffmpeg",
        "-i",
        outputm4a,
        "-i",
        "FFMETADATAFILE",
        "-map_metadata",
        "1",
        "-codec",
        "copy",
        outputm4b,
    ]
    subprocess.run(ffmpeg_command)
    os.remove(filelist)
    os.remove("FFMETADATAFILE")
    os.remove(outputm4a)
    for f in files:
        os.remove(f)
    return outputm4b

def add_cover(cover_img, filename):
    try:
        if os.path.isfile(cover_img):
            m4b = mp4.MP4(filename)
            cover_image = open(cover_img, "rb").read()
            m4b["covr"] = [mp4.MP4Cover(cover_image)]
            m4b.save()
        else:
            print(f"Cover image {cover_img} not found")
    except:
        print(f"Cover image {cover_img} not found")

def validate_text_file(sourcefile, book_title, book_author, book_contents):
    """
    Validate that the text file contains required elements: title, author, and at least one chapter break.

    Args:
        sourcefile: Path to the source file
        book_title: Extracted book title
        book_author: Extracted book author
        book_contents: List of chapter dictionaries

    Raises:
        SystemExit: If validation fails
    """
    errors = []

    # Check if title was found (if it's still the filename, no title was extracted)
    if book_title == sourcefile:
        errors.append("- Missing 'Title:' line at the beginning of the file")

    # Check if author was found
    if book_author == "Unknown":
        errors.append("- Missing 'Author:' line at the beginning of the file")

    # Check if at least one chapter break was found
    has_chapter_break = False
    with open(sourcefile, "r", encoding="utf-8") as file:
        for line in file:
            if line.strip().startswith("#"):
                has_chapter_break = True
                break

    if not has_chapter_break:
        errors.append("- Missing at least one chapter break line starting with '#'")

    # If there are any errors, display them and exit
    if errors:
        print("\n" + "="*70)
        print("ERROR: Text file validation failed")
        print("="*70)
        print("\nThe text file must contain the following elements:\n")
        print("1. A 'Title:' line at the beginning (e.g., 'Title: My Book')")
        print("2. An 'Author:' line at the beginning (e.g., 'Author: John Doe')")
        print("3. At least one chapter break line starting with '#' (e.g., '# Chapter 1')")
        print("\nMissing elements:")
        for error in errors:
            print(error)
        print("\nPlease correct the text file format and try again.")
        print("="*70 + "\n")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(
        prog="epub2tts-vibevoice",
        description="Read a text file to audiobook format using VibeVoice TTS",
    )
    parser.add_argument("sourcefile", type=str, help="The epub or text file to process")
    parser.add_argument(
        "--speaker",
        type=str,
        default="Carter",
        help="VibeVoice speaker name (e.g., Carter, Emma, Frank, Grace)",
    )
    parser.add_argument(
        "--model_path",
        type=str,
        default="microsoft/VibeVoice-Realtime-0.5B",
        help="Path to VibeVoice model (default: microsoft/VibeVoice-Realtime-0.5B)",
    )
    parser.add_argument(
        "--cover",
        type=str,
        help="Image file to use for cover (jpg or png)",
    )
    parser.add_argument(
        "--notitles",
        action="store_true",
        help="Do not read chapter titles"
    )
    parser.add_argument(
        "--device",
        type=str,
        choices=["cuda", "mps", "cpu"],
        help="Force device to use (overrides auto-detection).",
    )

    args = parser.parse_args()
    print(args)

    ensure_punkt()

    # If we get an epub, export that to txt file, then exit
    if args.sourcefile.endswith(".epub"):
        book = epub.read_epub(args.sourcefile)
        export(book, args.sourcefile)
        exit()

    book_contents, book_title, book_author, chapter_titles = get_book(args.sourcefile)

    # Validate the text file before proceeding
    validate_text_file(args.sourcefile, book_title, book_author, book_contents)

    files = read_book(book_contents, args.speaker, args.model_path, args.notitles, forced_device=args.device)
    generate_metadata(files, book_author, book_title, chapter_titles)
    m4bfilename = make_m4b(files, args.sourcefile, args.speaker)
    if args.cover:
        add_cover(args.cover, m4bfilename)

    print(f"\n{'='*50}")
    print(f"Audiobook created successfully: {m4bfilename}")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
