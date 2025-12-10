MODEL_NAME = "openai/gpt-4o-mini"
SOURCE_FOLDER = "F://老爸文件整理//新建文件夹"
AI_PROMPT = """
You are helping me organize a large legacy project folder of CAD drawings, photos and documents.

Goal:
- Infer meaningful project names from noisy folder paths.
- Merge similar project names into a single canonical project label.
- Propose a clean target folder structure like:
  "<time-range>-<project-name>/<category>"
  where category is one of: "cad", "photos", "docs", "other".

Input data description:
- I will provide a folder summary JSON that includes the directory tree and counts. Its shape is:
  {
    "root": "<root-folder-name>",
    "node_count": <number of nodes collected>,
    "folders": [
      {
        "folder_chain": "<path components separated by ' / '>",
        "folder_name": "<current folder name>",
        "depth": <depth relative to root>,
        "file_count": <number of files directly under this folder>,
        "extensions": {".jpg": 12, ".dwg": 3, ...},
        "children": ["<child-folder-chain>", ...],
        "min_date": "YYYY-MM-DD" or null,
        "max_date": "YYYY-MM-DD" or null
      },
      ...
    ]
  }
- You should only rely on these folder-level summaries; the script will handle actual file timestamps separately and does not need raw file entries.

What you should do:
1. From the folder_chain values, identify candidate project labels.
   - Normalize similar names into a single canonical label
     (e.g. "龙湖固定家具", "龙湖图片", "龙湖会所变更图纸" -> "龙湖").
   - Apply the same strategy to other projects like 香山, 美泉宫, 昆泰, 保利, etc,
     even when the folder names vary slightly.

2. Define file categories by extension:
   - cad: .dwg, .dxf, .cad, etc.
   - photos: .jpg, .jpeg, .png, .tif, .bmp, camera folders like "100_FUJI".
   - docs: .doc, .docx, .xls, .xlsx, .ppt, .pptx, .pdf, etc.
   - other: everything else.

3. Design the target folder naming convention:
   For each canonical project, return the folder name pattern:
     "<time-range>-<project-name>/"
   with the standard categories underneath.

4. Do not define time ranges; they will be computed locally from the file timestamps. You may omit the "time_ranges" field or leave it empty.

Output format (very important):
Return STRICTLY a JSON object with:
{
  "projects": [
    {
      "canonical_name": "龙湖",
      "aliases": ["龙湖固定家具(定稿07-04-25)", "龙湖会所变更图纸", "龙湖图片", "..."]
    },
    {
      "canonical_name": "香山",
      "aliases": ["香山CAD-0", "香山"]
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
