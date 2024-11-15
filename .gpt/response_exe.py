#!/usr/bin/env python3
"""
Script to merge code blocks into a FastAPI template project.

Usage:
    python merge_code.py <path_to_code_block_file>

The code block file should follow the format:
$$$ FILE: <relative/path/to/file>
$$$ CONTENT:
<file content>
"""

import os
import sys

def merge_code_block(file_path):
    if not os.path.isfile(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        sys.exit(1)

    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    current_path = None
    current_content = []
    inside_content = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('&&& FILE:'):
            # Write the previous file if it exists
            if current_path and current_content:
                write_file(current_path, ''.join(current_content))
                current_content = []

            # Extract the file path
            current_path = stripped[len('&&& FILE:'):].strip()
            inside_content = False

        elif stripped.startswith('&&& CONTENT:'):
            inside_content = True
            current_content = []  # Reset content buffer

        elif inside_content:
            current_content.append(line)

    # Write the last file if it exists
    if current_path and current_content:
        write_file(current_path, ''.join(current_content))

def write_file(relative_path, content):
    # Define the base directory as the script's directory
    base_dir = os.getcwd()
    # Remove leading './' or '.\' if present
    if relative_path.startswith('./') or relative_path.startswith('.\\'):
        relative_path = relative_path[2:]
    full_path = os.path.join(base_dir, relative_path.replace('\\', os.sep).replace('/', os.sep))

    # Ensure the directory exists
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated: {relative_path}")

def main():
    merge_code_block(".gpt/response.txt")

if __name__ == "__main__":
    main()
