import yaml
import re
from collections import OrderedDict
from typing import List, Tuple, Optional
from enum import Enum, auto

# Constants for commonly used strings
MESSAGEBODY_TYPE = 'messageBodyType'
MESSAGEBODY_CONTENT = 'messageBodyContent'
MESSAGE = 'message'
DATASET_NAME = 'datasetName'
REASONING = 'reasoning'

# Add custom representer for OrderedDict
def ordered_dict_representer(dumper, data):
    return dumper.represent_mapping('tag:yaml.org,2002:map', data.items())

yaml.add_representer(OrderedDict, ordered_dict_representer)

def is_message_type_line(line: str) -> Tuple[bool, bool]:
    """Check if line is a message type line and if it needs a dash prefix."""
    stripped = line.strip()
    is_message_type = stripped.startswith((f'- {MESSAGEBODY_TYPE}:', f'{MESSAGEBODY_TYPE}:'))
    needs_dash = is_message_type and not stripped.startswith('-')
    return is_message_type, needs_dash

def is_content_line(line: str) -> bool:
    """Check if line is a content line."""
    stripped = line.strip()
    return stripped.startswith((f'{MESSAGEBODY_CONTENT}:', f'{MESSAGE}:', f'{DATASET_NAME}:', f'{REASONING}:'))

def extract_key_value(line: str) -> Tuple[str, str]:
    """Extract key and value from a line."""
    key, value = line.strip().split(':', 1)
    return key.strip().strip('- '), value.strip()

def process_multi_line_value(lines: List[str], start_idx: int, is_quoted: bool) -> Tuple[List[str], int]:
    """Process a multi-line value and return the value lines and the new index."""
    value_lines = []
    i = start_idx
    indent_level = None
    in_value = False
    collecting_quoted = False
    
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() and not in_value:
            i += 1
            continue
            
        # Determine indentation level on first non-empty line
        if indent_level is None:
            indent_level = len(line) - len(line.lstrip())
            # For first line, split key and value
            if ':' in line:
                key, value = line.split(':', 1)
                value = value.strip()
                if value:
                    if value.startswith("'"):
                        collecting_quoted = True
                        value = value.strip("'")
                    value_lines.append(value)
                    in_value = True
            else:
                value_lines.append(line.strip())
                in_value = True
            i += 1
            continue
            
        # Check if line maintains the indentation level
        current_indent = len(line) - len(line.lstrip())
        if current_indent < indent_level and in_value and not collecting_quoted:
            break
            
        # Check for new entry or new key
        stripped = line.strip()
        if stripped.startswith((f'- {MESSAGEBODY_TYPE}:', f'{MESSAGEBODY_TYPE}:')) and not collecting_quoted:
            break
            
        # For quoted values, check for closing quote
        if collecting_quoted and stripped.endswith("'") and not stripped.endswith("''"):
            if stripped.startswith("'"):
                value_lines.append(stripped.strip("'"))
            else:
                value_lines.append(stripped.rstrip("'"))
            collecting_quoted = False
            i += 1
            break
                
        # Add the line to value_lines, maintaining relative indentation
        if current_indent > indent_level:
            # Preserve relative indentation
            relative_indent = ' ' * (current_indent - indent_level)
            value_lines.append(relative_indent + stripped)
        else:
            value_lines.append(stripped)
        in_value = True
        i += 1
        
    # Join multi-line values with newlines
    if len(value_lines) > 0:
        # Extract the key from the first line if it exists
        first_line = lines[start_idx]
        if ':' in first_line:
            key = first_line.split(':', 1)[0]
            joined_value = '\n'.join(value_lines)
            # Escape any single quotes in the value
            joined_value = joined_value.replace("'", "''")
            return [f"{key}: '{joined_value}'"], i
    
    return value_lines, i

class ParserState(Enum):
    BETWEEN_ENTRIES = auto()
    IN_ENTRY = auto()
    IN_CONTENT = auto()

