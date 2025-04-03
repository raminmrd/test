import yaml
import re

def clean_yaml_string(input_string):
    """
    Clean and format a YAML-like string to make it compatible with yaml.safe_load().
    Handles:
    1. Escaped apostrophes in values
    2. Incorrect indentation
    3. Missing initial "-" for messageBodyType
    4. Extra characters before and after the YAML content
    5. Preserves newlines within quoted values
    """
    # Extract message entries
    entries = []
    current_entry = []
    lines = input_string.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()
        
        if not stripped:
            i += 1
            continue
            
        # Start of a new entry
        if stripped.startswith(('- messageBodyType:', 'messageBodyType:')):
            if current_entry:
                entries.append(current_entry)
            current_entry = []
            
            # Add the messageBodyType line with proper format
            if not stripped.startswith('- '):
                line = '- ' + stripped
            current_entry.append(line)
            i += 1
            continue
            
        # Part of current entry
        if current_entry and (
            stripped.startswith(('messageBodyContent:', 'message:', 'datasetName:', 'reasoning:'))
            or stripped.startswith((' ', '\t'))
        ):
            # Handle multi-line values (both quoted and unquoted)
            is_quoted = stripped.count("'") % 2 == 1
            is_continuation = (stripped.startswith(' ') or stripped.startswith('\t')) and not stripped.lstrip().startswith(('- messageBodyType:', 'messageBodyType:'))
            
            if is_quoted or is_continuation:
                full_value = [line]
                i += 1
                while i < len(lines):
                    next_line = lines[i].rstrip()
                    next_stripped = next_line.strip()
                    
                    # Break if we hit a new entry
                    if next_stripped.startswith(('- messageBodyType:', 'messageBodyType:')):
                        break
                        
                    # For quoted values, break if we find the closing quote
                    if is_quoted and "'" in next_line and not next_line.strip().startswith("'"):
                        full_value.append(next_line)
                        break
                        
                    # For unquoted values, break if we hit a new key
                    if not is_quoted and next_stripped and not next_stripped.startswith((' ', '\t')):
                        break
                        
                    full_value.append(next_line)
                    i += 1
                current_entry.extend(full_value)
                continue
                
            current_entry.append(line)
        i += 1
    
    if current_entry:
        entries.append(current_entry)
    
    # Process entries into Python objects
    yaml_objects = []
    for entry_lines in entries:
        entry_dict = {'messageBodyType': None, 'messageBodyContent': {}}
        current_key = None
        multi_line_value = []
        
        for line in entry_lines:
            stripped = line.strip()
            
            if stripped.startswith(('- messageBodyType:', 'messageBodyType:')):
                # Extract messageBodyType value
                value = stripped.split(':', 1)[1].strip()
                if value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                entry_dict['messageBodyType'] = value
            elif stripped.startswith(('message:', 'datasetName:', 'reasoning:')):
                # If we were collecting a multi-line value, save it
                if current_key and multi_line_value:
                    entry_dict['messageBodyContent'][current_key] = '\n'.join(multi_line_value)
                    multi_line_value = []
                
                # Extract key and value
                key, value = stripped.split(':', 1)
                current_key = key.strip()
                value = value.strip()
                
                # Handle start of a multi-line value
                if value.startswith("'") and not value.endswith("'"):
                    multi_line_value = [value.lstrip("'")]
                else:
                    if value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    value = value.replace("'", "\\'")
                    entry_dict['messageBodyContent'][current_key] = value
                    current_key = None
            elif current_key and multi_line_value:
                # Continue collecting multi-line value
                if stripped.endswith("'"):
                    multi_line_value.append(stripped.rstrip("'"))
                    entry_dict['messageBodyContent'][current_key] = '\n'.join(multi_line_value)
                    current_key = None
                    multi_line_value = []
                else:
                    multi_line_value.append(stripped)
        
        # Handle any remaining multi-line value
        if current_key and multi_line_value:
            entry_dict['messageBodyContent'][current_key] = '\n'.join(multi_line_value)
        
        yaml_objects.append(entry_dict)
    
    # Use PyYAML to dump the objects with proper formatting
    return yaml.dump(yaml_objects, default_flow_style=False, allow_unicode=True)

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
      reasoning without quotes"""
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