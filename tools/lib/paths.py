"""仓库内的文件路径，一处定义处处用。"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DIR = os.path.join(ROOT, 'source')
DATA_DIR = os.path.join(ROOT, 'data')
ORIGINAL_DIR = os.path.join(SOURCE_DIR, 'original')

CARDS_MD_PATH = os.path.join(SOURCE_DIR, 'cards.md')
PROPS_PATH = os.path.join(SOURCE_DIR, 'props.md')
MAP_DATA_PATH = os.path.join(SOURCE_DIR, 'map-print-data.json')

CARDS_JSON_PATH = os.path.join(DATA_DIR, 'cards.json')
PROPS_JSON_PATH = os.path.join(DATA_DIR, 'props.json')

INDEX_PATH = os.path.join(ROOT, 'index.html')
PRINT_PATH = os.path.join(ROOT, 'print.html')
ORIGINAL_PATH = os.path.join(ROOT, 'original.html')
MAP_PATH = os.path.join(ROOT, 'map.html')
README_PATH = os.path.join(ROOT, 'README.md')
