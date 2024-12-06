import os

def write_directory_structure_to_file(base_path=".", output_file="directory_structure.txt"):
    with open(output_file, "w") as file:
        for root, dirs, files in os.walk(base_path):
            level = root.replace(base_path, "").count(os.sep)
            indent = " " * 4 * level
            file.write(f"{indent}{os.path.basename(root)}/\n")
            sub_indent = " " * 4 * (level + 1)
            for f in files:
                file.write(f"{sub_indent}{f}\n")

write_directory_structure_to_file()