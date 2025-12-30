"""File processing utilities for the Financial Analyst agent.

Handles PDF, CSV, image, and text file processing, replacing the
browser-based file processing from the Next.js application.
"""

import base64
import io
from typing import Dict, Any
from PyPDF2 import PdfReader
from PIL import Image
import pandas as pd


class FileProcessor:
    """Process uploaded files for the financial agent."""

    @staticmethod
    async def process_file(
        base64_data: str,
        file_name: str,
        media_type: str,
        is_text: bool = False,
    ) -> Dict[str, Any]:
        """Process file based on type and return structured data.

        Args:
            base64_data: Base64-encoded file content
            file_name: Name of the file
            media_type: MIME type of the file
            is_text: Whether the file is a text file

        Returns:
            Dictionary with processed file data

        Raises:
            ValueError: If file type is unsupported
        """
        if is_text:
            return FileProcessor._process_text_file(base64_data, file_name)
        elif media_type == "application/pdf":
            return await FileProcessor._process_pdf_file(base64_data, file_name)
        elif media_type.startswith("image/"):
            return FileProcessor._process_image_file(base64_data, file_name, media_type)
        elif file_name.endswith(".csv"):
            return await FileProcessor._process_csv_file(base64_data, file_name)
        else:
            raise ValueError(f"Unsupported file type: {media_type}")

    @staticmethod
    def _process_text_file(base64_data: str, file_name: str) -> Dict[str, Any]:
        """Process text files (TXT, MD, HTML, etc.).

        Args:
            base64_data: Base64-encoded text content
            file_name: Name of the file

        Returns:
            Dictionary with file data
        """
        try:
            # Decode base64 text content
            text_content = base64.b64decode(base64_data).decode("utf-8")

            return {
                "type": "text",
                "content": text_content,
                "fileName": file_name,
            }
        except UnicodeDecodeError:
            # Try with latin-1 encoding if UTF-8 fails
            text_content = base64.b64decode(base64_data).decode("latin-1")
            return {
                "type": "text",
                "content": text_content,
                "fileName": file_name,
            }

    @staticmethod
    async def _process_pdf_file(base64_data: str, file_name: str) -> Dict[str, Any]:
        """Extract text from PDF files.

        Args:
            base64_data: Base64-encoded PDF content
            file_name: Name of the PDF file

        Returns:
            Dictionary with extracted text
        """
        try:
            # Decode base64 to bytes
            pdf_bytes = base64.b64decode(base64_data)

            # Create PDF reader
            pdf_reader = PdfReader(io.BytesIO(pdf_bytes))

            # Extract text from all pages
            text_content = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_content += page_text + "\n\n"

            return {
                "type": "pdf_text",
                "content": text_content.strip(),
                "fileName": file_name,
                "pageCount": len(pdf_reader.pages),
            }
        except Exception as e:
            return {
                "type": "pdf_text",
                "content": f"Error extracting PDF text: {str(e)}",
                "fileName": file_name,
                "pageCount": 0,
            }

    @staticmethod
    def _process_image_file(
        base64_data: str, file_name: str, media_type: str
    ) -> Dict[str, Any]:
        """Process image files for Claude vision API.

        Args:
            base64_data: Base64-encoded image data
            file_name: Name of the image file
            media_type: MIME type of the image

        Returns:
            Dictionary with image data formatted for Claude API
        """
        try:
            # Validate image by attempting to open it
            image_bytes = base64.b64decode(base64_data)
            img = Image.open(io.BytesIO(image_bytes))

            # Verify it's a valid image
            img.verify()

            # Return in Claude API format (keep as base64)
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64_data,
                },
                "fileName": file_name,
            }
        except Exception as e:
            return {
                "type": "error",
                "content": f"Error processing image: {str(e)}",
                "fileName": file_name,
            }

    @staticmethod
    async def _process_csv_file(base64_data: str, file_name: str) -> Dict[str, Any]:
        """Parse CSV files into structured data.

        Args:
            base64_data: Base64-encoded CSV content
            file_name: Name of the CSV file

        Returns:
            Dictionary with parsed CSV data
        """
        try:
            # Decode base64 to bytes
            csv_bytes = base64.b64decode(base64_data)

            # Parse CSV with pandas
            df = pd.read_csv(io.BytesIO(csv_bytes))

            # Convert to string representation
            csv_string = f"CSV Data from {file_name}:\n\n"
            csv_string += df.to_string(index=False)

            # Add summary statistics if numeric columns exist
            numeric_cols = df.select_dtypes(include=["number"]).columns
            if len(numeric_cols) > 0:
                csv_string += "\n\nSummary Statistics:\n"
                csv_string += df[numeric_cols].describe().to_string()

            return {
                "type": "csv",
                "content": csv_string,
                "fileName": file_name,
                "rowCount": len(df),
                "columns": df.columns.tolist(),
                "dataframe": df.to_dict("records"),  # Include raw data for potential analysis
            }
        except Exception as e:
            return {
                "type": "csv",
                "content": f"Error parsing CSV: {str(e)}",
                "fileName": file_name,
                "rowCount": 0,
                "columns": [],
            }