def clean_yaml_string(input_string: str) -> str:
    """Clean and format a YAML-like string to ensure proper structure and escaping."""
    lines = input_string.split('\n')
    output_entries = []
    
    # Step 1: Find all entry start points
    entry_start_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('- ' + MESSAGEBODY_TYPE) or (stripped.startswith(MESSAGEBODY_TYPE) and not stripped.startswith('messageBodyContent:')):
            entry_start_indices.append(i)
    
    # Step 2: Process each entry
    for idx, start_idx in enumerate(entry_start_indices):
        # Determine where this entry ends (either at the next entry or end of input)
        end_idx = len(lines)
        if idx < len(entry_start_indices) - 1:
            end_idx = entry_start_indices[idx + 1]
        
        entry_lines = lines[start_idx:end_idx]
        
        # Create a new entry
        entry = OrderedDict()
        entry[MESSAGEBODY_TYPE] = None
        entry[MESSAGEBODY_CONTENT] = OrderedDict()
        
        # Get the messageBodyType value
        first_line = entry_lines[0].strip()
        if first_line.startswith('- '):
            type_value = first_line[2:].split(':', 1)[1].strip()
        else:
            type_value = first_line.split(':', 1)[1].strip()
        entry[MESSAGEBODY_TYPE] = type_value.strip("'")
        
        # Separate processing for entries with direct fields and messageBodyContent
        has_content_section = False
        content_start_idx = -1
        
        # Find messageBodyContent position
        for j, line in enumerate(entry_lines):
            if line.strip() == 'messageBodyContent:':
                has_content_section = True
                content_start_idx = j
                break
        
        # Process direct fields (for entries like test case 8)
        if not has_content_section:
            for j in range(1, len(entry_lines)):
                line = entry_lines[j].strip()
                if not line or line.startswith('- ' + MESSAGEBODY_TYPE):
                    continue
                    
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip("'")
                    entry[MESSAGEBODY_CONTENT][key] = value
        else:
            # Process messageBodyContent section
            content_lines = []
            for j in range(content_start_idx + 1, len(entry_lines)):
                line = entry_lines[j]
                if not line.strip() or line.strip().startswith(('- ' + MESSAGEBODY_TYPE, 'Extra')):
                    continue
                content_lines.append(line)
            
            # Process all fields at the same indentation level
            i = 0
            base_indent = None
            
            # Find base indentation level
            for line in content_lines:
                if line.strip() and ':' in line:
                    base_indent = len(line) - len(line.lstrip())
                    break
            
            if base_indent is not None:
                # Group lines by field (each field starts at base_indent)
                fields = []
                current_field = []
                
                for line in content_lines:
                    if not line.strip():
                        continue
                        
                    current_indent = len(line) - len(line.lstrip())
                    if current_indent == base_indent and ':' in line:
                        # This is a new field
                        if current_field:
                            fields.append(current_field)
                        current_field = [line]
                    else:
                        # This is part of the current field
                        current_field.append(line)
                
                # Add the last field
                if current_field:
                    fields.append(current_field)
                
                # Process each field
                for field_lines in fields:
                    if not field_lines:
                        continue
                        
                    # Get the key and initial value
                    first_line = field_lines[0]
                    key, value = first_line.strip().split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if len(field_lines) > 1:
                        # This is a multi-line value
                        if value.startswith("'"):
                            value = value.strip("'")
                        
                        value_lines = [value] if value else []
                        
                        for i in range(1, len(field_lines)):
                            line = field_lines[i].strip()
                            if line.endswith("'") and not line.endswith("''"):
                                value_lines.append(line.rstrip("'"))
                            else:
                                value_lines.append(line)
                        
                        value = '\n'.join(value_lines)
                    else:
                        # Single-line value
                        value = value.strip("'")
                    
                    entry[MESSAGEBODY_CONTENT][key] = value
        
        output_entries.append(entry)
    
    # Convert entries to YAML with proper indentation
    def custom_str_presenter(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
    
    yaml.add_representer(str, custom_str_presenter)
    yaml_output = yaml.dump(output_entries, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
    
    # Clean up the output
    cleaned_lines = []
    for line in yaml_output.split('\n'):
        if line.strip():
            cleaned_lines.append(line.rstrip())
    
    return '\n'.join(cleaned_lines)

def test_yaml_loading():
    try:
        with open('messages.yaml', 'r') as file:
            data = yaml.safe_load(file)
            print("YAML file loaded successfully!")
            print("\nLoaded data:")
            print(data)
            return True
    except yaml.YAMLError as e:
        print(f"Error loading YAML file: {e}")
        return False
    except FileNotFoundError:
        print("Error: messages.yaml file not found")
        return False

def test_clean_yaml():
    # Test cases
    test_cases = [
        # Test case 1: Escaped apostrophes
        """Some extra text
- messageBodyType: 'Basic_Message'
messageBodyContent:
    message: 'Katy's message'
- messageBodyType: 'Dataset_Message'
messageBodyContent:
    datasetName: 'test's dataset'
    reasoning: 'test's reasoning'
Extra text at the end""",
        
        # Test case 2: Wrong indentation
        """- messageBodyType: 'Basic_Message'
messageBodyContent:
message: 'test message'
- messageBodyType: 'Dataset_Message'
messageBodyContent:
datasetName: 'test dataset'
reasoning: 'test reasoning'""",
        
        # Test case 3: Missing initial "-"
        """messageBodyType: 'Basic_Message'
messageBodyContent:
    message: 'test message'
messageBodyType: 'Dataset_Message'
messageBodyContent:
    datasetName: 'test dataset'
    reasoning: 'test reasoning'""",
        
        # Test case 4: Newlines in values
        """- messageBodyType: 'Basic_Message'
messageBodyContent:
    message: 'This is a multi-line
message with newlines'
- messageBodyType: 'Dataset_Message'
messageBodyContent:
    datasetName: 'test dataset'
    reasoning: 'This is a multi-line
reasoning with newlines'""",
        
        # Test case 5: Unquoted multi-line values
        """- messageBodyType: 'Basic_Message'
messageBodyContent:
    message: 'This is a multi-line
      message without quotes'
- messageBodyType: 'Dataset_Message'
messageBodyContent:
    datasetName: 'test dataset'
    reasoning: 'This is a multi-line
      reasoning without quotes'""",
        
        # Test case 6: Apostrophe handling
        """- messageBodyType: 'Basic_Message'
messageBodyContent:
    message: 'cashier's check'
- messageBodyType: 'Dataset_Message'
messageBodyContent:
    datasetName: 'test dataset'
    reasoning: 'test's reasoning'""",
        
        # Test case 7: Nested quotes
        """- messageBodyType: 'Basic_Message'
messageBodyContent:
    message: 'He said ''Hello'' and left'
- messageBodyType: 'Dataset_Message'
messageBodyContent:
    reasoning: 'Quote ''test'' here'""",
        
        # Test case 8: Direct fields without messageBodyContent
        """- messageBodyType: 'Basic_Message'
   message: 'this is a message'
- messageBodyType: 'DATASET_MESSAGE'
   datasetName: 'name of some dataset'
   reasoning: 'this dataset could answer the questions because ...'"""
    ]
    
    # Save all cleaned outputs to a single string
    all_cleaned_output = ""
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest Case {i}:")
        print("Input:")
        print(test_case)
        print("\nCleaned Output:")
        cleaned = clean_yaml_string(test_case)
        print(cleaned)
        all_cleaned_output += cleaned + "\n\n"
        print("\nVerifying with yaml.safe_load:")
        try:
            data = yaml.safe_load(cleaned)
            print("Successfully loaded!")
            print(data)
        except yaml.YAMLError as e:
            print(f"Error: {e}")
    
    # Save the combined cleaned output to a file
    with open('cleaned_messages.yaml', 'w') as f:
        f.write(all_cleaned_output)
    
    print("\nAll cleaned outputs have been saved to 'cleaned_messages.yaml'")
    
    # Verify the combined file can be loaded
    print("\nVerifying combined file:")
    try:
        with open('cleaned_messages.yaml', 'r') as f:
            data = yaml.safe_load(f)
            print("Successfully loaded combined file!")
            print(data)
    except yaml.YAMLError as e:
        print(f"Error loading combined file: {e}")

if __name__ == "__main__":
    print("Testing original YAML file:")
    test_yaml_loading()
    print("\nTesting YAML string cleaning:")
    test_clean_yaml() 