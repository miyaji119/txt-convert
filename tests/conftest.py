import sys
import os
import pytest

# Ensure the txt-convert directory is on sys.path so web_server can import its siblings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
