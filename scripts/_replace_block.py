"""Replace the <!-- BEGIN jev-first … --> … <!-- END jev-first --> block in a file with a new block file.

usage: _replace_block.py <file> <block-file>
"""
import re
import sys

path, block_path = sys.argv[1:3]
text = open(path).read()
block = open(block_path).read().rstrip("\n")
new, n = re.subn(r"<!-- BEGIN jev-first.*?<!-- END jev-first -->", lambda _: block, text, count=1, flags=re.S)
if n != 1:
    sys.exit(f"no jev-first block in {path}")
if new != text:
    open(path, "w").write(new)
