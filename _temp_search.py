import sys
sys.path.insert(0, r'D:\AiAlign\generate-lyrics')
from lrclib import search
lyrics = search('Village Green Preservation Society', 'The Kinks')
print(lyrics)
