import sys
sys.path.insert(0, r"D:\AiAlign\generate-lyrics")
from lrclib import search
lyrics = search("Oh Oh I Love Her So", "Ramones")
print(lyrics)
