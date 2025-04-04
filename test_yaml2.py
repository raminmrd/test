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

def clean_yaml_string(input_string: str) -> str:
    """Clean and format a YAML-like string to ensure proper structure and escaping."""
    lines = input_string.split('\n')
    entries = []
    current_entry = None
    i = 0
    
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue
            
        # Start of a new entry
        if stripped.startswith('- ' + MESSAGEBODY_TYPE) or (not stripped.startswith('messageBodyContent') and stripped.startswith(MESSAGEBODY_TYPE)):
            if current_entry is not None:
                entries.append(current_entry)
            current_entry = OrderedDict()
            current_entry[MESSAGEBODY_TYPE] = None
            current_entry[MESSAGEBODY_CONTENT] = OrderedDict()
            
            # Extract messageBodyType value
            if stripped.startswith('- '):
                value = stripped[2:].split(':', 1)[1].strip()
            else:
                value = stripped.split(':', 1)[1].strip()
            current_entry[MESSAGEBODY_TYPE] = value.strip("'")
            i += 1
            continue
            
        # Process messageBodyContent section
        if stripped == 'messageBodyContent:':
            i += 1
            base_indent = None
            current_key = None
            multi_line_value = []
            is_quoted = False
            
            while i < len(lines):
                line = lines[i].rstrip()
                stripped = line.strip()
                
                if not stripped:
                    i += 1
                    continue
                    
                # Break if we hit a new entry
                if stripped.startswith('- ' + MESSAGEBODY_TYPE) or (not stripped.startswith('messageBodyContent') and stripped.startswith(MESSAGEBODY_TYPE)):
                    if current_key and multi_line_value:
                        value = '\n'.join(multi_line_value)
                        current_entry[MESSAGEBODY_CONTENT][current_key] = value
                    break
                    
                # Track base indentation level
                if base_indent is None:
                    base_indent = len(line) - len(line.lstrip())
                
                current_indent = len(line) - len(line.lstrip())
                
                # Process key-value pair
                if ':' in stripped and current_indent <= base_indent:
                    # Save previous multi-line value if exists
                    if current_key and multi_line_value:
                        value = '\n'.join(multi_line_value)
                        if not is_quoted:
                            value = value.replace("'", "''")
                        current_entry[MESSAGEBODY_CONTENT][current_key] = value
                        multi_line_value = []
                        is_quoted = False
                    
                    key, value = stripped.split(':', 1)
                    current_key = key.strip()
                    value = value.strip()
                    
                    if value:
                        if value.startswith("'"):
                            # Quoted value
                            value = value.strip("'")
                            multi_line_value = [value]
                            is_quoted = True
                        else:
                            # Unquoted value
                            multi_line_value = [value]
                            is_quoted = False
                    else:
                        multi_line_value = []
                else:
                    # Continuation of multi-line value
                    if current_key is not None:
                        # Check if this line starts a new entry or section
                        next_stripped = stripped.strip()
                        if (next_stripped.startswith('- ' + MESSAGEBODY_TYPE) or 
                            next_stripped.startswith(MESSAGEBODY_TYPE + ':') or
                            next_stripped == 'messageBodyContent:'):
                            # Save current value and break
                            if multi_line_value:
                                value = '\n'.join(multi_line_value)
                                if not is_quoted:
                                    value = value.replace("'", "''")
                                current_entry[MESSAGEBODY_CONTENT][current_key] = value
                            i -= 1
                            break
                        
                        # Skip lines that look like they're part of a new entry
                        if next_stripped.startswith('-') or ':' in next_stripped:
                            i += 1
                            continue
                        
                        # Preserve indentation for unquoted values
                        if current_indent > base_indent:
                            indent = ' ' * (current_indent - base_indent)
                            multi_line_value.append(indent + stripped)
                        else:
                            multi_line_value.append(stripped)
                
                i += 1
                
            # Save last multi-line value if exists
            if current_key and multi_line_value:
                value = '\n'.join(multi_line_value)
                if not is_quoted:
                    value = value.replace("'", "''")
                current_entry[MESSAGEBODY_CONTENT][current_key] = value
            
            continue
                
        i += 1
        
    # Add the last entry if exists
    if current_entry is not None:
        entries.append(current_entry)
        
    # Convert entries to YAML with proper indentation
    def custom_str_presenter(dumper, data):
        if '\n' in data:
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
    
    yaml.add_representer(str, custom_str_presenter)
    yaml_output = yaml.dump(entries, default_flow_style=False, allow_unicode=True, sort_keys=False, indent=2)
    
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
    message: This is a multi-line
      message without quotes
- messageBodyType: 'Dataset_Message'
messageBodyContent:
    datasetName: test dataset
    reasoning: This is a multi-line
      reasoning without quotes""",
        
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
    reasoning: 'Quote ''test'' here'"""
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