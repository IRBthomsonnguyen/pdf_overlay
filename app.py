from __future__ import annotations

import io
import zipfile
from pathlib import Path

import fitz  # PyMuPDF
import streamlit as st
from PIL import Image, ImageEnhance, ImageOps


# Configure the browser page before creating any Streamlit UI elements.
st.set_page_config(page_title="PDF Overlay", page_icon="🔴", layout="wide")


def normalise_name(name: str) -> str:
    """Return a case-insensitive PDF name without its file extension."""
    return Path(name).stem.casefold().strip()


def pair_files(old_files, new_files):
    """Match old and new uploads by filename, falling back to sorted order."""
    # Build lookup tables so files with the same drawing name are paired reliably.
    old_by_name = {normalise_name(file.name): file for file in old_files}
    new_by_name = {normalise_name(file.name): file for file in new_files}
    shared = sorted(set(old_by_name) & set(new_by_name))

    if shared:
        # Use matching names when at least one match exists, and report the rest.
        pairs = [(old_by_name[key], new_by_name[key]) for key in shared]
        unmatched_old = sorted(set(old_by_name) - set(shared))
        unmatched_new = sorted(set(new_by_name) - set(shared))
        return pairs, unmatched_old, unmatched_new, "filename"

    # If no names match, pair the files alphabetically to provide a predictable fallback.
    old_sorted = sorted(old_files, key=lambda f: f.name.casefold())
    new_sorted = sorted(new_files, key=lambda f: f.name.casefold())
    count = min(len(old_sorted), len(new_sorted))
    return (
        list(zip(old_sorted[:count], new_sorted[:count])),
        [file.name for file in old_sorted[count:]],
        [file.name for file in new_sorted[count:]],
        "upload order",
    )


def page_to_image(page: fitz.Page, dpi: int) -> Image.Image:
    """Render one PDF page to a PIL image at the requested resolution."""
    # PDF points are 1/72 inch, so convert the requested DPI into a render scale.
    pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def tint(image: Image.Image, colour: tuple[int, int, int], strength: float) -> Image.Image:
    """Convert dark drawing lines into a coloured layer with a transparent background."""
    # Invert the page so dark drawing lines become opaque and white paper becomes transparent.
    grayscale = ImageEnhance.Contrast(image.convert("L")).enhance(1.35)
    line_strength = ImageOps.autocontrast(ImageOps.invert(grayscale), cutoff=1)
    alpha = line_strength.point(lambda value: min(255, int(value * strength)))

    # Store the drawing colour and transparency separately in an RGBA image.
    tinted = Image.new("RGBA", image.size, colour + (0,))
    tinted.putalpha(alpha)
    return tinted


