import streamlit as st
st.title("Research Data Extraction Dashboard")
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
import plotly.express as px


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
    
    # Custom CSS for background color and button styling
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] {
            background-color: #F1F3F5;
        }
        
        /* All buttons to purple */
        button {
            background-color: #6C63FF !important;
            border-color: #6C63FF !important;
            color: white !important;
        }
        
        /* Radio buttons to green */
        input[type="radio"] {
            accent-color: #28A745 !important;
        }
        
        /* Keywords text input outline and white background */
        [data-testid="stTextInput"] input {
            border: 2px solid #6C63FF !important;
            border-radius: 4px !important;
            background-color: white !important;
        }
        
        /* Hover effects */
        button:hover {
            opacity: 0.8 !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    
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
    number_pattern = None
    if mode == "Search Keywords":
        keywords_text = st.text_input(
            "Enter keywords or key phrases to search for (separated by commas):",
            key="keywords_input"
        )
        if keywords_text:
            keywords = [k.strip() for k in keywords_text.split(",")]
        
        sort_order = st.radio(
            "Rank papers by keyword matches:",
            ["No ranking", "Highest to lowest", "Lowest to highest"],
            key="sort_radio"
        )
    else:
        number_pattern = st.text_input(
            "Enter the exact number(s) or regex pattern to extract:",
            placeholder="e.g. 42, 3.14, \d{4}-\d{2}-\d{2}",
            key="number_pattern_input"
        )
        st.caption("Enter comma-separated numbers or a regex pattern. The app will extract only matching values.")
    
    # Process button
    if st.button("Process Files", type="primary"):
        if not uploaded_files:
            st.warning("Please upload at least one file.")
            return None, None, None, None, None
        if mode == "Search Keywords" and not keywords:
            st.warning("Please enter keywords.")
            return None, None, None, None, None
        if mode != "Search Keywords" and not number_pattern:
            st.warning("Please enter a number or pattern to extract.")
            return None, None, None, None, None
        return uploaded_files, mode, keywords, sort_order, number_pattern

    return None, None, None, None, None


def search_keywords(text: str, keywords: List[str]) -> Dict[str, int]:
    """Search for keywords or phrases in text and return counts (case-insensitive)."""
    counts = {}
    for keyword in keywords:
        keyword = keyword.strip()
        if not keyword:
            continue
        pattern = rf"\b{re.escape(keyword)}\b"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        counts[keyword] = len(matches)
    return counts


def extract_numbers(text: str, number_pattern: str) -> List[str]:
    """Extract only user-specified numbers or patterns from text."""
    if not number_pattern:
        return []

    patterns = []
    trimmed = number_pattern.strip()
    if "," in trimmed:
        for part in trimmed.split(","):
            part = part.strip()
            if not part:
                continue
            if re.search(r'[\\.^$*+?{}\[\]|()]', part):
                patterns.append(part)
            else:
                patterns.append(rf'\b{re.escape(part)}\b')
    else:
        if re.search(r'[\\.^$*+?{}\[\]|()]', trimmed):
            patterns.append(trimmed)
        else:
            patterns.append(rf'\b{re.escape(trimmed)}\b')

    numbers = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        numbers.extend(matches)

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
        for idx, (info, kc, _) in enumerate(results, start=1):
            total = sum(kc.values()) if kc else 0
            report_lines.append(f"  {idx}. {info.path.name} — {total} matches")
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


def highlight_keywords(text: str, keywords: List[str]) -> str:
    """Highlight keywords in text using markdown bold."""
    if not keywords:
        return text
    highlighted = text
    for keyword in keywords:
        # Use word boundaries and case-insensitive replacement
        pattern = r'\b' + re.escape(keyword) + r'\b'
        highlighted = re.sub(pattern, f'**{keyword}**', highlighted, flags=re.IGNORECASE)
    return highlighted


def generate_wordcloud_image(keyword_counts: Dict[str, int]):
    """Generate a word cloud image from keyword frequencies."""
    try:
        from wordcloud import WordCloud
        import io
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
    img = cloud.generate_from_frequencies(keyword_counts).to_image()
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def main() -> None:
    uploaded_files, mode, keywords, sort_order, number_pattern = setup_streamlit_ui()
    
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
                numbers = extract_numbers(info.text, number_pattern)
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
            fig = px.bar(df, x="Matches", y="Paper", orientation='h', title="Keyword Matches per Paper")
            st.plotly_chart(fig, use_container_width=True)
            
            # Top keywords frequency
            all_keywords = {}
            for _, kc, _ in results:
                if kc:
                    for k, v in kc.items():
                        all_keywords[k] = all_keywords.get(k, 0) + v
            if all_keywords:
                top_keywords = sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:10]
                kw_df = pd.DataFrame({"Keyword": [k for k, v in top_keywords], "Frequency": [v for k, v in top_keywords]})
                fig = px.bar(kw_df, x="Frequency", y="Keyword", orientation='h', title="Top 10 Keywords by Frequency")
                st.plotly_chart(fig, use_container_width=True)

                # Word cloud for top keyword frequencies
                wc_counts = dict(sorted(all_keywords.items(), key=lambda x: x[1], reverse=True)[:30])
                wc_image = generate_wordcloud_image(wc_counts)
                if wc_image is not None:
                    st.image(wc_image, caption="Keyword Word Cloud", use_column_width=True)
                else:
                    st.info("Install the `wordcloud` package to display the keyword word cloud.")
                
                # Table: Paper vs Keyword Counts
                st.subheader("Keyword Counts Table")
                unique_keywords = list(all_keywords.keys())
                table_data = []
                for info, kc, _ in results:
                    row = {"Paper": info.path.name}
                    for kw in unique_keywords:
                        row[kw] = kc.get(kw, 0) if kc else 0
                    table_data.append(row)
                df_table = pd.DataFrame(table_data)
                df_table.index = range(1, len(df_table) + 1)  # Start index from 1
                st.dataframe(df_table)
            
            # Most Relevant Papers
            st.subheader("Most Relevant Papers")
            for rank, (info, kc, _) in enumerate(results, start=1):
                total = sum(kc.values()) if kc else 0
                st.write(f"{rank}. {info.path.name} — {total} matches")
            
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
                    highlighted_preview = highlight_keywords(preview, keywords) if keywords else preview
                    st.markdown(highlighted_preview)
                    
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
            mime="text/plain",
            key="download_report"
        )


if __name__ == "__main__":
    main()
    