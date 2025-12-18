MODEL_NAME = "google/gemini-2.5-flash"
SOURCE_FOLDER = "Y://ldk backup//待整理"
AI_PROMPT = """
You are helping me organize a large legacy project folder of CAD drawings, photos and documents.

Goal:
- From a lightweight representation, surface canonical project labels and their noisy aliases.

Inputs:
1. Tag list JSON: {"tags": ["keyword1","keyword2",..."]}. Each keyword is a normalized folder name stripped of digits or filler text.
2. Folder overview JSON containing total file/folder counts plus a compact tree (ascii, each node annotated with its file count) so you can judge which branches are heavier.

What to do:
1. Map each tag to a canonical project name (merge similar keywords into a single label).
2. Place, People, and Object can also be considered as project name.
3. For each canonical project, return all alias tags that should be grouped under it.
4. Cover as many tags as possible—start with the obvious project names and then include the subtler keywords. If a tag is unclear, feel free to keep it standalone, but don't drop a reasonable tag just because it's not immediately recognizable.
5. After the high-priority steps above, if you still can't decide whether a tag represents a project, especially when it contains Chinese characters, treat it as a project rather than discarding it unless it truly looks like meaningless alphanumeric noise.

Output format:
Return STRICTLY a JSON object with:
{
  "projects": [
    {
      "canonical_name": "龙湖",
      "aliases": ["龙湖固定家具(定稿07-04-25)", "龙湖图片", ...]
    },
    ...
  ]
}

Only output valid JSON without comments.

"""