def overlay_pdf(
    old_bytes: bytes,
    new_bytes: bytes,
    dpi: int,
    tint_strength: float,
    blend: float,
    background: tuple[int, int, int],
) -> bytes:
    """Render, colourise, blend, and export matching PDF pages as one PDF."""
    # Open both uploaded files directly from memory; no temporary files are needed.
    old_doc = fitz.open(stream=old_bytes, filetype="pdf")
    new_doc = fitz.open(stream=new_bytes, filetype="pdf")
    if len(old_doc) != len(new_doc):
        raise ValueError(f"page count differs ({len(old_doc)} vs {len(new_doc)})")

    pages: list[Image.Image] = []
    try:
        # Process corresponding pages together so their geometry can be compared.
        for index, (old_page, new_page) in enumerate(zip(old_doc, new_doc), start=1):
            old_image = page_to_image(old_page, dpi)
            new_image = page_to_image(new_page, dpi)
            if old_image.size != new_image.size:
                new_image = new_image.resize(old_image.size, Image.Resampling.LANCZOS)

            # Adjust each layer's opacity using the selected old/new blend ratio.
            old_red = tint(old_image, (220, 30, 45), tint_strength * 2 * (1 - blend))
            new_green = tint(new_image, (25, 165, 80), tint_strength * 2 * blend)

            # Composite transparent coloured linework over a neutral background.
            result = Image.new("RGBA", old_image.size, background + (255,))
            result.alpha_composite(old_red)
            result.alpha_composite(new_green)
            result = result.convert("RGB")
            pages.append(result)
    finally:
        # Always release the PDF handles, including when a page raises an error.
        old_doc.close()
        new_doc.close()

    # Save the rendered pages as a multi-page PDF in memory for Streamlit download.
    output = io.BytesIO()
    pages[0].save(output, format="PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return output.getvalue()

def combine_pdfs(pdf_bytes_list: list[bytes]) -> bytes:
    """Combine multiple PDFs into a single PDF."""
    output = io.BytesIO()
    pdf_writer = fitz.open()  # Create a new PDF document

    for pdf_bytes in pdf_bytes_list:
        pdf_reader = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in pdf_reader:
            pdf_writer.insert_pdf(pdf_reader, from_page=page.number, to_page=page.number)
        pdf_reader.close()

    pdf_writer.save(output)
    pdf_writer.close()
    return output.getvalue()


def output_name(old_name: str, new_name: str) -> str:
    """Create a stable download filename based on the new PDF name."""
    stem = Path(new_name).stem or Path(old_name).stem
    return f"{stem}_overlay.pdf"


# Main application heading and short explanation.
st.title("PDF Overlay")
st.caption("Colourise an old drawing red, a new drawing green, and blend them to reveal changes.")

# Sidebar controls let the user trade output quality and file size against speed.
with st.sidebar:
    st.header("Processing settings")
    dpi = st.slider("Render quality (DPI)", min_value=72, max_value=200, value=192, step=12)
    tint_strength = st.slider("Colour strength", min_value=0.0, max_value=1.0, value=0.85, step=0.05)
    blend = st.slider("New PDF blend", min_value=0.0, max_value=1.0, value=0.85, step=0.05)
    background_name = st.selectbox(
        "Overlay background",
        ["Light grey", "Dark charcoal", "White"],
        help="A neutral background improves contrast once the PDF paper background is removed.",
    )
    background = {
        "Light grey": (238, 240, 242),
        "Dark charcoal": (35, 39, 45),
        "White": (255, 255, 255),
    }[background_name]
    st.info("Higher DPI improves detail but increases processing time and output size.")

# Keep the old and new upload areas side-by-side for easy visual association.
left, right = st.columns(2)
with left:
    st.subheader("Old PDFs")
    old_files = st.file_uploader("Upload the old set", type="pdf", accept_multiple_files=True, key="old")
with right:
    st.subheader("New PDFs")
    new_files = st.file_uploader("Upload the new set", type="pdf", accept_multiple_files=True, key="new")

if old_files and new_files:
    # Once both upload groups exist, show the pairing preview before processing.
    pairs, unmatched_old, unmatched_new, pairing_mode = pair_files(old_files, new_files)
    st.write(f"**{len(pairs)} pair(s) ready** - paired by {pairing_mode}.")
    if unmatched_old or unmatched_new:
        st.warning(f"Unmatched files will be skipped: {len(unmatched_old)} old, {len(unmatched_new)} new.")

    with st.expander("Review pairs", expanded=True):
        for old_file, new_file in pairs:
            st.write(f"`{old_file.name}`  ↔  `{new_file.name}`")

    if st.button("Create overlays", type="primary", use_container_width=True):
        results: list[tuple[str, bytes]] = []
        # Progress is updated after each pair so large batches remain transparent.
        progress = st.progress(0, text="Starting...")
        errors: list[str] = []
        for index, (old_file, new_file) in enumerate(pairs):
            try:
                result = overlay_pdf(
                    old_file.getvalue(),
                    new_file.getvalue(),
                    dpi,
                    tint_strength,
                    blend,
                    background,
                )
                results.append((output_name(old_file.name, new_file.name), result))
            except Exception as exc:  # Keep the batch going if one pair is invalid.
                errors.append(f"{old_file.name} / {new_file.name}: {exc}")
            progress.progress((index + 1) / len(pairs), text=f"Processed {index + 1} of {len(pairs)}")

        if errors:
            for error in errors:
                st.error(error)
        if results:
            st.success(f"Created {len(results)} overlay PDF(s).")
            # Package every successful result into one convenient ZIP download.
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for name, data in results:
                    archive.writestr(name, data)
            st.download_button(
                "Download all overlays (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="pdf_overlays.zip",
                mime="application/zip",
                use_container_width=True,
            )

            st.download_button(
                "Download all overlays (combined PDF)",
                data=combine_pdfs([data for _, data in results]),
                file_name="pdf_overlays_combined.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

            for name, data in results:
                # Also provide individual download buttons for users who need one file.
                st.download_button(f"Download {name}", data=data, file_name=name, mime="application/pdf")


else:
    # Keep the empty state helpful before any files have been selected.
    st.info("Upload at least one old PDF and one new PDF to begin.")
