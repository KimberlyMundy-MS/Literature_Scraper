import streamlit as st

st.title("Literature Scraping Dashboard")
st.write(
    "Welcome to the Literature Scraping Tool and Dashboard, designed to simplify research and make science a little easier for us all. Let's get started!")
"""Literature Scraping Tool - Streamlit App.

This app extracts text from PDF, DOCX, or TXT files and either searches for keywords or extracts all numeric values.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import re
import tempfile
import pandas as pd

import pypdf as PyPDF2
from docx import Document
import streamlit as st


@dataclass
class PaperInfo:
    path: Path
    text: str
    page_count: int
    file_size_bytes: int
    title: Optional[str]
    author: Optional[str]
    producer: Optional[str]
    creation_date: Optional[str]
    modification_date: Optional[str]
    character_count: int
    word_count: int
    metadata: Dict[str, str]


def format_bytes(size: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def extract_text_from_file(file_input) -> PaperInfo:
    """Extract plain text and metadata from a PDF, DOCX, or TXT file.
    
    Args:
        file_input: Either a Path object or a file-like object from st.file_uploader
    """
    # Determine file type and handle both Path and file-like objects
    if isinstance(file_input, Path):
        suffix = file_input.suffix.lower()
        file_name = file_input.name
        file_size_bytes = file_input.stat().st_size
        file_obj = None
        is_path = True
    else:
        # File-like object from Streamlit
        suffix = Path(file_input.name).suffix.lower()
        file_name = file_input.name
        file_size_bytes = len(file_input.getvalue()) if hasattr(file_input, 'getvalue') else 0
        file_obj = file_input
        is_path = False
    
    text = ""
    metadata = {}
    page_count = 0

    if suffix == ".pdf":
        if is_path:
            with file_input.open("rb") as f:
                reader = PyPDF2.PdfReader(f)
                pages = reader.pages
                text_chunks: List[str] = [page.extract_text() or "" for page in pages]
                text = "\n".join(text_chunks)
                raw_metadata = reader.metadata or {}
                metadata = {k[1:]: str(v) for k, v in raw_metadata.items() if k.startswith("/") and v is not None}
                page_count = len(pages)
        else:
            reader = PyPDF2.PdfReader(file_obj)
            pages = reader.pages
            text_chunks: List[str] = [page.extract_text() or "" for page in pages]
            text = "\n".join(text_chunks)
            raw_metadata = reader.metadata or {}
            metadata = {k[1:]: str(v) for k, v in raw_metadata.items() if k.startswith("/") and v is not None}
            page_count = len(pages)
    elif suffix == ".docx":
        if is_path:
            doc = Document(file_input)
        else:
            doc = Document(file_obj)
        text_chunks = [para.text for para in doc.paragraphs if para.text.strip()]
        text = "\n".join(text_chunks)
        # Basic metadata from docx
        core_props = doc.core_properties
        metadata = {
            "Title": core_props.title,
            "Author": core_props.author,
            "Created": str(core_props.created) if core_props.created else None,
            "Modified": str(core_props.modified) if core_props.modified else None,
        }
        metadata = {k: v for k, v in metadata.items() if v}
        page_count = 1  # DOCX doesn't have pages easily
    elif suffix == ".txt":
        if is_path:
            with file_input.open("r", encoding="utf-8") as f:
                text = f.read()
        else:
            text = file_obj.getvalue().decode("utf-8")
        page_count = 1  # TXT doesn't have pages
    else:
        raise ValueError(f"Unsupported file type: {suffix}")

    if not text:
        text = ""

    return PaperInfo(
        path=Path(file_name),
        text=text,
        page_count=page_count,
        file_size_bytes=file_size_bytes,
        title=metadata.get("Title"),
        author=metadata.get("Author"),
        producer=metadata.get("Producer"),
        creation_date=metadata.get("Created") or metadata.get("CreationDate"),
        modification_date=metadata.get("Modified") or metadata.get("ModDate"),
        character_count=len(text),
        word_count=len(text.split()),
        metadata=metadata,
    )


def setup_streamlit_ui():
    """Set up the Streamlit user interface and return user inputs."""
    st.set_page_config(page_title="Literature Scraper", layout="wide")
    st.title("📄 Literature Scraper")
    
    st.write("Upload up to 10 PDF, DOCX, or TXT files and extract information.")
    
    # File upload
    uploaded_files = st.file_uploader(
        "Upload files",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        key="file_uploader"
    )
    
    if len(uploaded_files) > 10:
        st.error("Please upload no more than 10 files.")
        return None, None, None, None
    
    # Mode selection
    mode = st.radio(
        "Choose mode:",
        ["Search Keywords", "Extract Numbers"],
        key="mode_radio"
    )
    
    # Keywords input and sorting (conditional)
    keywords = None
    sort_order = None
    if mode == "Search Keywords":
        keywords_text = st.text_input(
            "Enter keywords to search for (separated by commas):",
            key="keywords_input"
        )
        if keywords_text:
            keywords = [k.strip() for k in keywords_text.split(",")]
        
        sort_order = st.radio(
            "Rank papers by keyword matches:",
            ["No ranking", "Highest to lowest", "Lowest to highest"],
            key="sort_radio"
        )
    
    # Process button
    if st.button("Process Files", type="primary"):
        if not uploaded_files:
            st.warning("Please upload at least one file.")
            return None, None, None, None
        if mode == "Search Keywords" and not keywords:
            st.warning("Please enter keywords.")
            return None, None, None, None
        return uploaded_files, mode, keywords, sort_order
    
    return None, None, None, None


def search_keywords(text: str, keywords: List[str]) -> Dict[str, int]:
    """Search for keywords in text and return counts (case-insensitive)."""
    text_lower = text.lower()
    counts = {}
    for keyword in keywords:
        keyword_lower = keyword.lower()
        count = text_lower.count(keyword_lower)
        counts[keyword] = count
    return counts


def extract_numbers(text: str) -> List[str]:
    """Extract all numeric values from text using regex (integers, decimals, fractions, complex)."""
    # Regex patterns for different number types
    patterns = [
        r'\b\d+\.\d+\b',  # decimals like 3.14
        r'\b\d+/\d+\b',   # fractions like 1/2
        r'\b\d+\+\d+i\b', # complex like 2+3i
        r'\b\d+i\b',      # imaginary like 5i
        r'\b\d+\b',       # integers like 42
    ]
    numbers = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        numbers.extend(matches)
    # Remove duplicates while preserving order
    seen = set()
    unique_numbers = []
    for num in numbers:
        if num not in seen:
            unique_numbers.append(num)
            seen.add(num)
    return unique_numbers


def generate_report(results, mode, keywords, sort_order):
    """Generate a text report of the analysis results."""
    report_lines = []
    report_lines.append("Literature Scraper Report")
    report_lines.append(f"Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"Mode: {mode}")
    if mode == "Search Keywords":
        report_lines.append(f"Keywords: {', '.join(keywords)}")
        report_lines.append(f"Sort Order: {sort_order}")
    report_lines.append("")

    if mode == "Search Keywords":
        total_files = len(results)
        total_matches = sum(sum(kc.values()) for _, kc, _ in results if kc)
        papers_with_matches = sum(1 for _, kc, _ in results if kc and sum(kc.values()) > 0)
        total_words = sum(info.word_count for info, _, _ in results)

        report_lines.append("Summary:")
        report_lines.append(f"  Total Files Analyzed: {total_files}")
        report_lines.append(f"  Total Keyword Matches: {total_matches}")
        report_lines.append(f"  Papers with Matches: {papers_with_matches}")
        report_lines.append(f"  Total Words Extracted: {total_words}")
        report_lines.append("")

        report_lines.append("Most Relevant Papers:")
        for info, kc, _ in results:
            total = sum(kc.values()) if kc else 0
            report_lines.append(f"  {info.path.name} — {total} matches")
        report_lines.append("")

        report_lines.append("Detailed Results:")
        for info, keyword_counts, _ in results:
            report_lines.append(f"Paper: {info.path.name}")
            report_lines.append(f"  Pages: {info.page_count}")
            report_lines.append(f"  Words: {info.word_count}")
            total_matches = sum(keyword_counts.values()) if keyword_counts else 0
            report_lines.append(f"  Keyword Matches: {total_matches}")
            report_lines.append("")

            preview = info.text.strip().replace("\n", " ")[:500]
            if len(info.text.strip()) > 500:
                preview += "..."
            report_lines.append(f"  Preview: {preview}")
            report_lines.append("")

            if keyword_counts:
                report_lines.append("  Keyword Breakdown:")
                for k, v in keyword_counts.items():
                    if v > 0:
                        report_lines.append(f"    {k}: {v}")
                report_lines.append("")

            if info.title or info.author or info.producer:
                report_lines.append("  Metadata:")
                if info.title:
                    report_lines.append(f"    Title: {info.title}")
                if info.author:
                    report_lines.append(f"    Author: {info.author}")
                if info.producer:
                    report_lines.append(f"    Producer: {info.producer}")
                if info.creation_date:
                    report_lines.append(f"    Created: {info.creation_date}")
                if info.modification_date:
                    report_lines.append(f"    Modified: {info.modification_date}")
                report_lines.append("")

            report_lines.append("-" * 50)
            report_lines.append("")
    else:
        report_lines.append("Processed Files:")
        for info, _, numbers in results:
            report_lines.append(f"Paper: {info.path.name}")
            report_lines.append(f"  Pages: {info.page_count}")
            report_lines.append(f"  Words: {info.word_count}")
            report_lines.append(f"  Size: {format_bytes(info.file_size_bytes)}")

            if numbers:
                report_lines.append(f"  Extracted Numbers ({len(numbers)} found): {', '.join(numbers[:50])}")
                if len(numbers) > 50:
                    report_lines.append(f"    ... and {len(numbers) - 50} more")
            else:
                report_lines.append("  No numbers found.")

            preview = info.text.strip().replace("\n", " ")[:300]
            if len(info.text.strip()) > 300:
                preview += "..."
            report_lines.append(f"  Preview: {preview}")

            if info.title or info.author or info.producer:
                report_lines.append("  Metadata:")
                if info.title:
                    report_lines.append(f"    Title: {info.title}")
                if info.author:
                    report_lines.append(f"    Author: {info.author}")
                if info.producer:
                    report_lines.append(f"    Producer: {info.producer}")
                if info.creation_date:
                    report_lines.append(f"    Created: {info.creation_date}")
                if info.modification_date:
                    report_lines.append(f"    Modified: {info.modification_date}")

            report_lines.append("")
            report_lines.append("-" * 50)
            report_lines.append("")

    return "\n".join(report_lines)


def generate_wordcloud_image(keyword_counts: Dict[str, int]):
    """Generate a word cloud image from keyword frequencies."""
    try:
        from wordcloud import WordCloud
    except ImportError:
        return None

    if not keyword_counts:
        return None

    cloud = WordCloud(
        width=800,
        height=400,
        background_color="white",
        colormap="viridis"
    )
    return cloud.generate_from_frequencies(keyword_counts).to_image()


def main() -> None:
    uploaded_files, mode, keywords, sort_order = setup_streamlit_ui()
    
    if uploaded_files is None:
        return

    # Process files
    results = []
    for uploaded_file in uploaded_files:
        try:
            info = extract_text_from_file(uploaded_file)
            
            if mode == "Search Keywords":
                keyword_counts = search_keywords(info.text, keywords)
                total_matches = sum(keyword_counts.values())
                results.append((info, keyword_counts, None))
            else:  # Extract Numbers
                numbers = extract_numbers(info.text)
                results.append((info, None, numbers))
        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {str(e)}")
            continue

    # Sort results if ranking is enabled
    if mode == "Search Keywords" and sort_order != "No ranking":
        reverse_sort = sort_order == "Highest to lowest"
        results.sort(key=lambda x: sum(x[1].values()) if x[1] else 0, reverse=reverse_sort)

    # Display results
    if results:
        st.divider()
        st.subheader("Results")
        
        if mode == "Search Keywords":
            # Summary metrics
            total_files = len(results)
            total_matches = sum(sum(kc.values()) for _, kc, _ in results if kc)
            papers_with_matches = sum(1 for _, kc, _ in results if kc and sum(kc.values()) > 0)
            total_words = sum(info.word_count for info, _, _ in results)
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Files Analyzed", total_files)
            with col2:
                st.metric("Total Keyword Matches", total_matches)
            with col3:
                st.metric("Papers with Matches", papers_with_matches)
            with col4:
                st.metric("Total Words Extracted", total_words)
            
            # Visual Insights
            st.subheader("Visual Insights")
            
            # Bar chart: Keyword matches per paper
            data = {"Paper": [info.path.name for info, kc, _ in results], "Matches": [sum(kc.values()) if kc else 0 for _, kc, _ in results]}
            df = pd.DataFrame(data)
            st.bar_chart(df.set_index("Paper"))
            
            # Top keywords frequency
            all_keywords = {}
            for _, kc, _ in results:
                if kc:
                    for k, v in kc.items():
                        all_keywords[k] = all_keywords.get(k, 0) + v
            if all_keywords:
                top_keywords = sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:10]
                kw_df = pd.DataFrame({"Keyword": [k for k, v in top_keywords], "Frequency": [v for k, v in top_keywords]})
                st.bar_chart(kw_df.set_index("Keyword"))

                # Word cloud for top keyword frequencies
                wc_counts = dict(sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:30])
                wc_image = generate_wordcloud_image(wc_counts)
                if wc_image is not None:
                    st.image(wc_image, caption="Keyword Word Cloud", use_column_width=True)
                else:
                    st.info("Install the `wordcloud` package to display the keyword word cloud.")
            
            # Most Relevant Papers
            st.subheader("Most Relevant Papers")
            for info, kc, _ in results:
                total = sum(kc.values()) if kc else 0
                st.write(f"{info.path.name} — {total} matches")
            
            # Detailed Results
            st.subheader("Detailed Results")
            for info, keyword_counts, numbers in results:
                with st.expander(f"{info.path.name}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"Pages: {info.page_count}")
                    with col2:
                        st.write(f"Words: {info.word_count}")
                    with col3:
                        total_matches = sum(keyword_counts.values()) if keyword_counts else 0
                        st.write(f"Keyword Matches: {total_matches}")
                    
                    # Expanded content
                    st.write("**Preview:**")
                    preview = info.text.strip().replace("\n", " ")[:500]
                    if len(info.text.strip()) > 500:
                        preview += "..."
                    st.text(preview)
                    
                    if keyword_counts:
                        st.write("**Keyword Breakdown:**")
                        for k, v in keyword_counts.items():
                            if v > 0:
                                st.write(f"{k}: {v}")
                    
                    # Metadata
                    if info.title or info.author or info.producer:
                        st.write("**Metadata:**")
                        metadata_dict = {}
                        if info.title:
                            metadata_dict["Title"] = info.title
                        if info.author:
                            metadata_dict["Author"] = info.author
                        if info.producer:
                            metadata_dict["Producer"] = info.producer
                        if info.creation_date:
                            metadata_dict["Created"] = info.creation_date
                        if info.modification_date:
                            metadata_dict["Modified"] = info.modification_date
                        st.json(metadata_dict)
        else:
            # For Extract Numbers mode, keep simple display
            for info, keyword_counts, numbers in results:
                with st.expander(f"📋 {info.path.name}", expanded=True):
                    # Display summary in columns
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Pages", info.page_count)
                    with col2:
                        st.metric("Words", info.word_count)
                    with col3:
                        st.metric("Size", format_bytes(info.file_size_bytes))
                    
                    # Metadata
                    if info.title or info.author or info.producer:
                        st.write("**Metadata:**")
                        metadata_dict = {}
                        if info.title:
                            metadata_dict["Title"] = info.title
                        if info.author:
                            metadata_dict["Author"] = info.author
                        if info.producer:
                            metadata_dict["Producer"] = info.producer
                        if info.creation_date:
                            metadata_dict["Created"] = info.creation_date
                        if info.modification_date:
                            metadata_dict["Modified"] = info.modification_date
                        st.json(metadata_dict)
                    
                    # Results
                    if numbers is not None:
                        st.write(f"**Extracted Numbers** ({len(numbers)} found):")
                        numbers_display = ", ".join(numbers[:50])
                        if len(numbers) > 50:
                            numbers_display += f"\n... and {len(numbers) - 50} more"
                        st.text(numbers_display)
                    
                    # Preview
                    preview = info.text.strip().replace("\n", " ")[:300]
                    if len(info.text.strip()) > 300:
                        preview += "..."
                    st.write("**Preview:**")
                    st.text(preview)
        
        # Summary (only for numbers mode now)
        if mode != "Search Keywords":
            st.divider()
            st.subheader("Summary")
            st.write(f"✅ Processed {len(results)} files successfully")
    
    # Download Report
    if results:
        st.divider()
        st.subheader("Download Report")
        report = generate_report(results, mode, keywords, sort_order)
        st.download_button(
            label="📥 Download Report",
            data=report,
            file_name="literature_report.txt",
            mime_type="text/plain",
            key="download_report"
        )


if __name__ == "__main__":
    main()
    