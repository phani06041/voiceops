"""
Data Management Service for VoiceOps
Handles case upload, validation, and management operations
"""
import csv
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from fastapi import UploadFile, HTTPException
import logging

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from app.config import DATA_DIR
from app.services.data_loader import normalize, load_cases

logger = logging.getLogger(__name__)

class DataManagementService:
    """Service for managing case data uploads and operations"""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def validate_case_data(self, case_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate a single case record
        Returns: (is_valid, list_of_errors)
        """
        errors = []

        # Required fields
        required_fields = ['case_id', 'domain', 'exception_text']
        for field in required_fields:
            if not case_data.get(field):
                errors.append(f"Missing required field: {field}")

        # Domain validation
        domain = case_data.get('domain', '').lower().strip()
        if domain not in ['healthcare', 'mortgage']:
            errors.append(f"Invalid domain: {domain}. Must be 'healthcare' or 'mortgage'")

        # Case ID should be string and not empty
        case_id = case_data.get('case_id', '').strip()
        if not case_id:
            errors.append("Case ID cannot be empty")
        elif not isinstance(case_id, str):
            errors.append("Case ID must be a string")

        # Exception text should not be empty
        exception_text = case_data.get('exception_text', '').strip()
        if not exception_text:
            errors.append("Exception text cannot be empty")

        # Validate boolean fields
        bool_fields = ['sensitive_case', 'manual_review_required']
        for field in bool_fields:
            value = case_data.get(field)
            if value is not None and value not in [True, False, 'true', 'false', '1', '0', 1, 0]:
                errors.append(f"Field {field} must be a boolean value")

        # Validate numeric fields
        numeric_fields = ['confidence_score']
        for field in numeric_fields:
            value = case_data.get(field)
            if value is not None:
                try:
                    num_value = float(value)
                    if not (0.0 <= num_value <= 1.0):
                        errors.append(f"Field {field} must be between 0.0 and 1.0")
                except (ValueError, TypeError):
                    errors.append(f"Field {field} must be a valid number")

        # Validate array fields (should be lists or convertible to lists)
        array_fields = ['missing_fields', 'evidence_references']
        for field in array_fields:
            value = case_data.get(field)
            if value is not None:
                if isinstance(value, str):
                    # Convert semicolon-separated string to list
                    case_data[field] = [x.strip() for x in value.split(';') if x.strip()]
                elif not isinstance(value, list):
                    errors.append(f"Field {field} must be a list or semicolon-separated string")

        return len(errors) == 0, errors

    def process_uploaded_file(self, file: UploadFile) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Process an uploaded file (CSV, JSON, or Excel) and extract case data
        Returns: (valid_cases, errors)
        """
        valid_cases = []
        errors = []

        # Get file extension
        filename = file.filename or ""
        file_extension = Path(filename).suffix.lower()

        try:
            # Read file content
            content = file.file.read()
            file.file.seek(0)  # Reset for potential re-reading

            if file_extension == '.csv':
                valid_cases, errors = self._process_csv(content)
            elif file_extension == '.json':
                valid_cases, errors = self._process_json(content)
            elif file_extension in ['.xlsx', '.xls']:
                valid_cases, errors = self._process_excel(content)
            else:
                errors.append({
                    'file': filename,
                    'error': f'Unsupported file format: {file_extension}. Supported formats: CSV, JSON, Excel'
                })

        except Exception as e:
            logger.error(f"Error processing uploaded file {filename}: {e}")
            errors.append({
                'file': filename,
                'error': f'Failed to process file: {str(e)}'
            })

        return valid_cases, errors

    def _process_csv(self, content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process CSV file content"""
        valid_cases = []
        errors = []

        try:
            # Decode content
            text_content = content.decode('utf-8-sig')
            lines = text_content.splitlines()

            if not lines:
                errors.append({'file': 'upload.csv', 'error': 'Empty file'})
                return valid_cases, errors

            # Parse CSV
            reader = csv.DictReader(lines)
            if not reader.fieldnames:
                errors.append({'file': 'upload.csv', 'error': 'Missing CSV header'})
                return valid_cases, errors

            # Process each row
            for row_num, row in enumerate(reader, start=2):  # Start at 2 since header is row 1
                try:
                    # Normalize the case data
                    case = normalize(row)

                    # Validate the case
                    is_valid, validation_errors = self.validate_case_data(case)

                    if is_valid:
                        valid_cases.append(case)
                    else:
                        errors.append({
                            'file': 'upload.csv',
                            'row': row_num,
                            'errors': validation_errors
                        })

                except Exception as e:
                    errors.append({
                        'file': 'upload.csv',
                        'row': row_num,
                        'error': f'Failed to process row: {str(e)}'
                    })

        except UnicodeDecodeError:
            errors.append({'file': 'upload.csv', 'error': 'Invalid file encoding. Please use UTF-8.'})
        except Exception as e:
            errors.append({'file': 'upload.csv', 'error': f'Failed to parse CSV: {str(e)}'})

        return valid_cases, errors

    def _process_json(self, content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process JSON file content"""
        valid_cases = []
        errors = []

        try:
            # Decode and parse JSON
            text_content = content.decode('utf-8')
            data = json.loads(text_content)

            # Handle different JSON structures
            if isinstance(data, dict):
                # Single case or {cases: [...]} format
                if 'cases' in data and isinstance(data['cases'], list):
                    case_list = data['cases']
                else:
                    # Treat as single case
                    case_list = [data]
            elif isinstance(data, list):
                # Array of cases
                case_list = data
            else:
                errors.append({'file': 'upload.json', 'error': 'Invalid JSON structure'})
                return valid_cases, errors

            # Process each case
            for index, case_data in enumerate(case_list, start=1):
                try:
                    if not isinstance(case_data, dict):
                        errors.append({
                            'file': 'upload.json',
                            'item': index,
                            'error': 'Each item must be a JSON object'
                        })
                        continue

                    # Normalize the case data
                    case = normalize(case_data)

                    # Validate the case
                    is_valid, validation_errors = self.validate_case_data(case)

                    if is_valid:
                        valid_cases.append(case)
                    else:
                        errors.append({
                            'file': 'upload.json',
                            'item': index,
                            'errors': validation_errors
                        })

                except Exception as e:
                    errors.append({
                        'file': 'upload.json',
                        'item': index,
                        'error': f'Failed to process item: {str(e)}'
                    })

        except UnicodeDecodeError:
            errors.append({'file': 'upload.json', 'error': 'Invalid file encoding. Please use UTF-8.'})
        except json.JSONDecodeError as e:
            errors.append({'file': 'upload.json', 'error': f'Invalid JSON format: {str(e)}'})
        except Exception as e:
            errors.append({'file': 'upload.json', 'error': f'Failed to process JSON: {str(e)}'})

        return valid_cases, errors

    def _process_excel(self, content: bytes) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Process Excel file content"""
        valid_cases = []
        errors = []

        if not PANDAS_AVAILABLE:
            errors.append({
                'file': 'upload.xlsx',
                'error': 'Excel file processing is not available. Please install pandas and openpyxl.'
            })
            return valid_cases, errors

        try:
            # Read Excel file
            excel_file = pd.ExcelFile(content)

            # Process each sheet
            for sheet_name in excel_file.sheet_names:
                try:
                    # Read sheet into DataFrame
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)

                    # Convert DataFrame to list of dicts
                    records = df.to_dict('records')

                    # Process each record
                    for index, record in enumerate(records, start=1):
                        try:
                            # Convert pandas NaN to None
                            clean_record = {}
                            for key, value in record.items():
                                if pd.isna(value):
                                    clean_record[key] = None
                                else:
                                    clean_record[key] = value

                            # Normalize the case data
                            case = normalize(clean_record)

                            # Validate the case
                            is_valid, validation_errors = self.validate_case_data(case)

                            if is_valid:
                                valid_cases.append(case)
                            else:
                                errors.append({
                                    'file': f'upload.xlsx (sheet: {sheet_name})',
                                    'row': index,
                                    'errors': validation_errors
                                })

                        except Exception as e:
                            errors.append({
                                'file': f'upload.xlsx (sheet: {sheet_name})',
                                'row': index,
                                'error': f'Failed to process row: {str(e)}'
                            })

                except Exception as e:
                    errors.append({
                        'file': f'upload.xlsx (sheet: {sheet_name})',
                        'error': f'Failed to process sheet: {str(e)}'
                    })

        except Exception as e:
            errors.append({'file': 'upload.xlsx', 'error': f'Failed to process Excel file: {str(e)}'})

        return valid_cases, errors

    def save_cases_to_file(self, cases: List[Dict[str, Any]], filename: str) -> bool:
        """
        Save cases to a CSV file in the data directory
        Returns: True if successful
        """
        try:
            file_path = self.data_dir / filename

            if not cases:
                logger.warning("No cases to save")
                return False

            # Define the canonical field order
            fieldnames = [
                'case_id', 'domain', 'exception_text', 'status', 'suggested_action',
                'manual_review_required', 'exception_type', 'confidence_score',
                'sensitive_case', 'missing_fields', 'supporting_evidence', 'authorization_type'
            ]

            # Write CSV file
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
                writer.writeheader()

                for case in cases:
                    # Prepare row for writing (convert lists to semicolon-separated strings)
                    row = case.copy()
                    if isinstance(row.get('missing_fields'), list):
                        row['missing_fields'] = ';'.join(row['missing_fields']) if row['missing_fields'] else ''
                    writer.writerow(row)

            logger.info(f"Saved {len(cases)} cases to {file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save cases to {filename}: {e}")
            return False

    def get_available_datasets(self) -> List[Dict[str, Any]]:
        """
        Get list of available datasets in the data directory
        Returns: List of dataset information
        """
        datasets = []

        try:
            for file_path in self.data_dir.glob("*.csv"):
                try:
                    stat = file_path.stat()
                    datasets.append({
                        'filename': file_path.name,
                        'size_bytes': stat.st_size,
                        'modified_time': stat.st_mtime,
                        'display_name': file_path.name.replace('.csv', '').replace('_', ' ').title()
                    })
                except Exception as e:
                    logger.warning(f"Could not read stats for {file_path}: {e}")

        except Exception as e:
            logger.error(f"Error scanning data directory: {e}")

        return sorted(datasets, key=lambda x: x['filename'])