MODEL_NAME = "openai/gpt-4o-mini"
SOURCE_FOLDER = "F://老爸文件整理"
AI_PROMPT = """
You are helping me organize a large legacy project folder of CAD drawings, photos and documents.

Goal:
- Infer meaningful project names from noisy folder paths.
- Merge similar project names into a single canonical project label.
- Group files into coarse time ranges based on last modified time.
- Propose a clean target folder structure like:
  "<time-range>-<project-name>/<category>"
  where category is one of: "cad", "photos", "docs", "other".

Input data description:
- Each row is one file sample from my disk.
- Fields:
  - full_path: absolute Windows path to the file
  - folder_chain: only the folder names in order, separated by " / "
  - file_ext: file extension (e.g. .dwg, .jpg, .doc)
  - modified_time: last modified time in "YYYY-MM-DD" format

Here are some examples (JSON array):
[ 
  { "full_path": "...", "folder_chain": "...", "file_ext": "...", "modified_time": "2007-04-15" },
  { "full_path": "...", "folder_chain": "...", "file_ext": "...", "modified_time": "2010-11-03" },
  ...
]

What you should do:
1. From the folder_chain values, identify candidate project labels.
   - Normalize similar names into one canonical label
     (e.g. "龙湖固定家具", "龙湖图片", "龙湖会所变更图纸" -> "龙湖").
   - Do the same for other projects like 香山, 美泉宫, 昆泰, 保利, etc
     even if the exact folder names differ slightly.

2. For each canonical project label:
   - Based on modified_time distribution, propose 1–3 time ranges,
     for example "2006-2007", "2008-2010", "2010-2012".
   - Choose ranges that reflect obvious clusters, not overly fine-grained.

3. Define file categories by extension:
   - cad: .dwg, .dxf, .cad, etc.
   - photos: .jpg, .jpeg, .png, .tif, .bmp, camera folders like "100_FUJI".
   - docs: .doc, .docx, .xls, .xlsx, .ppt, .pptx, .pdf, etc.
   - other: everything else.

4. Design the target folder naming convention:
   For each (time-range, project) combination, I want a base folder:
     "<time-range>-<project-name>/"
   and inside it subfolders:
     "cad", "photos", "docs", "other".

Output format (very important):
Return STRICTLY a JSON object with:
{
  "projects": [
    {
      "canonical_name": "龙湖",
      "aliases": ["龙湖固定家具(定稿07-04-25)", "龙湖会所变更图纸", "龙湖图片", "..."],
      "time_ranges": [
        { "label": "2006-2007", "from": "2006-01-01", "to": "2007-12-31" },
        { "label": "2010-2012", "from": "2010-01-01", "to": "2012-12-31" }
      ]
    },
    {
      "canonical_name": "香山",
      "aliases": [...],
      "time_ranges": [...]
    }
  ],
  "categories": {
    "cad": [".dwg", ".dxf", "..."],
    "photos": [".jpg", ".jpeg", ".png", "..."],
    "docs": [".doc", ".docx", ".xls", ".xlsx", ".pdf", "..."],
    "other": []
  },
  "target_pattern": "<time-range>-<project-name>/<category>"
}

Only output valid JSON, with no comments and no extra explanations.

"""
